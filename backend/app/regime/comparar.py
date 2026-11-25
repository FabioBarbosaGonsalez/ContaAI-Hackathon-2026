"""POST /regime/comparar com os motores oficiais (E3-01 e E3-02; plano 11.2, ADR 0003 e ADR 0007).

Mesmo preço total V ao cliente nos dois regimes, linha a linha:

- Tradicional: o motor SN calcula a CBS/IBS dentro do DAS sobre V. O cliente se credita desse valor
  (LC 214/2025, art. 47, §9º, II) e o custo líquido dele é V − crédito.
- Híbrido: a base B de cada linha sai do ajuste afim B + T(B) = V, com T = CBS + IBS + IS do motor
  RR (duas avaliações dão a reta e uma terceira confirma; se a confirmação errar por mais de
  TOLERANCIA_LINHA, a secante refina até MAX_CONFIRMACOES vezes). O débito é a CBS + IBS; o cliente
  se credita do débito; o IS entra no preço, mas não no débito nem no crédito.
- Empate (plano 11.2, opcional): o preço no tradicional que dá ao cliente o custo líquido de um
  concorrente do regime regular com o mesmo preço total. Duas avaliações a mais do motor SN.
- Crédito das compras: creditoCompraUnitario (grupo IBSCBS da NF-e) × quantidade vendida; sem ele, o
  motor RR sobre o custo das unidades vendidas, com a hipótese de fornecedor no regime regular.

Os totais são a soma das linhas, que já vêm arredondadas ao centavo pelos motores (P1: o backend só
soma e subtrai). Qualquer item que um motor não calcule recusa a comparação inteira (422), porque
os dois lados precisam ter os mesmos itens.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_FLOOR, ROUND_HALF_UP, Decimal
from typing import Literal

from app.cenarios.premissas import aviso_simulacao, br, premissas, simulado
from app.contrato import (
    EmpateTradicional,
    ErroMotor,
    ItemComparado,
    ItemEntrada,
    LadoHibrido,
    LadoTradicional,
    Premissa,
    Regime,
    RegimeCompararRequisicao,
    RegimeCompararResposta,
)
from app.motores.cliente import Calculo, ClienteMotores
from app.motores.conversao import LeituraItem
from app.motores.requisicoes import Linha
from app.precificacao.carrinho import aliquotas_premissa, calcular_venda, valor_linha, versoes_dos_calculos
from app.precificacao.preco_alvo import CalculoRecusado

C2 = Decimal("0.01")
ZERO = Decimal("0.00")
# Diferença aceita, por linha, entre base + CBS/IBS + IS e o preço da venda. O motor arredonda cada
# tributo ao centavo, então a base em centavos raramente fecha exato (ADR 0003: "pode sobrar
# diferença de centavos"). A diferença aparece em diferencaPrecoCliente.
TOLERANCIA_LINHA = Decimal("0.05")
MAX_CONFIRMACOES = 3  # avaliações do RR depois das duas da reta

FonteCredito = Literal["nfe", "motor", "custo_zero"]


def _centavos(valor: Decimal) -> Decimal:
    """Só a escala: os motores devolvem centavos, mas um zero pode vir como "0"."""
    return valor.quantize(C2)


def _tributo_hibrido(lei: LeituraItem) -> Decimal:
    """O que vai ao preço no híbrido: CBS + IBS + IS."""
    return lei.tributo_cbs_ibs() + (lei.tributos.impostoSeletivo or ZERO)


def _recusar_nao_calculados(calculo: Calculo, itens: list[ItemEntrada], etapa: str) -> None:
    faltam = [(i, lei) for i, lei in zip(itens, calculo.itens, strict=True) if not lei.calculado]
    if not faltam:
        return
    erros: list[ErroMotor] = [e for _, lei in faltam for e in lei.erros]
    descricao = "; ".join(
        f"{i.id} (estado {lei.estado.value}{': ' + lei.motivoEstado if lei.motivoEstado else ''})" for i, lei in faltam
    )
    raise CalculoRecusado(
        f"O motor não calculou {etapa} de todos os itens, e a comparação precisa dos mesmos itens nos dois "
        f"regimes: {descricao}.",
        erros,
    )


@dataclass
class _Ponto:
    x: Decimal
    t: Decimal


async def _bases_hibrido(
    motores: ClienteMotores, req: RegimeCompararRequisicao, vendas: list[Decimal]
) -> tuple[list[Decimal], Calculo, list[Calculo]]:
    """Base de cada linha com base + T(base) = venda. Devolve as bases, o cálculo final e todos os cálculos."""
    itens = req.itens

    async def avaliar(bases: list[Decimal]) -> Calculo:
        linhas = [Linha(i, i.quantidade, b) for i, b in zip(itens, bases, strict=True)]
        calculo = await calcular_venda(motores, req, Regime.SIMPLES_HIBRIDO, linhas)
        _recusar_nao_calculados(calculo, itens, "a CBS/IBS do lado híbrido")
        return calculo

    c1 = await avaliar(vendas)
    c2 = await avaliar([2 * v for v in vendas])
    calculos = [c1, c2]
    pontos = [
        [_Ponto(v, _tributo_hibrido(a)), _Ponto(2 * v, _tributo_hibrido(b))]
        for v, a, b in zip(vendas, c1.itens, c2.itens, strict=True)
    ]
    bases = list(vendas)
    fechadas = [False] * len(itens)
    final = c2
    for _ in range(MAX_CONFIRMACOES):
        for n, (v, pts) in enumerate(zip(vendas, pontos, strict=True)):
            if fechadas[n]:
                continue
            a, b = pts[-2], pts[-1]
            if b.x == a.x:  # a secante não anda mais: fica a última base
                fechadas[n] = True
                continue
            beta = (b.t - a.t) / (b.x - a.x)
            alfa = a.t - beta * a.x
            if 1 + beta <= 0:
                raise CalculoRecusado(f"O item {itens[n].id} não tem base que feche o preço no híbrido.")
            bases[n] = ((v - alfa) / (1 + beta)).quantize(C2, ROUND_HALF_UP)
        final = await avaliar(bases)
        calculos.append(final)
        for n, (v, lei) in enumerate(zip(vendas, final.itens, strict=True)):
            t = _tributo_hibrido(lei)
            if abs(bases[n] + t - v) <= TOLERANCIA_LINHA:
                fechadas[n] = True
            elif not fechadas[n]:
                pontos[n].append(_Ponto(bases[n], t))
        if all(fechadas):
            break
    for n, (v, lei) in enumerate(zip(vendas, final.itens, strict=True)):
        if abs(bases[n] + _tributo_hibrido(lei) - v) > TOLERANCIA_LINHA:
            raise CalculoRecusado(
                f"A base do item {itens[n].id} no híbrido não fechou o preço da venda em "
                f"{2 + MAX_CONFIRMACOES} avaliações do motor RR."
            )
    return bases, final, calculos


async def _creditos_compras(
    motores: ClienteMotores, req: RegimeCompararRequisicao
) -> tuple[list[Decimal], list[FonteCredito], list[ItemEntrada], Calculo | None]:
    creditos: list[Decimal | None] = []
    fontes: list[FonteCredito] = []
    pelo_motor: list[ItemEntrada] = []
    for i in req.itens:
        custo = i.custoUnitario or ZERO  # o contrato exige o custo
        if i.creditoCompraUnitario is not None:
            creditos.append(valor_linha(i.quantidade, i.creditoCompraUnitario))
            fontes.append("nfe")
        elif custo == 0:
            creditos.append(ZERO)
            fontes.append("custo_zero")
        else:
            creditos.append(None)
            fontes.append("motor")
            pelo_motor.append(i)
    compra = None
    if pelo_motor:
        compra = await motores.regime_regular(
            [Linha(i, i.quantidade, valor_linha(i.quantidade, i.custoUnitario or ZERO)) for i in pelo_motor],
            req.data,
            req.uf,
            req.municipio,
            aliquotas_premissa(req),
        )
        _recusar_nao_calculados(compra, pelo_motor, "o crédito da compra")
        leituras = iter(compra.itens)
        creditos = [c if c is not None else next(leituras).tributo_cbs_ibs() for c in creditos]
    return [c or ZERO for c in creditos], fontes, pelo_motor, compra


def _premissas_da_comparacao(req: RegimeCompararRequisicao, pelo_motor: list[ItemEntrada]) -> list[Premissa]:
    lista = premissas(req, Regime.SIMPLES_TRADICIONAL, req.itens, usou_rr=True, creditos_pelo_motor=pelo_motor)
    extras = [
        Premissa(
            nome="Crédito das compras no Simples híbrido",
            valor="a CBS + IBS da compra vira crédito integral; compra com alíquota zero não gera crédito",
            fonte="LC 214/2025, art. 47, caput (o contribuinte do regime regular apropria créditos do IBS e da CBS "
            "das aquisições, quando extintos os débitos) e art. 49 (alíquota zero não permite crédito). Leitura da "
            "equipe: com a opção do art. 41, §3º, não vale a vedação do art. 47, §9º, I, que se aplica 'quando não "
            "for exercida a opção pelo regime regular'.",
        ),
        Premissa(
            nome="Opção pelo Simples híbrido",
            valor="semestral: em setembro, para janeiro a junho, e em março, para julho a dezembro; irretratável no "
            "semestre",
            fonte="LC 123/2006, art. 13, §10, na redação da LC 227/2026, e Portal do Simples Nacional (ADR 0003).",
        ),
    ]
    if any(i.impostoSeletivo for i in req.itens):
        extras.append(
            Premissa(
                nome="Imposto Seletivo fora do crédito do cliente",
                valor="o IS entra no preço do híbrido, mas não no débito nem no crédito",
                fonte="LC 214/2025, art. 410: o IS incide uma única vez, 'sendo vedado qualquer tipo de "
                "aproveitamento de crédito do imposto com operações anteriores ou geração de créditos para operações "
                "posteriores'. Na revenda (CST 200 do IS, ex.: 200007) o motor RR devolve IS zero.",
            )
        )
    icms = lista.pop()  # o ICMS fica por último, como nas outras rotas
    return [*lista, *extras, icms]


def _simplificacoes(req: RegimeCompararRequisicao) -> list[str]:
    lista = list(SIMPLIFICACOES)
    com_tratamento = [i.descricao for i in req.itens if i.cst != "000"]
    if com_tratamento:
        lista.insert(
            -1,
            f"No Simples tradicional, {', '.join(com_tratamento)} paga(m) as alíquotas efetivas do anexo, sem a "
            "redução do regime regular (premissa da equipe; validar com o contador). O resultado da comparação "
            "depende dela.",
        )
    return lista


SIMPLIFICACOES = [
    "O restante do DAS (IRPJ, CSLL, CPP etc.) é tratado como igual nos dois regimes; só a parcela de CBS/IBS muda "
    "(plano, 11.2).",
    "Mesmo preço total ao cliente nos dois regimes: no híbrido, a base de cada linha é o valor que somado à CBS/IBS "
    "(e ao IS) dá esse preço. Pode sobrar diferença de centavos pelo arredondamento (diferencaPrecoCliente).",
    "diferencaCaixa compara os tributos a preço igual: tributo no DAS − (débito − crédito das compras).",
    "Crédito das compras das unidades vendidas: o crédito por unidade informado (grupo IBSCBS da NF-e) ou, sem ele, "
    "o motor RR sobre o custo. Supõe os débitos da compra pagos pelo fornecedor (LC 214/2025, art. 47, caput).",
    "No Simples tradicional o crédito das compras não é aproveitado (LC 214/2025, art. 47, §9º, I).",
    "ICMS fora das contas.",
]


HIPOTESE_EMPATE = (
    "Concorrente do regime regular que vende os mesmos itens pelo mesmo preço total: o custo líquido do cliente "
    "nele é o do lado híbrido. O preço de empate de cada linha sai do ajuste afim no motor SN, arredondado ao "
    "centavo para baixo; o custo líquido resultante pode diferir em centavos de custoLiquidoAlvo."
)


async def _empate_tradicional(
    motores: ClienteMotores,
    req: RegimeCompararRequisicao,
    vendas: list[Decimal],
    trad: Calculo,
    alvos: list[Decimal],
) -> EmpateTradicional | None:
    """P − T(P) = alvo em cada linha, com T = CBS + IBS do DAS. 2 avaliações a mais do motor SN."""

    async def avaliar(precos: list[Decimal]) -> Calculo:
        linhas = [Linha(i, i.quantidade, p) for i, p in zip(req.itens, precos, strict=True)]
        return await calcular_venda(motores, req, Regime.SIMPLES_TRADICIONAL, linhas)

    dobro = await avaliar([2 * v for v in vendas])
    precos = []
    for v, a, b, alvo in zip(vendas, trad.itens, dobro.itens, alvos, strict=True):
        if not b.calculado:
            return None
        beta = (b.tributo_cbs_ibs() - a.tributo_cbs_ibs()) / v
        alfa = a.tributo_cbs_ibs() - beta * v
        if 1 - beta <= 0:
            return None
        preco = ((alvo + alfa) / (1 - beta)).quantize(C2, ROUND_FLOOR)
        precos.append(max(preco, C2))
    confirmacao = await avaliar(precos)
    tributos = []
    for p, lei, alvo in zip(precos, confirmacao.itens, alvos, strict=True):
        if not lei.calculado or abs(p - lei.tributo_cbs_ibs() - alvo) > TOLERANCIA_LINHA:
            return None
        tributos.append(_centavos(lei.tributo_cbs_ibs()))
    preco, tributo = sum(precos, ZERO), sum(tributos, ZERO)
    return EmpateTradicional(
        hipotese=HIPOTESE_EMPATE,
        precoCliente=preco,
        descontoNecessario=sum(vendas, ZERO) - preco,
        tributo=tributo,
        creditoCliente=tributo,
        custoLiquidoCliente=preco - tributo,
        custoLiquidoAlvo=sum(alvos, ZERO),
    )


def _aviso(req: RegimeCompararRequisicao) -> str:
    das = req.premissasDas
    hibrido = aviso_simulacao(req, Regime.SIMPLES_HIBRIDO, True) or f"Simulação de {req.data.year}"
    if das is None:  # o contrato já exige
        return hibrido
    return f"{hibrido} e alíquotas efetivas do Simples assumidas (CBS {br(das.pCBSSN)}%, IBS {br(das.pIBSSN)}%)"


async def comparar_regimes(req: RegimeCompararRequisicao, motores: ClienteMotores) -> RegimeCompararResposta:
    vendas = [valor_linha(i.quantidade, i.valorUnitario) for i in req.itens]

    linhas_trad = [Linha(i, i.quantidade, v) for i, v in zip(req.itens, vendas, strict=True)]
    trad = await calcular_venda(motores, req, Regime.SIMPLES_TRADICIONAL, linhas_trad)
    _recusar_nao_calculados(trad, req.itens, "a CBS/IBS do Simples tradicional")

    bases, hib, calculos_rr = await _bases_hibrido(motores, req, vendas)
    creditos, fontes, pelo_motor, compra = await _creditos_compras(motores, req)

    itens = [
        ItemComparado(
            id=i.id,
            descricao=i.descricao,
            quantidade=i.quantidade,
            valorVenda=v,
            tributoTradicional=_centavos(lt.tributo_cbs_ibs()),
            valorProdutosHibrido=b,
            debitoHibrido=_centavos(lh.tributo_cbs_ibs()),
            impostoSeletivoHibrido=_centavos(lh.tributos.impostoSeletivo or ZERO),
            precoClienteHibrido=_centavos(b + _tributo_hibrido(lh)),
            creditoCompras=_centavos(cc),
            fonteCredito=f,
        )
        for i, v, lt, b, lh, cc, f in zip(
            req.itens, vendas, trad.itens, bases, hib.itens, creditos, fontes, strict=True
        )
    ]

    def soma(campo: str) -> Decimal:
        return sum((getattr(i, campo) for i in itens), ZERO)

    valor_venda, tributo_trad = soma("valorVenda"), soma("tributoTradicional")
    debito, credito_compras = soma("debitoHibrido"), soma("creditoCompras")
    preco_hib = soma("precoClienteHibrido")
    tributo_liquido = debito - credito_compras
    empate = await _empate_tradicional(
        motores, req, vendas, trad, [i.precoClienteHibrido - i.debitoHibrido for i in itens]
    )

    estados = [lei.estado for c in (trad, hib) for lei in c.itens]
    simulado_motor = any(c.simuladoPeloMotor for c in (trad, *calculos_rr))
    eh_simulado = simulado(req, Regime.SIMPLES_TRADICIONAL, simulado_motor, estados)
    return RegimeCompararResposta(
        criterio="mesmo_preco_total_ao_cliente",
        cliente=req.cliente,
        data=req.data,
        valorVenda=valor_venda,
        tradicional=LadoTradicional(
            precoCliente=valor_venda,
            tributo=tributo_trad,
            creditoCliente=tributo_trad,
            custoLiquidoCliente=valor_venda - tributo_trad,
        ),
        hibrido=LadoHibrido(
            precoCliente=preco_hib,
            valorProdutos=soma("valorProdutosHibrido"),
            debito=debito,
            impostoSeletivo=soma("impostoSeletivoHibrido"),
            creditoCompras=credito_compras,
            tributoLiquido=tributo_liquido,
            creditoCliente=debito,
            custoLiquidoCliente=preco_hib - debito,
        ),
        diferencaCaixa=tributo_trad - tributo_liquido,
        diferencaPrecoCliente=preco_hib - valor_venda,
        itens=itens,
        empateTradicional=empate,
        fonteTradicional="motor",
        simplificacoes=_simplificacoes(req),
        simulado=eh_simulado,
        avisoSimulacao=_aviso(req) if eh_simulado else None,
        premissas=_premissas_da_comparacao(req, pelo_motor),
        versoes=versoes_dos_calculos(trad, hib, compra),
    )
