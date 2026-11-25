"""E1-03: POST /item/preco-alvo no modo real, com motores falsos (CI).

Valores fictícios (tests/conftest.py). Aqui se confere o método: 3 avaliações no ajuste afim,
bisseção quando o tributo não é linear, o critério "menor preço em centavos com margem ≥ alvo",
as recusas e o cache. Os números reais estão em tests/test_preco_alvo_golden.py.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import pytest
from conftest import cbs_linear
from fastapi.testclient import TestClient

from app.contrato import PrecoAlvoRequisicao, PrecoAlvoResposta, ProblemaCalculo
from app.main import app
from app.precificacao.preco_alvo import MAX_AVALIACOES, Avaliador, CalculoRecusado

cliente = TestClient(app)
C2 = Decimal("0.01")
DAS = {"anexo": "I", "cAtivSN": "01", "pCBSSN": "1.1612", "pIBSSN": "0.0129"}
CHOCOLATE = {
    "id": "chocolate",
    "descricao": "Chocolate",
    "ncm": "18063210",
    "cst": "000",
    "cClassTrib": "000001",
    "unidade": "UN",
}


def pedido(regime: str, custo: str = "4.10", margem: str = "20", **extra: Any) -> dict[str, Any]:
    corpo = {
        "data": "2027-03-16",
        "uf": "RS",
        "municipio": 4314902,
        "aliquotasNominais": {"cbs": "8.8", "ibsEstadual": "0.05", "ibsMunicipal": "0.05"},
        "regime": regime,
        "item": CHOCOLATE,
        "custoUnitario": custo,
        "margemAlvoPct": margem,
        **extra,
    }
    if regime == "simples_tradicional":
        corpo.setdefault("premissasDas", DAS)
    return corpo


def calcular(corpo: dict[str, Any]) -> PrecoAlvoResposta:
    r = cliente.post("/item/preco-alvo", json=corpo)
    assert r.status_code == 200, r.text
    assert "X-ContaAI-Mock" not in r.headers
    return PrecoAlvoResposta.model_validate(r.json())


def centavos(valor: Decimal) -> Decimal:
    return valor.quantize(C2, ROUND_HALF_UP)


# Réplica do motor falso, para conferir o critério por força bruta.
def tributo_rr(x: Decimal, cbs_de: Callable[[Decimal], Decimal] = cbs_linear) -> Decimal:
    base = centavos(100 * x)
    return (centavos(cbs_de(base)) + 2 * centavos(base * Decimal("0.0005"))) / 100


def tributo_sn(x: Decimal) -> Decimal:
    base = centavos(100 * x)
    return (centavos(base * Decimal("1.1612") / 100) + centavos(base * Decimal("0.0129") / 100)) / 100


def margem_hibrido(x: Decimal, custo: Decimal, cbs_de=cbs_linear) -> Decimal:
    return (x - custo) / (x + tributo_rr(x, cbs_de))


def margem_tradicional(x: Decimal, custo: Decimal) -> Decimal:
    return (x - tributo_sn(x) - custo) / x


def assert_menor_centavo(preco: Decimal, margem: Callable[[Decimal], Decimal], alvo: Decimal) -> None:
    assert margem(preco) >= alvo
    assert margem(preco - C2) < alvo, "um centavo a menos ainda atinge a margem: não é o menor preço"


# ---------------------------------------------------------------------------
# Ajuste afim: 3 avaliações nos itens lineares (critério de saída da E1)


def test_hibrido_linear_converge_em_3_avaliacoes_no_menor_centavo(motores_falsos) -> None:
    r = calcular(pedido("simples_hibrido"))
    assert (r.metodo, r.chamadas, r.loteReferencia) == ("afim", 3, 100)
    custo = Decimal("4.10")
    assert r.custoEfetivoUnitario == custo
    assert_menor_centavo(r.valorUnitario, lambda x: margem_hibrido(x, custo), Decimal("0.20"))
    assert r.precoCliente == r.valorUnitario + tributo_rr(r.valorUnitario)
    assert r.margemObtidaPct >= r.margemAlvoPct
    assert len(motores_falsos.chamadas_de("rr")) == 3


def test_tradicional_linear_converge_em_3_avaliacoes_no_menor_centavo(motores_falsos) -> None:
    r = calcular(pedido("simples_tradicional", creditoCompraUnitario="0.36"))
    custo = Decimal("4.46")  # custo + CBS/IBS da compra (não aproveitada no Simples)
    assert (r.metodo, r.chamadas) == ("afim", 3) and r.custoEfetivoUnitario == custo
    assert r.precoCliente == r.valorUnitario  # CBS/IBS dentro do DAS
    assert_menor_centavo(r.valorUnitario, lambda x: margem_tradicional(x, custo), Decimal("0.20"))
    assert motores_falsos.chamadas_de("rr") == [] and len(motores_falsos.chamadas_de("sn")) == 3


def test_tradicional_sem_credito_calcula_a_compra_no_rr_e_rotula(motores_falsos) -> None:
    r = calcular(pedido("simples_tradicional"))
    # Motor falso sobre o lote de 100 a R$ 4,10: CBS 36,08 + IBS 0,21 + 0,21 → 0,365 por unidade
    assert r.custoEfetivoUnitario == Decimal("4.10") + Decimal("0.365")
    assert len(motores_falsos.chamadas_de("rr")) == 1 and r.chamadas == 3  # a compra não conta no método
    assert "Crédito das compras sem valor informado" in [p.nome for p in r.premissas]


def test_custo_zero_nao_quebra_a_reta(motores_falsos) -> None:
    r = calcular(pedido("simples_hibrido", custo="0"))
    assert r.metodo == "afim" and r.valorUnitario == Decimal("0.01")


# ---------------------------------------------------------------------------
# Bisseção de reserva


def degrau(base: Decimal) -> Decimal:
    """CBS fictícia não linear: 8,8% até R$ 1.500 por lote, 90% acima."""
    return base * (Decimal("0.088") if base <= 1500 else Decimal("0.9"))


def test_tributo_nao_linear_cai_na_bisseccao_e_acha_o_menor_centavo(motores_falsos) -> None:
    motores_falsos.cbs_rr = degrau
    r = calcular(pedido("simples_hibrido", custo="10.00"))
    assert r.metodo == "bissecao" and 3 < r.chamadas <= MAX_AVALIACOES
    custo = Decimal("10.00")
    assert_menor_centavo(r.valorUnitario, lambda x: margem_hibrido(x, custo, degrau), Decimal("0.20"))


def test_limite_de_avaliacoes() -> None:
    req = PrecoAlvoRequisicao.model_validate(pedido("simples_hibrido"))
    avaliar = Avaliador(motores=None, req=req)  # type: ignore[arg-type]
    avaliar.avaliacoes = MAX_AVALIACOES
    with pytest.raises(CalculoRecusado, match="não convergiu"):
        asyncio.run(avaliar(Decimal("5.00")))


# ---------------------------------------------------------------------------
# Recusas


def test_margem_impossivel(motores_falsos) -> None:
    r = cliente.post("/item/preco-alvo", json=pedido("simples_tradicional", margem="99.5", creditoCompraUnitario="0"))
    assert r.status_code == 422
    recusado = ProblemaCalculo.model_validate(r.json())
    assert recusado.type == "/problemas/calculo-recusado" and "Margem impossível" in recusado.detail


def test_item_que_o_motor_nao_calcula_volta_com_os_erros(motores_falsos) -> None:
    motores_falsos.estados_rr = {"18063210": "INCONSISTENCIA_ENTRADA"}
    r = cliente.post("/item/preco-alvo", json=pedido("simples_hibrido"))
    assert r.status_code == 422
    recusa = ProblemaCalculo.model_validate(r.json())
    assert "INCONSISTENCIA_ENTRADA" in recusa.detail and [e.codigo for e in recusa.erros] == ["REG-011"]
    assert "127.0.0.1" not in r.text and len(motores_falsos.chamadas_de("rr")) == 1


@pytest.mark.parametrize(
    ("extra", "trecho"),
    [
        ({"premissasDas": None}, "premissasDas"),
        ({"item": {**CHOCOLATE, "impostoSeletivo": {"cst": "000", "cClassTrib": "000001"}}}, "Imposto Seletivo"),
    ],
)
def test_tradicional_recusa_entrada_incompleta_ou_nao_suportada(motores_falsos, extra, trecho: str) -> None:
    corpo = {**pedido("simples_tradicional"), **extra}
    r = cliente.post("/item/preco-alvo", json=corpo)
    assert r.status_code == 422 and trecho in r.text and motores_falsos.chamadas == []


# ---------------------------------------------------------------------------
# Cache e premissas


def test_mesmo_pedido_vem_do_cache_e_conta_as_mesmas_avaliacoes(motores_falsos) -> None:
    primeiro = calcular(pedido("simples_hibrido"))
    chamadas_http = len(motores_falsos.chamadas)
    segundo = calcular(pedido("simples_hibrido"))
    assert len(motores_falsos.chamadas) == chamadas_http  # nada novo foi ao motor
    assert segundo == primeiro and segundo.chamadas == 3
    assert motores_falsos.cache.acertos >= 3


def test_rotulo_do_preset_vai_para_a_premissa(motores_falsos) -> None:
    al = {"cbs": "11.3", "ibsEstadual": "0.05", "ibsMunicipal": "0.05", "fonte": "Referência do TCU (teste)"}
    r = calcular(pedido("simples_hibrido", aliquotasNominais=al))
    nominais = next(p for p in r.premissas if p.nome == "Alíquotas nominais de 2027")
    assert nominais.fonte.startswith("Referência do TCU (teste).") and "Não são alíquotas oficiais" in nominais.fonte
    assert r.simulado and r.avisoSimulacao == "Simulação de 2027 com CBS 11,3% assumida"
    assert "Método do preço-alvo" in [p.nome for p in r.premissas]
