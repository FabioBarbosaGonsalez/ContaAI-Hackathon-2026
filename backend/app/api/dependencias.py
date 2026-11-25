"""Dependências das rotas: configuração, clientes dos motores e dos dados abertos, banco e token da demo."""

from __future__ import annotations

from collections.abc import AsyncIterator
from functools import lru_cache
from pathlib import Path
from typing import Annotated

import httpx
from fastapi import Depends, Header, HTTPException, Response

from app.config import Configuracao, configuracao
from app.motores.cache import CacheRespostas
from app.motores.cliente import ClienteMotores
from app.motores.dados_abertos import CacheConsultas, DadosAbertos
from app.persistencia.banco import Banco
from app.persistencia.repositorio import Repositorio
from app.seguranca import token_confere

Cfg = Annotated[Configuracao, Depends(configuracao)]
Token = Annotated[str | None, Header(alias="X-ContaAI-Token")]

# Um cache por processo, compartilhado entre as requisições (app/motores/cache.py).
CACHE_MOTORES = CacheRespostas(configuracao().cache_motores_itens)
# Tabelas oficiais dos dados abertos (iguais para todos): um cache por processo.
CACHE_DADOS_ABERTOS = CacheConsultas()


def novo_cliente_motores(http: httpx.AsyncClient, cfg: Configuracao) -> ClienteMotores:
    return ClienteMotores(http, cfg.motor_rr_url, cfg.motor_sn_url, CACHE_MOTORES)


def http_interno(timeout_s: float) -> httpx.AsyncClient:
    """Cliente HTTP para os motores e o provedor: trust_env=False, nunca passa por proxy do ambiente."""
    return httpx.AsyncClient(timeout=timeout_s, trust_env=False)


async def cliente_motores(cfg: Cfg) -> AsyncIterator[ClienteMotores]:
    async with http_interno(cfg.timeout_calculo_s) as http:
        yield novo_cliente_motores(http, cfg)


async def dados_abertos(cfg: Cfg) -> AsyncIterator[DadosAbertos]:
    async with http_interno(cfg.timeout_calculo_s) as http:
        yield DadosAbertos(http, cfg.motor_rr_url, cfg.motor_sn_url, CACHE_DADOS_ABERTOS)


Motores = Annotated[ClienteMotores, Depends(cliente_motores)]
Dados = Annotated[DadosAbertos, Depends(dados_abertos)]


@lru_cache
def banco(caminho: Path) -> Banco:
    """Um Banco por arquivo, migrado na primeira vez que é pedido (inclusive na subida, no modo real)."""
    b = Banco(caminho)
    b.migrar()
    return b


def repositorio(cfg: Configuracao) -> Repositorio:
    """Chamado só no ramo do modo real: no modo mock nenhuma rota cria o arquivo do banco."""
    return Repositorio(banco(cfg.banco_caminho))


def exigir_token(cfg: Configuracao, token: str | None) -> None:
    """Rotas que mudam o estado compartilhado da demo (e o chat) exigem o token, quando ele está configurado."""
    if not token_confere(cfg.token_demo, token):
        raise HTTPException(status_code=401, detail="Token da demo ausente ou inválido.")


def so_no_modo_real(cfg: Configuracao, detalhe: str = "Esta rota muda o estado e só funciona no modo real.") -> None:
    if cfg.modo != "real":
        raise HTTPException(status_code=501, detail=detalhe)


def marcar_mock(response: Response) -> None:
    """Toda resposta montada a partir dos mocks leva X-ContaAI-Mock: 1."""
    response.headers["X-ContaAI-Mock"] = "1"
