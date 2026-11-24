"""API do ContaAI.

Etapa 0: as rotas seguem o contrato (app/contrato.py) e respondem com os mocks gerados a partir
dos motores oficiais (CONTAAI_MODO=mock, padrão). O cálculo real entra a partir da Etapa 1.
GET /saude é real nos dois modos.

Rodar: cd backend && uv run uvicorn app.main:app --reload   (documentação em /docs)
"""

from __future__ import annotations

import unicodedata
from typing import Annotated

import httpx
from fastapi import Depends, FastAPI, File, HTTPException, Path, Query, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from app import mocks
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
    Motor,
    NfeImportarResposta,
    PrecoAlvoRequisicao,
    PrecoAlvoResposta,
    Regime,
    RegimeCompararRequisicao,
    RegimeCompararResposta,
    SaudeMotor,
    SaudeResposta,
)

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


def responder_mock(cfg: Cfg, response: Response) -> mocks.Mocks:
    """Na Etapa 0 só o modo mock existe; o header deixa claro que não é cálculo real."""
    if cfg.modo != "mock":
        raise HTTPException(status_code=501, detail="Cálculo real a partir da Etapa 1. Use CONTAAI_MODO=mock.")
    response.headers["X-ContaAI-Mock"] = "1"
    return mocks.carregar()


Mock = Annotated[mocks.Mocks, Depends(responder_mock)]


def _normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return sem_acento.lower().strip()


@app.post("/carrinho/calcular", response_model=CarrinhoResposta, tags=["cálculo"])
def carrinho_calcular(req: CarrinhoRequisicao, m: Mock) -> CarrinhoResposta:
    return m.carrinho[req.regime]


@app.post("/item/preco-alvo", response_model=PrecoAlvoResposta, tags=["cálculo"])
def preco_alvo(req: PrecoAlvoRequisicao, m: Mock) -> PrecoAlvoResposta:
    return m.preco_alvo[req.regime]


@app.post("/regime/comparar", response_model=RegimeCompararResposta, tags=["cálculo"])
def regime_comparar(req: RegimeCompararRequisicao, m: Mock) -> RegimeCompararResposta:
    return m.regime_comparar


@app.post("/nfe/importar", response_model=NfeImportarResposta, tags=["notas"])
def nfe_importar(
    cfg: Cfg, m: Mock, arquivo: Annotated[UploadFile, File(description="XML da NF-e de compra")]
) -> NfeImportarResposta:
    if arquivo.size is not None and arquivo.size > cfg.tamanho_max_nfe_bytes:
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
    async with httpx.AsyncClient(timeout=cfg.timeout_motores_s) as cli:
        motores = [
            await _checar(
                cli, Motor.REGIME_REGULAR, f"{cfg.motor_rr_url}/calculadora/dados-abertos/versao", cfg.versao_rr
            ),
            await _checar(cli, Motor.SIMPLES_NACIONAL, f"{cfg.motor_sn_url}/versao", cfg.versao_sn),
        ]
    status = "ok" if all(m.ok and m.coerente for m in motores) else "degradado"
    return SaudeResposta(status=status, modo=cfg.modo, motores=motores)
