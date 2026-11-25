"""Gera o índice local de busca de NCM (E2-02) a partir dos dados abertos do motor RR em execução.

O motor só consulta NCM por código (ADR 0003): não há busca por texto. Este script lê a lista de
NCMs vigentes e, para cada uma, a hierarquia oficial (posição, subposição, item e subitem), porque
a lista traz só o último nível ("-- Outros"). O resultado vai para app/classificacao/, versionado,
com a versão do banco do motor de onde saiu. Nada é digitado à mão.

Uso (com os motores de pé: docker compose up -d):
    cd backend && uv run python scripts/gerar_indice_ncm.py [--data 2027-03-16]

Rodar de novo ao trocar a versão fixada do motor RR (P5), no mesmo PR.
"""

from __future__ import annotations

import argparse
import asyncio
import gzip
import json
import os
import sys
from datetime import date
from pathlib import Path

import httpx

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "backend"))
from app.classificacao.indice import ARQUIVO_INDICE  # noqa: E402
from app.config import Configuracao  # noqa: E402
from app.motores.dados_abertos import DA, DadosAbertos  # noqa: E402

MOTOR_RR_URL = os.environ.get("MOTOR_RR_URL", "http://127.0.0.1:8080/api")


async def gerar(data: date) -> dict:
    async with httpx.AsyncClient(timeout=60, trust_env=False) as http:
        versao = (await http.get(MOTOR_RR_URL + DA + "/versao")).raise_for_status().json()
        fixada = Configuracao().versao_rr
        if versao.get("versaoApp") != fixada:
            sys.exit(f"Motor RR em execução é {versao.get('versaoApp')!r}, mas a versão fixada é {fixada}.")
        vigentes = (
            (await http.get(MOTOR_RR_URL + DA + "/ncm/vigentes", params={"data": data.isoformat()}))
            .raise_for_status()
            .json()
        )
        da = DadosAbertos(http, MOTOR_RR_URL, "", cache=None)
        da.cache.max_itens = 0  # sem cache: cada NCM é consultada uma vez
        infos = await asyncio.gather(*(da.ncm(v["ncm"], data) for v in vigentes))

    itens = []
    for v, info in zip(vigentes, infos, strict=True):
        if info is None:
            continue
        itens.append(
            {
                "ncm": v["ncm"],
                "descricao": info.hierarquia(),
                "capitulo": (info.capitulo or "").rstrip("."),
                "is": info.tributadoPeloImpostoSeletivo,
            }
        )
    return {
        "fonte": f"GET {DA}/ncm/vigentes e {DA}/ncm (motor RR {versao['versaoApp']}, banco {versao['versaoDb']})",
        "versaoApp": versao["versaoApp"],
        "versaoDb": versao["versaoDb"],
        "dataVigencia": data.isoformat(),
        "ncms": itens,
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--data", type=date.fromisoformat, default=date(2027, 3, 16), help="Data de vigência das NCMs.")
    args = p.parse_args()
    indice = asyncio.run(gerar(args.data))
    conteudo = json.dumps(indice, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    # mtime=0: o mesmo conteúdo gera sempre o mesmo arquivo (diff limpo no git).
    ARQUIVO_INDICE.write_bytes(gzip.compress(conteudo, mtime=0))
    print(f"{len(indice['ncms'])} NCMs em {ARQUIVO_INDICE.relative_to(RAIZ)} ({ARQUIVO_INDICE.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
