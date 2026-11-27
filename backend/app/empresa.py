"""Operação de cálculo de uma empresa cadastrada: data, local e premissas do cenário dela (rotuladas)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from app.contrato import (
    AliquotasNominais,
    ExplicarRequisicao,
    ImpostoSeletivoEntrada,
    ItemBase,
    ItemEntrada,
    PremissasDas,
    Regime,
)
from app.dados_demo import Cenario, Empresa, ItemCatalogo
from app.precificacao.lote import LOTE

FONTE_ALIQUOTAS_DEMO = "Cenário de demonstração (data/demo): entradas do exemplo oficial da calculadora RR"
FONTE_DAS_DEMO = "Cenário de demonstração (data/demo): valores de exemplo do esquema do motor SN"
# Empresa própria (C3-B, ADR 0017): o mesmo cenário, rotulado como simulação, até a empresa informar o que é dela.
FONTE_ALIQUOTAS_SIMULACAO = "Simulação do ContaAI: entradas do exemplo oficial da calculadora RR"
FONTE_DAS_SIMULACAO = (
    "Simulação do ContaAI: valores de exemplo do esquema do motor SN, até a empresa informar os da apuração dela"
)
FONTE_DAS_EMPRESA = "Configurações da empresa"


def _fontes(cenario: Cenario) -> tuple[str, str]:
    """Os rótulos das alíquotas nominais e das premissas do DAS, conforme a origem do cenário."""
    propria = cenario.origem == "empresa_propria"
    aliquotas = FONTE_ALIQUOTAS_SIMULACAO if propria else FONTE_ALIQUOTAS_DEMO
    if cenario.premissasDas.origem == "usuario":
        return aliquotas, FONTE_DAS_EMPRESA
    return aliquotas, FONTE_DAS_SIMULACAO if propria else FONTE_DAS_DEMO


def operacao_da_empresa(empresa: Empresa, cenario: Cenario, data: date | None = None) -> dict[str, Any]:
    """Campos de Operacao. Sem `data`, vale a data do cenário. Antes de 2027 não vão alíquotas (P6)."""
    quando = data or cenario.data
    al = cenario.aliquotasNominais
    fonte_aliquotas, fonte_das = _fontes(cenario)
    return {
        "data": quando,
        "uf": empresa.uf,
        "municipio": empresa.municipio,
        "aliquotasNominais": AliquotasNominais(
            cbs=al.cbs,
            ibsEstadual=al.ibsEstadual,
            ibsMunicipal=al.ibsMunicipal,
            impostoSeletivoAdValorem=cenario.impostoSeletivoAdValorem.valor,
            fonte=fonte_aliquotas,
        )
        if quando.year >= 2027
        else None,
        "premissasDas": PremissasDas(
            anexo=cenario.premissasDas.anexo,
            cAtivSN=empresa.simples.cAtivSN,
            pCBSSN=cenario.premissasDas.pCBSSN,
            pIBSSN=cenario.premissasDas.pIBSSN,
            fonte=fonte_das,
        ),
    }


def regime_atual(empresa: Empresa) -> Regime:
    return Regime(empresa.regimeAtual)


def item_base(cat: ItemCatalogo) -> ItemBase:
    """O item do catálogo como o contrato o recebe (classificação já confirmada, P3)."""
    return ItemBase(
        id=cat.id,
        descricao=cat.descricao,
        ncm=cat.ncm,
        cst=cat.cst,
        cClassTrib=cat.cClassTrib,
        impostoSeletivo=ImpostoSeletivoEntrada(
            cst=cat.impostoSeletivo.cst,
            cClassTrib=cat.impostoSeletivo.cClassTrib,
            litrosPorUnidade=cat.impostoSeletivo.litrosPorUnidade,
        )
        if cat.impostoSeletivo
        else None,
        unidade=cat.unidade,
    )


def requisicao_explicar(
    empresa: Empresa, cenario: Cenario, cat: ItemCatalogo, preco: Decimal, regime: Regime
) -> ExplicarRequisicao:
    """O item do catálogo com o cenário da empresa, no lote de referência e ao preço atual (ADR 0011): a
    memória de cálculo da explicação é a mesma conta da linha do catálogo na tela."""
    return ExplicarRequisicao(
        **operacao_da_empresa(empresa, cenario),
        regime=regime,
        item=item_entrada(cat, LOTE, preco),
    )


def item_entrada(
    cat: ItemCatalogo,
    quantidade: Decimal,
    valor_unitario: Decimal,
    custo_unitario: Decimal | None = None,
    credito_unitario: Decimal | None = None,
) -> ItemEntrada:
    return ItemEntrada(
        **item_base(cat).model_dump(),
        quantidade=quantidade,
        valorUnitario=valor_unitario,
        custoUnitario=custo_unitario,
        creditoCompraUnitario=credito_unitario,
    )
