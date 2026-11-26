"""Middlewares: tamanho do corpo, limite por IP, Host, Origin e cabeçalhos de segurança (ADRs 0006, 0008, 0011 e
0015).

As respostas de recusa (400, 403, 411, 413, 429) saem no formato da RFC 9457, como as das rotas (ADR 0009).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import Request, Response

from app.api.problemas import simples
from app.config import Configuracao, configuracao
from app.seguranca import LimitadorPorIp

Proximo = Callable[[Request], Awaitable[Response]]

# Folga para o envelope multipart (boundary e cabeçalhos da parte) acima do tamanho do XML.
FOLGA_MULTIPART = 16 * 1024
ROTA_NFE = "/nfe/importar"

# Cadastro, entrada e código (C1, ADR 0015): limite por IP próprio, além do contador de falhas de cada conta.
ROTAS_ENTRADA = ("/contas", "/sessoes", "/conta/excluir")
# Rotas que chamam os motores (ou o provedor de IA) ou mudam o estado, e por isso têm limite por IP.
ROTAS_LIMITADAS = (
    "/carrinho/calcular",
    "/item/preco-alvo",
    "/regime/comparar",
    "/busca/ncm",
    "/explicar",
    "/erros/",
    "/chat",
    "/nfe/importar",
    "/alertas/",
    "/demo/restaurar",
    "/espacos",
    "/catalogo/",  # POST /catalogo/{id}/preco e /classificacao (o GET /catalogo não chama os motores)
    *ROTAS_ENTRADA,
)
# Métodos que mudam o estado: passam pela defesa contra CSRF.
METODOS_INSEGUROS = ("POST", "PUT", "PATCH", "DELETE")
# Cookie da sessão (app.api.dependencias.COOKIE_SESSAO; repetido aqui para o middleware não importar as rotas).
COOKIE_SESSAO = "__Host-contaai_sessao"
# Um limitador por processo. Os testes trocam estes objetos (monkeypatch neste módulo).
LIMITE_CHAT = LimitadorPorIp(configuracao().limite_chat_por_minuto)
LIMITE_GERAL = LimitadorPorIp(configuracao().limite_geral_por_minuto)
LIMITE_BUSCA = LimitadorPorIp(configuracao().limite_busca_por_minuto)
# Criar um espaço grava um arquivo no disco: limite próprio, além do teto de espaços (ADR 0010).
LIMITE_ESPACOS = LimitadorPorIp(configuracao().limite_espacos_por_minuto)
LIMITE_ENTRADA = LimitadorPorIp(configuracao().limite_entrada_por_minuto)

ROTAS_DOCUMENTACAO = ("/docs", "/redoc", "/openapi.json")


def _cfg_atual(request: Request) -> Configuracao:
    """A configuração em vigor, respeitando a troca feita pelos testes (dependency_overrides)."""
    return request.app.dependency_overrides.get(configuracao, configuracao)()


async def limitar_corpo(request: Request, call_next: Proximo) -> Response:
    """Recusa corpo grande antes de ele ser lido (ADR 0008 para a NF-e; ADR 0011 para as rotas JSON).

    O Starlette não limita o corpo: sem esta checagem, um JSON de 1 GB seria lido inteiro na memória antes
    da validação do contrato, e o arquivo da NF-e seria gravado em disco pelo parser multipart. O uvicorn
    recusa corpo maior que o Content-Length declarado. Sem Content-Length e sem Transfer-Encoding, a
    requisição não tem corpo (RFC 9112, 6.3); corpo em pedaços (chunked) é recusado, porque não diz o tamanho.
    """
    if request.method != "POST":
        return await call_next(request)
    cfg = _cfg_atual(request)
    declarado = request.headers.get("content-length")
    if request.url.path == ROTA_NFE:
        if declarado is None or not declarado.isdigit():
            return simples(411, "Envie o tamanho do arquivo (Content-Length).")
        if int(declarado) > cfg.tamanho_max_nfe_bytes + FOLGA_MULTIPART:
            return simples(413, "Arquivo maior que o limite para uma NF-e.")
        return await call_next(request)
    if "transfer-encoding" in request.headers:
        return simples(411, "Envie o tamanho do corpo (Content-Length).")
    if declarado is not None and (not declarado.isdigit() or int(declarado) > cfg.tamanho_max_json_bytes):
        return simples(413, "Corpo da requisição maior que o limite.")
    return await call_next(request)


def _host(valor: str) -> str:
    """O nome do host sem a porta ("127.0.0.1:8000" → "127.0.0.1"; "[::1]:8000" → "[::1]")."""
    if valor.startswith("["):
        return valor.split("]", 1)[0] + "]"
    return valor.rsplit(":", 1)[0] if valor.count(":") == 1 else valor


async def verificar_host(request: Request, call_next: Proximo) -> Response:
    """Só responde aos hosts configurados (ADR 0011). Contra DNS rebinding: uma página de outro domínio que
    passe a resolver para 127.0.0.1 chega aqui com o Host dela, e é recusada. "*" na lista desliga a checagem."""
    permitidos = _cfg_atual(request).hosts_permitidos
    if "*" not in permitidos and _host(request.headers.get("host", "").lower()) not in permitidos:
        return simples(400, "Host não autorizado.")
    return await call_next(request)


async def verificar_origem(request: Request, call_next: Proximo) -> Response:
    """Defesa contra CSRF nos métodos que mudam o estado (ADR 0011, reforçada no ADR 0015).

    1. Sec-Fetch-Site: cross-site (o navegador diz que a requisição saiu de outro site): recusada. O OWASP
       (Cross-Site Request Forgery Prevention) recomenda os cabeçalhos Fetch Metadata além do SameSite.
    2. Origin fora da lista: recusada. O navegador sempre manda Origin num POST de outra origem, até num
       formulário simples (que não passa pelo preflight do CORS).
    3. Com o cookie da sessão e sem Origin: recusada. Um navegador manda Origin nesses métodos; sem ele, a
       requisição não veio da tela. Sem cookie e sem Origin (curl, scripts, testes), segue: o estado da demo já
       exige um header próprio (token ou espaço).
    """
    if request.method in METODOS_INSEGUROS:
        origem = request.headers.get("origin")
        if request.headers.get("sec-fetch-site") == "cross-site":
            return simples(403, "Requisição de outro site recusada.")
        if origem is not None and origem not in _cfg_atual(request).cors_origens:
            return simples(403, "Origem não autorizada.")
        if origem is None and COOKIE_SESSAO in request.cookies:
            return simples(403, "Requisição sem Origin com o cookie da sessão recusada.")
    return await call_next(request)


async def limitar_requisicoes(request: Request, call_next: Proximo) -> Response:
    caminho = request.url.path
    if request.method in ("GET", "POST") and caminho.startswith(ROTAS_LIMITADAS):
        ip = request.client.host if request.client else "desconhecido"
        limitadores = [LIMITE_CHAT if caminho == "/chat" else LIMITE_GERAL]
        if caminho == "/busca/ncm":
            limitadores.append(LIMITE_BUSCA)
        if caminho == "/espacos" and request.method == "POST":
            limitadores.append(LIMITE_ESPACOS)
        if caminho.startswith(ROTAS_ENTRADA) and request.method == "POST":
            limitadores = [LIMITE_ENTRADA]
        for limitador in limitadores:
            permitido, espera = limitador.permitir(ip)
            if not permitido:
                return simples(
                    429, "Muitas requisições. Espere um pouco e tente de novo.", {"Retry-After": str(espera)}
                )
    return await call_next(request)


async def cabecalhos_de_seguranca(request: Request, call_next: Proximo) -> Response:
    """Cabeçalhos em toda resposta (ADR 0008). A API só devolve JSON: nada dela deve ser executado,
    emoldurado ou guardado em cache compartilhado. A documentação (/docs) carrega o Swagger da CDN do
    FastAPI e fica sem a CSP restritiva."""
    resposta = await call_next(request)
    resposta.headers["X-Content-Type-Options"] = "nosniff"
    resposta.headers["Referrer-Policy"] = "no-referrer"
    resposta.headers["X-Frame-Options"] = "DENY"
    # same-origin (ADR 0011, aviso do OWASP ZAP): o CORP só vale para requisições no-cors (padrão Fetch). A tela
    # chama a API com fetch em modo CORS, que o CORP não bloqueia; uma <img>/<script> de outro site, sim.
    resposta.headers["Cross-Origin-Resource-Policy"] = "same-origin"
    if not request.url.path.startswith(ROTAS_DOCUMENTACAO):
        resposta.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
        resposta.headers["Cache-Control"] = "no-store"
    return resposta
