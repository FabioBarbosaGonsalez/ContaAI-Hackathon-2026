"""POST /carrinho/calcular com os motores oficiais (E1-02).

Os tributos vêm dos motores (P1): o SN no Simples tradicional, o RR no híbrido. O backend só soma
e subtrai esses valores e calcula as margens com as fórmulas do ADR 0003. Todo item volta com o
estado do motor; os que não foram calculados ficam sem preço e sem margem e fora dos totais.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from app.cenarios.premissas import aviso_simulacao, premissas, simulado
from app.contrato import (
    CarrinhoRequisicao,
    CarrinhoResposta,
    ItemCalculado,
    ItemEntrada,
    Motor,
    Regime,
    Totais,
    Tributos,
    Versoes,
    _Operacao,
)
from app.motores.cliente import Calculo, ClienteMotores
from app.motores.conversao import LeituraItem
from app.motores.requisicoes import AliquotasPremissa, DasPremissa, Linha

C2 = Decimal("0.01")
ZERO = Decimal("0.00")


def valor_linha(quantidade: Decimal, unitario: Decimal) -> Decimal:
    return (quantidade * unitario).quantize(C2, ROUND_HALF_UP)


def pct(parte: Decimal, todo: Decimal) -> Decimal:
    return (parte / todo * 100).quantize(C2, ROUND_HALF_UP)


def aliquotas_premissa(op: _Operacao) -> AliquotasPremissa | None:
    al = op.aliquotasNominais
    if al is None:
        return None
    return AliquotasPremissa(
        cbs=al.cbs,
        ibsEstadual=al.ibsEstadual,
        ibsMunicipal=al.ibsMunicipal,
        impostoSeletivoAdValorem=al.impostoSeletivoAdValorem,
    )


def das_premissa(op: _Operacao) -> DasPremissa | None:
    das = op.premissasDas
    if das is None:
        return None
    return DasPremissa(anexo=das.anexo, cAtivSN=das.cAtivSN, pCBSSN=das.pCBSSN, pIBSSN=das.pIBSSN)


async def calcular_venda(motores: ClienteMotores, op: _Operacao, regime: Regime, linhas: list[Linha]) -> Calculo:
    if regime == Regime.SIMPLES_TRADICIONAL:
        das = das_premissa(op)
        if das is None:  # o contrato já exige; a checagem protege quem chamar sem validar
            raise ValueError("premissasDas é obrigatória no Simples tradicional.")
        return await motores.simples_nacional(linhas, op.data, das)
    return await motores.regime_regular(linhas, op.data, op.uf, op.municipio, aliquotas_premissa(op))


async def custos_efetivos(
    motores: ClienteMotores, req: CarrinhoRequisicao
) -> tuple[dict[str, Decimal | None], list[ItemEntrada], Calculo | None]:
    """Custo efetivo de cada linha com custo informado.

    Híbrido: o custo (a CBS/IBS da compra vira crédito). Tradicional: custo + CBS/IBS da compra, que
    não é aproveitada (LC 214/2025, art. 47, §9º, I). Sem creditoCompraUnitario, a CBS/IBS da compra
    vem do motor RR sobre o custo (uma chamada para todos esses itens).
    """
    custos: dict[str, Decimal | None] = {}
    com_custo = [i for i in req.itens if i.custoUnitario is not None]
    if req.regime == Regime.SIMPLES_HIBRIDO:
        return {i.id: valor_linha(i.quantidade, i.custoUnitario or ZERO) for i in com_custo}, [], None

    sem_credito = []
    for i in com_custo:
        custo = i.custoUnitario or ZERO
        if i.creditoCompraUnitario is not None:
            custos[i.id] = valor_linha(i.quantidade, custo + i.creditoCompraUnitario)
        elif custo == 0:
            custos[i.id] = ZERO
        else:
            sem_credito.append(i)
    if not sem_credito:
        return custos, [], None

    compra = await motores.regime_regular(
        [Linha(i, i.quantidade, valor_linha(i.quantidade, i.custoUnitario or ZERO)) for i in sem_credito],
        req.data,
        req.uf,
        req.municipio,
        aliquotas_premissa(req),
    )
    for i, lei in zip(sem_credito, compra.itens, strict=True):
        custos[i.id] = (
            valor_linha(i.quantidade, i.custoUnitario or ZERO) + lei.tributo_cbs_ibs() if lei.calculado else None
        )
    return custos, sem_credito, compra


def item_calculado(
    item: ItemEntrada, base: Decimal, lei: LeituraItem, regime: Regime, custo_ef: Decimal | None
) -> ItemCalculado:
    preco = margem = None
    if lei.calculado:
        tributo = lei.tributo_cbs_ibs()
        if regime == Regime.SIMPLES_TRADICIONAL:
            preco = base  # CBS/IBS dentro do DAS
            if custo_ef is not None and preco > 0:
                margem = pct(base - tributo - custo_ef, preco)
        else:
            preco = base + tributo + (lei.tributos.impostoSeletivo or ZERO)  # por fora
            if custo_ef is not None and preco > 0:
                margem = pct(base - custo_ef, preco)
    return ItemCalculado(
        id=item.id,
        descricao=item.descricao,
        motor=lei.motor,
        estado=lei.estado,
        motivoEstado=lei.motivoEstado,
        quantidade=item.quantidade,
        valorUnitario=item.valorUnitario,
        valorProdutos=base,
        tributos=lei.tributos,
        reducaoPct=lei.reducaoPct,
        aliquotaEfetiva=lei.aliquotaEfetiva,
        precoCliente=preco,
        custoEfetivo=custo_ef if lei.calculado else None,
        margemPct=margem,
        memoria=lei.memoria,
        erros=lei.erros,
    )


def _soma(valores: list[Decimal | None]) -> Decimal:
    return sum((v for v in valores if v is not None), ZERO)


def totais(itens: list[ItemCalculado]) -> Totais:
    """Somam só os itens calculados, como os motores."""
    calc = [i for i in itens if i.precoCliente is not None]
    return Totais(
        valorProdutos=_soma([i.valorProdutos for i in calc]),
        tributos=Tributos(
            cbs=_soma([i.tributos.cbs for i in calc]),
            ibs=_soma([i.tributos.ibs for i in calc]),
            impostoSeletivo=_soma([i.tributos.impostoSeletivo for i in calc]),
        ),
        precoCliente=_soma([i.precoCliente for i in calc]),
        itensCalculados=len(calc),
        itensComErro=len(itens) - len(calc),
    )


def versoes_dos_calculos(*calculos: Calculo | None) -> Versoes:
    rr = next((c for c in calculos if c and c.motor == Motor.REGIME_REGULAR), None)
    sn = next((c for c in calculos if c and c.motor == Motor.SIMPLES_NACIONAL), None)
    return Versoes(
        motorRegimeRegular=rr.versaoApp if rr else None,
        motorSimplesNacional=sn.versaoApp if sn else None,
        banco=(rr.versaoBanco if rr else None) or (sn.versaoBanco if sn else None),
    )


async def calcular_carrinho(req: CarrinhoRequisicao, motores: ClienteMotores) -> CarrinhoResposta:
    bases = [valor_linha(i.quantidade, i.valorUnitario) for i in req.itens]
    venda = await calcular_venda(
        motores, req, req.regime, [Linha(i, i.quantidade, b) for i, b in zip(req.itens, bases, strict=True)]
    )
    custos, creditos_pelo_motor, compra = await custos_efetivos(motores, req)

    itens = [
        item_calculado(item, base, lei, req.regime, custos.get(item.id))
        for item, base, lei in zip(req.itens, bases, venda.itens, strict=True)
    ]
    eh_simulado = simulado(req, req.regime, venda.simuladoPeloMotor, [i.estado for i in itens])
    return CarrinhoResposta(
        regime=req.regime,
        data=req.data,
        simulado=eh_simulado,
        avisoSimulacao=aviso_simulacao(req, req.regime, eh_simulado),
        premissas=premissas(
            req,
            req.regime,
            req.itens,
            usou_rr=req.regime == Regime.SIMPLES_HIBRIDO or compra is not None,
            creditos_pelo_motor=creditos_pelo_motor,
            carga_atual_pct=req.cargaAtualPct,
        ),
        itens=itens,
        totais=totais(itens),
        cargaAtualPct=req.cargaAtualPct,
        versoes=versoes_dos_calculos(venda, compra),
    )
