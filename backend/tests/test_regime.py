"""E3: POST /regime/comparar no modo real, com motores falsos (CI).

Os valores dos motores falsos são fictícios (tests/conftest.py). Aqui se testa a orquestração: as
contas do ADR 0003 fecham, o crédito das compras vem da fonte certa, as recusas são claras e nada
interno vaza. Os números reais são conferidos em tests/test_regime_golden.py, contra os motores.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app import main
from app.contrato import FalhaMotorResposta, RecusaCalculo, RegimeCompararResposta
from app.main import app
from app.seguranca import LimitadorPorIp
from tests.apoio_regime import assert_comparacao_fecha

cliente = TestClient(app)

AL_2027 = {"cbs": "8.8", "ibsEstadual": "0.05", "ibsMunicipal": "0.05"}
DAS = {"anexo": "I", "cAtivSN": "01", "pCBSSN": "1.1612", "pIBSSN": "0.0129"}


def item(id_: str, ncm: str, valor: str, custo: str | None, quantidade: str = "10", **extra: Any) -> dict[str, Any]:
    corpo = {
        "id": id_,
        "descricao": f"Item {id_}",
        "ncm": ncm,
        "cst": "000",
        "cClassTrib": "000001",
        "unidade": "UN",
        "quantidade": quantidade,
        "valorUnitario": valor,
        **extra,
    }
    if custo is not None:
        corpo["custoUnitario"] = custo
    return corpo


def pedido(itens: list[dict[str, Any]], data: str = "2027-03-16", **extra: Any) -> dict[str, Any]:
    corpo: dict[str, Any] = {
        "data": data,
        "uf": "RS",
        "municipio": 4314902,
        "cliente": {"nome": "Cliente fictício", "regime": "regime_regular"},
        "premissasDas": DAS,
        "itens": itens,
        **extra,
    }
    if data >= "2027":
        corpo.setdefault("aliquotasNominais", AL_2027)
    return corpo


def comparar(corpo: dict[str, Any]) -> RegimeCompararResposta:
    r = cliente.post("/regime/comparar", json=corpo)
    assert r.status_code == 200, r.text
    assert "X-ContaAI-Mock" not in r.headers  # modo real
    return RegimeCompararResposta.model_validate(r.json())


VENDA = [
    item("nota", "10000001", "10.00", "6.00", creditoCompraUnitario="0.50"),
    item("motor", "10000002", "20.00", "6.00"),
    item("zero", "10000003", "5.00", "0"),
]


def test_contas_fecham_e_cada_credito_tem_a_sua_fonte(motores_falsos) -> None:
    c = comparar(pedido(VENDA))
    assert_comparacao_fecha(c)
    fontes = {i.id: (i.fonteCredito, i.creditoCompras) for i in c.itens}
    # nota: 10 × 0,50; motor: RR falso sobre 60,00 (CBS 5,28 + IBS 0,03 + 0,03); zero: custo 0.
    assert fontes == {
        "nota": ("nfe", Decimal("5.00")),
        "motor": ("motor", Decimal("5.34")),
        "zero": ("custo_zero", Decimal("0.00")),
    }
    assert c.fonteTradicional == "motor" and c.data.isoformat() == "2027-03-16"
    nomes = [p.nome for p in c.premissas]
    assert "Crédito das compras sem valor informado" in nomes and "Item motor" in str(c.premissas)
    assert {"Crédito das compras no Simples híbrido", "Opção pelo Simples híbrido"} <= set(nomes)
    assert nomes[-1] == "ICMS"
    assert c.avisoSimulacao == (
        "Simulação de 2027 com CBS 8,8% assumida e alíquotas efetivas do Simples assumidas (CBS 1,1612%, IBS 0,0129%)"
    )


def test_tradicional_e_o_que_o_motor_sn_devolve(motores_falsos) -> None:
    c = comparar(pedido(VENDA))
    linhas_sn = motores_falsos.chamadas_de("sn")[0]["itens"]
    assert [Decimal(str(i["baseCalculo"])) for i in linhas_sn] == [i.valorVenda for i in c.itens]
    # SN falso: 1,1612% + 0,0129% sobre 100,00 = 1,16 + 0,01.
    assert c.itens[0].tributoTradicional == Decimal("1.17")
    assert c.tradicional.creditoCliente == c.tradicional.tributo  # LC 214, art. 47, §9º, II


def test_chamadas_aos_motores_no_caso_linear(motores_falsos) -> None:
    c = comparar(pedido(VENDA))
    assert len(motores_falsos.chamadas_de("sn")) == 3  # venda, e 2 avaliações do preço de empate
    assert c.empateTradicional is not None and c.empateTradicional.descontoNecessario > 0
    # Híbrido: venda, 2 × venda, confirmação; mais 1 lote para o crédito pelo motor.
    assert len(motores_falsos.chamadas_de("rr")) == 4


def test_sem_credito_pelo_motor_nao_ha_lote_de_compra(motores_falsos) -> None:
    comparar(pedido([VENDA[0], VENDA[2]]))
    assert len(motores_falsos.chamadas_de("rr")) == 3


def test_motor_nao_linear_refina_e_fecha_o_preco(motores_falsos) -> None:
    motores_falsos.cbs_rr = lambda base: base * Decimal("0.088") + base * base / Decimal(20000)
    c = comparar(pedido([item("a", "10000001", "100.00", "50.00")]))
    assert_comparacao_fecha(c)
    assert len(motores_falsos.chamadas_de("rr")) > 4  # a primeira confirmação não fechou
    assert abs(c.diferencaPrecoCliente) <= Decimal("0.05")


def test_reducao_vira_simplificacao_que_condiciona_o_resultado(motores_falsos) -> None:
    arroz = item("arroz", "10063021", "27.90", "20.00", cst="200", cClassTrib="200003")
    c = comparar(pedido([arroz]))
    assert c.itens[0].debitoHibrido == Decimal("0.00") and c.itens[0].tributoTradicional > 0
    assert any("depende dela" in s and "Item arroz" in s for s in c.simplificacoes)


def test_is_na_revenda_fica_fora_do_credito_e_vira_premissa(motores_falsos) -> None:
    cerveja = item("cerveja", "22030000", "3.79", "2.60", impostoSeletivo={"cst": "200", "cClassTrib": "200007"})
    c = comparar(pedido([cerveja], aliquotasNominais={**AL_2027, "impostoSeletivoAdValorem": "10"}))
    assert c.hibrido.impostoSeletivo == Decimal("0.00") and c.hibrido.creditoCliente == c.hibrido.debito
    assert "Imposto Seletivo fora do crédito do cliente" in [p.nome for p in c.premissas]


# ---------------------------------------------------------------------------
# Recusas


def test_item_que_o_rr_nao_calcula_recusa_a_comparacao(motores_falsos) -> None:
    motores_falsos.estados_rr = {"10000002": "INCONSISTENCIA_ENTRADA"}
    r = cliente.post("/regime/comparar", json=pedido(VENDA))
    assert r.status_code == 422
    corpo = RecusaCalculo.model_validate(r.json())
    assert "motor" in corpo.detail and [e.codigo for e in corpo.erros] == ["REG-011"]
    assert "127.0.0.1" not in r.text


def test_item_que_o_sn_nao_calcula_recusa_a_comparacao(motores_falsos) -> None:
    motores_falsos.estados_sn = {"10000001": "NAO_CALCULADO"}
    r = cliente.post("/regime/comparar", json=pedido(VENDA))
    assert r.status_code == 422 and "Atividade não vigente" in r.json()["detail"]
    assert motores_falsos.chamadas_de("rr") == []  # recusa antes de gastar chamadas no RR


@pytest.mark.parametrize(
    ("corpo", "trecho"),
    [
        (pedido(VENDA, data="2026-11-25"), "começa em 2027"),
        (pedido([item("a", "10000001", "10.00", None)]), "custoUnitario"),
        (pedido([VENDA[0], VENDA[0]]), "id único"),
        (
            pedido([{**item("s", "10000001", "10.00", "1.00"), "ncm": None, "nbs": "122011200"}]),
            "serviço (NBS)",
        ),
        (
            pedido([item("is", "22030000", "3.79", "2.60", impostoSeletivo={"cst": "000", "cClassTrib": "000001"})]),
            "Imposto Seletivo com incidência",
        ),
        ({k: v for k, v in pedido(VENDA).items() if k != "premissasDas"}, "premissasDas"),
    ],
)
def test_validacao_da_entrada(motores_falsos, corpo: dict[str, Any], trecho: str) -> None:
    r = cliente.post("/regime/comparar", json=corpo)
    assert r.status_code == 422 and trecho in r.text
    assert motores_falsos.chamadas == []


def test_falha_do_motor_nao_expoe_detalhe_interno(motores_falsos) -> None:
    motores_falsos.resposta_rr = (500, {"detail": "stack em http://127.0.0.1/interno"})
    r = cliente.post("/regime/comparar", json=pedido(VENDA))
    assert r.status_code == 503
    assert FalhaMotorResposta.model_validate(r.json()).motor == "regime_regular"
    assert "127.0.0.1" not in r.text and "rr.interno" not in r.text


def test_comparar_tem_limite_por_ip(motores_falsos, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main, "LIMITE_GERAL", LimitadorPorIp(1))
    assert cliente.post("/regime/comparar", json=pedido(VENDA)).status_code == 200
    assert cliente.post("/regime/comparar", json=pedido(VENDA)).status_code == 429


def test_empate_some_se_o_sn_nao_calcula_o_dobro(motores_falsos) -> None:
    """O empate é opcional: se o SN não calcula o ponto 2 × venda, a comparação sai sem ele."""
    original = motores_falsos.handler
    chamadas_sn = {"n": 0}

    def sn_falha_no_dobro(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("simples-nacional/nao-assistido"):
            chamadas_sn["n"] += 1
            motores_falsos.estados_sn = {"10000001": "NAO_CALCULADO"} if chamadas_sn["n"] == 2 else {}
        return original(request)

    motores_falsos.handler = sn_falha_no_dobro  # type: ignore[method-assign]
    c = comparar(pedido([VENDA[0]]))
    assert c.empateTradicional is None and c.tradicional.tributo > 0


def test_modo_mock_continua_servindo_o_mock() -> None:
    r = cliente.post("/regime/comparar", json=pedido(VENDA))
    assert r.status_code == 200 and r.headers["X-ContaAI-Mock"] == "1"
