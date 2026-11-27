"""Erros no formato Problem Details da RFC 9457 (ADR 0009): toda resposta 4xx/5xx em application/problem+json,
`status` igual ao código HTTP, about:blank com a frase do código, tipos próprios descritos em /problemas/{nome}
e nada interno (pilha, URL dos motores, valor enviado) no corpo."""

from __future__ import annotations

from http import HTTPStatus

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.api import middlewares
from app.api.problemas import TIPOS, ajustar_openapi, campos_invalidos
from app.config import Configuracao, configuracao
from app.contrato import Problema, ProblemaMotor, ProblemaValidacao, TipoProblema
from app.main import app
from app.seguranca import LimitadorPorIp
from tests.conftest import URL_RR
from tests.test_carrinho import item, pedido

cliente = TestClient(app)
ORIGEM = "http://localhost:3000"


def problema(r, status: int) -> dict:
    assert r.status_code == status
    assert r.headers["content-type"] == "application/problem+json"
    corpo = r.json()
    Problema.model_validate({k: corpo[k] for k in ("type", "title", "status", "detail") if k in corpo})
    assert corpo["status"] == status  # RFC 9457 3.1.2
    return corpo


def test_validacao_vira_campos_com_json_pointer_e_sem_o_valor_enviado() -> None:
    corpo = {"regime": "simples_tradicional", "data": "2026-03-16", "uf": "sp-x-segredo", "municipio": 1, "itens": []}
    c = problema(cliente.post("/carrinho/calcular", json=corpo), 422)
    v = ProblemaValidacao.model_validate(c)
    assert v.type == "/problemas/entrada-invalida" and v.title == TIPOS["entrada-invalida"].title
    assert any(f.origem == "body" and f.campo == "#/uf" for f in v.campos)
    assert "sp-x-segredo" not in str(c)  # o valor enviado (input) não volta


def test_validacao_de_query_e_de_path() -> None:
    c = ProblemaValidacao.model_validate(problema(cliente.get("/busca/ncm", params={"q": "a"}), 422))
    assert [(f.origem, f.campo) for f in c.campos] == [("query", "#/q")]
    c = ProblemaValidacao.model_validate(problema(cliente.get("/erros/qualquer-coisa"), 422))
    assert [(f.origem, f.campo) for f in c.campos] == [("path", "#/codigo")]


def test_ponteiro_escapa_e_aponta_o_objeto_inteiro() -> None:
    campos = campos_invalidos([{"loc": ("body", "a/b", 0, "c~d"), "msg": "x"}, {"loc": ("body",), "msg": "y"}])
    assert [c.campo for c in campos] == ["#/a~1b/0/c~0d", "#"]


def test_rota_inexistente_e_metodo_errado_sao_about_blank() -> None:
    c = problema(cliente.get("/nao-existe"), 404)
    assert c["type"] == "about:blank" and c["title"] == "Not Found" and "detail" not in c
    r = cliente.get("/carrinho/calcular")
    c = problema(r, 405)
    assert c["title"] == "Method Not Allowed" and "POST" in r.headers["allow"]


def test_http_exception_da_rota_mantem_a_mensagem() -> None:
    c = problema(cliente.get("/explicar/nao-existe"), 404)
    assert c == {"type": "about:blank", "title": "Not Found", "status": 404, "detail": "Item não encontrado."}


def test_token_errado_e_501_do_modo_mock() -> None:
    app.dependency_overrides[configuracao] = lambda: Configuracao(token_demo=SecretStr("t"))
    try:
        c = problema(cliente.post("/chat", json={"mensagens": [{"papel": "usuario", "texto": "oi"}]}), 401)
        assert c["title"] == "Unauthorized" and c["detail"] == "Token da demo ausente ou inválido."
    finally:
        app.dependency_overrides.clear()
    assert problema(cliente.post("/demo/restaurar"), 501)["title"] == "Not Implemented"


