"""Proteções da etapa 9 da C3-B (ADR 0009 e ADR 0017): o erro 500 com os cabeçalhos de segurança e o CORS, a
telemetria do FastAPI desligada e o inventário do limite por IP."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from starlette.types import Message, Receive, Scope, Send

from app.api import middlewares
from app.api.middlewares import ROTAS_LIMITADAS, ErroNaoTratado
from app.api.problemas import FRASE_ERRO_INTERNO
from app.main import app
from app.seguranca import LimitadorPorIp
from tests.test_papeis import _rotas
from tests.test_seguranca_api import FRONT, cabecalhos_ok

ROTA_QUE_FALHA = "/_teste/falha-nao-tratada"
SEGREDO = "ana@exemplo.com.br 11222333000181 /srv/contaai/banco.db"

# Rotas sem limite por IP, e por quê: leem o banco ou dados fixos, sem chamar os motores nem a IA; os DELETE só
# encerram sessões da própria pessoa. Toda rota nova falha o inventário até ter limite ou entrar aqui com o motivo.
SEM_LIMITE = {
    "GET /alertas",
    "GET /catalogo",
    "GET /notas",
    "GET /notas/{cnpj_emitente}/{serie}/{numero}",
    "GET /contador/painel",
    "GET /conta",
    "GET /cenarios/presets",
    "GET /problemas/{nome}",
    "DELETE /sessoes",
    "DELETE /sessoes/atual",
}


@pytest.fixture
def rota_que_falha() -> Iterator[None]:
    """Uma rota direto no roteador do app (o `include_router` do FastAPI 0.165 a embrulharia num `_IncludedRouter`,
    e a limpeza pelo caminho não a acharia). O OpenAPI guardado volta ao de antes: sem a rota de teste."""

    def falhar() -> None:
        raise RuntimeError(SEGREDO)

    contrato = app.openapi_schema
    app.router.add_api_route(ROTA_QUE_FALHA, falhar, methods=["GET"])
    try:
        yield
    finally:
        app.router.routes[:] = [r for r in app.router.routes if getattr(r, "path", "") != ROTA_QUE_FALHA]
        app.openapi_schema = contrato


class Explode:
    """Um limitador que falha: simula um erro dentro de um middleware."""

    def permitir(self, ip: str, agora: float | None = None) -> tuple[bool, int]:
        raise RuntimeError(SEGREDO)


# -- o 500 -------------------------------------------------------------------------------------------------


def test_o_500_da_rota_sai_com_os_cabecalhos_e_o_cors(rota_que_falha, caplog: pytest.LogCaptureFixture) -> None:
    """Antes, o 500 era montado por fora de todos os middlewares: sem nosniff, CSP, no-store e CORS."""
    # raise_server_exceptions=True (o padrão): a exceção não passa do nosso tratador para o servidor.
    with caplog.at_level(logging.INFO):
        r = TestClient(app).get(ROTA_QUE_FALHA, headers={"Origin": FRONT})
    assert r.status_code == 500 and r.headers["content-type"] == "application/problem+json"
    assert cabecalhos_ok(r), dict(r.headers)
    assert r.headers["access-control-allow-origin"] == FRONT  # a tela de outra origem consegue ler o erro
    assert r.json() == {
        "type": "about:blank",
        "title": "Internal Server Error",
        "status": 500,
        "detail": FRASE_ERRO_INTERNO,
    }
    # O log: uma linha do erro, sem a mensagem, e a linha de acesso com o 500.
    erros = [x.getMessage() for x in caplog.records if x.name == "contaai" and "Erro não tratado" in x.getMessage()]
    assert len(erros) == 1 and "builtins.RuntimeError" in erros[0]
    assert f"GET {ROTA_QUE_FALHA} 500" in caplog.text
    assert "ana@" not in caplog.text and "11222333000181" not in caplog.text and "/srv/" not in caplog.text
    assert not [x for x in caplog.records if x.name == "uvicorn.error"]


def test_origem_fora_da_lista_nao_recebe_o_cors_no_500(rota_que_falha) -> None:
    r = TestClient(app).get(ROTA_QUE_FALHA, headers={"Origin": "https://malvado.example"})
    assert r.status_code == 500 and cabecalhos_ok(r) and "access-control-allow-origin" not in r.headers


def test_o_500_de_um_middleware_sai_com_os_cabecalhos(monkeypatch: pytest.MonkeyPatch) -> None:
    """Uma falha dentro de um middleware (aqui, o limite por IP) não passa pelo tratador da rota: o dos cabeçalhos
    a pega. O CORS fica de fora nesse caso, porque a exceção atravessa o middleware dele."""
    monkeypatch.setattr(middlewares, "LIMITE_GERAL", Explode())
    r = TestClient(app).get("/saude")
    assert r.status_code == 500 and cabecalhos_ok(r), dict(r.headers)
    assert r.json()["detail"] == FRASE_ERRO_INTERNO and "ana@" not in r.text


def test_resposta_ja_comecada_nao_e_trocada() -> None:
    """Depois do início da resposta não dá para mandar outra: a exceção segue para o Starlette."""
    enviadas: list[Message] = []

    async def app_que_falha_no_meio(scope: Scope, receive: Receive, send: Send) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": []})
        raise RuntimeError(SEGREDO)

    async def receber() -> Message:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def enviar(mensagem: Message) -> None:
        enviadas.append(mensagem)

    with pytest.raises(RuntimeError):
        asyncio.run(ErroNaoTratado(app_que_falha_no_meio)({"type": "http"}, receber, enviar))
    assert [m["type"] for m in enviadas] == ["http.response.start"]


def test_o_500_esta_no_contrato_de_toda_rota() -> None:
    for caminho, operacoes in app.openapi()["paths"].items():
        for metodo, operacao in operacoes.items():
            assert "500" in operacao["responses"], (metodo, caminho)


# -- a telemetria do FastAPI -------------------------------------------------------------------------------


def test_a_telemetria_do_fastapi_fica_desligada() -> None:
    """Ela gravaria as mensagens das exceções e o corpo lido. Desligada na montagem do app, nem a variável
    FASTAPI_OTEL_AUTO_CONFIGURE nem um SDK instalado depois a ligam (os atributos são do FastAPI 0.165)."""
    config = app._telemetry  # noqa: SLF001
    assert not any(config[k] for k in ("tracing", "metrics", "logs", "operation_spans", "auto_configure"))
    assert app._native_telemetry.enabled() is False  # noqa: SLF001


# -- o limite por IP ---------------------------------------------------------------------------------------


def _limitada(rota: str) -> bool:
    metodo, caminho = rota.split(" ", 1)
    return metodo in ("GET", "POST", "PATCH") and caminho.startswith(ROTAS_LIMITADAS)


def test_toda_rota_tem_limite_por_ip_ou_um_motivo_para_nao_ter() -> None:
    rotas = {f"{m} {prefixo}{r.path}" for prefixo, r in _rotas(app.router.routes) for m in r.methods if m != "HEAD"}
    assert SEM_LIMITE <= rotas
    assert not {r for r in SEM_LIMITE if _limitada(r)}, "rota com limite não precisa estar em SEM_LIMITE"
    assert {r for r in rotas if not _limitada(r)} == SEM_LIMITE


def test_a_saude_tem_limite_por_ip(monkeypatch: pytest.MonkeyPatch) -> None:
    """O GET /saude consulta os dois motores a cada pedido: ficava sem limite, contra a regra de ROTAS_LIMITADAS."""
    monkeypatch.setattr(middlewares, "LIMITE_GERAL", LimitadorPorIp(1))
    cliente = TestClient(app)
    assert cliente.get("/saude").status_code == 200
    r = cliente.get("/saude")
    assert r.status_code == 429 and int(r.headers["retry-after"]) > 0 and cabecalhos_ok(r)
