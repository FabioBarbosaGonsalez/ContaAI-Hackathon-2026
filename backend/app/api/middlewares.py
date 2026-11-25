"""Middlewares: tamanho do upload da NF-e, limite por IP e cabeçalhos de segurança (ADR 0006 e ADR 0008).

As respostas de recusa (411, 413, 429) saem no formato da RFC 9457, como as das rotas (ADR 0009).
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
)
# Um limitador por processo. Os testes trocam estes objetos (monkeypatch neste módulo).
LIMITE_CHAT = LimitadorPorIp(configuracao().limite_chat_por_minuto)
LIMITE_GERAL = LimitadorPorIp(configuracao().limite_geral_por_minuto)
LIMITE_BUSCA = LimitadorPorIp(configuracao().limite_busca_por_minuto)

ROTAS_DOCUMENTACAO = ("/docs", "/redoc", "/openapi.json")


def _cfg_atual(request: Request) -> Configuracao:
    """A configuração em vigor, respeitando a troca feita pelos testes (dependency_overrides)."""
    return request.app.dependency_overrides.get(configuracao, configuracao)()


async def limitar_upload_nfe(request: Request, call_next: Proximo) -> Response:
    """Recusa o upload grande antes de o corpo ser lido e gravado em disco pelo parser multipart.

    O Starlette não limita o tamanho de uma parte de arquivo: sem esta checagem, o arquivo inteiro
    seria recebido antes da validação na rota. O uvicorn recusa corpo maior que o Content-Length.
    """
    if request.method == "POST" and request.url.path == ROTA_NFE:
        declarado = request.headers.get("content-length")
        if declarado is None or not declarado.isdigit():
            return simples(411, "Envie o tamanho do arquivo (Content-Length).")
        if int(declarado) > _cfg_atual(request).tamanho_max_nfe_bytes + FOLGA_MULTIPART:
            return simples(413, "Arquivo maior que o limite para uma NF-e.")
    return await call_next(request)


async def limitar_requisicoes(request: Request, call_next: Proximo) -> Response:
    caminho = request.url.path
    if request.method in ("GET", "POST") and caminho.startswith(ROTAS_LIMITADAS):
        ip = request.client.host if request.client else "desconhecido"
        limitadores = [LIMITE_CHAT if caminho == "/chat" else LIMITE_GERAL]
        if caminho == "/busca/ncm":
            limitadores.append(LIMITE_BUSCA)
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
    resposta.headers["Cross-Origin-Resource-Policy"] = "same-site"
    if not request.url.path.startswith(ROTAS_DOCUMENTACAO):
        resposta.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
        resposta.headers["Cache-Control"] = "no-store"
    return resposta
