"""Explicação (E2): memória de cálculo, fundamentação e premissas de um item, e os códigos de erro dos motores."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path as Caminho
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Response

from app import mocks
from app.api import respostas
from app.api.dependencias import Cfg, Dados, Motores, marcar_mock, so_no_modo_real
from app.contrato import ErroDescricao, ExplicarRequisicao, ExplicarResposta, Regime
from app.dados_demo import PASTA_DEMO, carregar_distribuidora
from app.empresa import item_entrada, operacao_da_empresa
from app.explicacao import explicar_item

rotas = APIRouter(tags=["explicação"])

NAO_ENCONTRADO: respostas.Respostas = {404: {"description": "Item ou código não encontrado."}}


def requisicao_demo(item_id: str, regime: Regime, pasta: Caminho = PASTA_DEMO) -> ExplicarRequisicao:
    """Item do catálogo de demonstração com o cenário da demo (data/demo, dados fictícios, P10)."""
    demo = carregar_distribuidora(pasta)
    cat = next((i for i in demo.catalogo if i.id == item_id), None)
    if cat is None:
        raise HTTPException(status_code=404, detail="Item não encontrado.")
    return ExplicarRequisicao(
        **operacao_da_empresa(demo.empresa, demo.cenario),
        regime=regime,
        item=item_entrada(cat, Decimal(1), cat.precoVenda),
    )


@rotas.get(
    "/explicar/{item_id}",
    response_model=ExplicarResposta,
    responses={**respostas.MOTOR, **NAO_ENCONTRADO, **respostas.LIMITE},
)
async def explicar(
    cfg: Cfg,
    response: Response,
    motores: Motores,
    da: Dados,
    item_id: Annotated[str, Path(max_length=64)],
    regime: Regime = Regime.SIMPLES_TRADICIONAL,
) -> ExplicarResposta:
    """Só o catálogo de demonstração (uma unidade pelo preço de venda da demo). Para outro item, POST /explicar."""
    if cfg.modo != "mock":
        return await explicar_item(requisicao_demo(item_id, regime, cfg.pasta_demo), motores, da)
    marcar_mock(response)
    try:
        return mocks.carregar().explicar[item_id][regime]
    except KeyError:
        raise HTTPException(status_code=404, detail="Item não encontrado.") from None


@rotas.post(
    "/explicar",
    response_model=ExplicarResposta,
    responses={**respostas.MOTOR, **respostas.SO_MODO_REAL, **respostas.LIMITE},
)
async def explicar_post(req: ExplicarRequisicao, cfg: Cfg, motores: Motores, da: Dados) -> ExplicarResposta:
    """Memória de cálculo, fundamentação e premissas de qualquer item. Não tem mock: 501 no modo mock."""
    so_no_modo_real(cfg, "POST /explicar só calcula no modo real (CONTAAI_MODO=real).")
    return await explicar_item(req, motores, da)


@rotas.get(
    "/erros/{codigo}",
    response_model=ErroDescricao,
    responses={**respostas.MOTOR, **NAO_ENCONTRADO, **respostas.LIMITE},
)
async def erro(
    cfg: Cfg, response: Response, da: Dados, codigo: Annotated[str, Path(pattern=r"^(REG|VSN)-\d{3}$")]
) -> ErroDescricao:
    if cfg.modo != "mock":
        achado = await da.erro(codigo)
        if achado is None:
            raise HTTPException(status_code=404, detail="Código de erro não encontrado.")
        motor, e = achado
        return ErroDescricao(codigo=e.codigo, titulo=e.titulo, descricao=e.descricao, motor=motor)
    marcar_mock(response)
    try:
        return mocks.carregar().erros[codigo]
    except KeyError:
        raise HTTPException(status_code=404, detail="Código de erro não encontrado.") from None
