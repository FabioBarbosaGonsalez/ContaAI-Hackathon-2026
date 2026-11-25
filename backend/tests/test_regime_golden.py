"""E3 contra os motores em execução (marcador golden: make golden / uv run pytest -m golden).

1. Com a venda mensal de demonstração ao cliente B2B (biscoito, cerveja e chocolate, todos com
   tributação integral), a rota real devolve exatamente o mock, que o gerador produz com o mesmo
   código de produção. Os números da demo ficam fixados aqui.
2. Conferência do algoritmo: a cesta antiga (arroz no lugar do biscoito) bate com a implementação de
   referência da E0, que era independente do código de produção (ADR 0003): venda R$ 19.901,00;
   tributo no DAS R$ 233,66; débito R$ 714,39; crédito das compras R$ 581,23; diferença R$ 100,50.
"""

from __future__ import annotations

import importlib.util
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app import mocks
from app.config import Configuracao, configuracao
from app.contrato import ClienteB2B, RegimeCompararRequisicao, RegimeCompararResposta
from app.main import app
from tests.apoio_regime import assert_comparacao_fecha

pytestmark = pytest.mark.golden

BACKEND = Path(__file__).resolve().parents[1]
cliente = TestClient(app)


@pytest.fixture(autouse=True)
def modo_real():
    app.dependency_overrides[configuracao] = lambda: Configuracao(modo="real")
    yield
    app.dependency_overrides.clear()


def _gerador() -> Any:
    spec = importlib.util.spec_from_file_location("gerar_mocks", BACKEND / "scripts" / "gerar_mocks.py")
    modulo = importlib.util.module_from_spec(spec)
    sys.modules["gerar_mocks"] = modulo  # os @dataclass do gerador procuram o módulo em sys.modules
    spec.loader.exec_module(modulo)
    return modulo


def _custos(g: Any) -> dict:
    with httpx.Client(timeout=30, trust_env=False) as cli:
        motores = g.Motores(cli)
        atuais: dict = {}
        for nota in g.ler_notas():  # em ordem de emissão: a última nota de cada item vale
            atuais.update(g.custos_da_nota(motores, nota))
    return atuais


def entrada_da_demo() -> dict:
    g = _gerador()
    return g.requisicao_comparar_demo(_custos(g)).model_dump(mode="json")


def cesta_antiga_com_arroz() -> dict:
    """A cesta da E0 a E3: 400 arroz, 1.200 cervejas e 700 chocolates, com o custo da última nota."""
    g = _gerador()
    custos = _custos(g)
    quantidades = {"arroz-5kg": 400, "cerveja-lata": 1200, "chocolate-barra": 700}
    req = RegimeCompararRequisicao(
        **g.operacao_demo(),
        cliente=ClienteB2B(nome="Mercado Bom Preço Ltda (fictício)", regime="regime_regular"),
        itens=[g.item_demo(g.DEMO.item(i), Decimal(q), custos[i]) for i, q in quantidades.items()],
    )
    return req.model_dump(mode="json")


def comparar(corpo: dict) -> RegimeCompararResposta:
    r = cliente.post("/regime/comparar", json=corpo)
    if r.status_code == 503:
        pytest.fail("Motores fora do ar. Suba com: docker compose up -d")
    assert r.status_code == 200, r.text
    return RegimeCompararResposta.model_validate(r.json())


def test_comparacao_real_da_demo_e_o_mock() -> None:
    real = comparar(entrada_da_demo())
    assert real == mocks.carregar().regime_comparar
    assert_comparacao_fecha(real)


def test_demo_sem_item_com_reducao_nao_depende_da_premissa_do_das() -> None:
    c = comparar(entrada_da_demo())
    assert [i.id for i in c.itens] == ["biscoito-pacote", "cerveja-lata", "chocolate-barra"]
    assert all(i.fonteCredito == "nfe" for i in c.itens)  # crédito do grupo IBSCBS da nota 2
    assert "Redução de alíquota dentro do DAS" not in [p.nome for p in c.premissas]
    assert not any("depende dela" in s for s in c.simplificacoes)
    assert c.valorVenda == Decimal("19898.65")
    assert c.tradicional.tributo == Decimal("233.63")
    assert c.hibrido.debito == Decimal("1626.26")
    assert c.hibrido.creditoCompras == Decimal("1266.84")
    assert c.hibrido.tributoLiquido == Decimal("359.42")
    assert c.diferencaCaixa == Decimal("-125.79")  # o híbrido custa caixa à empresa...
    assert c.hibrido.creditoCliente - c.tradicional.creditoCliente == Decimal("1392.63")  # ...e o cliente leva mais
    assert c.empateTradicional is not None
    assert (c.empateTradicional.precoCliente, c.empateTradicional.descontoNecessario) == (
        Decimal("18489.49"),
        Decimal("1409.16"),
    )


def test_cesta_antiga_bate_com_a_referencia_independente_da_e0() -> None:
    c = comparar(cesta_antiga_com_arroz())
    assert_comparacao_fecha(c)
    assert c.valorVenda == Decimal("19901.00")
    assert c.tradicional.tributo == Decimal("233.66")
    assert c.hibrido.debito == Decimal("714.39")
    assert c.hibrido.creditoCompras == Decimal("581.23")
    assert c.hibrido.tributoLiquido == Decimal("133.16")
    assert c.hibrido.precoCliente == Decimal("19901.03")
    assert c.diferencaCaixa == Decimal("100.50")
    assert c.versoes.motorRegimeRegular == "1.7.2" and c.versoes.motorSimplesNacional == "1.0.2"
    # 200003 (cesta básica, redução de 100% no RR): sem débito, e a compra com alíquota zero não gera
    # crédito (LC 214/2025, art. 49). No DAS o arroz paga a alíquota efetiva (premissa a validar), e
    # por isso a comparação imprime que o resultado depende dela.
    arroz = next(i for i in c.itens if i.id == "arroz-5kg")
    assert arroz.debitoHibrido == Decimal("0.00") and arroz.creditoCompras == Decimal("0.00")
    assert arroz.tributoTradicional == Decimal("131.03")
    assert any("depende dela" in s for s in c.simplificacoes)
