"""POST /item/preco-alvo (E1-03): ajuste afim do plano 11.1, com bisseção de reserva.

Os tributos vêm sempre do motor (P1). Com T(x) = α + βx medido em duas avaliações, o preço sai
em fórmula fechada (ADR 0003) e uma terceira avaliação confirma:

- híbrido (x = valor dos produtos, CBS/IBS por fora): m = (x − c) ÷ (x + T)  → x* = (c + mα) ÷ (1 − m(1 + β))
- tradicional (x = preço, CBS/IBS dentro do DAS):     m = (x − T − c) ÷ x   → x* = (c + α) ÷ (1 − β − m)

Critério de aceite (ADR 0005, resolve a pendência do ADR 0003): o preço é o menor valor em
centavos com margem ≥ alvo. O ajuste arredonda para cima. A confirmação exige item calculado,
margem ≥ alvo e tributo igual ao previsto pela reta (senão o tributo não é linear e o centavo
pode não ser o menor). Se ela falhar, a bisseção busca esse menor centavo em até 25 avaliações.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP, Decimal

from app.cenarios.premissas import aviso_simulacao, premissas, simulado
from app.contrato import ErroMotor, PrecoAlvoRequisicao, PrecoAlvoResposta, Premissa, Regime, Tributos
from app.motores.cliente import ClienteMotores
from app.motores.conversao import LeituraItem
from app.motores.requisicoes import Linha
from app.precificacao.carrinho import aliquotas_premissa, calcular_venda

LOTE = Decimal(100)  # unidades por avaliação: reduz o efeito do arredondamento ao centavo do motor
MAX_AVALIACOES = 25
# Diferença máxima, por unidade, entre o tributo da confirmação e o previsto pela reta. Acima disso o
# tributo não é linear nesse trecho e o preço do ajuste pode não ser o menor centavo: vai para a bisseção.
# R$ 0,001 por unidade = R$ 0,10 no lote de 100, folga para o arredondamento ao centavo do motor.
TOLERANCIA_RETA = Decimal("0.001")
C2, C4 = Decimal("0.01"), Decimal("0.0001")


class CalculoRecusado(Exception):
    """O pedido não tem resposta. Vira 422 com ProblemaCalculo."""

    def __init__(self, detalhe: str, erros: list[ErroMotor] | None = None) -> None:
        super().__init__(detalhe)
        self.detalhe = detalhe
        self.erros = erros or []


@dataclass(frozen=True)
class Avaliacao:
    x: Decimal  # valor unitário avaliado
    tributo: Decimal | None  # tributo por unidade (CBS + IBS, + IS no híbrido); None se não calculado
    leitura: LeituraItem
    simulado_motor: bool


class Avaliador:
    """Chama o motor para um valor unitário e conta as avaliações (inclusive as do cache)."""

    def __init__(self, motores: ClienteMotores, req: PrecoAlvoRequisicao) -> None:
        self.motores, self.req, self.avaliacoes = motores, req, 0

    async def __call__(self, x: Decimal) -> Avaliacao:
        if self.avaliacoes >= MAX_AVALIACOES:
            raise CalculoRecusado(f"O preço-alvo não convergiu em {MAX_AVALIACOES} avaliações do motor.")
        self.avaliacoes += 1
        base = (LOTE * x).quantize(C2, ROUND_HALF_UP)
        calculo = await calcular_venda(self.motores, self.req, self.req.regime, [Linha(self.req.item, LOTE, base)])
        lei = calculo.itens[0]
        tributo = None
        if lei.calculado:
            total = lei.tributo_cbs_ibs()
            if self.req.regime == Regime.SIMPLES_HIBRIDO:
                total += lei.tributos.impostoSeletivo or Decimal(0)
            tributo = total / LOTE
        return Avaliacao(x=x, tributo=tributo, leitura=lei, simulado_motor=calculo.simuladoPeloMotor)


def margem(regime: Regime, x: Decimal, tributo: Decimal, custo: Decimal) -> Decimal | None:
    if regime == Regime.SIMPLES_TRADICIONAL:
        return (x - tributo - custo) / x if x > 0 else None
    return (x - custo) / (x + tributo) if x + tributo > 0 else None


def atinge(regime: Regime, a: Avaliacao, custo: Decimal, m: Decimal) -> bool:
    if a.tributo is None:
        return False
    obtida = margem(regime, a.x, a.tributo, custo)
    return obtida is not None and obtida >= m


async def custo_efetivo_unitario(motores: ClienteMotores, req: PrecoAlvoRequisicao) -> tuple[Decimal, bool]:
    """Devolve o custo efetivo por unidade e se o crédito da compra veio do motor (premissa)."""
    if req.regime == Regime.SIMPLES_HIBRIDO:
        return req.custoUnitario, False
    if req.creditoCompraUnitario is not None:
        return req.custoUnitario + req.creditoCompraUnitario, False
    if req.custoUnitario == 0:
        return Decimal(0), False
    compra = await motores.regime_regular(
        [Linha(req.item, LOTE, (LOTE * req.custoUnitario).quantize(C2, ROUND_HALF_UP))],
        req.data,
        req.uf,
        req.municipio,
        aliquotas_premissa(req),
    )
    lei = compra.itens[0]
    if not lei.calculado:
        raise CalculoRecusado("O motor RR não calculou o crédito da compra deste item.", lei.erros)
    return req.custoUnitario + lei.tributo_cbs_ibs() / LOTE, True


def _recusar_se_nao_calculado(a: Avaliacao) -> None:
    if a.tributo is None:
        motivo = a.leitura.motivoEstado or "veja os erros do motor"
        raise CalculoRecusado(
            f"O motor não calculou o item (estado {a.leitura.estado.value}): {motivo}.", a.leitura.erros
        )


async def ajuste_afim(
    avaliar: Avaliador, regime: Regime, custo: Decimal, m: Decimal
) -> tuple[Avaliacao | None, Decimal | None]:
    """3 avaliações. Devolve a confirmação aceita, ou (None, estimativa) para a bisseção."""
    x1 = custo if custo > 0 else Decimal(1)
    x2 = 2 * x1
    a1 = await avaliar(x1)
    _recusar_se_nao_calculado(a1)  # o item não é calculado nem no primeiro ponto: não há preço
    a2 = await avaliar(x2)
    if a2.tributo is None:
        return None, None
    beta = (a2.tributo - a1.tributo) / (x2 - x1)
    alfa = a1.tributo - beta * x1
    if regime == Regime.SIMPLES_TRADICIONAL:
        den, num = 1 - beta - m, custo + alfa
    else:
        den, num = 1 - m * (1 + beta), custo + m * alfa
    if den <= 0:
        raise CalculoRecusado("Margem impossível: com a carga que o motor devolveu, nenhum preço chega a essa margem.")
    estimativa = max((num / den).quantize(C2, ROUND_CEILING), C2)  # o menor preço possível é R$ 0,01
    a3 = await avaliar(estimativa)
    na_reta = a3.tributo is not None and abs(a3.tributo - (alfa + beta * estimativa)) <= TOLERANCIA_RETA
    return (a3, estimativa) if na_reta and atinge(regime, a3, custo, m) else (None, estimativa)


async def bissecao(
    avaliar: Avaliador, regime: Regime, custo: Decimal, m: Decimal, estimativa: Decimal | None
) -> Avaliacao:
    """Menor preço em centavos com margem ≥ alvo, supondo a margem crescente no preço."""
    baixo = custo.quantize(C2, ROUND_FLOOR)  # no custo a margem é ≤ 0 < alvo
    alto = max(estimativa or Decimal(0), 2 * custo, Decimal("0.02")).quantize(C2, ROUND_CEILING)
    melhor = await avaliar(alto)
    while not atinge(regime, melhor, custo, m):
        baixo, alto = alto, 2 * alto
        melhor = await avaliar(alto)
    while alto - baixo > C2:
        meio = ((baixo + alto) / 2).quantize(C2, ROUND_FLOOR)
        a = await avaliar(meio)
        if atinge(regime, a, custo, m):
            alto, melhor = meio, a
        else:
            baixo = meio
    return melhor


def _unitario(valor: Decimal | None) -> Decimal:
    return ((valor or Decimal(0)) / LOTE).quantize(C4)


async def calcular_preco_alvo(req: PrecoAlvoRequisicao, motores: ClienteMotores) -> PrecoAlvoResposta:
    regime, m = req.regime, req.margemAlvoPct / 100
    custo, credito_pelo_motor = await custo_efetivo_unitario(motores, req)
    avaliar = Avaliador(motores, req)

    final, estimativa = await ajuste_afim(avaliar, regime, custo, m)
    metodo = "afim"
    if final is None:
        final, metodo = await bissecao(avaliar, regime, custo, m, estimativa), "bissecao"

    lei, valor, tributo = final.leitura, final.x, final.tributo or Decimal(0)
    obtida = margem(regime, valor, tributo, custo) or Decimal(0)
    eh_simulado = simulado(req, regime, final.simulado_motor, [lei.estado])
    return PrecoAlvoResposta(
        regime=regime,
        itemId=req.item.id,
        valorUnitario=valor,
        precoCliente=valor if regime == Regime.SIMPLES_TRADICIONAL else valor + tributo,
        tributosUnitarios=Tributos(
            cbs=_unitario(lei.tributos.cbs),
            ibs=_unitario(lei.tributos.ibs),
            impostoSeletivo=_unitario(lei.tributos.impostoSeletivo),
        ),
        custoEfetivoUnitario=custo,
        margemAlvoPct=req.margemAlvoPct,
        margemObtidaPct=(obtida * 100).quantize(C2, ROUND_HALF_UP),
        loteReferencia=int(LOTE),
        chamadas=avaliar.avaliacoes,
        metodo=metodo,
        memoria=lei.memoria,
        simulado=eh_simulado,
        avisoSimulacao=aviso_simulacao(req, regime, eh_simulado),
        premissas=premissas(
            req,
            regime,
            [req.item],
            usou_rr=regime == Regime.SIMPLES_HIBRIDO or credito_pelo_motor,
            creditos_pelo_motor=[req.item] if credito_pelo_motor else [],
        )
        + [
            Premissa(
                nome="Método do preço-alvo",
                valor=f"lote de {int(LOTE)} unidades por avaliação; menor preço em centavos com margem ≥ alvo",
                fonte="Plano, seção 11.1, e ADR 0005. Os tributos de cada avaliação vêm do motor.",
            )
        ],
    )
