"""Empresa própria (C3-B, ADR 0017): referências oficiais, cadastro e configurações da empresa da conta, e o catálogo
editável.

- Referências (UF, município, atividade do Simples): públicas, só leitura, dos motores oficiais (P5).
- Empresa: só com a sessão da conta, no banco da organização (ADR 0015). Cadastrar e configurar exigem o papel de
  dono. O header do espaço de avaliação não vale aqui: o espaço é uma cópia da demonstração.
- Catálogo: como as outras rotas do estado (espaço, conta ou demonstração com o token). Na empresa da conta, o CNPJ
  do fornecedor precisa do dígito certo; na demonstração e nos espaços, os CNPJs fictícios continuam aceitos.

Todas só no modo real: no modo mock respondem 501, como as contas.
"""

from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query

from app import cadastro
from app.api import respostas
from app.api.dependencias import (
    Cfg,
    Dados,
    EspacoId,
    SessaoCookie,
    Token,
    abrir_estado,
    banco_da_organizacao,
    contas,
    exigir_token_fora_do_espaco,
    sessao_do_cookie,
    so_no_modo_real,
)
from app.cnpj import PADRAO_CNPJ
from app.config import Configuracao
from app.contas.servico import SessaoAtiva
from app.contrato import (
    PADRAO_ID_ITEM,
    AtividadesResposta,
    EmpresaCadastroRequisicao,
    EmpresaConfiguracaoRequisicao,
    EmpresaResposta,
    ItemAlteracaoRequisicao,
    ItemArquivadoResposta,
    ItemArquivarRequisicao,
    ItemNovoRequisicao,
    ItemResposta,
    MunicipiosResposta,
    UfsResposta,
)
from app.nfe.consultas import AVISO_EMPRESA_PROPRIA, NaoEncontrado
from app.nfe.importacao import agora_utc
from app.persistencia.repositorio import Repositorio

rotas = APIRouter(tags=["empresa"])

CnpjCaminho = Annotated[str, Path(pattern=PADRAO_CNPJ, description="CNPJ da empresa da conta.")]
ItemId = Annotated[str, Path(pattern=PADRAO_ID_ITEM, description="Id do item no catálogo da empresa.")]

REFERENCIAS: respostas.Respostas = {**respostas.MOTOR, **respostas.LIMITE, **respostas.SO_MODO_REAL}
SESSAO: respostas.Respostas = {
    **respostas.SO_MODO_REAL,
    **respostas.LIMITE,
    401: {"description": "Sem sessão, ou sessão encerrada ou expirada."},
    403: {"description": "Só o dono da organização cadastra e configura a empresa."},
    404: {"description": "Empresa que a conta não alcança (a mesma resposta de uma que não existe)."},
}
EMPRESA: respostas.Respostas = {
    **respostas.MOTOR,
    **SESSAO,
    409: {
        "description": "A empresa já está na conta, o limite de empresas foi atingido, ou ela mudou durante a "
        "conferência."
    },
    422: {
        "description": "CNPJ com dígito errado, município fora da UF, atividade que o ContaAI não calcula, ou "
        "entrada fora do contrato."
    },
}
CATALOGO: respostas.Respostas = {
    **respostas.MOTOR,
    **respostas.ESTADO,
    **respostas.SO_MODO_REAL,
    409: {"description": "Código do fornecedor já em outro item, limite de itens, ou nada a mudar."},
    422: {
        "description": "NCM fora dos dados abertos, NCM com Imposto Seletivo, classificação que não vale para a "
        "NCM, CNPJ do fornecedor com dígito errado (na empresa da conta), ou entrada fora do contrato."
    },
}


def _versoes(cfg: Configuracao) -> cadastro.Versoes:
    return cadastro.Versoes(rr=cfg.versao_rr, sn=cfg.versao_sn)


