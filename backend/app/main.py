"""API do ContaAI: montagem da aplicação (rotas em app/api/rotas/, erros em app/api/problemas.py).

Modo mock (CONTAAI_MODO=mock, padrão): as rotas seguem o contrato (app/contrato.py) e respondem com
os mocks gerados a partir dos motores oficiais, com o header X-ContaAI-Mock: 1.
Modo real: as rotas calculam pelos motores (E1: carrinho e preço-alvo; E2: busca de NCM, explicação,
erros e chat; E3: comparação de regimes; E4: NF-e, alertas, catálogo e painel do contador, com o estado
no SQLite, ADR 0008). Nenhuma rota devolve número de mock como se fosse cálculo. GET /saude,
GET /cenarios/presets e GET /problemas/{nome} são iguais nos dois modos.
Erros: Problem Details da RFC 9457, application/problem+json (ADR 0009).

Rodar: cd backend && uv run uvicorn app.main:app --reload   (documentação em /docs)
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app.api import middlewares, problemas, registro
from app.api.dependencias import banco, http_interno, limpar_bancos_orfaos, novo_cliente_motores, repositorio
from app.api.dependencias import contas as contas_do_processo
from app.api.rotas import agente, calculo, classificacao, contas, empresa, espacos, explicacao, notas, operacao
from app.config import Configuracao, configuracao
from app.contrato import AVISO_LEGAL
from app.motores.cliente import FalhaMotor
from app.persistencia.repositorio import Repositorio
from app.persistencia.sementes import SementesInvalidas, restaurar

log = logging.getLogger("contaai")


async def semear_se_vazio(cfg: Configuracao) -> None:
    """Banco sem nenhuma empresa: carrega as sementes, para a demo (e a banca) já começar com dados.

    Se os motores ainda não estiverem de pé, o backend sobe assim mesmo e avisa no log; dá para
    restaurar depois com POST /demo/restaurar ou `uv run python -m app.persistencia.sementes`.
    """
    repo = repositorio(cfg)
    if await asyncio.to_thread(_tem_empresas, repo):
        return
    try:
        async with http_interno(cfg.timeout_calculo_s) as http:
            await restaurar(repo, novo_cliente_motores(http, cfg), cfg.pasta_demo)
        log.info("Banco vazio: sementes de data/demo carregadas.")
    except (FalhaMotor, httpx.HTTPError):
        log.warning("Banco vazio e motores indisponíveis: rode POST /demo/restaurar quando os motores subirem.")
    except SementesInvalidas as e:
        log.warning("Banco vazio e sementes indisponíveis: %s", e.mensagem)


def _tem_empresas(repo: Repositorio) -> bool:
    with repo.leitura() as s:
        return bool(s.empresas())


@asynccontextmanager
async def ciclo_de_vida(_: FastAPI) -> AsyncIterator[None]:
    registro.configurar()  # de novo na subida: vale também se o servidor reconfigurou os loggers depois do import
    cfg = configuracao()
    if cfg.modo == "real":
        banco(cfg.banco_caminho)  # migra na subida: um esquema alterado impede o backend de subir
        contas_do_processo(cfg)  # idem para o contas.db (ADR 0015)
        await asyncio.to_thread(limpar_bancos_orfaos, cfg)  # LGPD: organização excluída não deixa banco no disco
        if cfg.semear_ao_subir:
            await semear_se_vazio(cfg)
    yield


registro.configurar()  # logs sem dado pessoal (app.api.registro): sem o log de acesso do uvicorn
_DOCS = configuracao().docs_publica

app = FastAPI(
    title="ContaAI",
    lifespan=ciclo_de_vida,
    version="0.1.0",
    description="Copiloto de preço e margem na reforma tributária. Toda conta vem das calculadoras oficiais da "
    f"Receita Federal; a IA só interpreta e explica. {AVISO_LEGAL}",
    # CONTAAI_DOCS_PUBLICA=false no deploy (ADR 0011): o Swagger carrega scripts de uma CDN, e na mesma origem
    # da tela eles alcançariam o que a tela guarda no navegador. O contrato continua em docs/contrato/openapi.json.
    docs_url="/docs" if _DOCS else None,
    redoc_url="/redoc" if _DOCS else None,
    openapi_url="/openapi.json" if _DOCS else None,
    # A telemetria do FastAPI (OpenTelemetry) grava, pela documentação dela, as mensagens das exceções, as pilhas e o
    # corpo lido. Hoje ela não liga, porque não há SDK nem exportador instalado; desligada aqui, nem a variável
    # FASTAPI_OTEL_AUTO_CONFIGURE nem um SDK instalado depois a ligam sem uma decisão (logs sem dado pessoal, C3-B).
    telemetry={"tracing": False, "metrics": False, "logs": False, "operation_spans": False, "auto_configure": False},
)

# Ordem: cada middleware adicionado fica POR FORA dos anteriores. De fora para dentro: log de acesso, cabeçalhos
# de segurança, Host, CORS, Origin, limite por IP, tamanho do corpo e o 500 do erro não tratado. O CORS fica por
# fora dos limites para que um 403, 411, 413 ou 429 também leve Access-Control-Allow-Origin e o frontend consiga ler
# o erro; o 500 fica por dentro de todos pelo mesmo motivo (C3-B, etapa 9).
app.add_middleware(middlewares.ErroNaoTratado)
app.add_middleware(BaseHTTPMiddleware, dispatch=middlewares.limitar_corpo)
app.add_middleware(BaseHTTPMiddleware, dispatch=middlewares.limitar_requisicoes)
app.add_middleware(BaseHTTPMiddleware, dispatch=middlewares.verificar_origem)
app.add_middleware(
    CORSMiddleware,
    allow_origins=configuracao().cors_origens,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "X-ContaAI-Token", "X-ContaAI-Espaco"],
    # Sem isto, o JavaScript de outra origem não lê estes headers (só os da lista segura do padrão Fetch).
    expose_headers=["Retry-After", "X-ContaAI-Mock"],
    # Sem credenciais entre origens: o cookie da sessão só anda na mesma origem (proxy /api, ADR 0015).
    allow_credentials=False,
)
app.add_middleware(BaseHTTPMiddleware, dispatch=middlewares.verificar_host)
app.add_middleware(BaseHTTPMiddleware, dispatch=middlewares.cabecalhos_de_seguranca)
app.add_middleware(BaseHTTPMiddleware, dispatch=registro.registrar_acesso)

problemas.registrar(app)

for modulo in (calculo, notas, empresa, espacos, contas, classificacao, explicacao, agente, operacao):
    app.include_router(modulo.rotas)


def _openapi() -> dict[str, Any]:
    if app.openapi_schema is None:
        app.openapi_schema = problemas.ajustar_openapi(FastAPI.openapi(app))
    return app.openapi_schema


app.openapi = _openapi  # type: ignore[method-assign]
