"""Premissas e aviso de simulação montados a partir da requisição (P6, P7, P8).

Toda premissa vem do que o usuário informou ou de uma hipótese do produto, e sai impressa junto
do resultado. Nada aqui vem do cenário de demonstração.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from app.contrato import EstadoItem, ItemBase, Premissa, Regime, _Operacao

FONTE_USUARIO_ALIQUOTAS = "Informadas pelo usuário (P6). Não são alíquotas oficiais."
FONTE_USUARIO_DAS = "Informadas pelo usuário: saem da apuração do Simples do contribuinte (P8, ADR 0001)."


def _com_rotulo(rotulo: str | None, padrao: str) -> str:
    """O rótulo do preset escolhido (campo fonte) vem antes do aviso padrão, que nunca some."""
    return f"{rotulo}. {padrao}" if rotulo else padrao


def br(valor: Decimal) -> str:
    """12.50 → "12,5" (formato da tela; os números do resultado continuam no JSON)."""
    return f"{valor.normalize():f}".replace(".", ",")


def _nomes(itens: Sequence[ItemBase]) -> str:
    return ", ".join(i.descricao for i in itens)


def premissas(
    op: _Operacao,
    regime: Regime,
    itens: Sequence[ItemBase],
    usou_rr: bool,
    creditos_pelo_motor: Sequence[ItemBase] = (),
    carga_atual_pct: Decimal | None = None,
) -> list[Premissa]:
    ano = op.data.year
    lista: list[Premissa] = []
    al = op.aliquotasNominais
    if al is not None:
        lista.append(
            Premissa(
                nome=f"Alíquotas nominais de {ano}",
                valor=f"CBS {br(al.cbs)}% · IBS estadual {br(al.ibsEstadual)}% · IBS municipal {br(al.ibsMunicipal)}%",
                fonte=_com_rotulo(al.fonte, FONTE_USUARIO_ALIQUOTAS),
            )
        )
        if usou_rr and al.impostoSeletivoAdValorem is not None and any(i.impostoSeletivo for i in itens):
            lista.append(
                Premissa(
                    nome="Alíquota do Imposto Seletivo",
                    valor=f"{br(al.impostoSeletivoAdValorem)}%",
                    fonte="Informada pelo usuário (P7). O motor RR exige a alíquota do IS para NCM sujeita ao IS "
                    "enquanto ela não está definida em lei (erro REG-035). Sem efeito nos itens sem nova "
                    "incidência do IS (CST 200 do IS, ex.: revenda 200007).",
                )
            )
    elif usou_rr:
        lista.append(
            Premissa(
                nome=f"Alíquotas de {ano}",
                valor="as de referência do motor RR para a data",
                fonte="Antes de 2027 nenhuma alíquota é informada: o motor RR aplica as da sua base de dados.",
            )
        )

    if regime == Regime.SIMPLES_TRADICIONAL and op.premissasDas is not None:
        das = op.premissasDas
        lista += [
            Premissa(
                nome=f"Alíquotas efetivas do Simples (anexo {das.anexo}, atividade {das.cAtivSN})",
                valor=f"CBS {br(das.pCBSSN)}% · IBS {br(das.pIBSSN)}%",
                fonte=_com_rotulo(das.fonte, FONTE_USUARIO_DAS),
            ),
            Premissa(
                nome="Crédito das compras no Simples tradicional",
                valor="não aproveitado: entra no custo",
                fonte="LC 214/2025, art. 47, §9º, I: o optante do Simples não se credita de IBS e CBS.",
            ),
        ]
        com_tratamento = [i for i in itens if i.cst != "000"]
        if com_tratamento:
            lista.append(
                Premissa(
                    nome="Redução de alíquota dentro do DAS",
                    valor=f"sem redução: {_nomes(com_tratamento)} paga(m) as alíquotas efetivas do anexo",
                    fonte="Premissa da equipe. O motor do Simples aplica as alíquotas efetivas informadas, sem a "
                    "redução do cClassTrib do regime regular; não verificamos na lei se a redução vale dentro do "
                    "DAS. Validar com o contador (ADR 0003).",
                )
            )

    if creditos_pelo_motor:
        lista.append(
            Premissa(
                nome="Crédito das compras sem valor informado",
                valor=f"calculado no motor RR sobre o custo: {_nomes(creditos_pelo_motor)}",
                fonte="Hipótese de fornecedor no regime regular, na data e com as alíquotas da operação (plano, E3).",
            )
        )
    if carga_atual_pct is not None:
        lista.append(
            Premissa(
                nome="Carga atual informada",
                valor=f"{br(carga_atual_pct)}% do preço",
                fonte="Informada pelo usuário, só para comparação. Não entra em nenhuma conta.",
            )
        )
    lista.append(
        Premissa(
            nome="ICMS",
            valor="fora das contas",
            fonte="Simplificação do produto. Em 2027 o ICMS ainda existe e é deduzido da base do IBS/CBS "
            "(docs/exemplos.md da calculadora RR).",
        )
    )
    return lista


def simulado(op: _Operacao, regime: Regime, motor_sinalizou: bool, estados: Sequence[EstadoItem]) -> bool:
    """Há premissa de alíquota (DAS ou nominais) ou o próprio motor marcou o cálculo como simulado."""
    return (
        regime == Regime.SIMPLES_TRADICIONAL
        or op.aliquotasNominais is not None
        or motor_sinalizou
        or EstadoItem.CALCULO_SIMULADO in estados
    )


def aviso_simulacao(op: _Operacao, regime: Regime, eh_simulado: bool) -> str | None:
    """Frase de estado para o título da tela (seção 12 do plano)."""
    if not eh_simulado:
        return None
    ano = op.data.year
    if regime == Regime.SIMPLES_TRADICIONAL and op.premissasDas is not None:
        das = op.premissasDas
        return (
            f"Simulação de {ano} com alíquotas efetivas do Simples assumidas "
            f"(CBS {br(das.pCBSSN)}%, IBS {br(das.pIBSSN)}%)"
        )
    if op.aliquotasNominais is not None:
        return f"Simulação de {ano} com CBS {br(op.aliquotasNominais.cbs)}% assumida"
    return f"Simulação de {ano}: o motor marcou o cálculo como simulado"
