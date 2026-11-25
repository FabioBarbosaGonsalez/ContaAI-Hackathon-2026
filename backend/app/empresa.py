"""Operação de cálculo de uma empresa cadastrada: data, local e premissas do cenário dela (rotuladas)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from app.contrato import AliquotasNominais, ImpostoSeletivoEntrada, ItemBase, ItemEntrada, PremissasDas, Regime
from app.dados_demo import Cenario, Empresa, ItemCatalogo

FONTE_ALIQUOTAS_DEMO = "Cenário de demonstração (data/demo): entradas do exemplo oficial da calculadora RR"
FONTE_DAS_DEMO = "Cenário de demonstração (data/demo): valores de exemplo do esquema do motor SN"


def operacao_da_empresa(empresa: Empresa, cenario: Cenario, data: date | None = None) -> dict[str, Any]:
    """Campos de _Operacao. Sem `data`, vale a data do cenário. Antes de 2027 não vão alíquotas (P6)."""
    quando = data or cenario.data
    al = cenario.aliquotasNominais
    return {
        "data": quando,
        "uf": empresa.uf,
        "municipio": empresa.municipio,
        "aliquotasNominais": AliquotasNominais(
            cbs=al.cbs,
            ibsEstadual=al.ibsEstadual,
            ibsMunicipal=al.ibsMunicipal,
            impostoSeletivoAdValorem=cenario.impostoSeletivoAdValorem.valor,
            fonte=FONTE_ALIQUOTAS_DEMO,
        )
        if quando.year >= 2027
        else None,
        "premissasDas": PremissasDas(
            anexo=cenario.premissasDas.anexo,
            cAtivSN=empresa.simples.cAtivSN,
            pCBSSN=cenario.premissasDas.pCBSSN,
            pIBSSN=cenario.premissasDas.pIBSSN,
            fonte=FONTE_DAS_DEMO,
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
