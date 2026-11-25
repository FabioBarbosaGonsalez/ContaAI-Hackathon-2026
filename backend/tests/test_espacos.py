"""Espaços de avaliação (D2, ADR 0010): cópia própria dos dados da demo por visitante, isolada, com validade,
teto e sem token para mudar o estado dentro do próprio espaço."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.api import middlewares
from app.config import Configuracao, configuracao
from app.contrato import AlertasResposta, CatalogoResposta, EspacoResposta, ProblemaValidacao, RestaurarResposta
from app.main import app
from app.persistencia.espacos import EspacoInexistente, Espacos, EspacosEsgotados
from app.seguranca import LimitadorPorIp
from tests.test_nfe import NOTA_2, SERRA_AZUL, nota

cliente = TestClient(app)
ESPACO = "X-ContaAI-Espaco"
PERGUNTA = {"mensagens": [{"papel": "usuario", "texto": "oi"}]}


def criar() -> EspacoResposta:
    r = cliente.post("/espacos")
    assert r.status_code == 201, r.text
    return EspacoResposta.model_validate(r.json())


def importar_no(espaco_id: str | None, status: int = 200) -> dict:
    headers = {ESPACO: espaco_id} if espaco_id else {}
    r = cliente.post("/nfe/importar", files={"arquivo": ("nota.xml", nota(NOTA_2), "text/xml")}, headers=headers)
    assert r.status_code == status, r.text
    return r.json()


def alertas(espaco_id: str | None = None) -> AlertasResposta:
    headers = {ESPACO: espaco_id} if espaco_id else {}
    r = cliente.get("/alertas", headers=headers)
    assert r.status_code == 200, r.text
    return AlertasResposta.model_validate(r.json())


def sem_hora(r: AlertasResposta) -> list[dict]:
    """Os alertas sem criadoEm, que é a hora real da importação (ADR 0008): o modelo dos espaços e a
    demonstração compartilhada são semeados em instantes diferentes."""
    return [a.model_dump(exclude={"criadoEm"}) for a in r.alertas]


def configurar(**kw) -> None:
    app.dependency_overrides[configuracao] = lambda: Configuracao(modo="real", **kw)


@pytest.fixture
def demo(motores_falsos):
    """Modo real com os motores falsos e a demonstração compartilhada restaurada às sementes."""
    assert cliente.post("/demo/restaurar").status_code == 200
    return motores_falsos


# ---------------------------------------------------------------------------
# API


def test_criar_e_consultar_o_espaco(demo) -> None:
    e = criar()
    assert len(e.id) == 32 and e.expiraEm - e.criadoEm == timedelta(minutes=120)
    r = cliente.get("/espacos/atual", headers={ESPACO: e.id})
    assert EspacoResposta.model_validate(r.json()) == e


def test_espaco_nasce_com_as_sementes_e_e_isolado(demo) -> None:
    a, b = criar(), criar()
    antes_compartilhada, antes_b = alertas(), alertas(b.id)
    assert sem_hora(alertas(a.id)) == sem_hora(antes_b) == sem_hora(antes_compartilhada)  # nascem das sementes

    importar_no(a.id)  # a nota 2 gera o alerta da cerveja só no espaço A
    assert len(alertas(a.id).alertas) == len(antes_compartilhada.alertas) + 1
    assert alertas(b.id) == antes_b
    assert alertas() == antes_compartilhada  # a demonstração compartilhada não mudou


def test_modelo_e_montado_uma_vez_e_o_espaco_nao_chama_os_motores(demo) -> None:
    criar()
    chamadas = len(demo.chamadas)
    criar()
    assert len(demo.chamadas) == chamadas  # cópia do modelo, sem motor


def test_no_proprio_espaco_mudar_o_estado_dispensa_o_token(demo) -> None:
    e = criar()
    configurar(token_demo=SecretStr("segredo-de-teste"))
    importar_no(None, status=401)  # na demonstração compartilhada, o token continua exigido
    corpo = importar_no(e.id)  # no espaço, sem token
    alerta = next(a for a in corpo["alertas"] if a["itemId"] == "cerveja-lata")
    r = cliente.post(f"/alertas/{alerta['id']}/aplicar", headers={ESPACO: e.id})
    assert r.status_code == 200, r.text
    assert cliente.post("/demo/restaurar", headers={ESPACO: e.id}).status_code == 200
    assert cliente.post("/demo/restaurar").status_code == 401


def test_chat_continua_exigindo_o_token_dentro_do_espaco(demo) -> None:
    """O token do chat protege o crédito do provedor de IA, não o estado."""
    e = criar()
    configurar(token_demo=SecretStr("segredo-de-teste"))
    assert cliente.post("/chat", json=PERGUNTA, headers={ESPACO: e.id}).status_code == 401
    ok = cliente.post("/chat", json=PERGUNTA, headers={ESPACO: e.id, "X-ContaAI-Token": "segredo-de-teste"})
    assert ok.status_code == 200, ok.text


def test_restaurar_o_espaco_volta_as_sementes_sem_chamar_os_motores(demo) -> None:
    e = criar()
    sementes = alertas(e.id)
    importar_no(e.id)
    chamadas = len(demo.chamadas)
    r = cliente.post("/demo/restaurar", headers={ESPACO: e.id})
    assert r.status_code == 200
    assert RestaurarResposta.model_validate(r.json()).notasImportadas
    assert alertas(e.id) == sementes and len(demo.chamadas) == chamadas


def test_espaco_desconhecido_e_id_malformado(demo) -> None:
    r = cliente.get("/alertas", headers={ESPACO: "0" * 32})
    assert r.status_code == 404 and r.json()["type"] == "/problemas/espaco-inexistente"
    r = cliente.get("/alertas", headers={ESPACO: "../../etc/passwd"})
    assert r.status_code == 422
    campos = ProblemaValidacao.model_validate(r.json()).campos
    assert [(c.origem, c.campo) for c in campos] == [("header", "#/X-ContaAI-Espaco")]


def test_teto_de_espacos_responde_503_com_retry_after(demo) -> None:
    configurar(espacos_max=1)
    criar()
    r = cliente.post("/espacos")
    assert r.status_code == 503 and r.json()["type"] == "/problemas/espacos-esgotados"
    assert 1 <= int(r.headers["retry-after"]) <= 120 * 60 + 1


def test_criar_espaco_tem_limite_por_ip(demo, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(middlewares, "LIMITE_ESPACOS", LimitadorPorIp(1))
    criar()
    r = cliente.post("/espacos")
    assert r.status_code == 429 and "retry-after" in r.headers
    assert cliente.get("/alertas").status_code == 200  # as outras rotas seguem no limite geral


def test_no_modo_mock_o_espaco_nao_existe() -> None:
    assert cliente.post("/espacos").status_code == 501
    assert cliente.get("/espacos/atual", headers={ESPACO: "a" * 32}).status_code == 501


def test_cors_libera_o_header_do_espaco() -> None:
    r = cliente.options(
        "/alertas",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "x-contaai-espaco",
        },
    )
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# Gerenciador (sem a API): validade, limpeza, teto e caminho


AGORA = datetime(2027, 3, 16, 12, tzinfo=UTC)


@pytest.fixture
def gerenciador(tmp_path: Path) -> Espacos:
    """Modelo montado à mão (migrado e vazio): basta para testar a cópia e o registro."""
    g = Espacos(tmp_path / "espacos", timedelta(minutes=10), maximo=2)
    g.pasta.mkdir(parents=True)
    g.modelo.migrar()
    g._modelo_pronto = True
    return g


def test_espaco_vencido_e_apagado_ao_abrir(gerenciador: Espacos) -> None:
    e = gerenciador.criar(AGORA)
    assert gerenciador.abrir(e.id, AGORA + timedelta(minutes=9)) == e
    with pytest.raises(EspacoInexistente):
        gerenciador.abrir(e.id, AGORA + timedelta(minutes=10))
    assert not (gerenciador.pasta / f"{e.id}.db").exists()


def test_teto_conta_so_os_validos_e_limpa_os_vencidos(gerenciador: Espacos) -> None:
    antigo = gerenciador.criar(AGORA)
    gerenciador.criar(AGORA + timedelta(minutes=5))
    with pytest.raises(EspacosEsgotados) as esgotado:
        gerenciador.criar(AGORA + timedelta(minutes=6))
    assert esgotado.value.espera_s == 4 * 60 + 1  # até o mais antigo vencer
    novo = gerenciador.criar(AGORA + timedelta(minutes=11))  # o antigo venceu: abre vaga e é apagado
    assert not (gerenciador.pasta / f"{antigo.id}.db").exists()
    assert gerenciador.abrir(novo.id, AGORA + timedelta(minutes=11)) == novo


@pytest.mark.parametrize("ruim", ["../registro", "A" * 32, "a" * 31, "a" * 32 + "\n", "a" * 31 + "/"])
def test_id_fora_do_padrao_nunca_vira_caminho(gerenciador: Espacos, ruim: str) -> None:
    with pytest.raises(EspacoInexistente):
        gerenciador.banco(ruim)
    with pytest.raises(EspacoInexistente):
        gerenciador.abrir(ruim, AGORA)


def test_ids_sao_diferentes_e_tem_128_bits(gerenciador: Espacos) -> None:
    gerenciador.maximo = 50
    ids = {gerenciador.criar(AGORA).id for _ in range(20)}
    assert len(ids) == 20 and all(len(i) == 32 and int(i, 16) >= 0 for i in ids)


def test_criar_sem_modelo_e_erro_de_programacao(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError):
        Espacos(tmp_path, timedelta(minutes=1), 1).criar(AGORA)


def test_catalogo_do_espaco(demo) -> None:
    e = criar()
    r = cliente.get(f"/catalogo?cnpj={SERRA_AZUL}", headers={ESPACO: e.id})
    assert r.status_code == 200 and CatalogoResposta.model_validate(r.json()).itens
