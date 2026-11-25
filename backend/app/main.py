"""API do ContaAI.

Modo mock (CONTAAI_MODO=mock, padrão): as rotas seguem o contrato (app/contrato.py) e respondem com
os mocks gerados a partir dos motores oficiais, com o header X-ContaAI-Mock: 1.
Modo real: as rotas calculam pelos motores (E1: carrinho e preço-alvo; E2: busca de NCM, explicação,
erros e chat; E3: comparação de regimes; E4: NF-e, alertas, catálogo e painel do contador, com o estado
no SQLite, ADR 0008). Nenhuma rota devolve número de mock como se fosse cálculo. GET /saude e
GET /cenarios/presets são iguais nos dois modos.

Rodar: cd backend && uv run uvicorn app.main:app --reload   (documentação em /docs)
"""

from __future__ import annotations

import asyncio
import logging
import unicodedata
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import date
from decimal import Decimal
from functools import lru_cache
from pathlib import Path as Caminho
from typing import Annotated, Any

import httpx
from fastapi import Depends, FastAPI, File, Header, HTTPException, Path, Query, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import mocks
from app.agente.ferramentas import Ambiente
from app.agente.loop import responder_chat
from app.agente.provedor import ProvedorFalhou, criar_provedor
from app.cenarios.presets import presets
from app.classificacao.candidatos import buscar_candidatos
from app.config import Configuracao, configuracao
from app.contrato import (
    AVISO_LEGAL,
    AlertasResposta,
    AplicarAlertaResposta,
    BuscaNcmResposta,
    CarrinhoRequisicao,
    CarrinhoResposta,
    CatalogoResposta,
    ChatRequisicao,
    ChatResposta,
    ErroDescricao,
    ExplicarRequisicao,
    ExplicarResposta,
    FalhaMotorResposta,
    Motor,
    NfeImportarResposta,
    PainelContadorResposta,
    PrecoAlvoRequisicao,
    PrecoAlvoResposta,
    PresetsResposta,
    RecusaCalculo,
    Regime,
    RegimeCompararRequisicao,
    RegimeCompararResposta,
    RestaurarResposta,
    SaudeMotor,
    SaudeResposta,
)
from app.dados_demo import PASTA_DEMO, carregar_distribuidora
from app.empresa import item_entrada, operacao_da_empresa
from app.explicacao import explicar_item
from app.motores.cache import CacheRespostas
from app.motores.cliente import ClienteMotores, FalhaMotor, MotorIndisponivel, OperacaoRecusada
from app.motores.dados_abertos import CacheConsultas, DadosAbertos
from app.nfe import consultas
from app.nfe.importacao import NotaRecusada, agora_utc, importar_nota
from app.nfe.leitor import NotaInvalida
from app.persistencia.banco import Banco
from app.persistencia.repositorio import Repositorio
from app.persistencia.sementes import SementesInvalidas, restaurar
from app.precificacao.carrinho import calcular_carrinho
from app.precificacao.preco_alvo import CalculoRecusado, calcular_preco_alvo
from app.regime.comparar import comparar_regimes
from app.seguranca import LimitadorPorIp, token_confere

log = logging.getLogger("contaai")


@lru_cache
def _banco(caminho: Caminho) -> Banco:
    """Um Banco por arquivo, migrado na primeira vez que é pedido (inclusive na subida, no modo real)."""
    banco = Banco(caminho)
    banco.migrar()
    return banco


async def semear_se_vazio(cfg: Configuracao) -> None:
    """Banco sem nenhuma empresa: carrega as sementes, para a demo (e a banca) já começar com dados.

    Se os motores ainda não estiverem de pé, o backend sobe assim mesmo e avisa no log; dá para
    restaurar depois com POST /demo/restaurar ou `uv run python -m app.persistencia.sementes`.
    """
    repo = Repositorio(_banco(cfg.banco_caminho))
    if await asyncio.to_thread(_tem_empresas, repo):
        return
    try:
        async with httpx.AsyncClient(timeout=cfg.timeout_calculo_s, trust_env=False) as http:
            motores = ClienteMotores(http, cfg.motor_rr_url, cfg.motor_sn_url, CACHE_MOTORES)
            await restaurar(repo, motores, cfg.pasta_demo)
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
    cfg = configuracao()
    if cfg.modo == "real":
        _banco(cfg.banco_caminho)  # migra na subida: um esquema alterado impede o backend de subir
        if cfg.semear_ao_subir:
            await semear_se_vazio(cfg)
    yield