@pytest.mark.parametrize(
    ("status_motor", "status_api", "tipo"),
    [(500, 503, "/problemas/motor-indisponivel"), (400, 502, "/problemas/motor-resposta-invalida")],
)
def test_falha_do_motor_tem_tipo_proprio_e_nao_traz_a_url(motores_falsos, status_motor, status_api, tipo) -> None:
    motores_falsos.resposta_rr = (status_motor, {"detail": f"stack trace em {URL_RR}"})
    r = cliente.post("/carrinho/calcular", json=pedido("simples_hibrido", [item("a", "10000001", "10.00")]))
    c = ProblemaMotor.model_validate(problema(r, status_api))
    assert c.type == tipo and c.title == TIPOS[tipo.removeprefix("/problemas/")].title
    assert c.motor == "regime_regular" and "rr.interno" not in r.text and "stack" not in r.text


def test_429_sai_com_cors_e_retry_after(monkeypatch: pytest.MonkeyPatch) -> None:
    """O CORS fica por fora do limite: o frontend em outra origem consegue ler o 429."""
    monkeypatch.setattr(middlewares, "LIMITE_GERAL", LimitadorPorIp(1))
    cabecalho = {"Origin": ORIGEM}
    assert cliente.get("/erros/REG-011", headers=cabecalho).status_code == 200
    r = cliente.get("/erros/REG-011", headers=cabecalho)
    c = problema(r, 429)
    assert c["title"] == "Too Many Requests" and int(r.headers["retry-after"]) >= 1
    assert r.headers["access-control-allow-origin"] == ORIGEM
    assert r.headers["x-content-type-options"] == "nosniff"


def test_411_e_413_do_upload_no_formato_problema() -> None:
    r = cliente.post("/nfe/importar", content=b"x" * 10, headers={"content-length": "abc"})
    assert problema(r, 411)["detail"].startswith("Envie o tamanho")
    grande = str(configuracao().tamanho_max_nfe_bytes + middlewares.FOLGA_MULTIPART + 1)
    r = cliente.post("/nfe/importar", content=b"x", headers={"content-length": grande})
    assert problema(r, 413)["title"] == HTTPStatus(413).phrase


def test_erro_inesperado_nao_expoe_a_mensagem_interna() -> None:
    def explode() -> None:
        raise RuntimeError("segredo interno /srv/contaai/banco.db")

    # Direto no roteador: o `include_router` do FastAPI 0.165 embrulha as rotas num `_IncludedRouter`, e a limpeza
    # pelo caminho, abaixo, não as achava (a rota de teste ficava no app até o fim da bateria).
    app.router.add_api_route("/_teste/explode", explode, methods=["GET"])
    try:
        r = TestClient(app, raise_server_exceptions=False).get("/_teste/explode")
        c = problema(r, 500)
        assert c["type"] == "about:blank" and "segredo" not in r.text and "/srv" not in r.text
    finally:
        app.router.routes[:] = [rt for rt in app.router.routes if getattr(rt, "path", "") != "/_teste/explode"]


@pytest.mark.parametrize("nome", sorted(TIPOS))
def test_todo_tipo_proprio_e_descrito_na_api(nome: str) -> None:
    r = cliente.get(f"/problemas/{nome}")
    assert r.status_code == 200
    tipo = TipoProblema.model_validate(r.json())
    assert tipo.type == f"/problemas/{nome}" and tipo.title and tipo.status and tipo.descricao


def test_tipo_desconhecido() -> None:
    assert problema(cliente.get("/problemas/nao-existe"), 404)["detail"] == "Tipo de problema desconhecido."


def test_openapi_documenta_erros_como_problem_json() -> None:
    spec = app.openapi()
    for ops in spec["paths"].values():
        for op in ops.values():
            for codigo, resp in op["responses"].items():
                if int(codigo) >= 400:
                    assert list(resp["content"]) == ["application/problem+json"], (codigo, op["operationId"])
    assert "HTTPValidationError" not in spec["components"]["schemas"]
    assert ajustar_openapi(spec) == spec  # idempotente
