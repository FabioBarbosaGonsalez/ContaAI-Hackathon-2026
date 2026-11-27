"""Dependências das rotas: configuração, clientes dos motores e dos dados abertos, estado (banco da demonstração,
espaço de avaliação, ADR 0010, ou banco da organização de quem entrou com a conta, ADR 0015) e token da demo."""

from __future__ import annotations

import logging
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import timedelta
from functools import lru_cache
from pathlib import Path
from typing import Annotated

import httpx
from fastapi import Cookie, Depends, Header, HTTPException, Response

from app.config import Configuracao, configuracao
from app.contas.servico import Contas, SessaoAtiva
from app.motores.cache import CacheRespostas
from app.motores.cliente import ClienteMotores
from app.motores.dados_abertos import CacheConsultas, DadosAbertos
from app.nfe.consultas import AVISO_DEMO, AVISO_EMPRESA_PROPRIA, NaoEncontrado
from app.nfe.importacao import agora_utc
from app.persistencia.banco import Banco
from app.persistencia.espacos import PADRAO_ID, Espaco, Espacos
from app.persistencia.repositorio import Repositorio
from app.seguranca import token_confere

Cfg = Annotated[Configuracao, Depends(configuracao)]
Token = Annotated[str | None, Header(alias="X-ContaAI-Token")]
EspacoId = Annotated[
    str | None,
    Header(
        alias="X-ContaAI-Espaco",
        pattern=PADRAO_ID,
        description="Id de um espaço de avaliação (POST /espacos). Sem ele, vale a demonstração compartilhada.",
    ),
]

log = logging.getLogger("contaai")

# Cookies da conta (ADR 0015): HttpOnly, Secure, SameSite=Strict, Path=/ e sem Domain, o que o prefixo __Host-
# exige do navegador. A sessão dura até 8 h; o passe, entre a senha e o código, 5 min.
# Papéis na organização (C3-B, etapa 8; ADR 0017). As listas dizem quem pode, nunca quem não pode: um papel que
# não está nelas (o contador do 3c, por exemplo) não muda nada até ser posto aqui de propósito.
# - editar: o catálogo, os clientes B2B, as notas, os preços, os alertas e as classificações;
# - administrar: cadastrar, configurar e excluir a empresa.
# Ler (catálogo, alertas, notas, a empresa, a explicação e o chat) vale para todo integrante da organização.
PAPEIS_QUE_EDITAM = frozenset({"dono", "membro"})
PAPEIS_QUE_ADMINISTRAM = frozenset({"dono"})
RECUSA_EDICAO = "O seu papel na organização não permite mudar os dados da empresa."

COOKIE_SESSAO = "__Host-contaai_sessao"
COOKIE_PASSE = "__Host-contaai_passe"
SessaoCookie = Annotated[str | None, Cookie(alias=COOKIE_SESSAO, include_in_schema=False)]
PasseCookie = Annotated[str | None, Cookie(alias=COOKIE_PASSE, include_in_schema=False)]
_ID_ORGANIZACAO = re.compile(r"^[0-9a-f]{32}$")
# O banco da organização e os arquivos que o SQLite cria ao lado dele (WAL, memória compartilhada e diário).
_ARQUIVO_DA_ORGANIZACAO = re.compile(r"^([0-9a-f]{32})\.db(-wal|-shm|-journal)?$")


def cookie_apagado(nome: str) -> str:
    return f"{nome}=; Max-Age=0; Path=/; Secure; HttpOnly; SameSite=Strict"


# Um cache por processo, compartilhado entre as requisições (app/motores/cache.py).
CACHE_MOTORES = CacheRespostas(configuracao().cache_motores_itens)
# Tabelas oficiais dos dados abertos (iguais para todos): um cache por processo.
CACHE_DADOS_ABERTOS = CacheConsultas()


def novo_cliente_motores(http: httpx.AsyncClient, cfg: Configuracao) -> ClienteMotores:
    return ClienteMotores(http, cfg.motor_rr_url, cfg.motor_sn_url, CACHE_MOTORES)


def http_interno(timeout_s: float) -> httpx.AsyncClient:
    """Cliente HTTP para os motores e o provedor: trust_env=False, nunca passa por proxy do ambiente."""
    return httpx.AsyncClient(timeout=timeout_s, trust_env=False)


async def cliente_motores(cfg: Cfg) -> AsyncIterator[ClienteMotores]:
    async with http_interno(cfg.timeout_calculo_s) as http:
        yield novo_cliente_motores(http, cfg)


async def dados_abertos(cfg: Cfg) -> AsyncIterator[DadosAbertos]:
    async with http_interno(cfg.timeout_calculo_s) as http:
        yield DadosAbertos(http, cfg.motor_rr_url, cfg.motor_sn_url, CACHE_DADOS_ABERTOS)


