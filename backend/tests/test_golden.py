"""Testes de referência (golden) dos motores oficiais da Receita.

Duas camadas:

1. Sem marcador (rodam no CI, sem motores): conferem que as respostas gravadas em
   tests/golden/ batem com os números publicados na documentação oficial
   (docs/exemplos.md da calculadora-rtc-regime-regular, tag 1.7.2) e que a versão
   gravada é a mesma fixada nos Dockerfiles (princípio P5).
2. Marcador "golden" (make golden / uv run pytest -m golden): reenviam as entradas
   aos motores em execução e exigem resposta idêntica à gravada.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

import httpx
import pytest

RAIZ = Path(__file__).resolve().parents[2]
GOLDEN = Path(__file__).resolve().parent / "golden"

MOTOR_RR_URL = os.environ.get("MOTOR_RR_URL", "http://127.0.0.1:8080/api")
MOTOR_SN_URL = os.environ.get("MOTOR_SN_URL", "http://127.0.0.1:8082/api")

# caso -> (URL base do motor, arquivo de entrada, Dockerfile e ARG com a versão fixada)
CASOS = {
    "rr-exemplo-oficial": (
        MOTOR_RR_URL,
        "rr-operacao-exemplo-oficial.json",
        RAIZ / "motores" / "regime-regular" / "Dockerfile",
        "RR_TAG",
    ),
    "sn-nao-assistido-anexo-i": (
        MOTOR_SN_URL,
        "sn-operacao-nao-assistido-anexo-i.json",
        RAIZ / "motores" / "simples-nacional" / "Dockerfile",
        "SN_TAG",
    ),
}


def carregar(nome: str) -> dict[str, Any]:
    return json.loads((GOLDEN / nome).read_text(encoding="utf-8"))


def gravado(caso: str) -> dict[str, Any]:
    return carregar(f"{caso}.resposta.json")


def item(corpo: dict[str, Any], numero: int) -> dict[str, Any]:
    return next(o for o in corpo["objetos"] if o["nObj"] == numero)


def sem_type(valor: Any) -> Any:
    """Remove o campo "type" dos erros: é uma URL montada com o host de quem chamou."""
    if isinstance(valor, dict):
        return {k: sem_type(v) for k, v in valor.items() if k != "type"}
    if isinstance(valor, list):
        return [sem_type(v) for v in valor]
    return valor


def versao_fixada(dockerfile: Path, arg: str) -> str:
    achado = re.search(rf"^ARG {arg}=(\S+)$", dockerfile.read_text(encoding="utf-8"), re.MULTILINE)
    assert achado, f"ARG {arg} não encontrado em {dockerfile}"
    return achado.group(1)


# ---------------------------------------------------------------------------
# Camada 1: arquivos gravados x documentação oficial (roda no CI)


@pytest.mark.parametrize("caso", CASOS)
def test_versao_gravada_e_a_fixada_no_dockerfile(caso: str) -> None:
    _, _, dockerfile, arg = CASOS[caso]
    registro = gravado(caso)
    fixada = versao_fixada(dockerfile, arg)
    assert registro["versaoFixada"] == fixada
    assert registro["headers"]["x-calc-app-version"] == fixada
    assert registro["status"] == 200


def test_rr_gravado_bate_com_o_exemplo_oficial() -> None:
    registro = gravado("rr-exemplo-oficial")
    corpo = registro["corpo"]

    # Valores publicados em docs/exemplos.md (calculadora-rtc-regime-regular 1.7.2)
    educacao = item(corpo, 3)
    assert educacao["estadoItem"] == "CALCULO_SIMULADO"
    g = educacao["tribCalc"]["IBSCBS"]["gIBSCBS"]
    assert g["vBC"] == "1200.00"
    assert g["gCBS"]["gRed"]["pAliqEfet"] == "3.52"
    assert g["gCBS"]["vCBS"] == "42.24"
    assert g["vIBS"] == "0.48"

    com_erro = item(corpo, 4)
    assert com_erro["estadoItem"] == "INCONSISTENCIA_ENTRADA"
    assert [(e["code"], e["pointer"]) for e in com_erro["erros"]] == [("REG-011", "#/itens/3/ncm")]

    total = corpo["total"]["tribCalc"]
    assert total["ISTot"]["vIS"] == "15.00"
    assert total["IBSCBSTot"]["vBCIBSCBS"] == "1465.00"
    assert total["IBSCBSTot"]["gIBS"]["vIBS"] == "0.64"
    assert total["IBSCBSTot"]["gCBS"]["vCBS"] == "56.76"

    # A partir de 2027 as alíquotas são informadas: o motor marca o cálculo como simulado (P6).
    # Código 6 = CASO_CALCULOS_SIMULADOS (enum TipoWarningDadosSimulados do motor).
    assert registro["headers"]["x-warning-dados-simulados"] == "6"


def test_rr_gravado_tem_memoria_em_todo_item_calculado() -> None:
    corpo = gravado("rr-exemplo-oficial")["corpo"]
    calculados = [o for o in corpo["objetos"] if o["estadoItem"] in ("CALCULADO", "CALCULO_SIMULADO")]
    assert len(calculados) == 3
    for o in calculados:
        memoria = o["tribCalc"]["IBSCBS"]["memoriaCalculo"]
        assert set(memoria) == {"cbs", "ibsUF", "ibsMun"}
        assert all(texto.strip() for texto in memoria.values())


def test_sn_gravado_calcula_por_item_com_aliquotas_informadas() -> None:
    corpo = gravado("sn-nao-assistido-anexo-i")["corpo"]

    # As alíquotas efetivas foram informadas na entrada (premissa) e voltam como aplicadas.
    entrada = carregar("sn-operacao-nao-assistido-anexo-i.json")
    anexo_i = entrada["aliquotasEfetivas"]["anexoI"]
    for resolucao in corpo["resolucaoAliquotas"]["itens"]:
        assert resolucao["anexoAplicado"] == "I"
        assert (resolucao["pCBSSN"], resolucao["pIBSSN"]) == (anexo_i["pCBSSN"], anexo_i["pIBSSN"])

    for numero in (1, 2):
        o = item(corpo, numero)
        assert o["estadoItem"] == "CALCULADO"
        assert set(o["tribCalc"]["memoriaCalculo"]) == {"cbs", "ibs"}

    com_erro = item(corpo, 3)
    assert com_erro["estadoItem"] == "INCONSISTENCIA_ENTRADA"
    assert [(e["code"], e["pointer"]) for e in com_erro["erros"]] == [("VSN-047", "#/itens/2/ncm")]

    # O motor do Simples não manda header de simulação: o rótulo de premissa é nosso (P8).
    assert "x-warning-dados-simulados" not in gravado("sn-nao-assistido-anexo-i")["headers"]


# ---------------------------------------------------------------------------
# Camada 2: motor em execução x arquivos gravados (make golden)


@pytest.mark.golden
@pytest.mark.parametrize("caso", CASOS)
def test_motor_em_execucao_responde_igual_ao_gravado(caso: str) -> None:
    base, arquivo_entrada, dockerfile, arg = CASOS[caso]
    registro = gravado(caso)
    try:
        resposta = httpx.post(base + registro["rota"], json=carregar(arquivo_entrada), timeout=30)
    except httpx.ConnectError:
        pytest.fail(f"Motor fora do ar em {base}. Suba com: docker compose up -d")

    assert resposta.headers.get("x-calc-app-version") == versao_fixada(dockerfile, arg)
    assert resposta.status_code == registro["status"]
    for header, valor in registro["headers"].items():
        assert resposta.headers.get(header) == valor, header
    assert sem_type(resposta.json()) == sem_type(registro["corpo"])
