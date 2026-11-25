"""Cálculo: carrinho (E1), preço-alvo (E1), presets de 2027 (E1) e comparação de regimes (E3)."""

from __future__ import annotations

from fastapi import APIRouter, Response

from app import mocks
from app.api import respostas
from app.api.dependencias import Cfg, Motores, marcar_mock
from app.cenarios.presets import presets
from app.contrato import (
    CarrinhoRequisicao,
    CarrinhoResposta,
    PrecoAlvoRequisicao,
    PrecoAlvoResposta,
    PresetsResposta,
    RegimeCompararRequisicao,
    RegimeCompararResposta,
)
from app.precificacao.carrinho import calcular_carrinho
from app.precificacao.preco_alvo import calcular_preco_alvo
from app.regime.comparar import comparar_regimes

rotas = APIRouter()


@rotas.post("/carrinho/calcular", response_model=CarrinhoResposta, tags=["cálculo"], responses=respostas.MOTOR)
async def carrinho_calcular(
    req: CarrinhoRequisicao, cfg: Cfg, response: Response, motores: Motores
) -> CarrinhoResposta:
    if cfg.modo == "mock":
        marcar_mock(response)
        return mocks.carregar().carrinho[req.regime]
    return await calcular_carrinho(req, motores)


@rotas.post("/item/preco-alvo", response_model=PrecoAlvoResposta, tags=["cálculo"], responses=respostas.CALCULO)
async def preco_alvo(req: PrecoAlvoRequisicao, cfg: Cfg, response: Response, motores: Motores) -> PrecoAlvoResposta:
    if cfg.modo == "mock":
        marcar_mock(response)
        return mocks.carregar().preco_alvo[req.regime]
    return await calcular_preco_alvo(req, motores)


@rotas.get("/cenarios/presets", response_model=PresetsResposta, tags=["cenários"])
def cenarios_presets() -> PresetsResposta:
    """Presets de alíquota para 2027, só com valores de fonte verificada (ADR 0005). Igual nos dois modos."""
    return presets()


@rotas.post("/regime/comparar", response_model=RegimeCompararResposta, tags=["cálculo"], responses=respostas.CALCULO)
async def regime_comparar(
    req: RegimeCompararRequisicao, cfg: Cfg, response: Response, motores: Motores
) -> RegimeCompararResposta:
    """Simples tradicional × híbrido para uma venda a um cliente do regime regular (E3, ADR 0007)."""
    if cfg.modo == "mock":
        marcar_mock(response)
        return mocks.carregar().regime_comparar
    return await comparar_regimes(req, motores)
