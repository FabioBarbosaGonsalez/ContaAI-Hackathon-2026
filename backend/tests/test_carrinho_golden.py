"""E1-02 contra os motores em execução (marcador golden: make golden / uv run pytest -m golden).

1. A rota real reproduz os números publicados no exemplo oficial (docs/exemplos.md da calculadora
   RR 1.7.2) e na resposta gravada do motor SN, que estão em tests/golden/.
2. Com a entrada da demonstração, a rota real devolve os mesmos números dos mocks, que vieram da
   implementação de referência (scripts/gerar_mocks.py). O front pode trocar mock por real.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app import mocks
from app.config import Configuracao, configuracao
from app.contrato import CarrinhoResposta, EstadoItem, Regime
from app.dados_demo import carregar_distribuidora
from app.main import app

pytestmark = pytest.mark.golden

BACKEND = Path(__file__).resolve().parents[1]
GOLDEN = BACKEND / "tests" / "golden"
DEMO = carregar_distribuidora()
cliente = TestClient(app)

AL = {"cbs": "8.8", "ibsEstadual": "0.05", "ibsMunicipal": "0.05"}


@pytest.fixture(autouse=True)
def modo_real():
    app.dependency_overrides[configuracao] = lambda: Configuracao(modo="real")
    yield
    app.dependency_overrides.clear()


def calcular(corpo: dict[str, Any]) -> CarrinhoResposta:
    r = cliente.post("/carrinho/calcular", json=corpo)
    if r.status_code == 503:
        pytest.fail("Motores fora do ar. Suba com: docker compose up -d")
    assert r.status_code == 200, r.text
    return CarrinhoResposta.model_validate(r.json())


def linha(id_: str, valor: str, quantidade: str, unidade: str, **classificacao: Any) -> dict[str, Any]:
    return {
        "id": id_,
        "descricao": id_,
        "unidade": unidade,
        "quantidade": quantidade,
        "valorUnitario": valor,
        **classificacao,
    }


# ---------------------------------------------------------------------------
# 1. Referência oficial


def test_hibrido_bate_com_o_exemplo_oficial() -> None:
    entrada = json.loads((GOLDEN / "rr-operacao-exemplo-oficial.json").read_text(encoding="utf-8"))
    gravado = json.loads((GOLDEN / "rr-exemplo-oficial.resposta.json").read_text(encoding="utf-8"))["corpo"]
    assert entrada["dhFatoGerador"].startswith("2027-03-10")
    # Mesmos itens, bases e quantidades da entrada oficial. A cerveja do exemplo tem o IS informado
    # (impostoInformado 15,00); aqui o motor calcula com a alíquota ad valorem 10% da mesma entrada.
    itens = [
        linha("arroz", "5.00", "20", "KG", ncm="10063021", cst="200", cClassTrib="200003"),
        linha(
            "cerveja",
            "12.50",
            "12",
            "LT",
            ncm="22030000",
            cst="000",
            cClassTrib="000001",
            impostoSeletivo={"cst": "000", "cClassTrib": "000001"},
        ),
        linha("educacao", "1200.00", "1", "UN", nbs="122011200", cst="200", cClassTrib="200028"),
        linha("carne", "80.00", "1", "KG", ncm="02013000", cst="200", cClassTrib="200035"),
    ]
    c = calcular(
        {
            "data": "2027-03-10",
            "uf": "RS",
            "municipio": 4314902,
            "regime": "simples_hibrido",
            "aliquotasNominais": {**AL, "impostoSeletivoAdValorem": "10.0"},
            "itens": itens,
        }
    )
    arroz, cerveja, educacao, carne = c.itens
    assert educacao.estado == EstadoItem.CALCULO_SIMULADO
    assert (educacao.tributos.cbs, educacao.tributos.ibs) == (Decimal("42.24"), Decimal("0.48"))
    assert educacao.aliquotaEfetiva.cbs == Decimal("3.52") and educacao.reducaoPct == Decimal("60.00")
    assert (arroz.tributos.cbs, arroz.tributos.ibs, arroz.reducaoPct) == (
        Decimal("0.00"),
        Decimal("0.00"),
        Decimal("100.00"),
    )
    assert (cerveja.tributos.cbs, cerveja.tributos.ibs, cerveja.tributos.impostoSeletivo) == (
        Decimal("14.52"),
        Decimal("0.16"),
        Decimal("15.00"),
    )
    assert carne.estado == EstadoItem.INCONSISTENCIA_ENTRADA
    assert [(e.codigo, e.campo) for e in carne.erros] == [("REG-011", "#/itens/3/ncm")]

    total = gravado["total"]["tribCalc"]
    assert c.totais.tributos.cbs == Decimal(total["IBSCBSTot"]["gCBS"]["vCBS"])  # 56,76
    assert c.totais.tributos.ibs == Decimal(total["IBSCBSTot"]["gIBS"]["vIBS"])  # 0,64
    assert c.totais.tributos.impostoSeletivo == Decimal(total["ISTot"]["vIS"])  # 15,00
    assert c.simulado and c.totais.itensComErro == 1
    assert c.versoes.motorRegimeRegular == "1.7.2" and c.versoes.banco == "V0073"


def test_tradicional_bate_com_a_resposta_gravada_do_sn() -> None:
    entrada = json.loads((GOLDEN / "sn-operacao-nao-assistido-anexo-i.json").read_text(encoding="utf-8"))
    das = entrada["aliquotasEfetivas"]["anexoI"]
    c = calcular(
        {
            "data": entrada["data"],
            "uf": "RS",
            "municipio": 4314902,
            "regime": "simples_tradicional",
            "aliquotasNominais": AL,
            "premissasDas": {"anexo": "I", "cAtivSN": "01", **das},
            "itens": [
                linha("arroz", "100.00", "1", "UN", ncm="10063021", cst="200", cClassTrib="200003"),
                linha("carne", "80.00", "1", "KG", ncm="02013000", cst="200", cClassTrib="200035"),
            ],
        }
    )
    arroz, carne = c.itens
    assert (arroz.tributos.cbs, arroz.tributos.ibs) == (Decimal("1.16"), Decimal("0.01"))  # gravado, item 1
    assert arroz.precoCliente == Decimal("100.00") and arroz.motor == "simples_nacional"
    assert [e.codigo for e in carne.erros] == ["VSN-047"]


def test_sn_recusa_2026_e_a_api_repassa() -> None:
    r = cliente.post(
        "/carrinho/calcular",
        json={
            "data": "2026-11-24",
            "uf": "RS",
            "municipio": 4314902,
            "regime": "simples_tradicional",
            "premissasDas": {"anexo": "I", "cAtivSN": "01", "pCBSSN": "1.1612", "pIBSSN": "0.0129"},
            "itens": [linha("c", "5.99", "1", "UN", ncm="18063210", cst="000", cClassTrib="000001")],
        },
    )
    assert r.status_code == 422 and r.json()["erros"][0]["codigo"] == "VSN-015"
    assert "127.0.0.1" not in r.text


def test_2026_hibrido_usa_a_referencia_do_motor_e_nao_e_simulado() -> None:
    c = calcular(
        {
            "data": "2026-11-24",
            "uf": "RS",
            "municipio": 4314902,
            "regime": "simples_hibrido",
            "itens": [linha("c", "10.00", "10", "UN", ncm="18063210", cst="000", cClassTrib="000001")],
        }
    )
    assert c.itens[0].estado == EstadoItem.CALCULADO and not c.simulado and c.avisoSimulacao is None


# ---------------------------------------------------------------------------
# 2. Demonstração: real = mock


def _gerador():
    spec = importlib.util.spec_from_file_location("gerar_mocks", BACKEND / "scripts" / "gerar_mocks.py")
    modulo = importlib.util.module_from_spec(spec)
    sys.modules["gerar_mocks"] = modulo  # os @dataclass do gerador procuram o módulo em sys.modules
    spec.loader.exec_module(modulo)
    return modulo


def entrada_da_demo(regime: Regime) -> dict[str, Any]:
    """Catálogo com 100 unidades por item e o custo da última nota, como o gerador de mocks."""
    g = _gerador()
    custo: dict[str, tuple[Decimal, Decimal | None]] = {}
    for nota in g.ler_notas():  # em ordem de emissão: a última nota de cada item vale
        for item_nota in nota.itens:
            cat = g.casar(item_nota)
            if cat is not None:
                credito = None if item_nota.cbsIbs is None else (item_nota.cbsIbs / item_nota.qCom).quantize(g.C4)
                custo[cat.id] = (item_nota.vUnCom, credito)
    cen = DEMO.cenario
    itens = []
    for cat in DEMO.catalogo:
        linha_cat = {
            "id": cat.id,
            "descricao": cat.descricao,
            "ncm": cat.ncm,
            "cst": cat.cst,
            "cClassTrib": cat.cClassTrib,
            "impostoSeletivo": cat.impostoSeletivo.model_dump(exclude={"motivo"}, mode="json")
            if cat.impostoSeletivo
            else None,
            "unidade": cat.unidade,
            "quantidade": "100",
            "valorUnitario": str(cat.precoVenda),
        }
        if cat.id in custo:
            linha_cat["custoUnitario"] = str(custo[cat.id][0])
            if custo[cat.id][1] is not None:
                linha_cat["creditoCompraUnitario"] = str(custo[cat.id][1])
        itens.append(linha_cat)
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
        "itens": itens,
    }


@pytest.mark.parametrize("regime", list(Regime))
def test_carrinho_real_da_demo_bate_com_o_mock(regime: Regime) -> None:
    real = calcular(entrada_da_demo(regime))
    mock = mocks.carregar().carrinho[regime]
    campos = {"id", "estado", "tributos", "reducaoPct", "aliquotaEfetiva", "valorProdutos", "precoCliente"}
    campos |= {"custoEfetivo", "margemPct", "memoria", "erros"}
    for r, m in zip(real.itens, mock.itens, strict=True):
        assert r.model_dump(include=campos) == m.model_dump(include=campos), r.id
    assert real.totais == mock.totais
    assert real.simulado == mock.simulado and real.avisoSimulacao == mock.avisoSimulacao
