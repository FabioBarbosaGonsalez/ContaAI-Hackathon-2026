"""Verificações comuns da comparação de regimes, usadas pelos testes do CI e pelos golden.

Importado como tests.apoio_regime: o pytest põe a pasta backend/ no caminho (pythonpath em
pyproject.toml), sem depender da instalação editável.
"""

from __future__ import annotations

from decimal import Decimal

from app.contrato import ItemComparado, RegimeCompararResposta


def assert_comparacao_fecha(c: RegimeCompararResposta) -> None:
    """As asserções do inventário (.taste-skill/app/inventario.md) e do plano (seção 16, Regime)."""
    t, h = c.tradicional, c.hibrido
    assert t.creditoCliente == t.tributo and t.custoLiquidoCliente == t.precoCliente - t.tributo
    assert h.tributoLiquido == h.debito - h.creditoCompras
    assert h.creditoCliente == h.debito
    assert h.precoCliente == h.valorProdutos + h.debito + h.impostoSeletivo
    assert h.custoLiquidoCliente == h.precoCliente - h.creditoCliente
    assert c.diferencaCaixa == t.tributo - h.tributoLiquido
    assert c.diferencaPrecoCliente == h.precoCliente - c.valorVenda
    assert abs(c.diferencaPrecoCliente) < Decimal("0.10")  # mesmo preço, a menos de centavos
    # Os totais saem das linhas mostradas.
    soma = {
        campo: sum(getattr(i, campo) for i in c.itens)
        for campo in ItemComparado.model_fields
        if campo not in ("id", "descricao", "quantidade", "fonteCredito")
    }
    assert soma["valorVenda"] == c.valorVenda == t.precoCliente
    assert soma["tributoTradicional"] == t.tributo
    assert (soma["valorProdutosHibrido"], soma["debitoHibrido"]) == (h.valorProdutos, h.debito)
    assert (soma["impostoSeletivoHibrido"], soma["creditoCompras"]) == (h.impostoSeletivo, h.creditoCompras)
    assert soma["precoClienteHibrido"] == h.precoCliente
    assert c.premissas and c.simplificacoes and c.simulado and c.avisoSimulacao
    e = c.empateTradicional
    if e is not None:
        assert e.creditoCliente == e.tributo and e.custoLiquidoCliente == e.precoCliente - e.tributo
        assert e.descontoNecessario == c.valorVenda - e.precoCliente
        assert e.custoLiquidoAlvo == h.custoLiquidoCliente
        assert abs(e.custoLiquidoCliente - e.custoLiquidoAlvo) <= Decimal("0.05") * len(c.itens)
