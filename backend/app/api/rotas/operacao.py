"""Operação: saúde dos motores, restauração da demonstração e descrição dos tipos de problema (RFC 9457)."""

from __future__ import annotations

import asyncio
from typing import Annotated, Literal

import httpx
from fastapi import APIRouter, HTTPException, Path

from app.api import respostas
from app.api.dependencias import Cfg, Motores, Token, exigir_token, http_interno, repositorio, so_no_modo_real
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
async def demo_restaurar(cfg: Cfg, motores: Motores, token: Token = None) -> RestaurarResposta:
    """Volta o estado às sementes de data/demo (empresas fictícias e notas iniciais), desfazendo tudo o que foi
    importado ou aplicado. Atômico: se um motor falhar no meio, o estado fica como estava. Exige o token da
    demo quando ele está configurado."""
    so_no_modo_real(cfg)
    exigir_token(cfg, token)
    repo = repositorio(cfg)
    recibos = await restaurar(repo, motores, cfg.pasta_demo)
    empresas, alertas = await asyncio.to_thread(_contagem, repo)
    return RestaurarResposta(empresas=empresas, notasImportadas=[r.nota.numero for r in recibos], alertas=alertas)


def _contagem(repo: Repositorio) -> tuple[int, int]:
    with repo.leitura() as s:
        return len(s.empresas()), len(s.alertas())


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
