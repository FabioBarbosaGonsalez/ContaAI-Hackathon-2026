"""Estado (E4, ADR 0008): NF-e de compra, alertas de margem, catálogo e painel do contador. Desde a E5 (ADR 0011),
também o preço e a classificação que o usuário escolhe na tela.

Toda rota aceita o header X-ContaAI-Espaco (ADR 0010): com ele, lê e grava no espaço de avaliação do visitante.
Sem ele, com o cookie da sessão, no banco da organização de quem entrou (ADR 0015); sem os dois, na demonstração
compartilhada. Só a demonstração compartilhada exige o token nas rotas que mudam o estado.

Toda rota só enxerga as empresas de quem chama (`Estado.cnpjs`): um CNPJ fora do alcance responde o mesmo 404 de
um CNPJ que não existe (ADR 0015).
"""

from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, Path, Query, Response, UploadFile

from app import mocks
from app.api import respostas
from app.api.dependencias import (
    Cfg,
    Dados,
    EspacoId,
    Motores,
    SessaoCookie,
    Token,
    abrir_estado,
    exigir_token_fora_do_espaco,
    marcar_mock,
    so_no_modo_real,
)
from app.classificacao.candidatos import classificacoes_da_ncm
from app.contrato import (
    PADRAO_ID_ITEM,
    AlertasResposta,
    AplicarAlertaResposta,
    AplicarPrecoRequisicao,
    AplicarPrecoResposta,
    CatalogoResposta,
    CorrigirClassificacaoRequisicao,
    CorrigirClassificacaoResposta,
    NfeImportarResposta,
    NotasResposta,
    PainelContadorResposta,
)
from app.nfe import consultas
from app.nfe.importacao import agora_utc, importar_nota

rotas = APIRouter(tags=["notas"])

TIPOS_XML = {"application/xml", "text/xml", "application/octet-stream", ""}
CNPJ = Annotated[str, Query(pattern=r"^[0-9]{14}$", description="CNPJ da empresa (14 dígitos).")]


@rotas.post("/nfe/importar", response_model=NfeImportarResposta, responses=respostas.NFE)
async def nfe_importar(
    cfg: Cfg,
    response: Response,
    motores: Motores,
    arquivo: Annotated[UploadFile, File(description="XML da NF-e de compra (modelo 55, leiaute 4.00)")],
    token: Token = None,
    espaco: EspacoId = None,
    sessao: SessaoCookie = None,
) -> NfeImportarResposta:
    """Lê a nota, casa os itens, grava o histórico de custo e gera os alertas de margem (E4, plano 11.3)."""
    estado = None
    if cfg.modo == "mock":
        marcar_mock(response)
    else:
        estado = await asyncio.to_thread(abrir_estado, cfg, espaco, sessao)
        exigir_token_fora_do_espaco(cfg, token, estado)
    if (arquivo.content_type or "").split(";")[0].strip().lower() not in TIPOS_XML:
        raise HTTPException(status_code=415, detail="Envie o arquivo XML da NF-e.")
    # Lê no máximo o limite + 1 byte: não depende de UploadFile.size nem carrega mais que isso em memória.
    conteudo = await arquivo.read(cfg.tamanho_max_nfe_bytes + 1)
    if len(conteudo) > cfg.tamanho_max_nfe_bytes:
        raise HTTPException(status_code=413, detail="Arquivo maior que o limite para uma NF-e.")
    if estado is None:
        return mocks.carregar().nfe_importar
    return await importar_nota(conteudo, estado.repositorio, motores, cnpjs=estado.cnpjs)


@rotas.get("/alertas", response_model=AlertasResposta, responses=respostas.ESTADO)
def listar_alertas(
    cfg: Cfg,
    response: Response,
    cnpj: Annotated[str | None, Query(pattern=r"^[0-9]{14}$", description="Só os desta empresa.")] = None,
    abertos: Annotated[
        bool | None, Query(description="true: só os sem preço aplicado; false: só os aplicados.")
    ] = None,
    espaco: EspacoId = None,
    sessao: SessaoCookie = None,
) -> AlertasResposta:
    """Alertas de margem gerados pelas notas de compra, do mais recente para o mais antigo. Sem `cnpj`, os de
    todas as empresas que quem chama alcança."""
    if cfg.modo == "mock":
        marcar_mock(response)
        return mocks.carregar().alertas
    estado = abrir_estado(cfg, espaco, sessao)
    if cnpj is not None:
        estado.exigir_empresa(cnpj)
    todos = consultas.alertas(estado.repositorio, cnpj, abertos)
    return AlertasResposta(alertas=[a for a in todos if a.cnpj in estado.cnpjs])


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
    cfg: Cfg,
    alerta_id: Annotated[str, Path(pattern=r"^alerta-[0-9a-f]{16}$")],
    token: Token = None,
    espaco: EspacoId = None,
    sessao: SessaoCookie = None,
) -> AplicarAlertaResposta:
    """Aplica o preço sugerido do alerta como preço de venda do item. Só com o clique do usuário (P3). Um alerta de
    empresa fora do alcance de quem chama responde como alerta inexistente."""
    so_no_modo_real(cfg)
    estado = abrir_estado(cfg, espaco, sessao)
    exigir_token_fora_do_espaco(cfg, token, estado)
    return consultas.aplicar(estado.repositorio, alerta_id, agora_utc(), estado.cnpjs)


