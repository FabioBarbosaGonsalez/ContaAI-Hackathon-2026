"""Lê as respostas dos motores e devolve os campos do contrato. Não calcula tributo (P1).

As alíquotas efetivas saem como o motor publica: o RR separa IBS estadual e municipal, o SN traz
o IBS inteiro. Somar alíquotas seria calcular alíquota, o que o backend não faz.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from app.contrato import AliquotaEfetiva, ErroMotor, EstadoItem, Motor, Tributos, Versoes


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


def _dec(valor: Any) -> Decimal | None:
    return None if valor is None else Decimal(str(valor))


def ler_erros(objeto: Mapping[str, Any]) -> list[ErroMotor]:
    return [
        ErroMotor(codigo=e.get("code", ""), titulo=e.get("title", ""), campo=e.get("pointer"), detalhe=e.get("detail"))
        for e in objeto.get("erros") or []
    ]


def _efetiva(grupo: Mapping[str, Any], chave_nominal: str) -> Decimal | None:
    reducao = grupo.get("gRed")
    return _dec(reducao.get("pAliqEfet")) if reducao else _dec(grupo.get(chave_nominal))


def ler_item_rr(objeto: Mapping[str, Any]) -> LeituraItem:
    """Um item de POST /calculadora/observabilidade/regime-geral."""
    trib = objeto.get("tribCalc") or {}
    ibscbs = trib.get("IBSCBS") or {}
    g = ibscbs.get("gIBSCBS") or {}
    gcbs, guf, gmun = g.get("gCBS") or {}, g.get("gIBSUF") or {}, g.get("gIBSMun") or {}
    grupo_is = trib.get("IS")

    memoria = dict(ibscbs.get("memoriaCalculo") or {}) or None
    if grupo_is and grupo_is.get("memoriaCalculo"):
        memoria = {**(memoria or {}), "impostoSeletivo": grupo_is["memoriaCalculo"]}

    reducao = (gcbs.get("gRed") or {}).get("pRedAliq")
    return LeituraItem(
        numero=objeto["nObj"],
        motor=Motor.REGIME_REGULAR,
        estado=EstadoItem(objeto["estadoItem"]),
        motivoEstado=None,
        tributos=Tributos(
            cbs=_dec(gcbs.get("vCBS")),
            ibs=_dec(g.get("vIBS")),
            impostoSeletivo=_dec(grupo_is.get("vIS")) if grupo_is else None,
        ),
        reducaoPct=_dec(reducao) if reducao is not None else (Decimal("0.00") if g else None),
        aliquotaEfetiva=AliquotaEfetiva(
            cbs=_efetiva(gcbs, "pCBS"), ibsUF=_efetiva(guf, "pIBSUF"), ibsMun=_efetiva(gmun, "pIBSMun")
        )
        if g
        else None,
        memoria=memoria,
        erros=ler_erros(objeto),
    )


def ler_item_sn(objeto: Mapping[str, Any]) -> LeituraItem:
    """Um item de POST /calculadora/observabilidade/simples-nacional/nao-assistido."""
    trib = objeto.get("tribCalc") or {}
    estado = EstadoItem(objeto["estadoItem"])
    tem_valores = "vCBSSN" in trib
    return LeituraItem(
        numero=objeto["nObj"],
        motor=Motor.SIMPLES_NACIONAL,
        estado=estado,
        motivoEstado=(objeto.get("motivoEstado") or {}).get("descricao"),
        tributos=Tributos(
            cbs=_dec(trib.get("vCBSSN")),
            ibs=_dec(trib.get("vIBSSN")),
            impostoSeletivo=_dec((trib.get("IS") or {}).get("valor")),
        ),
        reducaoPct=None,
        aliquotaEfetiva=AliquotaEfetiva(cbs=_dec(trib.get("pCBSSN")), ibs=_dec(trib.get("pIBSSN")))
        if tem_valores
        else None,
        memoria=dict(trib.get("memoriaCalculo") or {}) or None,
        erros=ler_erros(objeto),
    )


def ler_resposta(corpo: Mapping[str, Any], motor: Motor) -> list[LeituraItem]:
    leitor = ler_item_rr if motor == Motor.REGIME_REGULAR else ler_item_sn
    return sorted((leitor(o) for o in corpo.get("objetos", [])), key=lambda i: i.numero)


def versoes(headers_rr: Mapping[str, str] | None = None, headers_sn: Mapping[str, str] | None = None) -> Versoes:
    def h(headers: Mapping[str, str] | None, nome: str) -> str | None:
        if not headers:
            return None
        return next((v for k, v in headers.items() if k.lower() == nome), None)

    return Versoes(
        motorRegimeRegular=h(headers_rr, "x-calc-app-version"),
        motorSimplesNacional=h(headers_sn, "x-calc-app-version"),
        banco=h(headers_rr, "x-calc-db-version") or h(headers_sn, "x-calc-db-version"),
    )