app = FastAPI(
    title="ContaAI",
    lifespan=ciclo_de_vida,
    version="0.1.0",
    description="Copiloto de preço e margem na reforma tributária. Toda conta vem das calculadoras oficiais da "
    f"Receita Federal; a IA só interpreta e explica. {AVISO_LEGAL}",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=configuracao().cors_origens,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-ContaAI-Token"],
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


# Rotas que chamam os motores (ou o provedor de IA) ou mudam o estado, e por isso têm limite por IP
# (ADR 0006 e ADR 0008).
ROTAS_LIMITADAS = (
    "/carrinho/calcular",
    "/item/preco-alvo",
    "/regime/comparar",
    "/busca/ncm",
    "/explicar",
    "/erros/",
    "/chat",
    "/nfe/importar",
    "/alertas/",
    "/demo/restaurar",
)
LIMITE_CHAT = LimitadorPorIp(configuracao().limite_chat_por_minuto)
LIMITE_GERAL = LimitadorPorIp(configuracao().limite_geral_por_minuto)
LIMITE_BUSCA = LimitadorPorIp(configuracao().limite_busca_por_minuto)


@app.middleware("http")
async def limitar_requisicoes(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    caminho = request.url.path
    if request.method in ("GET", "POST") and caminho.startswith(ROTAS_LIMITADAS):
        ip = request.client.host if request.client else "desconhecido"
        limitadores = [LIMITE_CHAT if caminho == "/chat" else LIMITE_GERAL]
        if caminho == "/busca/ncm":
            limitadores.append(LIMITE_BUSCA)
        permitido, espera = True, 0
        for limitador in limitadores:
            permitido, espera = limitador.permitir(ip)
            if not permitido:
                break
        if not permitido:
            return JSONResponse(
                status_code=429,
                content={"detail": "Muitas requisições. Espere um pouco e tente de novo."},
                headers={"Retry-After": str(espera)},
            )
    return await call_next(request)


ROTAS_DOCUMENTACAO = ("/docs", "/redoc", "/openapi.json")


@app.middleware("http")
async def cabecalhos_de_seguranca(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    """Cabeçalhos em toda resposta (ADR 0008). A API só devolve JSON: nada dela deve ser executado,
    emoldurado ou guardado em cache compartilhado. A documentação (/docs) carrega o Swagger da CDN do
    FastAPI e fica sem a CSP restritiva."""
    resposta = await call_next(request)
    resposta.headers["X-Content-Type-Options"] = "nosniff"
    resposta.headers["Referrer-Policy"] = "no-referrer"
    resposta.headers["X-Frame-Options"] = "DENY"
    resposta.headers["Cross-Origin-Resource-Policy"] = "same-site"
    if not request.url.path.startswith(ROTAS_DOCUMENTACAO):
        resposta.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
        resposta.headers["Cache-Control"] = "no-store"
    return resposta


@app.exception_handler(NotaInvalida)
async def nota_invalida(_: Request, exc: NotaInvalida) -> JSONResponse:
    """O texto diz qual campo falhou, sem repetir trecho do XML enviado."""
    return JSONResponse(status_code=422, content={"detail": exc.mensagem})


@app.exception_handler(NotaRecusada)
async def nota_recusada(_: Request, exc: NotaRecusada) -> JSONResponse:
    return JSONResponse(status_code=exc.status, content={"detail": exc.mensagem})


@app.exception_handler(SementesInvalidas)
async def sementes_invalidas(_: Request, exc: SementesInvalidas) -> JSONResponse:
    """Sem o caminho da pasta na resposta (não expõe a estrutura do servidor)."""
    return JSONResponse(status_code=503, content={"detail": exc.mensagem})


@app.exception_handler(consultas.NaoEncontrado)
async def nao_encontrado(_: Request, exc: consultas.NaoEncontrado) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": exc.mensagem})


@app.exception_handler(consultas.Conflito)
async def conflito(_: Request, exc: consultas.Conflito) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": exc.mensagem})


@app.exception_handler(ProvedorFalhou)
async def provedor_falhou(_: Request, exc: ProvedorFalhou) -> JSONResponse:
    """Falha do provedor de IA, sem chave, URL nem corpo do provedor."""
    return JSONResponse(status_code=503, content={"detail": exc.mensagem})


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


# Um cache por processo, compartilhado entre as requisições (app/motores/cache.py).
CACHE_MOTORES = CacheRespostas(configuracao().cache_motores_itens)


async def cliente_motores(cfg: Cfg) -> AsyncIterator[ClienteMotores]:
    # trust_env=False: as chamadas aos motores nunca passam por proxy configurado no ambiente.
    async with httpx.AsyncClient(timeout=cfg.timeout_calculo_s, trust_env=False) as http:
        yield ClienteMotores(http, cfg.motor_rr_url, cfg.motor_sn_url, CACHE_MOTORES)


Motores = Annotated[ClienteMotores, Depends(cliente_motores)]

# Tabelas oficiais dos dados abertos (iguais para todos): um cache por processo.
CACHE_DADOS_ABERTOS = CacheConsultas()


async def dados_abertos(cfg: Cfg) -> AsyncIterator[DadosAbertos]:
    async with httpx.AsyncClient(timeout=cfg.timeout_calculo_s, trust_env=False) as http:
        yield DadosAbertos(http, cfg.motor_rr_url, cfg.motor_sn_url, CACHE_DADOS_ABERTOS)


Dados = Annotated[DadosAbertos, Depends(dados_abertos)]


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


RESPOSTAS_COMPARAR: dict[int | str, dict[str, Any]] = {
    **RESPOSTAS_MOTOR,
    422: {
        "model": RecusaCalculo | FalhaMotorResposta,
        "description": "Sem comparação possível (RecusaCalculo: item que um dos motores não calcula ou base do "
        "híbrido que não fecha) ou recusa do motor (FalhaMotorResposta). A validação de entrada (data antes de "
        "2027, item sem custo, sem premissasDas) também usa 422, no formato padrão do FastAPI.",
    },
}


@app.post("/regime/comparar", response_model=RegimeCompararResposta, tags=["cálculo"], responses=RESPOSTAS_COMPARAR)
async def regime_comparar(
    req: RegimeCompararRequisicao, cfg: Cfg, response: Response, motores: Motores
) -> RegimeCompararResposta:
    """Simples tradicional × híbrido para uma venda a um cliente do regime regular (E3, ADR 0007)."""
    if cfg.modo == "mock":
        response.headers["X-ContaAI-Mock"] = "1"
        return mocks.carregar().regime_comparar
    return await comparar_regimes(req, motores)


# ---------------------------------------------------------------------------
# Estado (E4, ADR 0008): NF-e, alertas, catálogo, painel do contador e restauração da demonstração


def repositorio(cfg: Cfg) -> Repositorio:
    return Repositorio(_banco(cfg.banco_caminho))


Repo = Annotated[Repositorio, Depends(repositorio)]
Token = Annotated[str | None, Header(alias="X-ContaAI-Token")]

TIPOS_XML = {"application/xml", "text/xml", "application/octet-stream", ""}
CNPJ = Annotated[str, Query(pattern=r"^\d{14}$", description="CNPJ da empresa (14 dígitos).")]
RESPOSTAS_ESTADO: dict[int | str, dict[str, Any]] = {
    401: {"description": "Token da demo ausente ou errado (header X-ContaAI-Token)."},
    404: {"description": "Empresa ou alerta não encontrado."},
    429: {"description": "Limite de requisições por minuto atingido (header Retry-After)."},
}


def exigir_token(cfg: Configuracao, token: str | None) -> None:
    """Rotas que mudam o estado compartilhado da demo exigem o token, quando ele está configurado."""
    if not token_confere(cfg.token_demo, token):
        raise HTTPException(status_code=401, detail="Token da demo ausente ou inválido.")


def so_no_modo_real(cfg: Configuracao) -> None:
    if cfg.modo != "real":
        raise HTTPException(status_code=501, detail="Esta rota muda o estado e só funciona no modo real.")


RESPOSTAS_NFE: dict[int | str, dict[str, Any]] = {
    **RESPOSTAS_MOTOR,
    **RESPOSTAS_ESTADO,
    409: {"description": "A mesma nota (emitente, série e número) já foi importada com outro conteúdo."},
    411: {"description": "Upload sem Content-Length."},
    413: {"description": "Arquivo maior que o limite para uma NF-e."},
    415: {"description": "O arquivo não é XML."},
    422: {"description": "XML que não é uma NF-e lida pelo ContaAI, ou destinatário que não é empresa cadastrada."},
}


@app.post("/nfe/importar", response_model=NfeImportarResposta, tags=["notas"], responses=RESPOSTAS_NFE)
async def nfe_importar(
    cfg: Cfg,
    response: Response,
    motores: Motores,
    arquivo: Annotated[UploadFile, File(description="XML da NF-e de compra (modelo 55, leiaute 4.00)")],
    token: Token = None,
) -> NfeImportarResposta:
    """Lê a nota, casa os itens, grava o histórico de custo e gera os alertas de margem (E4, plano 11.3)."""
    if cfg.modo == "mock":
        response.headers["X-ContaAI-Mock"] = "1"
    else:
        exigir_token(cfg, token)
    if (arquivo.content_type or "").split(";")[0].strip().lower() not in TIPOS_XML:
        raise HTTPException(status_code=415, detail="Envie o arquivo XML da NF-e.")
    # Lê no máximo o limite + 1 byte: não depende de UploadFile.size nem carrega mais que isso em memória.
    conteudo = await arquivo.read(cfg.tamanho_max_nfe_bytes + 1)
    if len(conteudo) > cfg.tamanho_max_nfe_bytes:
        raise HTTPException(status_code=413, detail="Arquivo maior que o limite para uma NF-e.")
    if cfg.modo == "mock":
        return mocks.carregar().nfe_importar
    return await importar_nota(conteudo, repositorio(cfg), motores)


@app.get("/alertas", response_model=AlertasResposta, tags=["notas"], responses=RESPOSTAS_ESTADO)
def listar_alertas(
    cfg: Cfg,
    response: Response,
    cnpj: Annotated[str | None, Query(pattern=r"^\d{14}$", description="Só os desta empresa.")] = None,
    abertos: Annotated[
        bool | None, Query(description="true: só os sem preço aplicado; false: só os aplicados.")
    ] = None,
) -> AlertasResposta:
    """Alertas de margem gerados pelas notas de compra, do mais recente para o mais antigo."""
    if cfg.modo == "mock":
        response.headers["X-ContaAI-Mock"] = "1"
        return mocks.carregar().alertas
    return AlertasResposta(alertas=consultas.alertas(repositorio(cfg), cnpj, abertos))


@app.post(
    "/alertas/{alerta_id}/aplicar",
    response_model=AplicarAlertaResposta,
    tags=["notas"],
    responses={**RESPOSTAS_ESTADO, 409: {"description": "Já aplicado, ou alerta sem preço sugerido."}},
)
def aplicar_alerta(
    cfg: Cfg, alerta_id: Annotated[str, Path(pattern=r"^alerta-[0-9a-f]{16}$")], token: Token = None
) -> AplicarAlertaResposta:
    """Aplica o preço sugerido do alerta como preço de venda do item. Só com o clique do usuário (P3)."""
    so_no_modo_real(cfg)
    exigir_token(cfg, token)
    return consultas.aplicar(repositorio(cfg), alerta_id, agora_utc())


@app.get("/catalogo", response_model=CatalogoResposta, tags=["notas"], responses=RESPOSTAS_ESTADO)
def catalogo(cfg: Cfg, response: Response, cnpj: CNPJ) -> CatalogoResposta:
    """Itens da empresa com o preço de venda e o custo atuais e o histórico de custo. Não chama os motores:
    a margem de cada item sai do POST /carrinho/calcular com estes valores."""
    if cfg.modo == "mock":
        response.headers["X-ContaAI-Mock"] = "1"
        return mocks.carregar().catalogo
    return consultas.catalogo(repositorio(cfg), cnpj)


@app.get("/contador/painel", response_model=PainelContadorResposta, tags=["notas"])
def contador_painel(cfg: Cfg, response: Response) -> PainelContadorResposta:
    """Painel do contador (D1): empresas da carteira com os alertas abertos, a mais urgente primeiro."""
    if cfg.modo == "mock":
        response.headers["X-ContaAI-Mock"] = "1"
        return mocks.carregar().contador_painel
    return consultas.painel(repositorio(cfg))


@app.post(
    "/demo/restaurar",
    response_model=RestaurarResposta,
    tags=["operação"],
    responses={
        **RESPOSTAS_MOTOR,
        **RESPOSTAS_ESTADO,
        503: {"description": "Motor indisponível, ou sementes não encontradas (CONTAAI_PASTA_DEMO)."},
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


@app.get("/busca/ncm", response_model=BuscaNcmResposta, tags=["classificação"], responses=RESPOSTAS_MOTOR)
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
    response.headers["X-ContaAI-Mock"] = "1"
    m = mocks.carregar()
    consulta = _normalizar(q)
    achada = next((r for chave, r in m.busca_ncm.items() if chave in consulta), None)
    if achada is None:
        return BuscaNcmResposta(consulta=q, candidatos=[], aviso=next(iter(m.busca_ncm.values())).aviso)
    return achada.model_copy(update={"consulta": q})


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


@app.get("/explicar/{item_id}", response_model=ExplicarResposta, tags=["explicação"], responses=RESPOSTAS_MOTOR)
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
    response.headers["X-ContaAI-Mock"] = "1"
    try:
        return mocks.carregar().explicar[item_id][regime]
    except KeyError:
        raise HTTPException(status_code=404, detail="Item não encontrado.") from None


@app.post("/explicar", response_model=ExplicarResposta, tags=["explicação"], responses=RESPOSTAS_MOTOR)
async def explicar_post(req: ExplicarRequisicao, cfg: Cfg, motores: Motores, da: Dados) -> ExplicarResposta:
    """Memória de cálculo, fundamentação e premissas de qualquer item. Não tem mock: 501 no modo mock."""
    if cfg.modo == "mock":
        raise HTTPException(status_code=501, detail="POST /explicar só calcula no modo real (CONTAAI_MODO=real).")
    return await explicar_item(req, motores, da)


@app.get("/erros/{codigo}", response_model=ErroDescricao, tags=["explicação"], responses=RESPOSTAS_MOTOR)
async def erro(
    cfg: Cfg, response: Response, da: Dados, codigo: Annotated[str, Path(pattern=r"^(REG|VSN)-\d{3}$")]
) -> ErroDescricao:
    if cfg.modo != "mock":
        achado = await da.erro(codigo)
        if achado is None:
            raise HTTPException(status_code=404, detail="Código de erro não encontrado.")
        motor, e = achado
        return ErroDescricao(codigo=e.codigo, titulo=e.titulo, descricao=e.descricao, motor=motor)
    response.headers["X-ContaAI-Mock"] = "1"
    try:
        return mocks.carregar().erros[codigo]
    except KeyError:
        raise HTTPException(status_code=404, detail="Código de erro não encontrado.") from None


RESPOSTAS_CHAT: dict[int | str, dict[str, Any]] = {
    **RESPOSTAS_MOTOR,
    401: {"description": "Token da demo ausente ou errado (header X-ContaAI-Token)."},
    429: {"description": "Limite de mensagens por minuto atingido (header Retry-After)."},
    503: {"description": "Motor ou provedor de IA indisponível."},
}


@app.post("/chat", response_model=ChatResposta, tags=["agente"], responses=RESPOSTAS_CHAT)
async def chat(
    req: ChatRequisicao,
    cfg: Cfg,
    response: Response,
    motores: Motores,
    da: Dados,
    token: Annotated[str | None, Header(alias="X-ContaAI-Token")] = None,
) -> ChatResposta:
    """Agente com tool use (E2). As ações voltam como propostas: nada é aplicado sem o clique do usuário."""
    if not token_confere(cfg.token_demo, token):
        raise HTTPException(status_code=401, detail="Token da demo ausente ou inválido.")
    if cfg.modo == "mock":
        response.headers["X-ContaAI-Mock"] = "1"
        return mocks.carregar().chat
    async with httpx.AsyncClient(timeout=cfg.llm_timeout_s, trust_env=False) as http:
        provedor = criar_provedor(cfg, http)
        return await responder_chat(
            req, provedor, cfg, Ambiente(motores, da, req.contexto, repositorio=repositorio(cfg))
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
