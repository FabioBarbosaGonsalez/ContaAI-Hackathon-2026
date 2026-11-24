"""Modelos Pydantic das respostas dos motores oficiais (E1-01).

Descrevem só os campos que o ContaAI lê. O resto da resposta é ignorado (extra="ignore"), para
que um campo novo numa versão do motor não derrube o cálculo; um campo lido com tipo errado,
ou um estado desconhecido, derruba (vira RespostaInvalida no cliente).

Formatos conferidos nas respostas gravadas em tests/golden/ (RR 1.7.2 e SN 1.0.2, banco V0073)
e em chamadas aos motores em execução (ADR 0004).
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.contrato import EstadoItem


class _Motor(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class ErroDoMotor(_Motor):
    """Erro no formato dos motores. O campo "type" é ignorado: é uma URL com o host interno do motor."""

    code: str
    title: str
    pointer: str | None = None
    detail: str | None = None


class ProblemaMotor(_Motor):
    """Corpo de um 4xx (RFC 9457) quando o motor recusa a operação inteira."""

    title: str | None = None
    detail: str | None = None
    status: int | None = None
    errors: list[ErroDoMotor] = []


# ---------------------------------------------------------------------------
# Regime Regular: POST /calculadora/observabilidade/regime-geral


class Reducao(_Motor):
    pRedAliq: Decimal
    pAliqEfet: Decimal


class GrupoCBS(_Motor):
    pCBS: Decimal
    gRed: Reducao | None = None
    vCBS: Decimal


class GrupoIBSUF(_Motor):
    pIBSUF: Decimal
    gRed: Reducao | None = None
    vIBSUF: Decimal


class GrupoIBSMun(_Motor):
    pIBSMun: Decimal
    gRed: Reducao | None = None
    vIBSMun: Decimal


class ValoresIBSCBS(_Motor):
    vBC: Decimal
    gIBSUF: GrupoIBSUF
    gIBSMun: GrupoIBSMun
    vIBS: Decimal
    gCBS: GrupoCBS


class GrupoIBSCBS(_Motor):
    CST: str
    cClassTrib: str
    gIBSCBS: ValoresIBSCBS | None = None
    memoriaCalculo: dict[str, str] | None = None


class GrupoIS(_Motor):
    CSTIS: str
    cClassTribIS: str
    vBCIS: Decimal | None = None
    pIS: Decimal | None = None
    vIS: Decimal
    memoriaCalculo: str | None = None


class TributosItemRR(_Motor):
    IBSCBS: GrupoIBSCBS | None = None
    IS: GrupoIS | None = None


class ObjetoRR(_Motor):
    nObj: int
    estadoItem: EstadoItem
    tribCalc: TributosItemRR | None = None
    erros: list[ErroDoMotor] = []


class RespostaRR(_Motor):
    objetos: list[ObjetoRR]


# ---------------------------------------------------------------------------
# Simples Nacional: POST /calculadora/observabilidade/simples-nacional/nao-assistido


class MotivoEstado(_Motor):
    codigo: str | None = None
    descricao: str | None = None


class ValorIS(_Motor):
    valor: Decimal


class TributosItemSN(_Motor):
    vBC: Decimal | None = None
    pCBSSN: Decimal | None = None
    vCBSSN: Decimal | None = None
    pIBSSN: Decimal | None = None
    vIBSSN: Decimal | None = None
    IS: ValorIS | None = None
    totalItem: Decimal | None = None
    memoriaCalculo: dict[str, str] | None = None


class ObjetoSN(_Motor):
    nObj: int
    estadoItem: EstadoItem
    motivoEstado: MotivoEstado | None = None
    tribCalc: TributosItemSN | None = None
    erros: list[ErroDoMotor] = []


class RespostaSN(_Motor):
    objetos: list[ObjetoSN]


# Header que o motor RR manda quando o cálculo usa dados simulados (ex.: alíquotas informadas
# a partir de 2027). O motor SN não manda (ADR 0001).
HEADER_SIMULADO = "x-warning-dados-simulados"
HEADER_VERSAO_APP = "x-calc-app-version"
HEADER_VERSAO_BANCO = "x-calc-db-version"

__all__ = [
    "HEADER_SIMULADO",
    "HEADER_VERSAO_APP",
    "HEADER_VERSAO_BANCO",
    "ErroDoMotor",
    "ObjetoRR",
    "ObjetoSN",
    "ProblemaMotor",
    "RespostaRR",
    "RespostaSN",
]
