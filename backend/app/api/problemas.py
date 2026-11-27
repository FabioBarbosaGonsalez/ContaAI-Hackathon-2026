"""Respostas de erro no formato Problem Details da RFC 9457 (application/problem+json), ADR 0009.

Regras seguidas (RFC 9457, seções 3, 4 e 5):
- `status` é sempre o mesmo código da resposta HTTP.
- Sem tipo próprio, `type` é "about:blank" e `title` é a frase do código HTTP (ex.: "Not Found").
- Tipos próprios usam caminho completo relativo à API (/problemas/<nome>) e `GET /problemas/<nome>`
  devolve a descrição do tipo (título, códigos e significado), como a RFC pede para tipos novos.
- `detail` ajuda a pessoa a corrigir o pedido; nunca traz pilha, URL, host, caminho do servidor ou
  corpo dos motores e do provedor de IA. Os membros de extensão (`motor`, `erros`, `campos`) têm nome
  com 3+ letras, e quem consome deve ignorar os que não conhece.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from http import HTTPStatus
from typing import Any, get_args

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.agente.provedor import ProvedorFalhou
from app.api.mensagens import traduzir
from app.api.registro import resumo_da_excecao
from app.cadastro import ItemEmUso, Recusado
from app.contas.servico import ContaBloqueada
from app.contrato import (
    CampoInvalido,
    OrigemCampo,
    Problema,
    ProblemaCalculo,
    ProblemaItemEmUso,
    ProblemaMotor,
    ProblemaValidacao,
    TipoProblema,
)
from app.motores.cliente import FalhaMotor, MotorIndisponivel, OperacaoRecusada
from app.nfe import consultas
from app.nfe.importacao import NotaRecusada
from app.nfe.leitor import NotaInvalida
from app.persistencia.espacos import EspacoInexistente, EspacosEsgotados
from app.persistencia.sementes import SementesInvalidas
from app.precificacao.preco_alvo import CalculoRecusado
from app.seguranca import METODOS_INSEGUROS

log = logging.getLogger("contaai")

TIPO_MIDIA = "application/problem+json"
PREFIXO = "/problemas/"

# Os tipos próprios do ContaAI. Mudar um título ou um código aqui é mudança de contrato.
TIPOS: dict[str, TipoProblema] = {
    t.type.removeprefix(PREFIXO): t
    for t in (
        TipoProblema(
            type=f"{PREFIXO}entrada-invalida",
            title="Requisição inválida",
            status=[422],
            descricao="A requisição não segue o contrato: campo ausente, formato errado ou regra do contrato (ex.: "
            "a partir de 2027 as alíquotas são premissas e precisam vir em aliquotasNominais). `campos` lista cada "
            "problema com a origem (body, query, path, header) e o JSON Pointer do campo.",
        ),
        TipoProblema(
            type=f"{PREFIXO}calculo-recusado",
            title="Cálculo sem resposta",
            status=[422],
            descricao="O cálculo pedido não tem resposta: margem impossível, item que o motor não calcula, base do "
            "híbrido que não fecha ou preço-alvo que não converge. `erros` traz os erros do motor quando eles "
            "explicam a recusa.",
        ),
        TipoProblema(
            type=f"{PREFIXO}motor-recusou",
            title="O motor oficial recusou a operação",
            status=[422],
            descricao="A calculadora oficial da Receita recusou a operação inteira (ex.: VSN-015). `motor` diz qual "
            "e `erros` traz os códigos dele, que GET /erros/{codigo} explica.",
        ),
        TipoProblema(
            type=f"{PREFIXO}motor-resposta-invalida",
            title="Resposta do motor não reconhecida",
            status=[502],
            descricao="A calculadora oficial respondeu num formato que o ContaAI não reconhece (versão diferente da "
            "fixada?). Nada foi calculado; GET /saude mostra as versões em execução.",
        ),
        TipoProblema(
            type=f"{PREFIXO}motor-indisponivel",
            title="Motor oficial indisponível",
            status=[503],
            descricao="A calculadora oficial não respondeu a tempo. Nada foi calculado; tente de novo.",
        ),
        TipoProblema(
            type=f"{PREFIXO}nota-invalida",
            title="Arquivo não é uma NF-e lida pelo ContaAI",
            status=[422],
            descricao="O XML não é uma NF-e modelo 55, leiaute 4.00, legível pelo ContaAI. `detail` diz qual campo "
            "falhou, sem repetir trecho do arquivo.",
        ),
        TipoProblema(
            type=f"{PREFIXO}nota-recusada",
            title="NF-e não pode ser importada",
            status=[409, 422],
            descricao="A NF-e é legível, mas não entra: 422 quando o destinatário não é uma empresa cadastrada, 409 "
            "quando a mesma nota (emitente, série e número) já entrou com outro conteúdo ou o estado mudou durante "
            "a importação. Nada foi gravado.",
        ),
        TipoProblema(
            type=f"{PREFIXO}espaco-inexistente",
            title="Espaço de avaliação inexistente ou expirado",
            status=[404],
            descricao="O id enviado em X-ContaAI-Espaco não corresponde a um espaço válido: nunca existiu ou já "
            "expirou (os espaços duram um tempo fixo desde a criação). Crie outro com POST /espacos.",
        ),
        TipoProblema(
            type=f"{PREFIXO}espacos-esgotados",
            title="Sem espaço de avaliação livre",
            status=[503],
            descricao="O teto de espaços ao mesmo tempo foi atingido. O header Retry-After diz em quantos segundos "
            "o mais antigo expira. Enquanto isso, a demonstração compartilhada segue disponível sem o header.",
        ),
        TipoProblema(
            type=f"{PREFIXO}ia-indisponivel",
            title="Provedor de IA indisponível",
            status=[503],
            descricao="O provedor de IA do chat não está configurado ou falhou. As rotas de cálculo seguem funcionando.",
        ),
        TipoProblema(
            type=f"{PREFIXO}conta-bloqueada",
            title="Conta bloqueada",
            status=[429],
            descricao="Depois de 100 tentativas erradas seguidas, a conta fica bloqueada até um administrador "
            "desbloquear. Esperar não adianta: o Retry-After (1 h) só pede a clientes automáticos que não insistam. "
            "As outras esperas do limite de tentativas saem como about:blank, com o Retry-After que vale.",
        ),
        TipoProblema(
            type=f"{PREFIXO}item-em-uso",
            title="Item na compra mensal de clientes",
            status=[409],
            descricao="O item está na compra mensal de clientes B2B da empresa e não pode sair do catálogo: a venda "
            "desses clientes ficaria sem ele. `clientes` lista o CNPJ e o nome de cada um. Tire o item da compra "
            "deles (PATCH /clientes/{cnpj_cliente}) e arquive de novo.",
        ),
        TipoProblema(
            type=f"{PREFIXO}sementes-indisponiveis",
            title="Sementes da demonstração indisponíveis",
            status=[503],
            descricao="A pasta de dados da demonstração não tem sementes legíveis (CONTAAI_PASTA_DEMO). O estado "
            "não foi alterado.",
        ),
    )
}


def frase(status: int) -> str:
    try:
        return HTTPStatus(status).phrase
    except ValueError:
        return "Error"


def resposta(corpo: Problema, headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=corpo.status,
        content=corpo.model_dump(mode="json", exclude_none=True),
        media_type=TIPO_MIDIA,
        headers=headers,
    )


def simples(status: int, detalhe: str | None, headers: dict[str, str] | None = None) -> JSONResponse:
    """Problema sem tipo próprio: about:blank, com a frase do código HTTP como título."""
    return resposta(Problema(title=frase(status), status=status, detail=detalhe), headers)


def tipado(nome: str, status: int, detalhe: str) -> Problema:
    tipo = TIPOS[nome]
    if status not in tipo.status:  # erro de programação, não de entrada
        raise ValueError(f"{nome} não é usado com {status}")
    return Problema(type=tipo.type, title=tipo.title, status=status, detail=detalhe)


# ---------------------------------------------------------------------------
# Erros de validação: o formato do FastAPI vira `campos`


def _ponteiro(partes: Sequence[Any]) -> str:
    """JSON Pointer (RFC 6901) dentro da origem; "#" quando o erro é do objeto inteiro."""
    escapadas = (str(p).replace("~", "~0").replace("/", "~1") for p in partes)
    return "#" + "".join(f"/{p}" for p in escapadas)


ORIGENS: dict[Any, OrigemCampo] = {o: o for o in get_args(OrigemCampo)}


def campos_invalidos(erros: Sequence[Any]) -> list[CampoInvalido]:
    """Só local e mensagem em português (app/api/mensagens.py): o valor enviado (`input`) não volta, e o
    `ctx` só entra como limite do contrato (tamanho, casas decimais, valores aceitos)."""
    campos = []
    for e in erros:
        loc = list(e.get("loc", ()))
        origem = ORIGENS.get(loc[0]) if loc else None
        resto = loc[1:] if origem else loc  # sem origem conhecida, o local inteiro fica no ponteiro
        if e.get("type") == "json_invalid":
            resto = []  # o FastAPI põe a posição do caractere no local; não é um campo
        campos.append(CampoInvalido(origem=origem or "body", campo=_ponteiro(resto), detalhe=traduzir(e)))
    return campos


# Nome da origem no texto do `detail` (em `campos`, a origem fica com o nome do contrato).
NOMES_ORIGEM: dict[OrigemCampo, str] = {
    "body": "corpo",
    "query": "parâmetro",
    "path": "caminho",
    "header": "cabeçalho",
    "cookie": "cookie",
}


def _resumo(campos: list[CampoInvalido]) -> str:
    primeiro = campos[0] if campos else None
    if primeiro is None:
        return "A requisição não segue o contrato."
    origem = NOMES_ORIGEM.get(primeiro.origem, primeiro.origem)
    onde = "" if primeiro.campo == "#" else f"{primeiro.campo[2:]} ({origem}): "  # "#": a frase já diz o quê
    extra = f" E mais {len(campos) - 1} problema(s)." if len(campos) > 1 else ""
    return f"{onde}{primeiro.detalhe}{extra}"


# ---------------------------------------------------------------------------
# Tratadores


async def _validacao(_: Request, exc: RequestValidationError) -> JSONResponse:
    campos = campos_invalidos(exc.errors())
    base = tipado("entrada-invalida", 422, _resumo(campos))
    return resposta(ProblemaValidacao(**base.model_dump(), campos=campos))


async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    detalhe = exc.detail if isinstance(exc.detail, str) and exc.detail != frase(exc.status_code) else None
    return simples(exc.status_code, detalhe, dict(exc.headers) if exc.headers else None)


async def _falha_motor(_: Request, exc: FalhaMotor) -> JSONResponse:
    """Sem URL, host ou corpo do motor (ver app/motores/cliente.py)."""
    if isinstance(exc, OperacaoRecusada):
        nome, status, erros = "motor-recusou", 422, exc.erros
    elif isinstance(exc, MotorIndisponivel):
        nome, status, erros = "motor-indisponivel", 503, []
    else:
        nome, status, erros = "motor-resposta-invalida", 502, []
    base = tipado(nome, status, exc.mensagem)
    return resposta(ProblemaMotor(**base.model_dump(), motor=exc.motor, erros=erros))


async def _calculo_recusado(_: Request, exc: CalculoRecusado) -> JSONResponse:
    base = tipado("calculo-recusado", 422, exc.detalhe)
    return resposta(ProblemaCalculo(**base.model_dump(), erros=exc.erros))


async def _nota_invalida(_: Request, exc: NotaInvalida) -> JSONResponse:
    """O texto diz qual campo falhou, sem repetir trecho do XML enviado."""
    return resposta(tipado("nota-invalida", 422, exc.mensagem))


async def _nota_recusada(_: Request, exc: NotaRecusada) -> JSONResponse:
    return resposta(tipado("nota-recusada", exc.status, exc.mensagem))


async def _sementes(_: Request, exc: SementesInvalidas) -> JSONResponse:
    """Sem o caminho da pasta (não expõe a estrutura do servidor)."""
    return resposta(tipado("sementes-indisponiveis", 503, exc.mensagem))


async def _provedor(_: Request, exc: ProvedorFalhou) -> JSONResponse:
    """Sem chave, URL nem corpo do provedor."""
    return resposta(tipado("ia-indisponivel", 503, exc.mensagem))


async def _recusado(_: Request, exc: Recusado) -> JSONResponse:
    """Regra que depende dos dados (CNPJ com dígito errado, município fora da UF, NCM fora dos dados abertos)."""
    return simples(422, exc.mensagem)


async def _nao_encontrado(_: Request, exc: consultas.NaoEncontrado) -> JSONResponse:
    return simples(404, exc.mensagem)


async def _conflito(_: Request, exc: consultas.Conflito) -> JSONResponse:
    return simples(409, exc.mensagem)


async def _item_em_uso(_: Request, exc: ItemEmUso) -> JSONResponse:
    base = tipado("item-em-uso", 409, exc.mensagem)
    return resposta(ProblemaItemEmUso(**base.model_dump(), clientes=exc.clientes))


async def _espaco_inexistente(_: Request, exc: EspacoInexistente) -> JSONResponse:
    return resposta(tipado("espaco-inexistente", 404, "Espaço de avaliação inexistente ou expirado. Crie outro."))


async def _espacos_esgotados(_: Request, exc: EspacosEsgotados) -> JSONResponse:
    detalhe = "Todos os espaços de avaliação estão em uso. Tente de novo depois do tempo indicado em Retry-After."
    return resposta(tipado("espacos-esgotados", 503, detalhe), {"Retry-After": str(exc.espera_s)})


async def _conta_bloqueada(_: Request, exc: ContaBloqueada) -> JSONResponse:
    return resposta(tipado("conta-bloqueada", 429, exc.mensagem), {"Retry-After": str(exc.espera_s)})


# Sem "avise a equipe": o ContaAI não publica um contato (decisão 4 da C2), e a frase prometeria um canal que não
# existe.
FRASE_ERRO_INTERNO = "Erro interno. Tente de novo em instantes."


def erro_interno(exc: BaseException) -> JSONResponse:
    """Qualquer exceção sem tratador: registra no log do servidor e responde sem pilha nem mensagem interna. O log
    leva o tipo e onde aconteceu, sem a mensagem, que pode repetir um valor enviado (app.api.registro)."""
    log.error("Erro não tratado: %s", resumo_da_excecao(exc))
    return simples(500, FRASE_ERRO_INTERNO)


async def _inesperado(_: Request, exc: Exception) -> JSONResponse:
    """Último recurso, no ServerErrorMiddleware do Starlette, por fora de todos os middlewares: o 500 daqui sai sem os
    cabeçalhos de segurança. Desde a etapa 9 da C3-B, o erro de uma rota vira 500 por dentro deles
    (app.api.middlewares.ErroNaoTratado), e o de um middleware, em cabecalhos_de_seguranca; aqui só chega uma
    falha no próprio log de acesso ou nos cabeçalhos."""
    return erro_interno(exc)


def registrar(app: FastAPI) -> None:
    app.add_exception_handler(RequestValidationError, _validacao)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, _http)  # type: ignore[arg-type]
    app.add_exception_handler(FalhaMotor, _falha_motor)  # type: ignore[arg-type]
    app.add_exception_handler(CalculoRecusado, _calculo_recusado)  # type: ignore[arg-type]
    app.add_exception_handler(NotaInvalida, _nota_invalida)  # type: ignore[arg-type]
    app.add_exception_handler(NotaRecusada, _nota_recusada)  # type: ignore[arg-type]
    app.add_exception_handler(SementesInvalidas, _sementes)  # type: ignore[arg-type]
    app.add_exception_handler(ProvedorFalhou, _provedor)  # type: ignore[arg-type]
    app.add_exception_handler(consultas.NaoEncontrado, _nao_encontrado)  # type: ignore[arg-type]
    app.add_exception_handler(Recusado, _recusado)  # type: ignore[arg-type]
    app.add_exception_handler(consultas.Conflito, _conflito)  # type: ignore[arg-type]
    app.add_exception_handler(ItemEmUso, _item_em_uso)  # type: ignore[arg-type]
    app.add_exception_handler(EspacoInexistente, _espaco_inexistente)  # type: ignore[arg-type]
    app.add_exception_handler(EspacosEsgotados, _espacos_esgotados)  # type: ignore[arg-type]
    app.add_exception_handler(ContaBloqueada, _conta_bloqueada)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, _inesperado)


# ---------------------------------------------------------------------------
# OpenAPI: toda resposta 4xx/5xx em application/problem+json e todo 422 aceitando ProblemaValidacao


def _ref(nome: str) -> dict[str, str]:
    return {"$ref": f"#/components/schemas/{nome}"}


def _incluir_modelos(esquemas: dict[str, Any], *modelos: type[Problema]) -> None:
    for modelo in modelos:
        esquema = modelo.model_json_schema(ref_template="#/components/schemas/{model}", mode="serialization")
        for nome, definicao in esquema.pop("$defs", {}).items():
            esquemas.setdefault(nome, definicao)
        esquemas.setdefault(modelo.__name__, esquema)


# Recusas dos middlewares (app/api/middlewares.py, ADR 0011): o Host vale para toda rota; o CSRF, para todo método
# que muda o estado (METODOS_INSEGUROS, com o DELETE das sessões); o tamanho do corpo, para o POST e o PATCH (o PATCH
# entrou nas defesas na C3-B, ADR 0017).
RECUSA_HOST = {"400": {"description": "Host não autorizado (CONTAAI_HOSTS_PERMITIDOS, contra DNS rebinding)."}}
# O erro não tratado (C3-B, etapa 9): toda rota pode dar 500, com a frase fixa e os cabeçalhos de segurança.
ERRO_INTERNO = {"500": {"description": "Erro interno, sem a causa (o log do servidor guarda o tipo e o lugar)."}}
RECUSA_CSRF = "Pedido vindo de outra origem (Origin fora de CONTAAI_CORS_ORIGENS, contra CSRF)."
RECUSAS_CORPO = {
    "411": {"description": "Corpo sem Content-Length (corpo em pedaços não é aceito)."},
    "413": {"description": "Corpo maior que o limite."},
}


def _somar_csrf(respostas: dict[str, Any]) -> None:
    """O 403 do CSRF junto do 403 da própria rota (o papel, na C3-B), sem esconder nenhum dos dois. Idempotente."""
    propria = respostas.get("403")
    csrf = RECUSA_CSRF[0].lower() + RECUSA_CSRF[1:]
    if propria is None:
        respostas["403"] = {"description": RECUSA_CSRF}
    elif csrf not in propria.get("description", ""):
        propria["description"] = f"{propria['description'].rstrip('.')}; ou {csrf}"


def ajustar_openapi(spec: dict[str, Any]) -> dict[str, Any]:
    esquemas = spec.setdefault("components", {}).setdefault("schemas", {})
    _incluir_modelos(esquemas, Problema, ProblemaValidacao)
    for operacoes in spec.get("paths", {}).values():
        for metodo, operacao in operacoes.items():
            respostas = operacao.setdefault("responses", {})
            if metodo.upper() in METODOS_INSEGUROS:
                _somar_csrf(respostas)
            gerais = RECUSA_HOST | ERRO_INTERNO | (RECUSAS_CORPO if metodo in ("post", "patch") else {})
            for codigo, resp in gerais.items():
                respostas.setdefault(codigo, dict(resp))
            for codigo, resp in operacao.get("responses", {}).items():
                if not codigo.isdigit() or int(codigo) < 400:
                    continue
                conteudo = resp.pop("content", {})
                esquema = (conteudo.get("application/json") or conteudo.get(TIPO_MIDIA) or {}).get("schema")
                if codigo == "422":
                    validacao = _ref("ProblemaValidacao")
                    if esquema is None or esquema == _ref("HTTPValidationError"):
                        esquema = validacao
                    elif esquema != validacao:
                        opcoes = esquema.get("anyOf", [esquema])
                        esquema = {"anyOf": [*opcoes, validacao]}
                resp["content"] = {TIPO_MIDIA: {"schema": esquema or _ref("Problema")}}
    for nome in ("HTTPValidationError", "ValidationError"):
        esquemas.pop(nome, None)
    return spec