Motores = Annotated[ClienteMotores, Depends(cliente_motores)]
Dados = Annotated[DadosAbertos, Depends(dados_abertos)]


@lru_cache(maxsize=256)
def banco(caminho: Path) -> Banco:
    """Um Banco por arquivo, migrado na primeira vez que é pedido (inclusive na subida, no modo real).

    Com teto: cada espaço de avaliação e cada organização é um arquivo, e sem teto o cache cresceria enquanto o
    processo vive. Um arquivo que sai do cache só roda `migrar()` de novo ao voltar, sem nada a aplicar."""
    b = Banco(caminho)
    b.migrar()
    return b


def repositorio(cfg: Configuracao) -> Repositorio:
    """Chamado só no ramo do modo real: no modo mock nenhuma rota cria o arquivo do banco."""
    return Repositorio(banco(cfg.banco_caminho))


@lru_cache
def _espacos(pasta: Path, validade_min: int, maximo: int) -> Espacos:
    """Um gerenciador por pasta, no processo: guarda se o banco-modelo já foi montado."""
    return Espacos(pasta, timedelta(minutes=validade_min), maximo)


def espacos(cfg: Configuracao) -> Espacos:
    return _espacos(cfg.banco_caminho.parent / "espacos", cfg.espaco_validade_min, cfg.espacos_max)


@dataclass(frozen=True)
class Estado:
    """Onde a requisição lê e grava: a demonstração compartilhada (espaco e sessao None), um espaço de avaliação
    ou o banco da organização de quem entrou com a conta (ADR 0015)."""

    repositorio: Repositorio
    espaco: Espaco | None = None
    sessao: SessaoAtiva | None = None
    cnpjs: frozenset[str] = field(default_factory=frozenset)

    @property
    def na_demo(self) -> bool:
        return self.espaco is None and self.sessao is None

    @property
    def na_empresa_propria(self) -> bool:
        """O banco da organização de quem entrou: dados reais, o CNPJ precisa do dígito certo (C3-B, ADR 0017)."""
        return self.espaco is None and self.sessao is not None

    @property
    def aviso(self) -> str:
        return AVISO_EMPRESA_PROPRIA if self.na_empresa_propria else AVISO_DEMO

    def exigir_empresa(self, cnpj: str) -> None:
        """CNPJ fora do alcance de quem chama: o mesmo 404 de uma empresa que não existe, para não dizer quais
        CNPJs existem (ADR 0015)."""
        if cnpj not in self.cnpjs:
            raise NaoEncontrado("Empresa não cadastrada.")


@lru_cache
def _contas(caminho: Path) -> Contas:
    return Contas(caminho)


def contas(cfg: Configuracao) -> Contas:
    return _contas(cfg.contas_caminho)


def banco_da_organizacao(cfg: Configuracao, organizacao_id: str) -> Banco:
    if not _ID_ORGANIZACAO.fullmatch(organizacao_id):  # o id vira nome de arquivo: só depois de conferido
        raise ValueError("Id de organização fora do padrão.")
    cfg.pasta_organizacoes.mkdir(parents=True, exist_ok=True)
    return banco(cfg.pasta_organizacoes / f"{organizacao_id}.db")


def apagar_banco_da_organizacao(cfg: Configuracao, organizacao_id: str) -> None:
    """Depois de excluir a organização (LGPD, art. 18 VI). Um arquivo preso (Windows) fica registrado no log."""
    if not _ID_ORGANIZACAO.fullmatch(organizacao_id):
        return
    base = cfg.pasta_organizacoes / f"{organizacao_id}.db"
    banco.cache_clear()  # o Banco guardado no cache apontaria para um arquivo apagado
    for caminho in (base, base.with_name(base.name + "-wal"), base.with_name(base.name + "-shm")):
        try:
            caminho.unlink(missing_ok=True)
        except OSError:
            log.warning("Arquivo de estado de uma organização excluída ficou no disco: %s", caminho.name)


