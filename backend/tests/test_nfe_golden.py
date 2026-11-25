"""E4 contra os motores em execução (marcador golden: make golden / uv run pytest -m golden).

Critério de saída do plano (E4): subir o XML de demonstração gera o alerta com o preço sugerido em
menos de 5 s. Com o estado restaurado às sementes, a nota 2 dá, para a cerveja da Serra Azul
(Simples tradicional, preço R$ 3,79, alvo 15%): margem de 24,12% para 11,19% e preço sugerido R$ 3,97.
São os mesmos números da implementação de referência da E0 (scripts/gerar_mocks.py), que o gerador
confere antes de gravar os mocks (ADR 0008).
"""

from __future__ import annotations

import time
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app import mocks
from app.config import Configuracao, configuracao
from app.contrato import AplicarAlertaResposta, CatalogoResposta, NfeImportarResposta, PainelContadorResposta
from app.dados_demo import PASTA_DEMO
from app.main import app

pytestmark = pytest.mark.golden

cliente = TestClient(app)
SERRA_AZUL, VALE_VERDE = "36817420000113", "52918364000170"


@pytest.fixture(autouse=True)
def estado_restaurado():
    app.dependency_overrides[configuracao] = lambda: Configuracao(modo="real")
    r = cliente.post("/demo/restaurar")
    assert r.status_code == 200, r.text
    yield
    app.dependency_overrides.clear()


def importar(nome: str) -> NfeImportarResposta:
    conteudo = (PASTA_DEMO / nome).read_bytes()
    r = cliente.post("/nfe/importar", files={"arquivo": ("nota.xml", conteudo, "text/xml")})
    assert r.status_code == 200, r.text
    return NfeImportarResposta.model_validate(r.json())


def test_nota_2_gera_o_alerta_da_cerveja_em_menos_de_5_s() -> None:
    inicio = time.perf_counter()
    corpo = importar("notas/nfe-compra-2.xml")
    assert time.perf_counter() - inicio < 5
    [alerta] = corpo.alertas
    assert (alerta.itemId, alerta.margemAntesPct, alerta.margemDepoisPct) == (
        "cerveja-lata",
        Decimal("24.12"),
        Decimal("11.19"),
    )
    assert (alerta.precoAtual, alerta.precoSugerido) == (Decimal("3.79"), Decimal("3.97"))


def test_rota_real_devolve_o_mock_menos_a_hora_da_criacao() -> None:
    """O mock sai do mesmo código, com o relógio fixo; só o criadoEm muda (hora real × hora da nota)."""
    real = importar("notas/nfe-compra-2.xml").model_dump(mode="json")
    mock = mocks.carregar().nfe_importar.model_dump(mode="json")
    for corpo in (real, mock):
        for alerta in corpo["alertas"]:
            alerta.pop("criadoEm")
    assert real == mock


def test_carteira_do_contador_e_aplicar_preco() -> None:
    painel = PainelContadorResposta.model_validate(cliente.get("/contador/painel").json())
    primeira = painel.empresas[0]
    assert primeira.empresa.cnpj == VALE_VERDE and primeira.alertasAbertos == 2
    alertas = {a["itemId"]: a for a in cliente.get(f"/alertas?cnpj={VALE_VERDE}").json()["alertas"]}
    assert (alertas["biscoito-pacote"]["margemAntesPct"], alertas["biscoito-pacote"]["margemDepoisPct"]) == (
        "26.84",
        "12.91",
    )
    assert alertas["biscoito-pacote"]["precoSugerido"] == "5.12"
    assert alertas["chocolate-barra"]["precoSugerido"] == "6.77"

    [cerveja] = importar("notas/nfe-compra-2.xml").alertas
    r = cliente.post(f"/alertas/{cerveja.id}/aplicar")
    assert r.status_code == 200, r.text
    assert AplicarAlertaResposta.model_validate(r.json()).precoNovo == Decimal("3.97")
    cat = CatalogoResposta.model_validate(cliente.get(f"/catalogo?cnpj={SERRA_AZUL}").json())
    assert next(i for i in cat.itens if i.id == "cerveja-lata").precoVenda == Decimal("3.97")


def test_item_sem_par_com_os_motores() -> None:
    corpo = importar("notas/nfe-item-sem-par.xml")
    assert [i.codigoFornecedor for i in corpo.itensSemPar] == ["AE-REF-2L", "AE-BIS-140"]
    [chocolate] = corpo.itensCasados
    assert chocolate.fonteCredito == "motor" and chocolate.creditoCompraUnitario == Decimal("0.3649")
