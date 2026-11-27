"""Empresa própria (C3-B, ADR 0017): referências oficiais, cadastro e configurações da empresa da conta, e o catálogo
e os clientes B2B editáveis.

- Referências (UF, município, atividade do Simples): públicas, só leitura, dos motores oficiais (P5).
- Empresa: só com a sessão da conta, no banco da organização (ADR 0015). Cadastrar, configurar e excluir são de
  PAPEIS_QUE_ADMINISTRAM (o dono); ler, de todo integrante. O header do espaço de avaliação não vale aqui: o espaço
  é uma cópia da demonstração.
- Catálogo e clientes B2B: como as outras rotas do estado (espaço, conta ou demonstração com o token). Na
  organização, mudar é de PAPEIS_QUE_EDITAM (o dono e o membro). Na empresa da conta, o CNPJ do fornecedor e o do
  cliente precisam do dígito certo; na demonstração e nos espaços, os CNPJs fictícios continuam aceitos.

Todas só no modo real: no modo mock respondem 501, como as contas.
"""

from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query, Response

from app import cadastro
from app.api import respostas
from app.api.dependencias import (
    PAPEIS_QUE_ADMINISTRAM,
    Cfg,
    Dados,
    EspacoId,
    SessaoCookie,
    Token,
    abrir_estado,
    banco_da_organizacao,
    contas,
    exigir_papel,
    exigir_permissao_para_mudar,
    sessao_do_cookie,
    so_no_modo_real,
)
from app.api.rotas.contas import recusa
from app.cnpj import PADRAO_CNPJ
from app.config import Configuracao
from app.contas.servico import AguardeParaTentar, EntradaRecusada, SessaoAtiva
from app.contrato import (
    PADRAO_ID_ITEM,
    AtividadesResposta,
    ClienteAlteracaoRequisicao,
    ClienteExcluidoResposta,
    ClienteExcluirRequisicao,
    ClienteNovoRequisicao,
    ClienteResposta,
    EmpresaCadastroRequisicao,
    EmpresaConfiguracaoRequisicao,
    EmpresaExcluirRequisicao,
    EmpresaResposta,
    ItemAlteracaoRequisicao,
    ItemArquivadoResposta,
    ItemArquivarRequisicao,
    ItemNovoRequisicao,
    ItemResposta,
    MunicipiosResposta,
    Problema,
    ProblemaItemEmUso,
    UfsResposta,
)
from app.nfe.consultas import AVISO_EMPRESA_PROPRIA, NaoEncontrado
from app.nfe.importacao import agora_utc
from app.persistencia.repositorio import Repositorio

rotas = APIRouter(tags=["empresa"])

CnpjCaminho = Annotated[str, Path(pattern=PADRAO_CNPJ, description="CNPJ da empresa da conta.")]
ItemId = Annotated[str, Path(pattern=PADRAO_ID_ITEM, description="Id do item no catálogo da empresa.")]
CnpjCliente = Annotated[str, Path(pattern=PADRAO_CNPJ, description="CNPJ do cliente B2B.")]

REFERENCIAS: respostas.Respostas = {**respostas.MOTOR, **respostas.LIMITE, **respostas.SO_MODO_REAL}
SESSAO: respostas.Respostas = {
    **respostas.SO_MODO_REAL,
    **respostas.LIMITE,
    401: {"description": "Sem sessão, ou sessão encerrada ou expirada."},
    404: {"description": "Empresa que a conta não alcança (a mesma resposta de uma que não existe)."},
}
RECUSA_CONFIGURAR = "Só o dono da organização cadastra e configura a empresa."
RECUSA_EXCLUIR = "Só o dono da organização exclui a empresa."
EMPRESA: respostas.Respostas = {
    **respostas.MOTOR,
    **SESSAO,
    403: {"description": RECUSA_CONFIGURAR},
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
    **respostas.PAPEL,
    409: {"description": "Código do fornecedor já em outro item, limite de itens, ou nada a mudar."},
    422: {
        "description": "NCM fora dos dados abertos, NCM com Imposto Seletivo, classificação que não vale para a "
        "NCM, CNPJ do fornecedor com dígito errado (na empresa da conta), ou entrada fora do contrato."
    },
}
ARQUIVAR: respostas.Respostas = {
    **respostas.ESTADO,
    **respostas.SO_MODO_REAL,
    **respostas.PAPEL,
    409: {
        "model": ProblemaItemEmUso | Problema,
        "description": "O item está na compra mensal de clientes B2B (/problemas/item-em-uso, com a lista em "
        "`clientes`).",
    },
}
CLIENTES: respostas.Respostas = {
    **respostas.MOTOR,
    **respostas.ESTADO,
    **respostas.SO_MODO_REAL,
    **respostas.PAPEL,
    409: {"description": "Cliente já cadastrado, limite de clientes, ou nada a mudar."},
    422: {
        "description": "Cliente do Simples Nacional, CNPJ do cliente com dígito errado (na empresa da conta), cliente "
        "igual à empresa, município fora da UF, item da compra fora do catálogo, ou entrada fora do contrato."
    },
}
EXCLUIR_CLIENTE: respostas.Respostas = {**respostas.ESTADO, **respostas.SO_MODO_REAL, **respostas.PAPEL}


