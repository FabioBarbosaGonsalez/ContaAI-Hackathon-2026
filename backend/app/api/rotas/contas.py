"""Contas (C1, ADR 0015): cadastro com segundo fator, entrada em duas etapas, sessão, saída e exclusão.

A sessão e o passe só andam em cookies HttpOnly, Secure, SameSite=Strict e com o prefixo __Host-: o JavaScript da
tela não os lê, e outro site não os envia. A tela e a API ficam na mesma origem (proxy /api do Vite, ADR 0015).
"""

from __future__ import annotations

import asyncio
from datetime import datetime

from fastapi import APIRouter, HTTPException, Response

from app.api import respostas
from app.api.dependencias import (
    COOKIE_PASSE,
    COOKIE_SESSAO,
    Cfg,
    PasseCookie,
    SessaoCookie,
    apagar_banco_da_organizacao,
    contas,
    cookie_apagado,
    sessao_do_cookie,
    so_no_modo_real,
)
from app.contas.servico import (
    PASSE,
    AguardeParaTentar,
    CadastroRecusado,
    EntradaRecusada,
    NovaSessao,
    PosseNaoTransferida,
    SessaoAtiva,
)
from app.contas.servico import Conta as ContaServico
from app.contrato import (
    AtivacaoResposta,
    CadastroRequisicao,
    CadastroResposta,
    CodigoRequisicao,
    ContaResposta,
    EntrarRequisicao,
    EntrarResposta,
    EventoSeguranca,
    ExcluirContaRequisicao,
    OrganizacaoDaConta,
    SegundaEtapaRequisicao,
    SegundaEtapaResposta,
)
from app.nfe.importacao import agora_utc

rotas = APIRouter(tags=["contas"])

ENTRADA: respostas.Respostas = {
    **respostas.SO_MODO_REAL,
    401: {"description": "E-mail, senha ou código incorretos, ou passe vencido. A frase não diz qual."},
    429: {
        "description": "Espera depois de falhas seguidas na conta, conta bloqueada (100 falhas) ou limite por IP "
        "(header Retry-After)."
    },
}
SESSAO: respostas.Respostas = {
    **respostas.SO_MODO_REAL,
    401: {"description": "Sem sessão, ou sessão encerrada ou expirada (o cookie é apagado na resposta)."},
}


def _gravar_cookie(response: Response, nome: str, valor: str, ate: datetime, agora: datetime) -> None:
    response.set_cookie(
        nome,
        valor,
        max_age=max(1, int((ate - agora).total_seconds())),
        path="/",
        secure=True,
        httponly=True,
        samesite="strict",
    )


def _apagar_cookie(response: Response, nome: str) -> None:
    response.headers.append("Set-Cookie", cookie_apagado(nome))


def _recusa(e: EntradaRecusada | AguardeParaTentar | CadastroRecusado) -> HTTPException:
    if isinstance(e, AguardeParaTentar):
        return HTTPException(status_code=429, detail=e.mensagem, headers={"Retry-After": str(e.espera_s)})
    if isinstance(e, CadastroRecusado):
        return HTTPException(status_code=e.status, detail=e.mensagem)
    return HTTPException(status_code=401, detail=e.mensagem)


def _conta(c: ContaServico, expira: datetime) -> ContaResposta:
    return ContaResposta(
        email=c.email,
        criadaEm=c.criada_em,
        organizacao=OrganizacaoDaConta(id=c.organizacao_id, nome=c.organizacao_nome, papel=c.papel),
        empresas=c.empresas,
        codigosRecuperacaoRestantes=c.codigos_restantes,
        eventos=[EventoSeguranca(tipo=t, em=em) for t, em in c.eventos],
        sessaoExpiraEm=expira,
    )


