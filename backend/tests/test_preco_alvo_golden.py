"""E1-03 contra os motores em execução (marcador golden).

Critério de saída da E1: o preço-alvo converge em até 3 chamadas nos itens lineares. Os itens da
demonstração (arroz, cerveja e chocolate) convergem pelo ajuste afim nos dois regimes; a carne,
classificada errada de propósito, é recusada com o erro do motor. Para a cerveja, o resultado real
é igual ao mock, que veio da implementação de referência.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app import mocks
from app.config import Configuracao, configuracao
from app.contrato import PrecoAlvoResposta, ProblemaCalculo, Regime
from app.dados_demo import carregar_distribuidora
from app.main import app

pytestmark = pytest.mark.golden

DEMO = carregar_distribuidora()
cliente = TestClient(app)
CUSTOS = {"arroz-5kg": "21.50", "cerveja-lata": "3.05", "chocolate-barra": "4.10", "carne-bovina-kg": "30.00"}


@pytest.fixture(autouse=True)
def modo_real():
    app.dependency_overrides[configuracao] = lambda: Configuracao(modo="real")
    yield
    app.dependency_overrides.clear()


def pedido(item_id: str, regime: Regime, **extra: Any) -> dict[str, Any]:
    cat, cen = DEMO.item(item_id), DEMO.cenario
    return {
        "data": cen.data.isoformat(),
        "uf": DEMO.empresa.uf,
        "municipio": DEMO.empresa.municipio,
        "regime": regime.value,
        "aliquotasNominais": {
            "cbs": str(cen.aliquotasNominais.cbs),
            "ibsEstadual": str(cen.aliquotasNominais.ibsEstadual),
            "ibsMunicipal": str(cen.aliquotasNominais.ibsMunicipal),
            "impostoSeletivoAdValorem": str(cen.impostoSeletivoAdValorem.valor),
        },
        "premissasDas": {
            "anexo": cen.premissasDas.anexo,
            "cAtivSN": DEMO.empresa.simples.cAtivSN,
            "pCBSSN": str(cen.premissasDas.pCBSSN),
            "pIBSSN": str(cen.premissasDas.pIBSSN),
        },
        "item": {
            "id": cat.id,
            "descricao": cat.descricao,
            "ncm": cat.ncm,
            "cst": cat.cst,
            "cClassTrib": cat.cClassTrib,
            "impostoSeletivo": cat.impostoSeletivo.model_dump(exclude={"motivo"}, mode="json")
            if cat.impostoSeletivo
            else None,
            "unidade": cat.unidade,
        },
        "custoUnitario": CUSTOS[item_id],
        "margemAlvoPct": str(cat.margemAlvoPct),
        **extra,
    }


def calcular(corpo: dict[str, Any]) -> PrecoAlvoResposta:
    r = cliente.post("/item/preco-alvo", json=corpo)
    if r.status_code == 503:
        pytest.fail("Motores fora do ar. Suba com: docker compose up -d")
    assert r.status_code == 200, r.text
    return PrecoAlvoResposta.model_validate(r.json())


@pytest.mark.parametrize("regime", list(Regime))
@pytest.mark.parametrize("item_id", ["arroz-5kg", "cerveja-lata", "chocolate-barra"])
def test_itens_da_demo_convergem_em_3_chamadas(item_id: str, regime: Regime) -> None:
    r = calcular(pedido(item_id, regime))
    assert (r.metodo, r.chamadas) == ("afim", 3), item_id
    assert r.margemObtidaPct >= r.margemAlvoPct
    assert r.simulado and r.avisoSimulacao


@pytest.mark.parametrize("regime", list(Regime))
def test_cerveja_real_igual_ao_mock(regime: Regime) -> None:
    mock = mocks.carregar().preco_alvo[regime]
    # O mock usa o custo e o crédito da nota 2 (grupo IBSCBS), por unidade.
    extra = {"custoUnitario": "3.05", "creditoCompraUnitario": str(mock.custoEfetivoUnitario - Decimal("3.05"))}
    real = calcular(pedido("cerveja-lata", regime, **extra))
    campos = {"valorUnitario", "precoCliente", "tributosUnitarios", "custoEfetivoUnitario", "margemObtidaPct"}
    campos |= {"chamadas", "metodo", "loteReferencia", "memoria", "simulado", "avisoSimulacao"}
    assert real.model_dump(include=campos) == mock.model_dump(include=campos)


@pytest.mark.parametrize(
    ("regime", "codigo"), [(Regime.SIMPLES_HIBRIDO, "REG-011"), (Regime.SIMPLES_TRADICIONAL, "VSN-047")]
)
def test_carne_classificada_errada_e_recusada_com_o_erro_do_motor(regime: Regime, codigo: str) -> None:
    extra = {"creditoCompraUnitario": "0"} if regime == Regime.SIMPLES_TRADICIONAL else {}
    r = cliente.post("/item/preco-alvo", json=pedido("carne-bovina-kg", regime, **extra))
    assert r.status_code == 422
    assert [e.codigo for e in ProblemaCalculo.model_validate(r.json()).erros] == [codigo]
