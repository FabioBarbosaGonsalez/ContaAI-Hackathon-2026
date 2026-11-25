"""Classificação (E2): candidatos de NCM e cClassTrib pelo nome do produto."""

from __future__ import annotations

import unicodedata
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query, Response

from app import mocks
from app.api import respostas
from app.api.dependencias import Cfg, Dados, marcar_mock
from app.classificacao.candidatos import buscar_candidatos
from app.contrato import BuscaNcmResposta

rotas = APIRouter(tags=["classificação"])


def _normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return sem_acento.lower().strip()


@rotas.get("/busca/ncm", response_model=BuscaNcmResposta, responses={**respostas.MOTOR, **respostas.LIMITE})
async def busca_ncm(
    cfg: Cfg,
    response: Response,
    da: Dados,
    q: Annotated[str, Query(min_length=2, max_length=60)],
    data: Annotated[date | None, Query(description="Data da vigência das classificações (padrão: hoje).")] = None,
) -> BuscaNcmResposta:
    """Candidatos de NCM e cClassTrib pelo nome do produto, para o usuário confirmar (P3)."""
    if cfg.modo != "mock":
        return await buscar_candidatos(da, q, data or date.today())
    marcar_mock(response)
    m = mocks.carregar()
    consulta = _normalizar(q)
    achada = next((r for chave, r in m.busca_ncm.items() if chave in consulta), None)
    if achada is None:
        return BuscaNcmResposta(consulta=q, candidatos=[], aviso=next(iter(m.busca_ncm.values())).aviso)
    return achada.model_copy(update={"consulta": q})
