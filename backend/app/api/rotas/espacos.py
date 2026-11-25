"""Espaços de avaliação (D2, ADR 0010): cada avaliador cria o seu e testa tudo sem afetar os outros."""

from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, Header

from app.api import respostas
from app.api.dependencias import Cfg, Motores, espacos, so_no_modo_real
from app.contrato import EspacoResposta, ProblemaMotor
from app.nfe.importacao import agora_utc
from app.persistencia.espacos import PADRAO_ID, Espaco

rotas = APIRouter(tags=["espaços"])


def _resposta(espaco: Espaco, validade_min: int) -> EspacoResposta:
    return EspacoResposta(
        id=espaco.id,
        criadoEm=espaco.criado_em,
        expiraEm=espaco.expira_em,
        aviso=f"Espaço de avaliação com uma cópia própria dos dados fictícios da demonstração, válido por "
        f"{validade_min} minutos desde a criação. Envie o id no header X-ContaAI-Espaco; nele, importar notas, "
        "aplicar preços e restaurar não exigem o token da demo. Quem tem o id acessa o espaço.",
    )


@rotas.post(
    "/espacos",
    status_code=201,
    response_model=EspacoResposta,
    responses={
        **respostas.MOTOR,
        **respostas.LIMITE,
        **respostas.SO_MODO_REAL,
        503: {
            "model": ProblemaMotor,
            "description": "Teto de espaços atingido (/problemas/espacos-esgotados, com Retry-After), motor "
            "indisponível na montagem do banco-modelo ou sementes não encontradas.",
        },
    },
)
async def criar_espaco(cfg: Cfg, motores: Motores) -> EspacoResposta:
    """Cria um espaço de avaliação. Não exige o token: o espaço é isolado, expira e tem teto por servidor e
    limite por IP. Na primeira vez do processo, monta o banco-modelo com os motores (como a restauração)."""
    so_no_modo_real(cfg)
    gerenciador = espacos(cfg)
    await gerenciador.garantir_modelo(motores, cfg.pasta_demo)
    espaco = await asyncio.to_thread(gerenciador.criar, agora_utc())
    return _resposta(espaco, cfg.espaco_validade_min)


@rotas.get(
    "/espacos/atual",
    response_model=EspacoResposta,
    responses={**respostas.ESPACO, **respostas.SO_MODO_REAL},
)
def espaco_atual(
    cfg: Cfg,
    espaco: Annotated[str, Header(alias="X-ContaAI-Espaco", pattern=PADRAO_ID, description="Id do espaço.")],
) -> EspacoResposta:
    """O espaço do header, com a validade, para a tela mostrar quanto tempo falta."""
    so_no_modo_real(cfg)
    return _resposta(espacos(cfg).abrir(espaco, agora_utc()), cfg.espaco_validade_min)
