"""Leitura das respostas dos motores e montagem das requisições, contra as respostas oficiais gravadas."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.contrato import EstadoItem, Motor
from app.dados_demo import carregar_distribuidora
from app.motores.conversao import ler_resposta, versoes
from app.motores.requisicoes import AliquotasPremissa, DasPremissa, Linha, operacao_rr, operacao_sn

GOLDEN = Path(__file__).resolve().parent / "golden"


def gravado(nome: str) -> dict:
    return json.loads((GOLDEN / f"{nome}.resposta.json").read_text(encoding="utf-8"))


def test_le_o_exemplo_oficial_do_regime_regular() -> None:
    itens = ler_resposta(gravado("rr-exemplo-oficial")["corpo"], Motor.REGIME_REGULAR)
    arroz, cerveja, educacao, com_erro = itens

    assert arroz.reducaoPct == Decimal("100.00") and arroz.tributos.cbs == Decimal("0.00")
    assert cerveja.tributos.impostoSeletivo == Decimal("15.00") and "impostoSeletivo" in cerveja.memoria

    assert educacao.estado == EstadoItem.CALCULO_SIMULADO and educacao.calculado
    assert (educacao.tributos.cbs, educacao.tributos.ibs) == (Decimal("42.24"), Decimal("0.48"))
    assert educacao.reducaoPct == Decimal("60.00")
    assert (educacao.aliquotaEfetiva.cbs, educacao.aliquotaEfetiva.ibsUF) == (Decimal("3.52"), Decimal("0.02"))
    assert set(educacao.memoria) == {"cbs", "ibsUF", "ibsMun"}
    assert educacao.tributo_cbs_ibs() == Decimal("42.72")

    assert com_erro.estado == EstadoItem.INCONSISTENCIA_ENTRADA and not com_erro.calculado
    assert [(e.codigo, e.campo) for e in com_erro.erros] == [("REG-011", "#/itens/3/ncm")]
    assert com_erro.tributos.cbs is None and com_erro.aliquotaEfetiva is None


def test_le_o_simples_nao_assistido() -> None:
    itens = ler_resposta(gravado("sn-nao-assistido-anexo-i")["corpo"], Motor.SIMPLES_NACIONAL)
    primeiro, _, com_erro = itens
    assert primeiro.estado == EstadoItem.CALCULADO and primeiro.motor == Motor.SIMPLES_NACIONAL
    assert (primeiro.tributos.cbs, primeiro.tributos.ibs) == (Decimal("1.16"), Decimal("0.01"))
    assert (primeiro.aliquotaEfetiva.cbs, primeiro.aliquotaEfetiva.ibs) == (Decimal("1.1612"), Decimal("0.0129"))
    assert primeiro.reducaoPct is None and set(primeiro.memoria) == {"cbs", "ibs"}
    assert [e.codigo for e in com_erro.erros] == ["VSN-047"]


def test_versoes_saem_dos_headers_dos_motores() -> None:
    v = versoes(gravado("rr-exemplo-oficial")["headers"], gravado("sn-nao-assistido-anexo-i")["headers"])
    assert (v.motorRegimeRegular, v.motorSimplesNacional, v.banco) == ("1.7.2", "1.0.2", "V0073")


def test_operacao_rr_da_cerveja_leva_o_is_da_revenda() -> None:
    cerveja = carregar_distribuidora().item("cerveja-lata")
    aliquotas = AliquotasPremissa(Decimal("8.8"), Decimal("0.05"), Decimal("0.05"), Decimal("10.0"))
    op = operacao_rr([Linha(cerveja, Decimal(100), Decimal("379.00"))], date(2027, 3, 16), "RS", 4314902, aliquotas)
    item = op["itens"][0]
    assert op["dhFatoGerador"] == "2027-03-16T10:00:00-03:00"
    assert item["impostoSeletivo"] == {
        "cst": "200",
        "cClassTrib": "200007",
        "baseCalculo": 379.0,
        "quantidade": 35.0,
        "unidade": "LT",
    }
    assert item["aliquotasNominais"]["impostoSeletivo"] == {"adValorem": 10.0}


@dataclass
class _IS:
    cst: str
    cClassTrib: str
    litrosPorUnidade: Decimal | None = None


@dataclass
class _Item:
    ncm: str
    cst: str
    cClassTrib: str
    unidade: str
    impostoSeletivo: _IS | None


def test_operacao_sn_exige_o_vis_quando_o_is_incide() -> None:
    das = DasPremissa(anexo="I", cAtivSN="01", pCBSSN=Decimal("1.1612"), pIBSSN=Decimal("0.0129"))
    tributado = _Item("22030000", "000", "000001", "UN", _IS("000", "000001"))
    with pytest.raises(ValueError, match="vIS"):
        operacao_sn([Linha(tributado, Decimal(1), Decimal("10.00"))], date(2027, 3, 16), das)
    op = operacao_sn([Linha(tributado, Decimal(1), Decimal("10.00"), Decimal("1.00"))], date(2027, 3, 16), das)
    assert op["itens"][0]["valorImpostoSeletivo"] == "1.00"
    revenda = _Item("22030000", "000", "000001", "UN", _IS("200", "200007"))
    op = operacao_sn([Linha(revenda, Decimal(1), Decimal("10.00"))], date(2027, 3, 16), das)
    assert op["itens"][0]["valorImpostoSeletivo"] == "0.00"
    assert op["aliquotasEfetivas"] == {"anexoI": {"pCBSSN": "1.1612", "pIBSSN": "0.0129"}}
