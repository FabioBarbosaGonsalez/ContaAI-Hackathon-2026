"""Motores falsos para os testes que rodam no CI (sem docker).

Respondem no formato dos motores oficiais (conferido nas respostas gravadas em tests/golden/),
mas os VALORES são fictícios, só para testar a orquestração: CBS 8,8% e IBS 0,05% + 0,05% sobre a
base no RR, e as alíquotas efetivas recebidas no SN. Não são alíquotas oficiais nem resultado dos
motores. Os testes que conferem números reais são os de marcador "golden".
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable, Iterator
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import httpx
import pytest

from app.config import Configuracao, configuracao
from app.main import app, cliente_motores
from app.motores.cache import CacheRespostas
from app.motores.cliente import ROTA_RR, ROTA_SN, ClienteMotores

C2 = Decimal("0.01")
URL_RR, URL_SN = "http://rr.interno.test/api", "http://sn.interno.test/api"
HOST_INTERNO = "http://127.0.0.1/interno"  # vai no "type" dos erros, como nos motores reais


def dinheiro(valor: Decimal) -> str:
    return str(valor.quantize(C2, ROUND_HALF_UP))


def cbs_linear(base: Decimal) -> Decimal:
    return base * Decimal("0.088")


def objeto_rr(
    numero: int, item: dict[str, Any], estado: str, cbs_de: Callable[[Decimal], Decimal] = cbs_linear
) -> dict[str, Any]:
    if estado == "INCONSISTENCIA_ENTRADA":
        erro = {
            "type": f"{HOST_INTERNO}?codigo=REG-011",
            "title": "NCM não vinculada",
            "code": "REG-011",
            "pointer": f"#/itens/{numero - 1}/ncm",
            "detail": "NCM não vinculada à classificação (teste)",
        }
        return {"nObj": numero, "estadoItem": estado, "erros": [erro]}
    if estado in ("NAO_IMPLEMENTADO", "FALHA_TECNICA"):
        return {"nObj": numero, "estadoItem": estado}
    base = Decimal(str(item["baseCalculo"]))
    reducao = item["cst"] != "000"  # fictício: CST diferente de 000 = redução de 100%
    cbs = Decimal(0) if reducao else cbs_de(base)
    uf = Decimal(0) if reducao else base * Decimal("0.0005")
    grupo_red = {"gRed": {"pRedAliq": "100.00", "pAliqEfet": "0.00"}} if reducao else {}
    trib: dict[str, Any] = {
        "IBSCBS": {
            "CST": item["cst"],
            "cClassTrib": item["cClassTrib"],
            "gIBSCBS": {
                "vBC": dinheiro(base),
                "gIBSUF": {"pIBSUF": "0.05", **grupo_red, "vIBSUF": dinheiro(uf)},
                "gIBSMun": {"pIBSMun": "0.05", **grupo_red, "vIBSMun": dinheiro(uf)},
                "vIBS": dinheiro(2 * uf.quantize(C2, ROUND_HALF_UP)),
                "gCBS": {"pCBS": "8.80", **grupo_red, "vCBS": dinheiro(cbs)},
            },
            "memoriaCalculo": {"cbs": "memória (teste)", "ibsUF": "memória (teste)", "ibsMun": "memória (teste)"},
        }
    }
    if "impostoSeletivo" in item:
        sem_incidencia = item["impostoSeletivo"]["cst"] == "200"
        trib["IS"] = {
            "CSTIS": item["impostoSeletivo"]["cst"],
            "cClassTribIS": item["impostoSeletivo"]["cClassTrib"],
            "vIS": "0.00" if sem_incidencia else dinheiro(base * Decimal("0.10")),
            "memoriaCalculo": "memória do IS (teste)",
        }
    return {"nObj": numero, "estadoItem": estado, "tribCalc": trib}


def objeto_sn(numero: int, item: dict[str, Any], estado: str, anexo: dict[str, str]) -> dict[str, Any]:
    if estado == "INCONSISTENCIA_ENTRADA":
        erro = {
            "type": f"{HOST_INTERNO}?codigo=VSN-047",
            "title": "NCM não aplicável",
            "code": "VSN-047",
            "pointer": f"#/itens/{numero - 1}/ncm",
            "detail": "NCM não vinculada (teste)",
        }
        return {"nObj": numero, "estadoItem": estado, "erros": [erro]}
    if estado == "NAO_CALCULADO":
        motivo = {"codigo": "CATIVSN_DESCONHECIDO", "descricao": "Atividade não vigente (teste)."}
        return {"nObj": numero, "estadoItem": estado, "motivoEstado": motivo}
    if estado != "CALCULADO":
        return {"nObj": numero, "estadoItem": estado}
    base = Decimal(item["baseCalculo"])
    cbs = base * Decimal(anexo["pCBSSN"]) / 100
    ibs = base * Decimal(anexo["pIBSSN"]) / 100
    return {
        "nObj": numero,
        "estadoItem": estado,
        "tribCalc": {
            "vBC": dinheiro(base),
            "pCBSSN": anexo["pCBSSN"],
            "vCBSSN": dinheiro(cbs),
            "pIBSSN": anexo["pIBSSN"],
            "vIBSSN": dinheiro(ibs),
            "IS": {"valor": item["valorImpostoSeletivo"]},
            "memoriaCalculo": {"cbs": "memória (teste)", "ibs": "memória (teste)"},
        },
    }


@dataclass
class MotoresFalsos:
    """estados_*: NCM (ou NBS) → estado do item. resposta_*: (status, corpo) para forçar uma falha."""

    estados_rr: dict[str, str] = field(default_factory=dict)
    estados_sn: dict[str, str] = field(default_factory=dict)
    simulado_rr: bool = True
    resposta_rr: tuple[int, Any] | None = None
    resposta_sn: tuple[int, Any] | None = None
    chamadas: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    cbs_rr: Callable[[Decimal], Decimal] = cbs_linear  # troque para simular um motor não linear
    cache: CacheRespostas = field(default_factory=CacheRespostas)

    def chamadas_de(self, motor: str) -> list[dict[str, Any]]:
        return [corpo for m, corpo in self.chamadas if m == motor]

    def handler(self, request: httpx.Request) -> httpx.Response:
        corpo = json.loads(request.content)
        if request.url.path.endswith(ROTA_RR):
            self.chamadas.append(("rr", corpo))
            if self.resposta_rr:
                return httpx.Response(self.resposta_rr[0], json=self.resposta_rr[1])
            objetos = [
                objeto_rr(
                    i["numero"], i, self.estados_rr.get(i.get("ncm") or i.get("nbs"), "CALCULO_SIMULADO"), self.cbs_rr
                )
                for i in corpo["itens"]
            ]
            headers = {"x-calc-app-version": "1.7.2", "x-calc-db-version": "V0073", "server": "interno"}
            if self.simulado_rr:
                headers["x-warning-dados-simulados"] = "6"
            return httpx.Response(200, json={"objetos": objetos, "total": {}}, headers=headers)
        if request.url.path.endswith(ROTA_SN):
            self.chamadas.append(("sn", corpo))
            if self.resposta_sn:
                return httpx.Response(self.resposta_sn[0], json=self.resposta_sn[1])
            anexo = next(iter(corpo["aliquotasEfetivas"].values()))
            objetos = [
                objeto_sn(i["numero"], i, self.estados_sn.get(i["ncm"], "CALCULADO"), anexo) for i in corpo["itens"]
            ]
            headers = {"x-calc-app-version": "1.0.2", "x-calc-db-version": "V0073"}
            return httpx.Response(200, json={"objetos": objetos, "total": {}}, headers=headers)
        return httpx.Response(404)


@pytest.fixture
def motores_falsos() -> Iterator[MotoresFalsos]:
    """Liga a API em modo real aos motores falsos. Desfaz tudo no fim do teste."""
    falsos = MotoresFalsos()

    async def cliente() -> AsyncIterator[ClienteMotores]:
        async with httpx.AsyncClient(transport=httpx.MockTransport(falsos.handler)) as http:
            yield ClienteMotores(http, URL_RR, URL_SN, falsos.cache)

    app.dependency_overrides[configuracao] = lambda: Configuracao(modo="real")
    app.dependency_overrides[cliente_motores] = cliente
    yield falsos
    app.dependency_overrides.clear()