def _versoes(cfg: Configuracao) -> cadastro.Versoes:
    return cadastro.Versoes(rr=cfg.versao_rr, sn=cfg.versao_sn)


def _sessao(cfg: Configuracao, token: str | None, recusa_sem_papel: str | None = None) -> SessaoAtiva:
    """A sessão do cookie (401 sem ela). Com `recusa_sem_papel`, a rota é de PAPEIS_QUE_ADMINISTRAM e quem não tem
    o papel recebe 403 com esta frase, antes de qualquer consulta à empresa (o 403 não diz se o CNPJ existe)."""
    sessao = sessao_do_cookie(cfg, token)
    if sessao is None:
        raise HTTPException(status_code=401, detail="Entre com a sua conta.")
    if recusa_sem_papel is not None:
        exigir_papel(sessao, PAPEIS_QUE_ADMINISTRAM, recusa_sem_papel)
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
    quem = await asyncio.to_thread(_sessao, cfg, sessao, RECUSA_CONFIGURAR)
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
    quem = await asyncio.to_thread(_sessao, cfg, sessao, RECUSA_CONFIGURAR)
    repo = await asyncio.to_thread(_da_conta, cfg, quem, cnpj)
    base = await asyncio.to_thread(cadastro.cenario_padrao, cfg.pasta_demo)
    return await cadastro.configurar_empresa(da, repo, cnpj, req, base, _versoes(cfg), AVISO_EMPRESA_PROPRIA)


EXCLUIR_EMPRESA: respostas.Respostas = {
    **SESSAO,
    401: {"description": "Sem sessão, sessão encerrada ou expirada, ou senha incorreta."},
    403: {"description": RECUSA_EXCLUIR},
    422: {"description": "O CNPJ digitado para confirmar não é o da empresa, ou entrada fora do contrato."},
    429: {
        "description": "Espera depois de falhas seguidas da senha ou limite por IP (header Retry-After), ou conta "
        "bloqueada (/problemas/conta-bloqueada)."
    },
}


@rotas.post("/empresas/{cnpj}/excluir", status_code=204, response_class=Response, responses=EXCLUIR_EMPRESA)
async def excluir_empresa(
    cfg: Cfg, cnpj: CnpjCaminho, req: EmpresaExcluirRequisicao, sessao: SessaoCookie = None
) -> None:
    """Exclui a empresa de vez, sem excluir a conta: o catálogo, as notas, os custos, os preços, os alertas e os
    clientes dela saem juntos, e o contador deixa de alcançá-la. Só o dono, com a senha de novo e o CNPJ digitado
    para confirmar. O ContaAI não guarda o XML das notas: guarde-as antes (o arquivo fiscal é seu)."""
    so_no_modo_real(cfg)
    quem = await asyncio.to_thread(_sessao, cfg, sessao, RECUSA_EXCLUIR)
    repo = await asyncio.to_thread(_da_conta, cfg, quem, cnpj)
    if req.cnpjConfirmacao != cnpj:
        raise cadastro.Recusado("O CNPJ digitado não é o desta empresa.")
    try:
        await asyncio.to_thread(contas(cfg).conferir_senha, quem.usuario_id, req.senha, agora_utc())
    except (EntradaRecusada, AguardeParaTentar) as e:
        raise recusa(e) from None
    await asyncio.to_thread(cadastro.excluir_empresa, repo, contas(cfg), quem.organizacao_id, cnpj)


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
    exigir_permissao_para_mudar(cfg, token, estado)
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
    exigir_permissao_para_mudar(cfg, token, estado)
    estado.exigir_empresa(req.cnpj)
    return cadastro.alterar_item(estado.repositorio, item_id, req, estado.na_empresa_propria)


