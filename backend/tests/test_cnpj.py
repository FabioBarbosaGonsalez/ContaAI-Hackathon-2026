"""CNPJ numérico e alfanumérico (C3, ADR 0017): formato e dígitos verificadores (app/cnpj.py)."""

from __future__ import annotations

import re

import pytest

from app.cnpj import PADRAO_CNPJ, cnpj_valido, digitos_verificadores
from app.dados_demo import carregar_cliente_b2b, carregar_distribuidora
from app.persistencia.sementes import carregar_manifesto


def test_exemplo_do_manual_do_serpro() -> None:
    """O único exemplo publicado no manual: 12.ABC.345/01DE-35 (1º DV = 3, 2º DV = 5)."""
    assert digitos_verificadores("12ABC34501DE") == "35"
    assert cnpj_valido("12ABC34501DE35")
    assert not cnpj_valido("12ABC34501DE36")
    assert not cnpj_valido("12ABC34501DE53")


def test_o_cnpj_numerico_e_o_mesmo_calculo() -> None:
    """Para um dígito, ASCII menos 48 é o próprio dígito: o cálculo antigo continua valendo."""
    base = "112223330001"
    dv = digitos_verificadores(base)
    assert cnpj_valido(base + dv)
    assert not cnpj_valido(base + str((int(dv) + 1) % 100).zfill(2))


@pytest.mark.parametrize(
    "texto",
    [
        "12abc34501de35",  # a Receita fala só em letras maiúsculas
        "12ABC34501DEA5",  # os dígitos verificadores são numéricos
        "12.ABC.345/01DE-35",  # a API recebe sem máscara
        "12ABC34501DE3",
        "12ABC34501DE355",
        "١٢ABC34501DE35",  # dígitos de outra escrita
        "12ÁBC34501DE35",
        "",
    ],
)
def test_formato_fora_do_oficial_e_recusado(texto: str) -> None:
    assert not cnpj_valido(texto)
    assert not re.fullmatch(PADRAO_CNPJ, texto)


def test_base_fora_do_formato_nao_calcula() -> None:
    with pytest.raises(ValueError, match="12 caracteres"):
        digitos_verificadores("12abc34501de")


def test_os_cnpjs_da_demo_tem_digito_invalido_de_proposito() -> None:
    """ADR 0008: os CNPJs fictícios não podem ser de uma empresa real. Fora da demonstração, a API exige o dígito
    certo, então nenhum deles entra como empresa própria."""
    manifesto = carregar_manifesto()
    distribuidora = carregar_distribuidora()
    cnpjs = {distribuidora.empresa.cnpj, carregar_cliente_b2b().cliente.cnpj}
    cnpjs |= {i.cnpjFornecedor for i in distribuidora.catalogo}
    cnpjs |= {c.empresa for c in manifesto.clientesB2B}
    assert cnpjs
    for cnpj in cnpjs:
        assert re.fullmatch(PADRAO_CNPJ, cnpj)
        assert not cnpj_valido(cnpj), cnpj
