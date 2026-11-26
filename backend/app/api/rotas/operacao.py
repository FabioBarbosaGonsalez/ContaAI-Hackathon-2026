"""Operação: saúde dos motores, restauração da demonstração e descrição dos tipos de problema (RFC 9457)."""

from __future__ import annotations

import asyncio
from typing import Annotated, Literal

import httpx
from fastapi import APIRouter, HTTPException, Path

from app.api import respostas
from app.api.dependencias import (
    Cfg,
    EspacoId,
    Motores,
    SessaoCookie,
    Token,
    abrir_estado,
    espacos,
    exigir_token_fora_do_espaco,
    http_interno,
    so_no_modo_real,
)
from app.api.problemas import TIPOS
from app.contrato import Motor, ProblemaMotor, RestaurarResposta, SaudeMotor, SaudeResposta, TipoProblema
from app.persistencia.repositorio import Repositorio
from app.persistencia.sementes import restaurar

rotas = APIRouter(tags=["operação"])


@rotas.post(
    "/demo/restaurar",
    response_model=RestaurarResposta,
    responses={
        **respostas.MOTOR,
        **respostas.ESTADO,
        **respostas.SO_MODO_REAL,
        503: {
            "model": ProblemaMotor,
            "description": "Motor indisponível (/problemas/motor-indisponivel), ou sementes não encontradas "
            "(/problemas/sementes-indisponiveis, CONTAAI_PASTA_DEMO).",
        },
    },
)
async def demo_restaurar(
    cfg: Cfg, motores: Motores, token: Token = None, espaco: EspacoId = None, sessao: SessaoCookie = None
) -> RestaurarResposta:
    """Volta o estado às sementes de data/demo (empresas fictícias e notas iniciais), desfazendo tudo o que foi
    importado ou aplicado. Atômico: se um motor falhar no meio, o estado fica como estava.

    Com X-ContaAI-Espaco, restaura só aquele espaço de avaliação, pela cópia do banco-modelo (sem token e sem
    chamar os motores, se o modelo já estiver montado). Sem o header, restaura a demonstração compartilhada e
    exige o token da demo quando ele está configurado. Com a sessão de uma conta (e sem o header), recusa: os
    dados de uma organização nunca são trocados pelas sementes (ADR 0015)."""
    so_no_modo_real(cfg)
    estado = await asyncio.to_thread(abrir_estado, cfg, espaco, sessao)
    if estado.sessao is not None:
        raise HTTPException(
            status_code=403,
            detail="Só a demonstração e os espaços de avaliação podem ser restaurados. Os dados da sua organização "
            "não são trocados pelos da demonstração.",
        )
    exigir_token_fora_do_espaco(cfg, token, estado)
    if estado.espaco is None:
        await restaurar(estado.repositorio, motores, cfg.pasta_demo)
    else:
        gerenciador = espacos(cfg)
        await gerenciador.garantir_modelo(motores, cfg.pasta_demo)
        await asyncio.to_thread(gerenciador.restaurar, estado.espaco.id)
    return await asyncio.to_thread(_resumo, estado.repositorio)


def _resumo(repo: Repositorio) -> RestaurarResposta:
    with repo.leitura() as s:
        return RestaurarResposta(
            empresas=len(s.empresas()), notasImportadas=s.numeros_das_notas(), alertas=len(s.alertas())
        )


async def _checar(cli: httpx.AsyncClient, motor: Motor, url: str, fixada: str) -> SaudeMotor:
    try:
        dados = (await cli.get(url)).raise_for_status().json()
    except (httpx.HTTPError, ValueError):
        return SaudeMotor(motor=motor, ok=False, versaoFixada=fixada, coerente=False, detalhe="Motor indisponível.")
    em_execucao = str(dados.get("versaoApp", ""))
    return SaudeMotor(
        motor=motor,
        ok=True,
        versaoFixada=fixada,
        versaoEmExecucao=em_execucao,
        banco=dados.get("versaoDb"),
        coerente=em_execucao == fixada,
    )


@rotas.get("/saude", response_model=SaudeResposta)
async def saude(cfg: Cfg) -> SaudeResposta:
    """Estado dos dois motores e versão em execução × fixada (P5). Usa as rotas locais de versão."""
    async with http_interno(cfg.timeout_motores_s) as cli:
        motores = list(
            await asyncio.gather(
                _checar(
                    cli, Motor.REGIME_REGULAR, f"{cfg.motor_rr_url}/calculadora/dados-abertos/versao", cfg.versao_rr
                ),
                _checar(cli, Motor.SIMPLES_NACIONAL, f"{cfg.motor_sn_url}/versao", cfg.versao_sn),
            )
        )
    status: Literal["ok", "degradado"] = "ok" if all(m.ok and m.coerente for m in motores) else "degradado"
    return SaudeResposta(status=status, modo=cfg.modo, motores=motores)


@rotas.get(
    "/problemas/{nome}",
    response_model=TipoProblema,
    responses={404: {"description": "Tipo de problema desconhecido."}},
)
def tipo_problema(nome: Annotated[str, Path(pattern=r"^[a-z-]{3,40}$")]) -> TipoProblema:
    """Descreve um tipo de problema que aparece no campo `type` das respostas de erro (RFC 9457)."""
    tipo = TIPOS.get(nome)
    if tipo is None:
        raise HTTPException(status_code=404, detail="Tipo de problema desconhecido.")
    return tipo