def _sessao_aberta(cfg: Cfg, response: Response, nova: NovaSessao, agora: datetime) -> ContaResposta:
    _gravar_cookie(response, COOKIE_SESSAO, nova.token, nova.expira_em, agora)
    _apagar_cookie(response, COOKIE_PASSE)
    servico = contas(cfg)
    sessao = servico.sessao(nova.token, agora)
    if sessao is None:  # acabou de ser criada: só falha se o banco sumir no meio
        raise HTTPException(status_code=500, detail="Sessão não encontrada logo depois de criada.")
    return _conta(servico.conta(sessao), sessao.expira_em)


def _exigir_sessao(cfg: Cfg, token: str | None) -> SessaoAtiva:
    sessao = sessao_do_cookie(cfg, token)
    if sessao is None:
        raise HTTPException(status_code=401, detail="Entre com a sua conta.")
    return sessao


@rotas.post(
    "/contas",
    status_code=201,
    response_model=CadastroResposta,
    responses={
        **respostas.SO_MODO_REAL,
        **respostas.LIMITE,
        409: {"description": "Este e-mail já tem uma conta (sem confirmação de e-mail, o cadastro não esconde isso)."},
        422: {"description": "Senha recusada (curta, longa ou comum) ou entrada fora do contrato."},
    },
)
async def cadastrar(cfg: Cfg, req: CadastroRequisicao, response: Response) -> CadastroResposta:
    """Cria a conta (pendente) e a organização dela, e devolve o segredo do segundo fator. A conta só vale
    depois de POST /contas/ativar com o primeiro código do aplicativo, dentro do prazo."""
    so_no_modo_real(cfg)
    agora = agora_utc()
    try:
        feito = await asyncio.to_thread(contas(cfg).cadastrar, req.email, req.senha, req.organizacao.strip(), agora)
    except CadastroRecusado as e:
        raise _recusa(e) from None
    _gravar_cookie(response, COOKIE_PASSE, feito.passe, feito.expira_em, agora)
    return CadastroResposta(
        otpauth=feito.endereco,
        segredo=feito.segredo,
        expiraEm=feito.expira_em,
        aviso="Leia o QR code (ou digite o segredo) num aplicativo autenticador e envie o primeiro código. "
        "O segredo não aparece de novo.",
    )


@rotas.post("/contas/ativar", response_model=AtivacaoResposta, responses=ENTRADA)
async def ativar(cfg: Cfg, req: CodigoRequisicao, response: Response, passe: PasseCookie = None) -> AtivacaoResposta:
    """Confirma o primeiro código: a conta passa a valer, a sessão começa e saem os 10 códigos de recuperação."""
    so_no_modo_real(cfg)
    agora = agora_utc()
    try:
        sessao, codigos = await asyncio.to_thread(contas(cfg).ativar, passe or "", req.codigo, agora)
    except (EntradaRecusada, AguardeParaTentar) as e:
        raise _recusa(e) from None
    conta = await asyncio.to_thread(_sessao_aberta, cfg, response, sessao, agora)
    return AtivacaoResposta(
        conta=conta,
        codigosRecuperacao=codigos,
        aviso="Guarde os códigos de recuperação fora do celular. Cada um vale uma vez, no lugar do código do "
        "aplicativo, e eles não aparecem de novo.",
    )


@rotas.post("/sessoes", response_model=EntrarResposta, responses={**ENTRADA, **respostas.LIMITE})
async def entrar(cfg: Cfg, req: EntrarRequisicao, response: Response) -> EntrarResposta:
    """Primeira etapa: e-mail e senha. Certos, o passe vai no cookie e falta o código (POST /sessoes/codigo)."""
    so_no_modo_real(cfg)
    agora = agora_utc()
    try:
        passe = await asyncio.to_thread(contas(cfg).entrar, req.email, req.senha, agora)
    except (EntradaRecusada, AguardeParaTentar) as e:
        raise _recusa(e) from None
    expira = agora + PASSE
    _gravar_cookie(response, COOKIE_PASSE, passe, expira, agora)
    return EntrarResposta(expiraEm=expira)


