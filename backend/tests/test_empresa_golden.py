"""Referências da empresa própria contra os motores em execução (C3-B, ADR 0017). Marcador golden: make golden.

Conferem que o formato lido em app/motores/dados_abertos.py é o dos motores fixados (RR 1.7.2 e SN 1.0.2) e que o
filtro das atividades deixa só as que saem em NF-e, com anexo e sem fator R.
"""

from __future__ import annotations

import asyncio
import os
from datetime import date

import httpx
import pytest

from app import cadastro
from app.motores.dados_abertos import CacheConsultas, DadosAbertos

pytestmark = pytest.mark.golden

MOTOR_RR_URL = os.environ.get("MOTOR_RR_URL", "http://127.0.0.1:8080/api")
MOTOR_SN_URL = os.environ.get("MOTOR_SN_URL", "http://127.0.0.1:8082/api")
VERSOES = cadastro.Versoes(rr="1.7.2", sn="1.0.2")
DATA_DO_CENARIO = date(2027, 3, 16)


async def _com_motores() -> DadosAbertos:
    return DadosAbertos(httpx.AsyncClient(timeout=30, trust_env=False), MOTOR_RR_URL, MOTOR_SN_URL, CacheConsultas())


def test_ufs_e_municipios_do_motor_rr() -> None:
    async def consultar() -> tuple[cadastro.UfsResposta, cadastro.MunicipiosResposta]:
        da = await _com_motores()
        async with da.http:
            return await cadastro.ufs(da, VERSOES), await cadastro.municipios(da, "RS", VERSOES)

    ufs, municipios = asyncio.run(consultar())
    assert next(u for u in ufs.ufs if u.sigla == "RS").codigo == 43
    assert len(ufs.ufs) == 27 and "EX" not in {u.sigla for u in ufs.ufs}  # 26 estados e o DF; sem o exterior
    # Porto Alegre: o município da Serra Azul (data/demo), com o código do IBGE.
    assert any(m.codigo == 4314902 and m.nome == "Porto Alegre" for m in municipios.municipios)


def test_atividades_que_o_contaai_calcula() -> None:
    async def consultar() -> cadastro.AtividadesResposta:
        da = await _com_motores()
        async with da.http:
            return await cadastro.atividades(da, DATA_DO_CENARIO, VERSOES)

    lista = asyncio.run(consultar())
    assert [(a.cAtivSN, a.anexo) for a in lista.atividades] == [("01", "I"), ("02", "I"), ("03", "II"), ("04", "II")]
