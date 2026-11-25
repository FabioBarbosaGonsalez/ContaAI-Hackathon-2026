"""Agente (E2): chat com tool use. As ações voltam como propostas; nada é aplicado sem o clique do usuário."""

from __future__ import annotations

from fastapi import APIRouter, Response

from app import mocks
from app.agente.ferramentas import Ambiente
from app.agente.loop import responder_chat
from app.agente.provedor import criar_provedor
from app.api import respostas
from app.api.dependencias import Cfg, Dados, Motores, Token, exigir_token, http_interno, marcar_mock, repositorio
from app.contrato import ChatRequisicao, ChatResposta

rotas = APIRouter(tags=["agente"])


@rotas.post("/chat", response_model=ChatResposta, responses=respostas.CHAT)
async def chat(
    req: ChatRequisicao, cfg: Cfg, response: Response, motores: Motores, da: Dados, token: Token = None
) -> ChatResposta:
    """Agente com tool use (E2). As ações voltam como propostas: nada é aplicado sem o clique do usuário."""
    exigir_token(cfg, token)
    if cfg.modo == "mock":
        marcar_mock(response)
        return mocks.carregar().chat
    async with http_interno(cfg.llm_timeout_s) as http:
        provedor = criar_provedor(cfg, http)
        return await responder_chat(
            req, provedor, cfg, Ambiente(motores, da, req.contexto, repositorio=repositorio(cfg))
        )
