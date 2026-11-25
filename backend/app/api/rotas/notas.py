"""Estado (E4, ADR 0008): NF-e de compra, alertas de margem, catálogo e painel do contador."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, HTTPException, Path, Query, Response, UploadFile

from app import mocks
from app.api import respostas
from app.api.dependencias import Cfg, Motores, Token, exigir_token, marcar_mock, repositorio, so_no_modo_real
from app.contrato import (
    AlertasResposta,
    AplicarAlertaResposta,
    CatalogoResposta,
    NfeImportarResposta,
    PainelContadorResposta,
)
from app.nfe import consultas
from app.nfe.importacao import agora_utc, importar_nota

rotas = APIRouter(tags=["notas"])

TIPOS_XML = {"application/xml", "text/xml", "application/octet-stream", ""}
CNPJ = Annotated[str, Query(pattern=r"^\d{14}$", description="CNPJ da empresa (14 dígitos).")]


@rotas.post("/nfe/importar", response_model=NfeImportarResposta, responses=respostas.NFE)
async def nfe_importar(
    cfg: Cfg,
    response: Response,
    motores: Motores,
    arquivo: Annotated[UploadFile, File(description="XML da NF-e de compra (modelo 55, leiaute 4.00)")],
    token: Token = None,
) -> NfeImportarResposta:
    """Lê a nota, casa os itens, grava o histórico de custo e gera os alertas de margem (E4, plano 11.3)."""
    if cfg.modo == "mock":
        marcar_mock(response)
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


@rotas.get("/alertas", response_model=AlertasResposta, responses=respostas.ESTADO)
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
        marcar_mock(response)
        return mocks.carregar().alertas
    return AlertasResposta(alertas=consultas.alertas(repositorio(cfg), cnpj, abertos))


@rotas.post(
    "/alertas/{alerta_id}/aplicar",
    response_model=AplicarAlertaResposta,
    responses={
        **respostas.ESTADO,
        **respostas.SO_MODO_REAL,
        409: {"description": "Já aplicado, ou alerta sem preço sugerido."},
    },
)
def aplicar_alerta(
    cfg: Cfg, alerta_id: Annotated[str, Path(pattern=r"^alerta-[0-9a-f]{16}$")], token: Token = None
) -> AplicarAlertaResposta:
    """Aplica o preço sugerido do alerta como preço de venda do item. Só com o clique do usuário (P3)."""
    so_no_modo_real(cfg)
    exigir_token(cfg, token)
    return consultas.aplicar(repositorio(cfg), alerta_id, agora_utc())


@rotas.get("/catalogo", response_model=CatalogoResposta, responses=respostas.ESTADO)
def catalogo(cfg: Cfg, response: Response, cnpj: CNPJ) -> CatalogoResposta:
    """Itens da empresa com o preço de venda e o custo atuais e o histórico de custo. Não chama os motores:
    a margem de cada item sai do POST /carrinho/calcular com estes valores."""
    if cfg.modo == "mock":
        marcar_mock(response)
        return mocks.carregar().catalogo
    return consultas.catalogo(repositorio(cfg), cnpj)


@rotas.get("/contador/painel", response_model=PainelContadorResposta)
def contador_painel(cfg: Cfg, response: Response) -> PainelContadorResposta:
    """Painel do contador (D1): empresas da carteira com os alertas abertos, a mais urgente primeiro."""
    if cfg.modo == "mock":
        marcar_mock(response)
        return mocks.carregar().contador_painel
    return consultas.painel(repositorio(cfg))