def _sessao(cfg: Configuracao, token: str | None, dono: bool = False) -> SessaoAtiva:
    sessao = sessao_do_cookie(cfg, token)
    if sessao is None:
        raise HTTPException(status_code=401, detail="Entre com a sua conta.")
    if dono and sessao.papel != "dono":
        raise HTTPException(status_code=403, detail="Só o dono da organização cadastra e configura a empresa.")
    return sessao


def _da_conta(cfg: Configuracao, sessao: SessaoAtiva, cnpj: str) -> Repositorio:
    """O banco da organização, se ela alcança o CNPJ; senão, o 404 de uma empresa que não existe."""
    if cnpj not in contas(cfg).empresas(sessao.organizacao_id):
        raise NaoEncontrado("Empresa não cadastrada.")
    return Repositorio(banco_da_organizacao(cfg, sessao.organizacao_id))


# -- referências ------------------------------------------------------------------------------------------


@rotas.get("/referencias/ufs", response_model=UfsResposta, responses=REFERENCIAS)
async def referencias_ufs(cfg: Cfg, da: Dados) -> UfsResposta:
    """As UFs dos dados abertos do motor RR (sigla, nome e código do IBGE)."""
    so_no_modo_real(cfg, "As referências vêm dos motores: só no modo real.")
    return await cadastro.ufs(da, _versoes(cfg))


@rotas.get("/referencias/municipios", response_model=MunicipiosResposta, responses=REFERENCIAS)
async def referencias_municipios(
    cfg: Cfg, da: Dados, uf: Annotated[str, Query(pattern=r"^[A-Z]{2}$", description="Sigla da UF.")]
) -> MunicipiosResposta:
    """Os municípios da UF nos dados abertos do motor RR, com o código do IBGE."""
    so_no_modo_real(cfg, "As referências vêm dos motores: só no modo real.")
    return await cadastro.municipios(da, uf, _versoes(cfg))


@rotas.get("/referencias/atividades", response_model=AtividadesResposta, responses=REFERENCIAS)
async def referencias_atividades(cfg: Cfg, da: Dados) -> AtividadesResposta:
    """As atividades do Simples que o ContaAI calcula, no motor SN, na data do cenário da empresa própria."""
    so_no_modo_real(cfg, "As referências vêm dos motores: só no modo real.")
    base = await asyncio.to_thread(cadastro.cenario_padrao, cfg.pasta_demo)
    return await cadastro.atividades(da, base.data, _versoes(cfg))


# -- empresa ----------------------------------------------------------------------------------------------


@rotas.post("/empresas", status_code=201, response_model=EmpresaResposta, responses=EMPRESA)
async def cadastrar_empresa(
    cfg: Cfg, da: Dados, req: EmpresaCadastroRequisicao, sessao: SessaoCookie = None
) -> EmpresaResposta:
    """Cadastra a empresa da conta com o cenário de simulação. O CNPJ precisa do dígito verificador certo (numérico
    ou alfanumérico); o nome do município e o anexo da atividade vêm dos motores."""
    so_no_modo_real(cfg)
    quem = await asyncio.to_thread(_sessao, cfg, sessao, True)
    base = await asyncio.to_thread(cadastro.cenario_padrao, cfg.pasta_demo)
    empresa, cenario = await cadastro.montar_empresa(da, req, base, _versoes(cfg))
    repo = Repositorio(banco_da_organizacao(cfg, quem.organizacao_id))
    return await asyncio.to_thread(
        cadastro.cadastrar_empresa,
        repo,
        contas(cfg),
        quem.organizacao_id,
        empresa,
        cenario,
        agora_utc(),
        AVISO_EMPRESA_PROPRIA,
    )


@rotas.get("/empresas/{cnpj}", response_model=EmpresaResposta, responses=SESSAO)
def ler_empresa(cfg: Cfg, cnpj: CnpjCaminho, sessao: SessaoCookie = None) -> EmpresaResposta:
    """A empresa da conta com a atividade, o cenário e a origem das premissas do DAS (configurações)."""
    so_no_modo_real(cfg)
    quem = _sessao(cfg, sessao)
    return cadastro.ler_empresa(_da_conta(cfg, quem, cnpj), cnpj, AVISO_EMPRESA_PROPRIA)


