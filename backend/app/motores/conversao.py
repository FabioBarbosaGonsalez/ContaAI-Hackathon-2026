"""Lê as respostas tipadas dos motores e devolve os campos do contrato. Não calcula tributo (P1).

As alíquotas efetivas saem como o motor publica: o RR separa IBS estadual e municipal, o SN traz
o IBS inteiro. Somar alíquotas seria calcular alíquota, o que o backend não faz.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from app.contrato import AliquotaEfetiva, ErroMotor, EstadoItem, Motor, Tributos, Versoes
from app.motores.modelos import (
    HEADER_VERSAO_APP,
    HEADER_VERSAO_BANCO,
    ErroDoMotor,
    ObjetoRR,
    ObjetoSN,
    Reducao,
    RespostaRR,
    RespostaSN,
)


@dataclass(frozen=True)
class LeituraItem:
    numero: int
    motor: Motor
    estado: EstadoItem
    motivoEstado: str | None
    tributos: Tributos
    reducaoPct: Decimal | None
    aliquotaEfetiva: AliquotaEfetiva | None
    memoria: dict[str, str] | None
    erros: list[ErroMotor]

    @property
    def calculado(self) -> bool:
        return self.estado in (EstadoItem.CALCULADO, EstadoItem.CALCULO_SIMULADO) and self.tributos.cbs is not None

    def tributo_cbs_ibs(self) -> Decimal:
        """CBS + IBS do item (soma de valores devolvidos pelo motor)."""
        return (self.tributos.cbs or Decimal(0)) + (self.tributos.ibs or Decimal(0))


def erro_do_contrato(e: ErroDoMotor) -> ErroMotor:
    return ErroMotor(codigo=e.code, titulo=e.title, campo=e.pointer, detalhe=e.detail)


def _efetiva(reducao: Reducao | None, nominal: Decimal) -> Decimal:
    return reducao.pAliqEfet if reducao else nominal


def ler_item_rr(objeto: ObjetoRR) -> LeituraItem:
    """Um item de POST /calculadora/observabilidade/regime-geral."""
    trib = objeto.tribCalc
    ibscbs = trib.IBSCBS if trib else None
    g = ibscbs.gIBSCBS if ibscbs else None
    grupo_is = trib.IS if trib else None

    memoria = dict(ibscbs.memoriaCalculo or {}) if ibscbs else {}
    if grupo_is and grupo_is.memoriaCalculo:
        memoria["impostoSeletivo"] = grupo_is.memoriaCalculo

    if g is None:
        reducao, aliquota = None, None
    else:
        reducao = g.gCBS.gRed.pRedAliq if g.gCBS.gRed else Decimal("0.00")
        aliquota = AliquotaEfetiva(
            cbs=_efetiva(g.gCBS.gRed, g.gCBS.pCBS),
            ibsUF=_efetiva(g.gIBSUF.gRed, g.gIBSUF.pIBSUF),
            ibsMun=_efetiva(g.gIBSMun.gRed, g.gIBSMun.pIBSMun),
        )
    return LeituraItem(
        numero=objeto.nObj,
        motor=Motor.REGIME_REGULAR,
        estado=objeto.estadoItem,
        motivoEstado=None,
        tributos=Tributos(
            cbs=g.gCBS.vCBS if g else None,
            ibs=g.vIBS if g else None,
            impostoSeletivo=grupo_is.vIS if grupo_is else None,
        ),
        reducaoPct=reducao,
        aliquotaEfetiva=aliquota,
        memoria=memoria or None,
        erros=[erro_do_contrato(e) for e in objeto.erros],
    )


def ler_item_sn(objeto: ObjetoSN) -> LeituraItem:
    """Um item de POST /calculadora/observabilidade/simples-nacional/nao-assistido."""
    trib = objeto.tribCalc
    tem_valores = trib is not None and trib.vCBSSN is not None
    return LeituraItem(
        numero=objeto.nObj,
        motor=Motor.SIMPLES_NACIONAL,
        estado=objeto.estadoItem,
        motivoEstado=objeto.motivoEstado.descricao if objeto.motivoEstado else None,
        tributos=Tributos(
            cbs=trib.vCBSSN if trib else None,
            ibs=trib.vIBSSN if trib else None,
            impostoSeletivo=trib.IS.valor if trib and trib.IS else None,
        ),
        reducaoPct=None,
        aliquotaEfetiva=AliquotaEfetiva(cbs=trib.pCBSSN, ibs=trib.pIBSSN) if tem_valores and trib else None,
        memoria=dict(trib.memoriaCalculo or {}) or None if trib else None,
        erros=[erro_do_contrato(e) for e in objeto.erros],
    )


def ler_rr(resposta: RespostaRR) -> list[LeituraItem]:
    return sorted((ler_item_rr(o) for o in resposta.objetos), key=lambda i: i.numero)


def ler_sn(resposta: RespostaSN) -> list[LeituraItem]:
    return sorted((ler_item_sn(o) for o in resposta.objetos), key=lambda i: i.numero)


def ler_resposta(corpo: Mapping[str, Any], motor: Motor) -> list[LeituraItem]:
    """Valida o JSON cru no modelo do motor e lê os itens (usado pelos scripts geradores)."""
    if motor == Motor.REGIME_REGULAR:
        return ler_rr(RespostaRR.model_validate(corpo))
    return ler_sn(RespostaSN.model_validate(corpo))


def _header(headers: Mapping[str, str] | None, nome: str) -> str | None:
    if not headers:
        return None
    return next((v for k, v in headers.items() if k.lower() == nome), None)


def versoes(headers_rr: Mapping[str, str] | None = None, headers_sn: Mapping[str, str] | None = None) -> Versoes:
    return Versoes(
        motorRegimeRegular=_header(headers_rr, HEADER_VERSAO_APP),
        motorSimplesNacional=_header(headers_sn, HEADER_VERSAO_APP),
        banco=_header(headers_rr, HEADER_VERSAO_BANCO) or _header(headers_sn, HEADER_VERSAO_BANCO),
    )
