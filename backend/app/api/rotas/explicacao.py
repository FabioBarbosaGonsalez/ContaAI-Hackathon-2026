"""Explicação (E2): memória de cálculo, fundamentação e premissas de um item, e os códigos de erro dos motores."""

from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query, Response

from app import mocks
from app.api import respostas
from app.api.dependencias import (
    Cfg,
    Dados,
    EspacoId,
    Motores,
    SessaoCookie,
    abrir_estado,
    marcar_mock,
    so_no_modo_real,
)
from app.config import Configuracao
from app.contrato import PADRAO_ID_ITEM, ErroDescricao, ExplicarRequisicao, ExplicarResposta, Regime
from app.dados_demo import carregar_distribuidora
from app.empresa import requisicao_explicar
from app.explicacao import explicar_item
from app.nfe import consultas

rotas = APIRouter(tags=["explicação"])

NAO_ENCONTRADO: respostas.Respostas = {404: {"description": "Item ou código não encontrado."}}


def requisicao_do_estado(
    cfg: Configuracao, espaco: str | None, cnpj: str | None, item_id: str, regime: Regime, sessao: str | None = None
) -> ExplicarRequisicao:
    """O item do catálogo da empresa como está no estado (preço atual, classificação corrigida), com o cenário
    dela e no lote de referência (ADR 0011). Sem `cnpj`, vale a distribuidora da demonstração. Só as empresas
    que quem chama alcança (ADR 0015)."""
    estado = abrir_estado(cfg, espaco, sessao)
    alvo = cnpj or carregar_distribuidora(cfg.pasta_demo).empresa.cnpj
    estado.exigir_empresa(alvo)
    achado = consultas.item_da_empresa(estado.repositorio, alvo, item_id)
    return requisicao_explicar(achado.empresa.empresa, achado.empresa.cenario, achado.item, achado.preco_atual, regime)


@rotas.get(
    "/explicar/{item_id}",
    response_model=ExplicarResposta,
    responses={**respostas.MOTOR, **NAO_ENCONTRADO, **respostas.LIMITE, **respostas.ESPACO},
)
async def explicar(
    cfg: Cfg,
    response: Response,
    motores: Motores,
    da: Dados,
    item_id: Annotated[str, Path(pattern=PADRAO_ID_ITEM)],
    regime: Regime = Regime.SIMPLES_TRADICIONAL,
    cnpj: Annotated[
        str | None, Query(pattern=r"^\d{14}$", description="Empresa do item. Sem ele, a distribuidora da demo.")
    ] = None,
    espaco: EspacoId = None,
    sessao: SessaoCookie = None,
) -> ExplicarResposta:
    """Um item do catálogo da empresa, como está no estado: preço atual, classificação atual e o lote de
    referência (o mesmo cálculo da linha do catálogo). Para um item fora do catálogo, POST /explicar."""
    if cfg.modo != "mock":
        req = await asyncio.to_thread(requisicao_do_estado, cfg, espaco, cnpj, item_id, regime, sessao)
        return await explicar_item(req, motores, da)
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
