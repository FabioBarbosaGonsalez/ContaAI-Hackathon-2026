"""Grava as respostas de referência (golden) dos motores oficiais em execução.

Uso (com os motores de pé: docker compose up -d):
    cd backend && uv run python scripts/gravar_golden.py

Só deve ser rodado ao trocar a versão fixada de um motor (princípio P5), em PR próprio.
Os testes em tests/test_golden.py comparam o motor em execução com estes arquivos.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date
from pathlib import Path

import httpx

PASTA = Path(__file__).resolve().parent.parent / "tests" / "golden"

MOTOR_RR_URL = os.environ.get("MOTOR_RR_URL", "http://127.0.0.1:8080/api")
MOTOR_SN_URL = os.environ.get("MOTOR_SN_URL", "http://127.0.0.1:8082/api")

# Só os headers que importam para o produto: aviso de simulação e versões em execução.
HEADERS_RELEVANTES = ("x-warning-dados-simulados", "x-calc-app-version", "x-calc-db-version")

# (nome do caso, URL base, rota, arquivo de entrada, versão fixada do motor)
CASOS = [
    (
        "rr-exemplo-oficial",
        MOTOR_RR_URL,
        "/calculadora/observabilidade/regime-geral",
        "rr-operacao-exemplo-oficial.json",
        "1.7.2",
    ),
    (
        "sn-nao-assistido-anexo-i",
        MOTOR_SN_URL,
        "/calculadora/observabilidade/simples-nacional/nao-assistido",
        "sn-operacao-nao-assistido-anexo-i.json",
        "1.0.2",
    ),
]


def gravar(nome: str, base: str, rota: str, arquivo_entrada: str, versao_fixada: str) -> None:
    entrada = json.loads((PASTA / arquivo_entrada).read_text(encoding="utf-8"))
    resposta = httpx.post(base + rota, json=entrada, timeout=30)
    headers = {h: resposta.headers[h] for h in HEADERS_RELEVANTES if h in resposta.headers}

    versao_em_execucao = headers.get("x-calc-app-version", "")
    if not versao_em_execucao.startswith(versao_fixada):
        sys.exit(f"{nome}: motor em execução é {versao_em_execucao!r}, mas a versão fixada é {versao_fixada}.")

    registro = {
        "caso": nome,
        "rota": rota,
        "versaoFixada": versao_fixada,
        "gravadoEm": date.today().isoformat(),
        "status": resposta.status_code,
        "headers": headers,
        "corpo": resposta.json(),
    }
    destino = PASTA / f"{nome}.resposta.json"
    destino.write_text(json.dumps(registro, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{nome}: HTTP {resposta.status_code} gravado em {destino.name}")


def main() -> None:
    for caso in CASOS:
        if not (PASTA / caso[3]).exists():
            print(f"{caso[0]}: entrada {caso[3]} ainda não existe, pulando")
            continue
        gravar(*caso)


if __name__ == "__main__":
    main()
