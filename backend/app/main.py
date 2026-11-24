"""API do ContaAI.

Modo mock (CONTAAI_MODO=mock, padrão): as rotas seguem o contrato (app/contrato.py) e respondem com
os mocks gerados a partir dos motores oficiais, com o header X-ContaAI-Mock: 1.
Modo real: as rotas já implementadas calculam pelos motores (E1: POST /carrinho/calcular); as
demais respondem 501 até a sua etapa, para nunca devolver número de mock como se fosse cálculo.
GET /saude é real nos dois modos.

Rodar: cd backend && uv run uvicorn app.main:app --reload   (documentação em /docs)
"""

from __future__ import annotations

import asyncio
import unicodedata
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Annotated, Any

import httpx
from fastapi import Depends, FastAPI, File, HTTPException, Path, Query, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import mocks
from app.cenarios.presets import presets
from app.config import Configuracao, configuracao
from app.contrato import (
    AVISO_LEGAL,
    AlertasResposta,
    BuscaNcmResposta,
    CarrinhoRequisicao,
    CarrinhoResposta,
    ChatRequisicao,
    ChatResposta,
    ErroDescricao,
    ExplicarResposta,
    FalhaMotorResposta,
    Motor,
    NfeImportarResposta,
    PrecoAlvoRequisicao,
    PrecoAlvoResposta,
    PresetsResposta,
    RecusaCalculo,
    Regime,
    RegimeCompararRequisicao,
    RegimeCompararResposta,
    SaudeMotor,
    SaudeResposta,
)
from app.motores.cache import CacheRespostas
from app.motores.cliente import ClienteMotores, FalhaMotor, MotorIndisponivel, OperacaoRecusada
from app.precificacao.carrinho import calcular_carrinho
from app.precificacao.preco_alvo import CalculoRecusado, calcular_preco_alvo

app = FastAPI(
    title="ContaAI",
    version="0.1.0",
    description="Copiloto de preço e margem na reforma tributária. Toda conta vem das calculadoras oficiais da "
    f"Receita Federal; a IA só interpreta e explica. {AVISO_LEGAL}",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=configuracao().cors_origens,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
    allow_credentials=False,
)

Cfg = Annotated[Configuracao, Depends(configuracao)]

# Folga para o envelope multipart (boundary e cabeçalhos da parte) acima do tamanho do XML.
FOLGA_MULTIPART = 16 * 1024


def _cfg_atual() -> Configuracao:
    """A configuração em vigor, respeitando a troca feita pelos testes (dependency_overrides)."""
    return app.dependency_overrides.get(configuracao, configuracao)()


