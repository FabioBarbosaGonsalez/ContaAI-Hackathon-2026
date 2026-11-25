"""Explicação de um item (E2-04, plano 11.6): memória de cálculo do motor, fundamentação e premissas.

Só reúne dados: a memória vem do motor (P1), a fundamentação dos dados abertos do motor RR e as
premissas do próprio cálculo. O texto em português simples é escrito pelo agente a partir daqui.
"""

from __future__ import annotations

from app.contrato import (
    AVISO_LEGAL,
    CarrinhoRequisicao,
    ExplicarRequisicao,
    ExplicarResposta,
    Fundamentacao,
)
from app.motores.cliente import ClienteMotores
from app.motores.dados_abertos import DadosAbertos
from app.precificacao.carrinho import calcular_carrinho


async def explicar_item(req: ExplicarRequisicao, motores: ClienteMotores, da: DadosAbertos) -> ExplicarResposta:
    carrinho = await calcular_carrinho(
        CarrinhoRequisicao(
            data=req.data,
            uf=req.uf,
            municipio=req.municipio,
            aliquotasNominais=req.aliquotasNominais,
            premissasDas=req.premissasDas,
            regime=req.regime,
            itens=[req.item],
        ),
        motores,
    )
    item = carrinho.itens[0]
    fundamentacoes = [
        Fundamentacao(
            cClassTrib=f.codigoClassificacaoTributaria,
            textoCurto=f.textoCurto or "",
            texto=f.texto or "",
            referenciaNormativa=f.referenciaNormativa or "",
        )
        for f in await da.fundamentacoes(req.data)
        if f.codigoClassificacaoTributaria == req.item.cClassTrib
    ]
    return ExplicarResposta(
        itemId=item.id,
        regime=req.regime,
        motor=item.motor,
        estado=item.estado,
        reducaoPct=item.reducaoPct,
        memoria=item.memoria,
        erros=item.erros,
        fundamentacoes=fundamentacoes,
        premissas=carrinho.premissas,
        aviso=AVISO_LEGAL,
    )
