"""Verificador anti-alucinação (E2-06): todo R$ e % da resposta precisa estar nas fontes."""

from __future__ import annotations

from decimal import Decimal

from app.agente.verificador import leituras, numeros_das_fontes, verificar

FONTE = {
    "itens": [{"tributos": {"cbs": "33.35", "ibs": "0.38"}, "precoCliente": "1234.50", "margemPct": "15.02"}],
    "aliquotaEfetiva": {"cbs": "1.1612"},
    "memoria": {"cbs": "Base de R$ 2.790,00 com alíquota efetiva de 1,1612%."},
}


def test_leituras_pt_br_e_ponto() -> None:
    assert leituras("1.234,50") == {Decimal("1234.50")}
    assert leituras("27.90") == {Decimal("27.90")}
    assert leituras("1.234") == {Decimal("1234"), Decimal("1.234")}
    assert leituras("15") == {Decimal("15")}


def test_numeros_das_fontes_incluem_os_textos_de_memoria() -> None:
    numeros = numeros_das_fontes([FONTE])
    assert {Decimal("2790.00"), Decimal("1.1612"), Decimal("33.35"), Decimal("1234.50")} <= numeros


def test_aprova_numeros_copiados_em_qualquer_formato() -> None:
    texto = "CBS R$ 33,35 e IBS R$ 0,38; preço R$ 1.234,50, margem de 15,02%. Base R$ 2.790,00; alíquota 1,1612%."
    assert verificar(texto, [FONTE]).aprovada
    assert verificar("Preço R$ 1234.50", [FONTE]).aprovada


def test_aceita_arredondamento_para_as_casas_citadas() -> None:
    assert verificar("alíquota efetiva de 1,16%", [FONTE]).aprovada
    assert verificar("margem de 15,0%", [FONTE]).aprovada


def test_recusa_numero_inventado() -> None:
    v = verificar("A CBS é de 50% e o preço sobe para R$ 40,00.", [FONTE])
    assert not v.aprovada
    assert v.sem_fonte == ["50%", "R$ 40,00"]


def test_arredondar_para_inteiro_nao_vale() -> None:
    # "15%" a partir de 15,02% esconderia a casa decimal; só vale com ao menos uma casa.
    assert not verificar("margem de 15%", [FONTE]).aprovada


def test_numero_sem_r_ou_porcento_nao_e_conferido() -> None:
    assert verificar("NCM 22030000, cClassTrib 200007, ano 2027, art. 47.", [FONTE]).aprovada


def test_por_cento_por_extenso_e_pontos_percentuais() -> None:
    assert not verificar("sobe 12 por cento", [FONTE]).aprovada
    assert not verificar("caiu 3 p.p.", [FONTE]).aprovada


def test_recusa_recomendacao_de_regime() -> None:
    v = verificar("Opte pelo híbrido: vale mais a pena.", [FONTE])
    assert not v.aprovada and v.proibidas
    assert not verificar("Recomendo que você mude para o regime híbrido.", [FONTE]).aprovada
    assert verificar("Valide a decisão de regime com o seu contador.", [FONTE]).aprovada


def test_sem_fontes_nenhum_valor_passa() -> None:
    assert not verificar("Custa R$ 1,00.", []).aprovada
    assert verificar("Sem valores.", []).aprovada


def test_decimal_com_quatro_casas_nao_vira_milhar() -> None:
    # Regressão: "5.5758" era lido como "5.575" (milhar) + "8".
    assert verificar("preço ao cliente R$ 5,5758", [{"precoCliente": "5.5758"}]).aprovada
    assert verificar("preço ao cliente R$ 5,58", [{"precoCliente": "5.5758"}]).aprovada
