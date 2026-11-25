"""Proteção da demo pública (E2-08): limite por IP, token do chat e configuração sem segredos."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.api import middlewares
from app.config import Configuracao, configuracao
from app.main import app
from app.seguranca import LimitadorPorIp, token_confere

cliente = TestClient(app)
PERGUNTA = {"mensagens": [{"papel": "usuario", "texto": "oi"}]}


def test_limitador_janela_deslizante() -> None:
    lim = LimitadorPorIp(2)
    assert lim.permitir("1.1.1.1", agora=0)[0]
    assert lim.permitir("1.1.1.1", agora=1)[0]
    permitido, espera = lim.permitir("1.1.1.1", agora=2)
    assert not permitido and 1 <= espera <= 60
    assert lim.permitir("2.2.2.2", agora=2)[0]  # outro IP não é afetado
    assert lim.permitir("1.1.1.1", agora=61)[0]  # a janela andou


def test_limitador_desligado_e_tabela_limitada() -> None:
    assert all(LimitadorPorIp(0).permitir("x", agora=i)[0] for i in range(100))
    lim = LimitadorPorIp(5, max_ips=3)
    for i in range(10):
        lim.permitir(f"10.0.0.{i}", agora=0)
    assert len(lim._vistos) == 3


def test_token() -> None:
    assert token_confere(None, None)
    assert not token_confere(SecretStr("segredo"), None)
    assert not token_confere(SecretStr("segredo"), "errado")
    assert token_confere(SecretStr("segredo"), "segredo")


@pytest.fixture
def configurar():
    def aplicar(**kw):
        app.dependency_overrides[configuracao] = lambda: Configuracao(**kw)

    yield aplicar
    app.dependency_overrides.clear()


def test_chat_exige_token_quando_configurado(configurar) -> None:
    configurar(token_demo=SecretStr("demo-123"))
    assert cliente.post("/chat", json=PERGUNTA).status_code == 401
    assert cliente.post("/chat", json=PERGUNTA, headers={"X-ContaAI-Token": "outro"}).status_code == 401
    assert cliente.post("/chat", json=PERGUNTA, headers={"X-ContaAI-Token": "demo-123"}).status_code == 200


def test_chat_responde_429_depois_do_limite(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(middlewares, "LIMITE_CHAT", LimitadorPorIp(2))
    assert [cliente.post("/chat", json=PERGUNTA).status_code for _ in range(3)] == [200, 200, 429]
    r = cliente.post("/chat", json=PERGUNTA)
    assert r.status_code == 429 and int(r.headers["Retry-After"]) >= 1


def test_rotas_dos_motores_tem_limite_geral(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(middlewares, "LIMITE_GERAL", LimitadorPorIp(1))
    assert cliente.get("/busca/ncm", params={"q": "arroz"}).status_code == 200
    assert cliente.get("/busca/ncm", params={"q": "arroz"}).status_code == 429
    assert cliente.get("/saude").status_code == 200  # fora do limite


def test_busca_tem_limite_proprio(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(middlewares, "LIMITE_BUSCA", LimitadorPorIp(1))
    assert cliente.get("/busca/ncm", params={"q": "arroz"}).status_code == 200
    assert cliente.get("/busca/ncm", params={"q": "cerveja"}).status_code == 429
    assert cliente.get("/erros/REG-011").status_code == 200  # as outras rotas seguem no limite geral


def test_cors_aceita_o_header_do_token() -> None:
    r = cliente.options(
        "/chat",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "x-contaai-token",
        },
    )
    assert r.status_code == 200


def test_variaveis_vazias_do_env_example_valem_como_nao_definidas(monkeypatch: pytest.MonkeyPatch) -> None:
    for nome in ("CONTAAI_TOKEN_DEMO", "CONTAAI_LLM_CHAVE", "CONTAAI_LLM_MODELO", "CONTAAI_LLM_URL"):
        monkeypatch.setenv(nome, "")
    cfg = Configuracao()
    assert cfg.token_demo is None and cfg.llm_chave is None and cfg.llm_modelo is None and cfg.llm_url is None


def test_chave_do_llm_nao_aparece_na_configuracao() -> None:
    cfg = Configuracao(llm_chave=SecretStr("sk-segredo"), token_demo=SecretStr("t"))
    assert "sk-segredo" not in repr(cfg) and "sk-segredo" not in cfg.model_dump_json()


def test_ultima_mensagem_precisa_ser_do_usuario() -> None:
    corpo = {"mensagens": [{"papel": "usuario", "texto": "oi"}, {"papel": "assistente", "texto": "olá"}]}
    assert cliente.post("/chat", json=corpo).status_code == 422