@rotas.patch("/empresas/{cnpj}", response_model=EmpresaResposta, responses=EMPRESA)
async def configurar_empresa(
    cfg: Cfg, da: Dados, cnpj: CnpjCaminho, req: EmpresaConfiguracaoRequisicao, sessao: SessaoCookie = None
) -> EmpresaResposta:
    """Muda só os campos enviados. As alíquotas efetivas do Simples informadas aqui substituem as da simulação
    em todo cálculo da empresa (P8); `premissasDas: null` volta à simulação."""
    so_no_modo_real(cfg)
    quem = await asyncio.to_thread(_sessao, cfg, sessao, True)
    repo = await asyncio.to_thread(_da_conta, cfg, quem, cnpj)
    base = await asyncio.to_thread(cadastro.cenario_padrao, cfg.pasta_demo)
    return await cadastro.configurar_empresa(da, repo, cnpj, req, base, _versoes(cfg), AVISO_EMPRESA_PROPRIA)


# -- catálogo ---------------------------------------------------------------------------------------------


@rotas.post("/catalogo/itens", status_code=201, response_model=ItemResposta, responses=CATALOGO)
async def criar_item(
    cfg: Cfg,
    da: Dados,
    req: ItemNovoRequisicao,
    token: Token = None,
    espaco: EspacoId = None,
    sessao: SessaoCookie = None,
) -> ItemResposta:
    """Um item novo, com a classificação escolhida entre as válidas para a NCM (P3) e o primeiro preço de venda.
    Itens com Imposto Seletivo ainda não entram (ADR 0017)."""
    so_no_modo_real(cfg)
    estado = await asyncio.to_thread(abrir_estado, cfg, espaco, sessao)
    exigir_token_fora_do_espaco(cfg, token, estado)
    estado.exigir_empresa(req.cnpj)
    return await cadastro.criar_item(da, estado.repositorio, req, estado.na_empresa_propria, agora_utc())


@rotas.patch("/catalogo/{item_id}", response_model=ItemResposta, responses=CATALOGO)
def alterar_item(
    cfg: Cfg,
    item_id: ItemId,
    req: ItemAlteracaoRequisicao,
    token: Token = None,
    espaco: EspacoId = None,
    sessao: SessaoCookie = None,
) -> ItemResposta:
    """Muda a descrição, a margem-alvo ou o fornecedor (CNPJ e código juntos) do item."""
    so_no_modo_real(cfg)
    estado = abrir_estado(cfg, espaco, sessao)
    exigir_token_fora_do_espaco(cfg, token, estado)
    estado.exigir_empresa(req.cnpj)
    return cadastro.alterar_item(estado.repositorio, item_id, req, estado.na_empresa_propria)


@rotas.post("/catalogo/{item_id}/arquivar", response_model=ItemArquivadoResposta, responses=CATALOGO)
def arquivar_item(
    cfg: Cfg,
    item_id: ItemId,
    req: ItemArquivarRequisicao,
    token: Token = None,
    espaco: EspacoId = None,
    sessao: SessaoCookie = None,
) -> ItemArquivadoResposta:
    """Tira o item do catálogo. O histórico dele (custos, preços, classificações e alertas) fica; os alertas abertos
    dele saem das listas, e uma nota nova com o código do fornecedor dele vira item sem par."""
    so_no_modo_real(cfg)
    estado = abrir_estado(cfg, espaco, sessao)
    exigir_token_fora_do_espaco(cfg, token, estado)
    estado.exigir_empresa(req.cnpj)
    return cadastro.arquivar_item(estado.repositorio, req.cnpj, item_id, agora_utc())
