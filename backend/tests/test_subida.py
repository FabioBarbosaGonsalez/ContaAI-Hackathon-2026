"""Subida do backend no modo real (ADR 0008): migra o banco e, com ele vazio, carrega as sementes de data/demo,
para a banca já encontrar dados. Motor fora do ar ou sementes ausentes não impedem a subida."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from app import main
from app.api.dependencias import repositorio
from app.config import Configuracao, configuracao


def _empresas(cfg: Configuracao) -> int:
    with repositorio(cfg).leitura() as s:
        return len(s.empresas())


@pytest.fixture
def motores_na_subida(motores_falsos, monkeypatch: pytest.MonkeyPatch):
    """A subida cria o próprio cliente HTTP (não passa pela dependência das rotas): troca-o pelo dos falsos."""
    monkeypatch.setattr(
        main, "http_interno", lambda _timeout: httpx.AsyncClient(transport=httpx.MockTransport(motores_falsos.handler))
    )
    return motores_falsos


def test_banco_vazio_recebe_as_sementes(motores_na_subida) -> None:
    cfg = configuracao()
    asyncio.run(main.semear_se_vazio(cfg))
    assert _empresas(cfg) == 3
    assert motores_na_subida.chamadas  # as notas iniciais passaram pelos motores


def test_banco_com_empresas_nao_e_semeado_de_novo(motores_na_subida) -> None:
    cfg = configuracao()
    asyncio.run(main.semear_se_vazio(cfg))
    motores_na_subida.chamadas.clear()
    asyncio.run(main.semear_se_vazio(cfg))
    assert motores_na_subida.chamadas == [] and _empresas(cfg) == 3


def test_motores_fora_do_ar_nao_impedem_a_subida(caplog: pytest.LogCaptureFixture) -> None:
    """Sem os falsos, os motores apontam para uma porta fechada (conftest.sem_motores_reais)."""
    cfg = configuracao()
    with caplog.at_level(logging.WARNING, logger="contaai"):
        asyncio.run(main.semear_se_vazio(cfg))
    assert _empresas(cfg) == 0
    assert "motores indisponíveis" in caplog.text


def test_sementes_ausentes_nao_impedem_a_subida(
    motores_na_subida, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    cfg = configuracao().model_copy(update={"pasta_demo": tmp_path / "nao-existe"})
    with caplog.at_level(logging.WARNING, logger="contaai"):
        asyncio.run(main.semear_se_vazio(cfg))
    assert _empresas(cfg) == 0
    assert "sementes indisponíveis" in caplog.text and str(tmp_path) not in caplog.text


def test_ciclo_de_vida_no_modo_real_migra_e_semeia(motores_na_subida, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CONTAAI_MODO", "real")
    configuracao.cache_clear()

    async def subir() -> None:
        async with main.ciclo_de_vida(FastAPI()):
            pass

    asyncio.run(subir())
    assert _empresas(configuracao()) == 3


def test_ciclo_de_vida_no_modo_mock_nao_cria_o_banco() -> None:
    async def subir() -> None:
        async with main.ciclo_de_vida(FastAPI()):
            pass

    asyncio.run(subir())
    assert not configuracao().banco_caminho.exists()