@rotas.post("/sessoes/codigo", response_model=SegundaEtapaResposta, responses=ENTRADA)
async def segunda_etapa(
    cfg: Cfg, req: SegundaEtapaRequisicao, response: Response, passe: PasseCookie = None
) -> SegundaEtapaResposta:
    """Segunda etapa: o código do aplicativo ou um código de recuperação. Certo, a sessão começa (token novo a
    cada entrada). O código de recuperação usado deixa de valer e outro entra no lugar."""
    so_no_modo_real(cfg)
    agora = agora_utc()
    try:
        sessao, novo = await asyncio.to_thread(
            contas(cfg).confirmar_codigo, passe or "", req.codigo, req.codigoRecuperacao, agora
        )
    except (EntradaRecusada, AguardeParaTentar) as e:
        raise _recusa(e) from None
    conta = await asyncio.to_thread(_sessao_aberta, cfg, response, sessao, agora)
    aviso = None
    if novo is not None:
        aviso = "Você entrou com um código de recuperação, que deixou de valer. Guarde o novo código no lugar dele."
    return SegundaEtapaResposta(conta=conta, novoCodigoRecuperacao=novo, aviso=aviso)


@rotas.get("/conta", response_model=ContaResposta, responses=SESSAO)
def conta(cfg: Cfg, sessao_token: SessaoCookie = None) -> ContaResposta:
    """Quem entrou: e-mail, organização e papel, empresas, códigos de recuperação restantes e avisos."""
    so_no_modo_real(cfg)
    sessao = _exigir_sessao(cfg, sessao_token)
    return _conta(contas(cfg).conta(sessao), sessao.expira_em)


@rotas.delete("/sessoes/atual", status_code=204, responses=SESSAO)
def sair(cfg: Cfg, response: Response, sessao_token: SessaoCookie = None) -> None:
    """Sai neste aparelho: a sessão é apagada no servidor, e não só o cookie."""
    so_no_modo_real(cfg)
    if sessao_token is not None:
        contas(cfg).sair(sessao_token)
    _apagar_cookie(response, COOKIE_SESSAO)


@rotas.delete("/sessoes", status_code=204, responses=SESSAO)
def sair_de_todos(cfg: Cfg, response: Response, sessao_token: SessaoCookie = None) -> None:
    """Sai em todos os aparelhos: apaga todas as sessões da conta."""
    so_no_modo_real(cfg)
    sessao = _exigir_sessao(cfg, sessao_token)
    contas(cfg).sair_de_todas(sessao.usuario_id)
    _apagar_cookie(response, COOKIE_SESSAO)


@rotas.post(
    "/conta/excluir",
    status_code=204,
    responses={
        **SESSAO,
        **respostas.LIMITE,
        409: {"description": "A única dona de uma organização com outros membros precisa passar a posse antes."},
        429: {"description": "Espera depois de falhas seguidas, ou conta bloqueada (header Retry-After)."},
    },
)
async def excluir(cfg: Cfg, req: ExcluirContaRequisicao, response: Response, sessao_token: SessaoCookie = None) -> None:
    """Apaga a conta (LGPD, art. 18 VI), com a senha de novo. Se a pessoa é a única integrante da organização, a
    organização e os dados dela vão junto, inclusive o banco de estado."""
    so_no_modo_real(cfg)
    sessao = await asyncio.to_thread(_exigir_sessao, cfg, sessao_token)
    try:
        feito = await asyncio.to_thread(contas(cfg).excluir, sessao, req.senha, agora_utc())
    except (EntradaRecusada, AguardeParaTentar) as e:
        raise _recusa(e) from None
    except PosseNaoTransferida:
        raise HTTPException(
            status_code=409, detail="Passe a posse da organização a outro membro antes de excluir a conta."
        ) from None
    if feito.organizacao_apagada is not None:
        await asyncio.to_thread(apagar_banco_da_organizacao, cfg, feito.organizacao_apagada)
    _apagar_cookie(response, COOKIE_SESSAO)
