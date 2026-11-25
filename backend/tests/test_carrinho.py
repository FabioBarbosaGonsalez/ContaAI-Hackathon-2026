"""E1-02: POST /carrinho/calcular no modo real, com motores falsos (CI).

Os valores dos motores falsos são fictícios (tests/conftest.py). Aqui se testa a orquestração:
estados, margens do ADR 0003, totais, premissas, simulação e falhas. Os números reais são
conferidos em tests/test_carrinho_golden.py, contra os motores em execução.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.contrato import CarrinhoResposta, EstadoItem, FalhaMotorResposta
from app.main import app

cliente = TestClient(app)

AL_2027 = {"cbs": "8.8", "ibsEstadual": "0.05", "ibsMunicipal": "0.05", "impostoSeletivoAdValorem": "10.0"}
DAS = {"anexo": "I", "cAtivSN": "01", "pCBSSN": "1.1612", "pIBSSN": "0.0129"}


def item(id_: str, ncm: str, valor: str, quantidade: str = "10", **extra: Any) -> dict[str, Any]:
    return {
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


def pedido(regime: str, itens: list[dict[str, Any]], data: str = "2027-03-16", **extra: Any) -> dict[str, Any]:
    corpo = {"data": data, "uf": "RS", "municipio": 4314902, "regime": regime, "itens": itens, **extra}
    if data >= "2027" and "aliquotasNominais" not in extra:
        corpo["aliquotasNominais"] = AL_2027
    if regime == "simples_tradicional" and "premissasDas" not in extra:
        corpo["premissasDas"] = DAS
    return corpo


def calcular(corpo: dict[str, Any]) -> CarrinhoResposta:
    r = cliente.post("/carrinho/calcular", json=corpo)
    assert r.status_code == 200, r.text
    assert "X-ContaAI-Mock" not in r.headers  # modo real
    return CarrinhoResposta.model_validate(r.json())


def nomes_premissas(c: CarrinhoResposta) -> list[str]:
    return [p.nome for p in c.premissas]


# ---------------------------------------------------------------------------
# Estados (os 5 do RR e o NAO_CALCULADO do SN)


def test_hibrido_trata_todos_os_estados_do_rr(motores_falsos) -> None:
    motores_falsos.estados_rr = {
        "10000001": "CALCULADO",
        "10000003": "INCONSISTENCIA_ENTRADA",
        "10000004": "NAO_IMPLEMENTADO",
        "10000005": "FALHA_TECNICA",
    }
    itens = [item(f"i{n}", f"1000000{n}", "10.00") for n in range(1, 6)]
    c = calcular(pedido("simples_hibrido", itens))

    estados = {i.id: i.estado for i in c.itens}
    assert estados == {
        "i1": EstadoItem.CALCULADO,
        "i2": EstadoItem.CALCULO_SIMULADO,
        "i3": EstadoItem.INCONSISTENCIA_ENTRADA,
        "i4": EstadoItem.NAO_IMPLEMENTADO,
        "i5": EstadoItem.FALHA_TECNICA,
    }
    for i in c.itens[2:]:
        assert i.precoCliente is None and i.margemPct is None and i.tributos.cbs is None
    erro = c.itens[2].erros[0]
    assert (erro.codigo, erro.campo) == ("REG-011", "#/itens/2/ncm")
    assert "127.0.0.1" not in c.model_dump_json()  # o "type" do erro do motor não passa
    assert c.totais.itensCalculados == 2 and c.totais.itensComErro == 3
    assert c.totais.valorProdutos == Decimal("200.00")


def test_tradicional_trata_nao_calculado_do_sn(motores_falsos) -> None:
    motores_falsos.estados_sn = {"10000002": "NAO_CALCULADO", "10000003": "INCONSISTENCIA_ENTRADA"}
    itens = [item("ok", "10000001", "10.00"), item("nc", "10000002", "10.00"), item("er", "10000003", "10.00")]
    c = calcular(pedido("simples_tradicional", itens))
    assert [i.estado for i in c.itens] == [
        EstadoItem.CALCULADO,
        EstadoItem.NAO_CALCULADO,
        EstadoItem.INCONSISTENCIA_ENTRADA,
    ]
    assert c.itens[1].motivoEstado == "Atividade não vigente (teste)." and c.itens[1].precoCliente is None
    assert [e.codigo for e in c.itens[2].erros] == ["VSN-047"]
    assert all(i.motor == "simples_nacional" for i in c.itens)
    assert motores_falsos.chamadas_de("rr") == []  # sem custo informado, nada vai ao RR


# ---------------------------------------------------------------------------
# Preço, custo e margem (ADR 0003)


def test_hibrido_preco_por_fora_e_margem_sobre_o_preco_ao_cliente(motores_falsos) -> None:
    c = calcular(pedido("simples_hibrido", [item("a", "10000001", "10.00", "10", custoUnitario="6.00")]))
    i = c.itens[0]
    tributo = i.tributos.cbs + i.tributos.ibs
    assert i.valorProdutos == Decimal("100.00")
    assert i.precoCliente == Decimal("100.00") + tributo + (i.tributos.impostoSeletivo or 0)
    assert i.custoEfetivo == Decimal("60.00")  # a CBS/IBS da compra vira crédito
    assert i.margemPct == ((Decimal("100.00") - Decimal("60.00")) / i.precoCliente * 100).quantize(Decimal("0.01"))
    assert c.totais.precoCliente == i.precoCliente
    assert motores_falsos.chamadas_de("rr")[0]["itens"][0]["aliquotasNominais"]["cbs"] == 8.8


def test_tradicional_com_credito_da_nota_entra_no_custo(motores_falsos) -> None:
    linha = item("a", "10000001", "10.00", "10", custoUnitario="6.00", creditoCompraUnitario="0.55")
    i = calcular(pedido("simples_tradicional", [linha])).itens[0]
    tributo = i.tributos.cbs + i.tributos.ibs
    assert i.precoCliente == i.valorProdutos == Decimal("100.00")  # CBS/IBS dentro do DAS
    assert i.custoEfetivo == Decimal("65.50")  # (6,00 + 0,55) × 10
    assert i.margemPct == ((Decimal("100.00") - tributo - Decimal("65.50")) / 100 * 100).quantize(Decimal("0.01"))
    assert motores_falsos.chamadas_de("rr") == []


def test_tradicional_sem_credito_calcula_a_compra_no_rr_e_rotula(motores_falsos) -> None:
    itens = [
        item("a", "10000001", "10.00", "10", custoUnitario="6.00"),
        item("b", "10000002", "10.00", "10", custoUnitario="6.00", creditoCompraUnitario="0.50"),
    ]
    c = calcular(pedido("simples_tradicional", itens))
    compra = motores_falsos.chamadas_de("rr")
    assert len(compra) == 1 and [i["baseCalculo"] for i in compra[0]["itens"]] == [60.0]  # só o item sem crédito
    # Motor falso: CBS 8,8% e IBS 0,05% + 0,05% sobre 60,00 → 5,28 + 0,03 + 0,03
    assert c.itens[0].custoEfetivo == Decimal("60.00") + Decimal("5.28") + Decimal("0.06")
    premissa = next(p for p in c.premissas if p.nome == "Crédito das compras sem valor informado")
    assert "Item a" in premissa.valor and "Item b" not in premissa.valor
    assert c.versoes.motorRegimeRegular == "1.7.2" and c.versoes.motorSimplesNacional == "1.0.2"


def test_custo_ausente_deixa_a_margem_vazia(motores_falsos) -> None:
    i = calcular(pedido("simples_hibrido", [item("a", "10000001", "10.00")])).itens[0]
    assert i.precoCliente is not None and i.custoEfetivo is None and i.margemPct is None


def test_valor_da_linha_arredonda_ao_centavo(motores_falsos) -> None:
    calcular(pedido("simples_hibrido", [item("a", "10000001", "0.333", "3")]))
    assert motores_falsos.chamadas_de("rr")[0]["itens"][0]["baseCalculo"] == 1.0  # 0,999 → 1,00


# ---------------------------------------------------------------------------
# Premissas e simulação (P6, P8)


def test_2027_hibrido_e_simulado_com_premissas_da_requisicao(motores_falsos) -> None:
    c = calcular(pedido("simples_hibrido", [item("a", "10000001", "10.00")]))
    assert c.simulado and c.avisoSimulacao == "Simulação de 2027 com CBS 8,8% assumida"
    nominais = next(p for p in c.premissas if p.nome == "Alíquotas nominais de 2027")
    assert nominais.valor == "CBS 8,8% · IBS estadual 0,05% · IBS municipal 0,05%"
    assert "Não são alíquotas oficiais" in nominais.fonte
    assert "Lote de referência" not in nomes_premissas(c)  # isso era do mock


def test_2026_hibrido_sem_premissa_nao_e_simulado(motores_falsos) -> None:
    motores_falsos.simulado_rr = False
    motores_falsos.estados_rr = {"10000001": "CALCULADO"}
    c = calcular(pedido("simples_hibrido", [item("a", "10000001", "10.00")], data="2026-11-24"))
    assert not c.simulado and c.avisoSimulacao is None
    assert "aliquotasNominais" not in motores_falsos.chamadas_de("rr")[0]["itens"][0]
    assert "Alíquotas de 2026" in nomes_premissas(c)


def test_tradicional_e_sempre_simulado_pela_premissa_do_das(motores_falsos) -> None:
    arroz = item("arroz", "10063021", "27.90", cst="200", cClassTrib="200003")
    c = calcular(pedido("simples_tradicional", [arroz, item("b", "10000001", "5.99")]))
    assert c.simulado
    assert (
        c.avisoSimulacao == "Simulação de 2027 com alíquotas efetivas do Simples assumidas (CBS 1,1612%, IBS 0,0129%)"
    )
    assert {
        "Alíquotas efetivas do Simples (anexo I, atividade 01)",
        "Crédito das compras no Simples tradicional",
    } <= set(nomes_premissas(c))
    reducao = next(p for p in c.premissas if p.nome == "Redução de alíquota dentro do DAS")
    assert "Item arroz" in reducao.valor and "Item b" not in reducao.valor


def test_premissa_do_is_so_aparece_com_item_sujeito_ao_is(motores_falsos) -> None:
    sem_is = calcular(pedido("simples_hibrido", [item("a", "10000001", "10.00")]))
    assert "Alíquota do Imposto Seletivo" not in nomes_premissas(sem_is)
    cerveja = item(
        "cerveja",
        "22030000",
        "3.79",
        impostoSeletivo={"cst": "200", "cClassTrib": "200007", "litrosPorUnidade": "0.35"},
    )
    com_is = calcular(pedido("simples_hibrido", [cerveja]))
    assert "Alíquota do Imposto Seletivo" in nomes_premissas(com_is)
    enviado = motores_falsos.chamadas_de("rr")[-1]["itens"][0]
    assert enviado["unidade"] == "LT" and enviado["quantidade"] == 3.5  # 10 latas × 0,35 L


# ---------------------------------------------------------------------------
# Recusas e falhas


def test_recusa_do_sn_vira_422_com_os_erros_do_motor(motores_falsos) -> None:
    motores_falsos.resposta_sn = (
        422,
        {
            "title": "Erros no processamento do cálculo do Simples Nacional",
            "status": 422,
            "errors": [
                {
                    "type": "http://127.0.0.1/erros?codigo=VSN-015",
                    "title": "Tipo de documento fiscal (tpDoc) não suportado",
                    "code": "VSN-015",
                    "pointer": "#/tpDoc",
                    "detail": "Tipo de documento não suportado pelo cálculo do Simples Nacional, recebido: '55'.",
                }
            ],
        },
    )
    r = cliente.post("/carrinho/calcular", json=pedido("simples_tradicional", [item("a", "1", "1")]))
    # NCM "1" é inválida: o contrato recusa antes de chamar o motor
    assert r.status_code == 422 and motores_falsos.chamadas == []

    r = cliente.post("/carrinho/calcular", json=pedido("simples_tradicional", [item("a", "10000001", "10.00")]))
    assert r.status_code == 422
    falha = FalhaMotorResposta.model_validate(r.json())
    assert falha.motor == "simples_nacional" and [e.codigo for e in falha.erros] == ["VSN-015"]
    assert "127.0.0.1" not in r.text and "sn.interno" not in r.text


@pytest.mark.parametrize(("status_motor", "status_api"), [(500, 503), (400, 502)])
def test_falha_do_motor_nao_expoe_detalhe_interno(motores_falsos, status_motor: int, status_api: int) -> None:
    motores_falsos.resposta_rr = (status_motor, {"detail": "java.lang.NullPointerException em rr.interno"})
    r = cliente.post("/carrinho/calcular", json=pedido("simples_hibrido", [item("a", "10000001", "10.00")]))
    assert r.status_code == status_api
    assert FalhaMotorResposta.model_validate(r.json()).motor == "regime_regular"
    assert "java" not in r.text and "interno" not in r.text


@pytest.mark.parametrize(
    ("itens", "trecho"),
    [
        (
            [{**item("e", "10000001", "1200"), "ncm": None, "nbs": "122011200"}],
            "serviço (NBS) no Simples tradicional",
        ),
        (
            [item("c", "22030000", "3.79", impostoSeletivo={"cst": "000", "cClassTrib": "000001"})],
            "Imposto Seletivo com incidência",
        ),
        ([item("a", "10000001", "1"), item("a", "10000002", "1")], "id único"),
    ],
)
def test_tradicional_recusa_o_que_ainda_nao_trata(motores_falsos, itens, trecho: str) -> None:
    r = cliente.post("/carrinho/calcular", json=pedido("simples_tradicional", itens))
    assert r.status_code == 422 and trecho in r.text
    assert motores_falsos.chamadas == []


@pytest.mark.parametrize(
    ("rota", "corpo"),
    [
        (
            "/carrinho/calcular",
            lambda: pedido("simples_tradicional", [item("a", "10000001", "10.00")], data="2026-11-25"),
        ),
        (
            "/item/preco-alvo",
            lambda: {
                **{k: v for k, v in pedido("simples_tradicional", [], data="2026-11-25").items() if k != "itens"},
                "item": {
                    k: v for k, v in item("a", "10000001", "10.00").items() if k not in ("quantidade", "valorUnitario")
                },
                "custoUnitario": "6.00",
                "margemAlvoPct": "20",
            },
        ),
        (
            "/explicar",
            lambda: {
                **{k: v for k, v in pedido("simples_tradicional", [], data="2026-11-25").items() if k != "itens"},
                "item": item("a", "10000001", "10.00"),
            },
        ),
    ],
)
def test_tradicional_antes_de_2027_e_recusado_com_mensagem_clara(motores_falsos, rota: str, corpo) -> None:
    r = cliente.post(rota, json=corpo())
    assert r.status_code == 422 and "só é calculado a partir de 2027" in r.text and "VSN-015" in r.text
    assert motores_falsos.chamadas == []  # recusa antes de chamar o motor


def test_hibrido_em_2026_continua_calculando(motores_falsos) -> None:
    c = calcular(pedido("simples_hibrido", [item("a", "10000001", "10.00")], data="2026-11-25"))
    assert c.itens[0].precoCliente is not None


def test_modo_mock_continua_servindo_o_mock() -> None:
    corpo = pedido("simples_hibrido", [item("a", "10000001", "10.00")])
    r = cliente.post("/carrinho/calcular", json=corpo)
    assert r.status_code == 200 and r.headers["X-ContaAI-Mock"] == "1"