ItemId = Annotated[str, Path(pattern=PADRAO_ID_ITEM, description="Id do item no catálogo da empresa.")]
RESPOSTAS_TELA: respostas.Respostas = {
    **respostas.ESTADO,
    **respostas.SO_MODO_REAL,
    409: {"description": "O valor pedido já é o atual, ou o item mudou durante a conferência."},
}


@rotas.post("/catalogo/{item_id}/preco", response_model=AplicarPrecoResposta, responses=RESPOSTAS_TELA)
def aplicar_preco(
    cfg: Cfg,
    item_id: ItemId,
    req: AplicarPrecoRequisicao,
    token: Token = None,
    espaco: EspacoId = None,
    sessao: SessaoCookie = None,
) -> AplicarPrecoResposta:
    """Lança o preço de venda escolhido na tela (ex.: a ação "aplicar_preco" do chat). Só com o clique do
    usuário (P3). O preço é decisão dele: o backend só confere o formato e o teto de sanidade."""
    so_no_modo_real(cfg)
    estado = abrir_estado(cfg, espaco, sessao)
    exigir_token_fora_do_espaco(cfg, token, estado)
    estado.exigir_empresa(req.cnpj)
    return consultas.aplicar_preco(estado.repositorio, req.cnpj, item_id, req.valorUnitario, agora_utc())


@rotas.post(
    "/catalogo/{item_id}/classificacao",
    response_model=CorrigirClassificacaoResposta,
    responses={**RESPOSTAS_TELA, **respostas.MOTOR},
)
async def corrigir_classificacao(
    cfg: Cfg,
    da: Dados,
    item_id: ItemId,
    req: CorrigirClassificacaoRequisicao,
    token: Token = None,
    espaco: EspacoId = None,
    sessao: SessaoCookie = None,
) -> CorrigirClassificacaoResposta:
    """Grava a classificação que o usuário confirmou (correção do REG-011 ou do VSN-047, P3). Só aceita uma
    classificação válida para a NCM do item nos dados abertos do motor RR, na data do cenário da empresa;
    o CST é o da fundamentação oficial. Depois disso, catálogo, alertas e explicação usam a nova."""
    so_no_modo_real(cfg)
    estado = await asyncio.to_thread(abrir_estado, cfg, espaco, sessao)
    exigir_token_fora_do_espaco(cfg, token, estado)
    estado.exigir_empresa(req.cnpj)
    lido = await asyncio.to_thread(consultas.item_da_empresa, estado.repositorio, req.cnpj, item_id)
    validas = await classificacoes_da_ncm(da, lido.item.ncm, lido.empresa.cenario.data)
    escolhida = next((c for c in validas if c.cClassTrib == req.cClassTrib), None)
    if escolhida is None:
        raise HTTPException(
            status_code=422,
            detail="Classificação não válida para a NCM do item nos dados abertos do motor RR. Use uma das "
            "candidatas da busca (GET /busca/ncm) ou da ação de correção do chat.",
        )
    return await asyncio.to_thread(
        consultas.corrigir_classificacao, estado.repositorio, req.cnpj, lido.item, escolhida, agora_utc()
    )


@rotas.get("/catalogo", response_model=CatalogoResposta, responses=respostas.ESTADO)
def catalogo(
    cfg: Cfg, response: Response, cnpj: CNPJ, espaco: EspacoId = None, sessao: SessaoCookie = None
) -> CatalogoResposta:
    """Itens da empresa com o preço de venda e o custo atuais e o histórico de custo. Não chama os motores:
    a margem de cada item sai do POST /carrinho/calcular com estes valores."""
    if cfg.modo == "mock":
        marcar_mock(response)
        return mocks.carregar().catalogo
    estado = abrir_estado(cfg, espaco, sessao)
    estado.exigir_empresa(cnpj)
    return consultas.catalogo(estado.repositorio, cnpj)


@rotas.get("/notas", response_model=NotasResposta, responses=respostas.ESTADO)
def listar_notas(
    cfg: Cfg,
    response: Response,
    cnpj: CNPJ,
    limite: Annotated[int, Query(ge=1, le=200, description="Quantas notas, no máximo.")] = 50,
    espaco: EspacoId = None,
    sessao: SessaoCookie = None,
) -> NotasResposta:
    """NF-e de compra já importadas pela empresa, da emissão mais recente para a mais antiga, com os itens
    casados e sem par e os alertas que cada uma gerou. Não chama os motores."""
    if cfg.modo == "mock":
        marcar_mock(response)
        return mocks.carregar().notas
    estado = abrir_estado(cfg, espaco, sessao)
    estado.exigir_empresa(cnpj)
    return consultas.notas(estado.repositorio, cnpj, limite)


@rotas.get("/contador/painel", response_model=PainelContadorResposta, responses=respostas.ESPACO)
def contador_painel(
    cfg: Cfg, response: Response, espaco: EspacoId = None, sessao: SessaoCookie = None
) -> PainelContadorResposta:
    """Painel do contador (D1): as empresas que quem chama alcança, com os alertas abertos, a mais urgente
    primeiro."""
    if cfg.modo == "mock":
        marcar_mock(response)
        return mocks.carregar().contador_painel
    estado = abrir_estado(cfg, espaco, sessao)
    return consultas.painel(estado.repositorio, estado.cnpjs)