def limpar_bancos_orfaos(cfg: Configuracao) -> list[str]:
    """Na subida (C3-B, etapa 7): apaga os bancos de organização que não existem mais no contas.db. Sobram, por
    exemplo, quando o arquivo estava preso (Windows) na hora da exclusão, ou quando a exclusão parou no meio. Um nome
    fora do padrão não é apagado: fica no disco e aparece no log, só pelo nome do arquivo.

    A pasta é lida antes das organizações: uma organização nova grava a linha no contas.db antes de existir o
    arquivo dela (que só nasce com a sessão), então um arquivo visto aqui nunca é de uma organização que ainda não
    foi lida. Devolve os nomes apagados."""
    pasta = cfg.pasta_organizacoes
    if not pasta.is_dir():
        return []
    arquivos = sorted(pasta.iterdir())
    existentes = contas(cfg).organizacoes()
    apagados = []
    for arquivo in arquivos:
        achado = _ARQUIVO_DA_ORGANIZACAO.fullmatch(arquivo.name)
        if achado is None:
            log.warning("Arquivo fora do padrão na pasta das organizações (não apagado): %s", arquivo.name)
            continue
        if achado.group(1) in existentes:
            continue
        try:
            arquivo.unlink()
        except OSError:
            log.warning("Arquivo de estado de uma organização excluída ficou no disco: %s", arquivo.name)
            continue
        apagados.append(arquivo.name)
    if apagados:
        banco.cache_clear()
        log.info("Subida: %d arquivo(s) de organizações excluídas apagado(s).", len(apagados))
    return apagados


def sessao_do_cookie(cfg: Configuracao, token: str | None) -> SessaoAtiva | None:
    """A sessão do cookie, ou None sem cookie. Cookie vencido ou desconhecido: 401, e a resposta apaga o cookie."""
    if token is None:
        return None
    sessao = contas(cfg).sessao(token, agora_utc())
    if sessao is None:
        raise HTTPException(
            status_code=401,
            detail="Sessão encerrada ou expirada. Entre de novo.",
            headers={"Set-Cookie": cookie_apagado(COOKIE_SESSAO)},
        )
    return sessao


def _cnpjs_do_banco(repo: Repositorio) -> frozenset[str]:
    with repo.leitura() as s:
        return frozenset(reg.empresa.cnpj for reg in s.empresas())


def abrir_estado(cfg: Configuracao, espaco_id: str | None, token_sessao: str | None = None) -> Estado:
    """Só no ramo do modo real. Ordem: o espaço do header (escolha explícita, também para quem tem conta), depois
    a sessão do cookie, depois a demonstração compartilhada. Espaço desconhecido ou vencido: EspacoInexistente
    (404); sessão vencida: 401."""
    if espaco_id is not None:
        gerenciador = espacos(cfg)
        espaco = gerenciador.abrir(espaco_id, agora_utc())
        # banco() migra uma vez por processo: um espaço copiado antes de uma migração nova (ex.: a 0002, com o
        # processo anterior no ar) recebe a migração ao ser aberto, em vez de falhar na primeira gravação.
        repo = Repositorio(banco(gerenciador.banco(espaco.id).caminho))
        return Estado(repo, espaco, cnpjs=_cnpjs_do_banco(repo))
    sessao = sessao_do_cookie(cfg, token_sessao)
    if sessao is not None:
        repo = Repositorio(banco_da_organizacao(cfg, sessao.organizacao_id))
        return Estado(repo, sessao=sessao, cnpjs=contas(cfg).empresas(sessao.organizacao_id))
    repo = repositorio(cfg)
    return Estado(repo, cnpjs=_cnpjs_do_banco(repo))


def exigir_papel(sessao: SessaoAtiva, papeis: frozenset[str], detalhe: str) -> None:
    """403 para quem não tem um dos papéis da lista (C3-B, etapa 8)."""
    if sessao.papel not in papeis:
        raise HTTPException(status_code=403, detail=detalhe)


def exigir_permissao_para_mudar(cfg: Configuracao, token: str | None, estado: Estado) -> None:
    """Toda rota que muda o estado passa por aqui. Na demonstração compartilhada, o token. No espaço (isolado e com
    validade, ADR 0010), nada a mais. No banco da organização, a sessão já diz quem é (ADR 0015) e o papel precisa
    estar em PAPEIS_QUE_EDITAM."""
    if estado.na_demo:
        exigir_token(cfg, token)
    elif estado.sessao is not None:
        exigir_papel(estado.sessao, PAPEIS_QUE_EDITAM, RECUSA_EDICAO)


def exigir_token(cfg: Configuracao, token: str | None) -> None:
    """Rotas que mudam o estado compartilhado da demo (e o chat) exigem o token, quando ele está configurado."""
    if not token_confere(cfg.token_demo, token):
        raise HTTPException(status_code=401, detail="Token da demo ausente ou inválido.")


def so_no_modo_real(cfg: Configuracao, detalhe: str = "Esta rota muda o estado e só funciona no modo real.") -> None:
    if cfg.modo != "real":
        raise HTTPException(status_code=501, detail=detalhe)


def marcar_mock(response: Response) -> None:
    """Toda resposta montada a partir dos mocks leva X-ContaAI-Mock: 1."""
    response.headers["X-ContaAI-Mock"] = "1"
