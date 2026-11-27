"""Testes de segurança da API (ADR 0011): XSS, CSRF, DNS rebinding, injeção, corpo grande, números extremos,
cabeçalhos em toda resposta e documentação desligável.

A API só devolve JSON. O que a protege de XSS é nunca responder HTML, mandar `nosniff` e uma CSP que não deixa
nada rodar; o que protege a tela (E5) é exibir todo texto como texto (docs/seguranca.md). Rodam no CI.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api import middlewares
from app.config import Configuracao, configuracao
from app.main import app
from app.seguranca import LimitadorPorIp
from tests.test_agente import contexto, item

cliente = TestClient(app, raise_server_exceptions=False)
BACKEND = Path(__file__).resolve().parents[1]
FRONT = "http://localhost:3000"
XSS = "<script>alert(1)</script>"
XSS_NO_CAMINHO = "%3Cscript%3Ealert(1)%3C%2Fscript%3E"
CSP_API = "default-src 'none'; frame-ancestors 'none'"


@pytest.fixture
def configurar() -> Iterator:
    def aplicar(**campos: object) -> None:
        app.dependency_overrides[configuracao] = lambda: Configuracao(**campos)

    yield aplicar
    app.dependency_overrides.clear()


def cabecalhos_ok(r) -> bool:
    return (
        r.headers.get("X-Content-Type-Options") == "nosniff"
        and r.headers.get("X-Frame-Options") == "DENY"
        and r.headers.get("Content-Security-Policy") == CSP_API
        and r.headers.get("Cache-Control") == "no-store"
        and r.headers.get("Cross-Origin-Resource-Policy") == "same-origin"
    )


def e_json(r) -> bool:
    tipo = r.headers.get("content-type", "").split(";")[0]
    return tipo in ("application/json", "application/problem+json")


def corpo_carrinho(**item_extra: str) -> dict:
    ctx = contexto(itens=["arroz-5kg"])
    return {k: v for k, v in ctx.items() if k != "itens"} | {
        "regime": "simples_hibrido",
        "itens": [item("arroz-5kg") | item_extra],
    }


# ---------------------------------------------------------------------------
# XSS: nenhuma rota responde HTML, e todo texto volta como dado JSON


def _rotas_da_api() -> list[tuple[str, str]]:
    """(método, caminho) de toda rota do contrato, pelo esquema OpenAPI do próprio app."""
    return [(m.upper(), caminho) for caminho, ops in app.openapi()["paths"].items() for m in ops]


@pytest.mark.parametrize("modo", ["mock", "real"])
def test_nenhuma_rota_responde_html_nem_quebra_com_payload_de_xss(modo: str, request: pytest.FixtureRequest) -> None:
    if modo == "real":
        request.getfixturevalue("motores_falsos")
        assert cliente.post("/demo/restaurar").status_code == 200
    vistas = 0
    for metodo, rota in _rotas_da_api():
        caminho = re.sub(r"\{[^}]+\}", XSS_NO_CAMINHO, rota)
        if metodo == "GET":
            r = cliente.get(caminho, params={"q": XSS, "cnpj": XSS, "regime": XSS})
        else:
            r = cliente.request(metodo, caminho, json={"texto": XSS, "cnpj": XSS, "mensagens": [XSS]})
        vistas += 1
        # 501: rota que muda o estado no modo mock (documentado). Nenhum 500.
        assert r.status_code < 500 or (modo == "mock" and r.status_code == 501), (metodo, rota, r.status_code, r.text)
        assert e_json(r), (metodo, rota, r.headers.get("content-type"))
        assert cabecalhos_ok(r), (metodo, rota, dict(r.headers))
    assert vistas >= 20


def test_texto_do_usuario_volta_como_dado_json_e_nunca_como_html(motores_falsos) -> None:
    """O backend não escapa nem remove o texto (é dado do usuário); ele volta como string JSON, que o navegador
    não executa (nosniff + CSP). A tela o exibe como texto (docs/seguranca.md, regras da interface)."""
    perigoso = '<img src=x onerror="alert(1)">'
    r = cliente.post("/carrinho/calcular", json=corpo_carrinho(descricao=perigoso))
    assert r.status_code == 200 and e_json(r) and cabecalhos_ok(r)
    assert r.json()["itens"][0]["descricao"] == perigoso


def test_erro_de_validacao_nao_repete_o_valor_enviado() -> None:
    r = cliente.get("/catalogo", params={"cnpj": XSS})
    assert r.status_code == 422 and "<script>" not in r.text and e_json(r)


def test_docs_e_a_unica_pagina_html_e_pode_ser_desligada() -> None:
    """CONTAAI_DOCS_PUBLICA=false: sem /docs, /redoc e /openapi.json (o Swagger carrega scripts de uma CDN)."""
    codigo = (
        "from fastapi.testclient import TestClient\n"
        "from app.main import app\n"
        "c = TestClient(app)\n"
        "print(*[c.get(p).status_code for p in ('/docs', '/redoc', '/openapi.json', '/saude')])\n"
    )
    env = {**os.environ, "CONTAAI_DOCS_PUBLICA": "false", "PYTHONIOENCODING": "utf-8"}
    saida = subprocess.run(  # noqa: S603 (o próprio interpretador, com código fixo do teste)
        [sys.executable, "-c", codigo], cwd=BACKEND, env=env, check=True, capture_output=True, text=True
    )
    assert saida.stdout.split() == ["404", "404", "404", "200"]


# ---------------------------------------------------------------------------
# DNS rebinding: só os hosts configurados


@pytest.mark.parametrize("host", ["rebinding.exemplo.test", "127.0.0.1.nip.io", "[::1]:8000", "", "evil:80:1"])
def test_host_fora_da_lista_e_recusado(host: str) -> None:
    r = cliente.get("/saude", headers={"Host": host})
    assert r.status_code == 400 and e_json(r) and cabecalhos_ok(r)
    assert r.json()["detail"] == "Host não autorizado."


@pytest.mark.parametrize("host", ["127.0.0.1", "127.0.0.1:8000", "localhost:8000", "LOCALHOST"])
def test_hosts_locais_sao_aceitos(host: str) -> None:
    assert cliente.get("/saude", headers={"Host": host}).status_code == 200


# ---------------------------------------------------------------------------
# CSRF: Origin de outro site no POST, e corpo que não é JSON


@pytest.mark.parametrize("origem", ["https://site-malicioso.exemplo.test", "null", "http://localhost:3001"])
def test_post_de_outra_origem_e_recusado(origem: str) -> None:
    for caminho, corpo in (("/espacos", None), ("/carrinho/calcular", corpo_carrinho()), ("/chat", {})):
        r = cliente.post(caminho, json=corpo, headers={"Origin": origem})
        assert r.status_code == 403 and e_json(r) and cabecalhos_ok(r), caminho


def test_post_da_tela_e_sem_origin_seguem() -> None:
    assert cliente.post("/carrinho/calcular", json=corpo_carrinho(), headers={"Origin": FRONT}).status_code == 200
    assert cliente.post("/carrinho/calcular", json=corpo_carrinho()).status_code == 200  # curl, scripts
    # GET de outra origem não muda nada: responde, mas sem Access-Control-Allow-Origin (o navegador não lê).
    r = cliente.get("/alertas", headers={"Origin": "https://site-malicioso.exemplo.test"})
    assert r.status_code == 200 and "access-control-allow-origin" not in r.headers


@pytest.mark.parametrize("tipo", ["text/plain", "application/x-www-form-urlencoded", "multipart/form-data; boundary=x"])
def test_corpo_que_nao_e_json_nao_e_lido_como_json(tipo: str) -> None:
    """Um formulário de outro site manda text/plain sem preflight: o FastAPI só lê JSON com content-type JSON."""
    import json

    r = cliente.post("/carrinho/calcular", content=json.dumps(corpo_carrinho()), headers={"Content-Type": tipo})
    assert r.status_code == 422


def test_cors_expoe_retry_after_e_o_marcador_de_mock() -> None:
    r = cliente.get("/alertas", headers={"Origin": FRONT})
    expostos = {h.strip().lower() for h in r.headers["access-control-expose-headers"].split(",")}
    assert {"retry-after", "x-contaai-mock"} <= expostos
    assert r.headers["access-control-allow-origin"] == FRONT


# ---------------------------------------------------------------------------
# Corpo grande e em pedaços


def test_json_maior_que_o_limite_e_recusado_antes_de_ser_lido(configurar) -> None:
    configurar(tamanho_max_json_bytes=2_000)
    grande = {"mensagens": [{"papel": "usuario", "texto": "a" * 3_000}]}
    r = cliente.post("/chat", json=grande)
    assert r.status_code == 413 and e_json(r) and cabecalhos_ok(r)


def test_corpo_em_pedacos_e_recusado() -> None:
    def pedacos() -> Iterator[bytes]:
        yield b'{"mensagens": ['
        yield b'{"papel": "usuario", "texto": "oi"}]}'

    r = cliente.post("/chat", content=pedacos(), headers={"Content-Type": "application/json"})
    assert r.status_code == 411 and e_json(r)


# ---------------------------------------------------------------------------
# Injeção: SQL e caminho


@pytest.mark.parametrize("valor", ["' OR '1'='1", "1; DROP TABLE empresas; --", "36817420000113' --", "../../etc"])
def test_parametros_com_injecao_sao_recusados_pelo_contrato(motores_falsos, valor: str) -> None:
    assert cliente.post("/demo/restaurar").status_code == 200
    assert cliente.get("/catalogo", params={"cnpj": valor}).status_code == 422
    assert cliente.get("/alertas", params={"cnpj": valor}).status_code == 422
    assert cliente.get("/alertas", headers={"X-ContaAI-Espaco": valor}).status_code == 422
    assert cliente.post(f"/alertas/{valor}/aplicar").status_code in (404, 422)
    assert cliente.post(
        f"/catalogo/{valor}/preco", json={"cnpj": "36817420000113", "valorUnitario": "1"}
    ).status_code in (
        404,
        422,
    )
    # O estado continua inteiro.
    assert cliente.get("/catalogo", params={"cnpj": "36817420000113"}).status_code == 200


def test_o_sql_do_repositorio_nunca_e_montado_com_texto() -> None:
    """Guarda: nenhum execute com f-string ou concatenação no código do app (só consultas parametrizadas)."""
    permitidos = {'conexao.execute(f"PRAGMA busy_timeout = {ESPERA_ESCRITA_MS}")'}  # constante do módulo
    achados = []
    for arquivo in (BACKEND / "app").rglob("*.py"):
        linhas = [linha.strip() for linha in arquivo.read_text(encoding="utf-8").splitlines()]
        for n, trecho in enumerate(linhas):
            if re.search(r"\.execute(many)?\(\s*f[\"']", trecho) or re.search(r"\.execute\([^)]*\+", trecho):
                if trecho not in permitidos:
                    achados.append(f"{arquivo.name}: {trecho}")
            # O SQL na linha seguinte ao execute( (achado da C3-B: a f-string ali escapava da regra acima).
            if re.search(r"\.execute(many)?\($", trecho) and n + 1 < len(linhas):
                seguinte = linhas[n + 1]
                if re.match(r"f[\"']", seguinte) or re.search(r"[\"']\s*\+|\+\s*[\"']", seguinte):
                    achados.append(f"{arquivo.name}: {trecho} {seguinte}")
    assert achados == []


# ---------------------------------------------------------------------------
# Números extremos: 422, nunca 500 nem ida ao motor


@pytest.mark.parametrize(
    ("campo", "valor"),
    [
        ("valorUnitario", "1e999999"),
        ("valorUnitario", "1e-999999"),
        ("valorUnitario", "99999999999999999999999999999999999.99"),
        ("valorUnitario", "NaN"),
        ("valorUnitario", "-Infinity"),
        ("quantidade", "1e30"),
        ("quantidade", "1.00001"),
        ("custoUnitario", "1e999999"),
        ("creditoCompraUnitario", "1e999999"),
    ],
)
def test_numero_extremo_e_recusado_sem_erro_500(motores_falsos, campo: str, valor: str) -> None:
    r = cliente.post("/carrinho/calcular", json=corpo_carrinho(**{campo: valor}))
    assert r.status_code == 422, r.text
    assert motores_falsos.chamadas == []


def test_aliquota_e_margem_com_casas_demais_sao_recusadas(motores_falsos) -> None:
    corpo = corpo_carrinho()
    corpo["aliquotasNominais"] = corpo["aliquotasNominais"] | {"cbs": "8.800001"}
    assert cliente.post("/carrinho/calcular", json=corpo).status_code == 422
    alvo = {k: v for k, v in corpo_carrinho().items() if k != "itens"} | {
        "item": {k: v for k, v in item("arroz-5kg").items() if k not in ("quantidade", "valorUnitario")},
        "custoUnitario": "10",
        "margemAlvoPct": "1e-999999",
    }
    assert cliente.post("/item/preco-alvo", json=alvo).status_code == 422
    assert motores_falsos.chamadas == []


# ---------------------------------------------------------------------------
# Cabeçalhos em toda resposta, inclusive nas de erro; limite nas rotas novas


def test_cabecalhos_de_seguranca_tambem_nos_erros(configurar) -> None:
    respostas = [
        cliente.get("/nao-existe"),  # 404
        cliente.put("/carrinho/calcular"),  # 405
        cliente.get("/catalogo"),  # 422
        cliente.post("/espacos", headers={"Origin": "https://x.exemplo.test"}),  # 403
        cliente.get("/saude", headers={"Host": "x.exemplo.test"}),  # 400
    ]
    configurar(tamanho_max_json_bytes=10)
    respostas.append(cliente.post("/chat", json={"mensagens": []}))  # 413
    for r in respostas:
        assert r.status_code >= 400 and e_json(r) and cabecalhos_ok(r), (r.status_code, dict(r.headers))


def test_rotas_da_tela_tem_limite_por_ip(motores_falsos, monkeypatch: pytest.MonkeyPatch) -> None:
    assert cliente.post("/demo/restaurar").status_code == 200
    monkeypatch.setattr(middlewares, "LIMITE_GERAL", LimitadorPorIp(1))
    corpo = {"cnpj": "36817420000113", "valorUnitario": "4.15"}
    assert cliente.post("/catalogo/cerveja-lata/preco", json=corpo).status_code == 200
    assert cliente.post("/catalogo/cerveja-lata/preco", json=corpo).status_code == 429
    assert cliente.get("/catalogo", params={"cnpj": "36817420000113"}).status_code == 200  # leitura sem motor