@rotas.post("/catalogo/{item_id}/arquivar", response_model=ItemArquivadoResposta, responses=ARQUIVAR)
def arquivar_item(
    cfg: Cfg,
    item_id: ItemId,
    req: ItemArquivarRequisicao,
    token: Token = None,
    espaco: EspacoId = None,
    sessao: SessaoCookie = None,
) -> ItemArquivadoResposta:
    """Tira o item do catálogo. O histórico dele (custos, preços, classificações e alertas) fica; os alertas abertos
    dele saem das listas, e uma nota nova com o código do fornecedor dele vira item sem par. Um item na compra mensal
    de um cliente B2B não sai (409): a venda do cliente ficaria sem o item."""
    so_no_modo_real(cfg)
    estado = abrir_estado(cfg, espaco, sessao)
    exigir_permissao_para_mudar(cfg, token, estado)
    estado.exigir_empresa(req.cnpj)
    return cadastro.arquivar_item(estado.repositorio, req.cnpj, item_id, agora_utc())


# -- clientes B2B -----------------------------------------------------------------------------------------


@rotas.post("/clientes", status_code=201, response_model=ClienteResposta, responses=CLIENTES)
async def criar_cliente(
    cfg: Cfg,
    da: Dados,
    req: ClienteNovoRequisicao,
    token: Token = None,
    espaco: EspacoId = None,
    sessao: SessaoCookie = None,
) -> ClienteResposta:
    """Um cliente empresa do regime regular e a compra mensal dele, com itens do catálogo da empresa. É a venda que a
    comparação de regimes usa (GET /catalogo, `clientesB2B`)."""
    so_no_modo_real(cfg)
    estado = await asyncio.to_thread(abrir_estado, cfg, espaco, sessao)
    exigir_permissao_para_mudar(cfg, token, estado)
    estado.exigir_empresa(req.cnpj)
    return await cadastro.criar_cliente(da, estado.repositorio, req, estado.na_empresa_propria)


@rotas.patch("/clientes/{cnpj_cliente}", response_model=ClienteResposta, responses=CLIENTES)
async def alterar_cliente(
    cfg: Cfg,
    da: Dados,
    cnpj_cliente: CnpjCliente,
    req: ClienteAlteracaoRequisicao,
    token: Token = None,
    espaco: EspacoId = None,
    sessao: SessaoCookie = None,
) -> ClienteResposta:
    """Muda a razão social, o local (UF e município juntos) ou a compra mensal do cliente."""
    so_no_modo_real(cfg)
    estado = await asyncio.to_thread(abrir_estado, cfg, espaco, sessao)
    exigir_permissao_para_mudar(cfg, token, estado)
    estado.exigir_empresa(req.cnpj)
    return await cadastro.alterar_cliente(da, estado.repositorio, cnpj_cliente, req)


@rotas.post("/clientes/{cnpj_cliente}/excluir", response_model=ClienteExcluidoResposta, responses=EXCLUIR_CLIENTE)
def excluir_cliente(
    cfg: Cfg,
    cnpj_cliente: CnpjCliente,
    req: ClienteExcluirRequisicao,
    token: Token = None,
    espaco: EspacoId = None,
    sessao: SessaoCookie = None,
) -> ClienteExcluidoResposta:
    """Exclui o cliente de vez: o ContaAI não guarda histórico de clientes."""
    so_no_modo_real(cfg)
    estado = abrir_estado(cfg, espaco, sessao)
    exigir_permissao_para_mudar(cfg, token, estado)
    estado.exigir_empresa(req.cnpj)
    return cadastro.excluir_cliente(estado.repositorio, req.cnpj, cnpj_cliente, agora_utc())