@app.middleware("http")
async def limitar_upload_nfe(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    """Recusa o upload grande antes de o corpo ser lido e gravado em disco pelo parser multipart.

    O Starlette não limita o tamanho de uma parte de arquivo: sem esta checagem, o arquivo inteiro
    seria recebido antes da validação na rota. O uvicorn recusa corpo maior que o Content-Length.
    """
    if request.method == "POST" and request.url.path == "/nfe/importar":
        declarado = request.headers.get("content-length")
        if declarado is None or not declarado.isdigit():
            return JSONResponse(status_code=411, content={"detail": "Envie o tamanho do arquivo (Content-Length)."})
        if int(declarado) > _cfg_atual().tamanho_max_nfe_bytes + FOLGA_MULTIPART:
            return JSONResponse(status_code=413, content={"detail": "Arquivo maior que o limite para uma NF-e."})
    return await call_next(request)


@app.exception_handler(FalhaMotor)
async def falha_motor(_: Request, exc: FalhaMotor) -> JSONResponse:
    """Falhas dos motores sem expor URL, host ou corpo do motor (ver app/motores/cliente.py)."""
    if isinstance(exc, OperacaoRecusada):
        status, erros = 422, exc.erros
    elif isinstance(exc, MotorIndisponivel):
        status, erros = 503, []
    else:
        status, erros = 502, []
    corpo = FalhaMotorResposta(detail=exc.mensagem, motor=exc.motor, erros=erros)
    return JSONResponse(status_code=status, content=corpo.model_dump(mode="json"))


@app.exception_handler(CalculoRecusado)
async def calculo_recusado(_: Request, exc: CalculoRecusado) -> JSONResponse:
    corpo = RecusaCalculo(detail=exc.detalhe, erros=exc.erros)
    return JSONResponse(status_code=422, content=corpo.model_dump(mode="json"))


RESPOSTAS_MOTOR: dict[int | str, dict[str, Any]] = {
    422: {
        "model": FalhaMotorResposta,
        "description": "O motor recusou a operação (erros do motor, ex.: VSN-015). A validação de entrada do "
        "ContaAI também responde 422, no formato padrão do FastAPI (detail como lista).",
    },
    502: {"model": FalhaMotorResposta, "description": "O motor devolveu uma resposta que o ContaAI não reconhece."},
    503: {"model": FalhaMotorResposta, "description": "Motor indisponível."},
}


def responder_mock(cfg: Cfg, response: Response) -> mocks.Mocks:
    """Rotas que ainda não calculam: mock no modo mock, 501 no modo real."""
    if cfg.modo != "mock":
        raise HTTPException(
            status_code=501, detail="Rota ainda sem cálculo real (próximas etapas). Use CONTAAI_MODO=mock."
        )
    response.headers["X-ContaAI-Mock"] = "1"
    return mocks.carregar()


Mock = Annotated[mocks.Mocks, Depends(responder_mock)]


# Um cache por processo, compartilhado entre as requisições (app/motores/cache.py).
CACHE_MOTORES = CacheRespostas(configuracao().cache_motores_itens)


async def cliente_motores(cfg: Cfg) -> AsyncIterator[ClienteMotores]:
    # trust_env=False: as chamadas aos motores nunca passam por proxy configurado no ambiente.
    async with httpx.AsyncClient(timeout=cfg.timeout_calculo_s, trust_env=False) as http:
        yield ClienteMotores(http, cfg.motor_rr_url, cfg.motor_sn_url, CACHE_MOTORES)


Motores = Annotated[ClienteMotores, Depends(cliente_motores)]


def _normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return sem_acento.lower().strip()


@app.post("/carrinho/calcular", response_model=CarrinhoResposta, tags=["cálculo"], responses=RESPOSTAS_MOTOR)
async def carrinho_calcular(
    req: CarrinhoRequisicao, cfg: Cfg, response: Response, motores: Motores
) -> CarrinhoResposta:
    if cfg.modo == "mock":
        response.headers["X-ContaAI-Mock"] = "1"
        return mocks.carregar().carrinho[req.regime]
    return await calcular_carrinho(req, motores)


RESPOSTAS_PRECO_ALVO: dict[int | str, dict[str, Any]] = {
    **RESPOSTAS_MOTOR,
    422: {
        "model": RecusaCalculo | FalhaMotorResposta,
        "description": "Sem preço possível (RecusaCalculo: margem impossível, item que o motor não calcula, "
        "sem convergência) ou recusa do motor (FalhaMotorResposta). A validação de entrada também usa 422, no "
        "formato padrão do FastAPI.",
    },
}


@app.post("/item/preco-alvo", response_model=PrecoAlvoResposta, tags=["cálculo"], responses=RESPOSTAS_PRECO_ALVO)
async def preco_alvo(req: PrecoAlvoRequisicao, cfg: Cfg, response: Response, motores: Motores) -> PrecoAlvoResposta:
    if cfg.modo == "mock":
        response.headers["X-ContaAI-Mock"] = "1"
        return mocks.carregar().preco_alvo[req.regime]
    return await calcular_preco_alvo(req, motores)


@app.get("/cenarios/presets", response_model=PresetsResposta, tags=["cenários"])
def cenarios_presets() -> PresetsResposta:
    """Presets de alíquota para 2027, só com valores de fonte verificada (ADR 0005). Igual nos dois modos."""
    return presets()


@app.post("/regime/comparar", response_model=RegimeCompararResposta, tags=["cálculo"])
def regime_comparar(req: RegimeCompararRequisicao, m: Mock) -> RegimeCompararResposta:
    return m.regime_comparar


@app.post("/nfe/importar", response_model=NfeImportarResposta, tags=["notas"])
async def nfe_importar(
    cfg: Cfg, m: Mock, arquivo: Annotated[UploadFile, File(description="XML da NF-e de compra")]
) -> NfeImportarResposta:
    # Lê no máximo o limite + 1 byte: não depende de UploadFile.size nem carrega mais que isso em memória.
    conteudo = await arquivo.read(cfg.tamanho_max_nfe_bytes + 1)
    if len(conteudo) > cfg.tamanho_max_nfe_bytes:
        raise HTTPException(status_code=413, detail="Arquivo maior que o limite para uma NF-e.")
    return m.nfe_importar


@app.get("/alertas", response_model=AlertasResposta, tags=["notas"])
def alertas(m: Mock) -> AlertasResposta:
    return m.alertas


@app.get("/busca/ncm", response_model=BuscaNcmResposta, tags=["classificação"])
def busca_ncm(m: Mock, q: Annotated[str, Query(min_length=2, max_length=60)]) -> BuscaNcmResposta:
    consulta = _normalizar(q)
    achada = next((r for chave, r in m.busca_ncm.items() if chave in consulta), None)
    if achada is None:
        return BuscaNcmResposta(consulta=q, candidatos=[], aviso=next(iter(m.busca_ncm.values())).aviso)
    return achada.model_copy(update={"consulta": q})


@app.get("/explicar/{item_id}", response_model=ExplicarResposta, tags=["explicação"])
def explicar(
    m: Mock, item_id: Annotated[str, Path(max_length=64)], regime: Regime = Regime.SIMPLES_TRADICIONAL
) -> ExplicarResposta:
    try:
        return m.explicar[item_id][regime]
    except KeyError:
        raise HTTPException(status_code=404, detail="Item não encontrado.") from None


@app.get("/erros/{codigo}", response_model=ErroDescricao, tags=["explicação"])
def erro(m: Mock, codigo: Annotated[str, Path(pattern=r"^(REG|VSN)-\d{3}$")]) -> ErroDescricao:
    try:
        return m.erros[codigo]
    except KeyError:
        raise HTTPException(status_code=404, detail="Código de erro não encontrado.") from None


@app.post("/chat", response_model=ChatResposta, tags=["agente"])
def chat(req: ChatRequisicao, m: Mock) -> ChatResposta:
    return m.chat


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


@app.get("/saude", response_model=SaudeResposta, tags=["operação"])
async def saude(cfg: Cfg) -> SaudeResposta:
    """Estado dos dois motores e versão em execução × fixada (P5). Usa as rotas locais de versão."""
    async with httpx.AsyncClient(timeout=cfg.timeout_motores_s, trust_env=False) as cli:
        motores = list(
            await asyncio.gather(
                _checar(
                    cli, Motor.REGIME_REGULAR, f"{cfg.motor_rr_url}/calculadora/dados-abertos/versao", cfg.versao_rr
                ),
                _checar(cli, Motor.SIMPLES_NACIONAL, f"{cfg.motor_sn_url}/versao", cfg.versao_sn),
            )
        )
    status = "ok" if all(m.ok and m.coerente for m in motores) else "degradado"
    return SaudeResposta(status=status, modo=cfg.modo, motores=motores)
