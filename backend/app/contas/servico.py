"""Contas (C1, ADR 0015): cadastro, segundo fator, entrada, sessão, tentativas e exclusão, sobre o contas.db.

Tokens (sessão e passe): 256 bits de `secrets.token_urlsafe`, e só o SHA-256 vai ao banco (OWASP, Session
Management). Quem lê o banco não consegue se passar por ninguém.

Tempos (OWASP, Session Management, e NIST SP 800-63B-4):
- sessão: 30 min sem uso e 8 h no total; token novo a cada entrada, contra sessão fixada;
- passe (entre a senha e o código, e entre o cadastro e a confirmação): 5 min;
- cadastro pendente: 30 min; depois, o e-mail fica livre de novo.

Tentativas (NIST 3.2.2): falhas seguidas por conta, somando senha, código e código de recuperação. Da 5ª em
diante, espera crescente (30 s, dobrando, até 1 h); na 100ª, a conta é bloqueada e só um administrador
desbloqueia (`python -m app.contas desbloquear <e-mail>`). Entrar com sucesso zera as falhas. Um e-mail sem conta
tem o mesmo contador, só em memória, para que a resposta não diga se a conta existe.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
import sqlite3
from collections import OrderedDict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.contas import senha as regras
from app.contas import totp
from app.persistencia.banco import Banco

PASTA_MIGRACOES = Path(__file__).with_name("migracoes")

SESSAO_OCIOSA = timedelta(minutes=30)
SESSAO_TOTAL = timedelta(hours=8)
PASSE = timedelta(minutes=5)
PENDENTE = timedelta(minutes=30)
# Gravar o último uso no máximo uma vez por minuto: cada GET não vira uma escrita.
ATUALIZAR_USO = timedelta(minutes=1)

FALHAS_PARA_ESPERAR = 5
FALHAS_PARA_BLOQUEAR = 100
ESPERA_INICIAL_S = 30
ESPERA_MAXIMA_S = 3600
CODIGOS_RECUPERACAO = 10
MAX_DESCONHECIDOS = 10_000

MENSAGEM_ENTRADA = "E-mail, senha ou código incorretos."
MENSAGEM_BLOQUEADA = (
    "Conta bloqueada depois de muitas tentativas erradas. Peça o desbloqueio ao administrador do ContaAI."
)


# -- erros ------------------------------------------------------------------------------------------------


class EntradaRecusada(Exception):
    """401. A mensagem não diz o que estava errado (e-mail, senha, código ou passe)."""

    def __init__(self, mensagem: str = MENSAGEM_ENTRADA) -> None:
        super().__init__(mensagem)
        self.mensagem = mensagem


class AguardeParaTentar(Exception):
    """429 com Retry-After: espera crescente depois de falhas seguidas, ou conta bloqueada."""

    def __init__(self, espera_s: int, mensagem: str | None = None) -> None:
        super().__init__(mensagem or "Muitas tentativas erradas. Espere um pouco e tente de novo.")
        self.espera_s = espera_s
        self.mensagem = str(self)


class ContaBloqueada(AguardeParaTentar):
    """429 da conta bloqueada (100 falhas): só um administrador desbloqueia, e esperar não adianta. Sai com o tipo
    /problemas/conta-bloqueada, para a tela não mostrar uma contagem. O Retry-After (1 h) fica, para um cliente
    automático não insistir. Um e-mail sem conta também chega a este bloqueio (contador em memória), então a
    resposta não revela se o e-mail tem conta."""

    def __init__(self) -> None:
        super().__init__(ESPERA_MAXIMA_S, MENSAGEM_BLOQUEADA)


class CadastroRecusado(Exception):
    """409 (e-mail já usado) ou 422 (senha recusada)."""

    def __init__(self, mensagem: str, status: int) -> None:
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.status = status


class PosseNaoTransferida(Exception):
    """409: a única dona de uma organização com outros membros precisa passar a posse antes de sair."""


# -- tipos ------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Cadastro:
    passe: str
    segredo: str
    endereco: str
    expira_em: datetime


@dataclass(frozen=True)
class Entrada:
    """O resultado da primeira etapa. `ativacao` vem só para a conta pendente: o segredo novo do segundo fator,
    porque a pessoa ainda não confirmou o primeiro código (plano v2.1, C2b, decisão 1)."""

    passe: str
    expira_em: datetime
    ativacao: Cadastro | None = None


@dataclass(frozen=True)
class NovaSessao:
    token: str
    expira_em: datetime


@dataclass(frozen=True)
class SessaoAtiva:
    usuario_id: str
    organizacao_id: str
    email: str
    papel: str
    expira_em: datetime


@dataclass(frozen=True)
class Conta:
    email: str
    criada_em: datetime
    organizacao_id: str
    organizacao_nome: str
    papel: str
    empresas: list[str]
    codigos_restantes: int
    eventos: list[tuple[str, datetime]]
    # A versão dos termos de uso aceita no cadastro e quando; None para conta de antes da migração 0002.
    termos: tuple[str, datetime] | None


@dataclass(frozen=True)
class Exclusao:
    """As organizações que saíram junto com a pessoa (as que só tinham ela): os bancos delas também saem."""

    organizacoes_apagadas: list[str]


@dataclass(frozen=True)
class OrganizacaoDaPessoa:
    id: str
    nome: str
    criada_em: datetime
    papel: str
    desde: datetime
    acessos: list[tuple[str, datetime]]  # (CNPJ, desde)


@dataclass(frozen=True)
class DadosDaPessoa:
    """O que o contas.db guarda da pessoa, para o arquivo dos dados (LGPD, art. 19). Sem a senha, o segredo do TOTP
    e os hashes (de senha, token e código)."""

    email: str
    criada_em: datetime
    situacao: str
    termos: tuple[str, datetime] | None
    segundo_fator_confirmado_em: datetime | None
    codigos_restantes: int
    tentativas: tuple[int, datetime | None, bool] | None  # (falhas seguidas, espera até, bloqueada)
    eventos: list[tuple[str, datetime]]
    sessoes: list[tuple[datetime, datetime, datetime, bool]]  # (criada, último uso, expira, é a atual)
    organizacoes: list[OrganizacaoDaPessoa]


# -- apoio ------------------------------------------------------------------------------------------------


def _t(quando: datetime) -> str:
    """Sempre o mesmo formato (UTC, microssegundos), para comparar datas como texto, igual no PostgreSQL."""
    return quando.astimezone(UTC).isoformat(timespec="microseconds")


def _d(texto: str) -> datetime:
    return datetime.fromisoformat(texto)


def _resumo(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def _novo_id() -> str:
    return secrets.token_hex(16)


def _novo_token() -> str:
    return secrets.token_urlsafe(32)


def _novo_codigo_recuperacao() -> str:
    """65 bits: 13 caracteres de base32 (A a Z e 2 a 7, sem 0, 1, 8 e 9), em 3 grupos para ler e digitar. O NIST
    (4.2) pede pelo menos 64 bits."""
    corpo = base64.b32encode(secrets.token_bytes(9)).decode("ascii")[:13]  # 72 bits sorteados, 65 usados
    return f"{corpo[:4]}-{corpo[4:8]}-{corpo[8:]}"


def normalizar_codigo_recuperacao(codigo: str) -> str:
    limpo = "".join(c for c in codigo.upper() if c.isalnum())
    return f"{limpo[:4]}-{limpo[4:8]}-{limpo[8:]}"


def normalizar_email(email: str) -> str:
    return email.strip().lower()


def _espera(falhas: int) -> int:
    """Segundos de espera depois de `falhas` falhas seguidas (0 antes da 5ª)."""
    if falhas < FALHAS_PARA_ESPERAR:
        return 0
    return min(ESPERA_INICIAL_S * 2 ** (falhas - FALHAS_PARA_ESPERAR), ESPERA_MAXIMA_S)


@dataclass
class _Falhas:
    falhas: int = 0
    espera_ate: datetime | None = None

    @property
    def bloqueada(self) -> bool:
        return self.falhas >= FALHAS_PARA_BLOQUEAR


class _FalhasDesconhecidas:
    """O contador dos e-mails sem conta, em memória e com teto (os mais antigos saem)."""

    def __init__(self, maximo: int = MAX_DESCONHECIDOS) -> None:
        self.maximo = maximo
        self._vistos: OrderedDict[str, _Falhas] = OrderedDict()

    def de(self, email: str) -> _Falhas:
        chave = _resumo(email)
        achado = self._vistos.get(chave)
        if achado is None:
            achado = _Falhas()
            self._vistos[chave] = achado
            while len(self._vistos) > self.maximo:
                self._vistos.popitem(last=False)
        self._vistos.move_to_end(chave)
        return achado


def _barrar(falhas: _Falhas, agora: datetime) -> None:
    if falhas.bloqueada:
        raise ContaBloqueada
    if falhas.espera_ate is not None and falhas.espera_ate > agora:
        raise AguardeParaTentar(max(1, int((falhas.espera_ate - agora).total_seconds()) + 1))


def _somar_falha(falhas: _Falhas, agora: datetime) -> None:
    falhas.falhas += 1
    espera = _espera(falhas.falhas)
    falhas.espera_ate = agora + timedelta(seconds=espera) if espera else None


# -- serviço ----------------------------------------------------------------------------------------------


class Contas:
    def __init__(self, caminho: Path) -> None:
        self.banco = Banco(caminho, PASTA_MIGRACOES)
        self.banco.migrar()
        self._desconhecidos = _FalhasDesconhecidas()

    # -- tentativas -------------------------------------------------------------------------------------

    def _falhas(self, c: sqlite3.Connection, usuario_id: str) -> _Falhas:
        linha = c.execute(
            "SELECT falhas_seguidas, espera_ate FROM tentativas WHERE usuario_id = ?", (usuario_id,)
        ).fetchone()
        if linha is None:
            return _Falhas()
        return _Falhas(linha["falhas_seguidas"], _d(linha["espera_ate"]) if linha["espera_ate"] else None)

    def _gravar_falhas(self, c: sqlite3.Connection, usuario_id: str, falhas: _Falhas) -> None:
        c.execute(
            "INSERT INTO tentativas (usuario_id, falhas_seguidas, espera_ate, bloqueada) VALUES (?, ?, ?, ?) "
            "ON CONFLICT (usuario_id) DO UPDATE SET falhas_seguidas = excluded.falhas_seguidas, "
            "espera_ate = excluded.espera_ate, bloqueada = excluded.bloqueada",
            (
                usuario_id,
                falhas.falhas,
                _t(falhas.espera_ate) if falhas.espera_ate else None,
                1 if falhas.bloqueada else 0,
            ),
        )

    def _falhou(self, usuario_id: str, agora: datetime) -> None:
        """Soma a falha numa transação própria: ela fica gravada mesmo com o erro que vem depois."""
        with self.banco.transacao(escrita=True) as c:
            falhas = self._falhas(c, usuario_id)
            _somar_falha(falhas, agora)
            self._gravar_falhas(c, usuario_id, falhas)

    # -- limpeza ----------------------------------------------------------------------------------------

    def _limpar(self, c: sqlite3.Connection, agora: datetime) -> None:
        t = _t(agora)
        c.execute("DELETE FROM passes WHERE expira_em <= ?", (t,))
        c.execute("DELETE FROM sessoes WHERE expira_em <= ? OR ultimo_uso <= ?", (t, _t(agora - SESSAO_OCIOSA)))
        vencidos = [
            r["id"]
            for r in c.execute("SELECT id FROM usuarios WHERE situacao = 'pendente' AND pendente_ate <= ?", (t,))
        ]
        for usuario_id in vencidos:
            self._apagar_usuario(c, usuario_id)

    def _apagar_usuario(self, c: sqlite3.Connection, usuario_id: str) -> list[str]:
        """Apaga a pessoa e as organizações em que ela era a única integrante. Devolve os ids delas."""
        sozinha = [
            r["organizacao_id"]
            for r in c.execute(
                "SELECT m.organizacao_id FROM membros m WHERE m.usuario_id = ? AND "
                "(SELECT count(*) FROM membros o WHERE o.organizacao_id = m.organizacao_id) = 1",
                (usuario_id,),
            )
        ]
        c.execute("DELETE FROM usuarios WHERE id = ?", (usuario_id,))
        c.executemany("DELETE FROM organizacoes WHERE id = ?", [(o,) for o in sozinha])
        return sozinha

    # -- cadastro e ativação ----------------------------------------------------------------------------

    def cadastrar(self, email: str, senha: str, organizacao: str, termos_versao: str, agora: datetime) -> Cadastro:
        """Cria a pessoa (pendente) e a organização dela, com o segredo do TOTP e a versão dos termos de uso
        aceita (o contrato já conferiu que é a atual). A conta só vale depois de confirmar o primeiro código."""
        email = normalizar_email(email)
        try:
            normalizada = regras.conferir_nova(senha, email)
        except regras.SenhaRecusada as e:
            raise CadastroRecusado(str(e), 422) from None
        senha_hash = regras.gerar_hash(normalizada)
        segredo = totp.novo_segredo()
        passe = _novo_token()
        expira = agora + PASSE
        with self.banco.transacao(escrita=True) as c:
            self._limpar(c, agora)
            if c.execute("SELECT 1 FROM usuarios WHERE email = ?", (email,)).fetchone():
                # Sem confirmação de e-mail (decisão 2), o cadastro não consegue esconder que o e-mail já tem
                # conta: qualquer resposta falsa se denuncia na ativação (ADR 0015). A entrada esconde.
                raise CadastroRecusado("Este e-mail já tem uma conta. Entre com a senha e o código.", 409)
            usuario_id, organizacao_id = _novo_id(), _novo_id()
            c.execute(
                "INSERT INTO organizacoes (id, nome, criada_em) VALUES (?, ?, ?)",
                (organizacao_id, organizacao, _t(agora)),
            )
            c.execute(
                "INSERT INTO usuarios "
                "(id, email, senha_hash, situacao, pendente_ate, criado_em, termos_versao, termos_aceitos_em) "
                "VALUES (?, ?, ?, 'pendente', ?, ?, ?, ?)",
                (usuario_id, email, senha_hash, _t(agora + PENDENTE), _t(agora), termos_versao, _t(agora)),
            )
            c.execute(
                "INSERT INTO membros (organizacao_id, usuario_id, papel, desde) VALUES (?, ?, 'dono', ?)",
                (organizacao_id, usuario_id, _t(agora)),
            )
            c.execute("INSERT INTO segundo_fator (usuario_id, segredo) VALUES (?, ?)", (usuario_id, segredo))
            c.execute(
                "INSERT INTO passes (hash, usuario_id, tipo, expira_em) VALUES (?, ?, 'ativacao', ?)",
                (_resumo(passe), usuario_id, _t(expira)),
            )
        return Cadastro(passe, segredo, totp.endereco(segredo, email), expira)

    def ativar(self, passe: str, codigo: str, agora: datetime) -> tuple[NovaSessao, list[str]]:
        """Confirma o primeiro código: a conta passa a valer, nascem os códigos de recuperação e a sessão."""
        usuario_id = self._usuario_do_passe(passe, "ativacao", agora)
        codigos = [_novo_codigo_recuperacao() for _ in range(CODIGOS_RECUPERACAO)]
        # Conferir e gravar o passo na mesma transação de escrita: duas requisições com o mesmo código não
        # passam as duas.
        with self.banco.transacao(escrita=True) as c:
            _barrar(self._falhas(c, usuario_id), agora)
            fator = c.execute("SELECT segredo, ultimo_passo FROM segundo_fator WHERE usuario_id = ?", (usuario_id,))
            linha = fator.fetchone()
            usado = totp.conferir(linha["segredo"], codigo, agora.timestamp(), linha["ultimo_passo"])
            if usado is not None:
                sessao = self._ativar(c, usuario_id, usado, codigos, agora)
        if usado is None:
            self._falhou(usuario_id, agora)
            raise EntradaRecusada
        return sessao, codigos

    def _ativar(
        self, c: sqlite3.Connection, usuario_id: str, usado: int, codigos: list[str], agora: datetime
    ) -> NovaSessao:
        c.execute("UPDATE usuarios SET situacao = 'ativa', pendente_ate = NULL WHERE id = ?", (usuario_id,))
        c.execute(
            "UPDATE segundo_fator SET ultimo_passo = ?, confirmado_em = ? WHERE usuario_id = ?",
            (usado, _t(agora), usuario_id),
        )
        c.executemany(
            "INSERT INTO codigos_recuperacao (hash, usuario_id, criado_em) VALUES (?, ?, ?)",
            [(_resumo(x), usuario_id, _t(agora)) for x in codigos],
        )
        c.execute("DELETE FROM passes WHERE usuario_id = ?", (usuario_id,))
        c.execute("DELETE FROM tentativas WHERE usuario_id = ?", (usuario_id,))
        return self._abrir_sessao(c, usuario_id, agora)

    # -- entrada ----------------------------------------------------------------------------------------

    def entrar(self, email: str, senha: str, agora: datetime) -> Entrada:
        """Primeira etapa: confere a senha e devolve o passe para a segunda (o código).

        Conta pendente com a senha certa (o passe da ativação venceu antes do primeiro código): sai um passe novo
        de ativação, com um segredo novo, e a pessoa volta ao passo do QR. Sem isso, o e-mail ficaria preso até o
        cadastro pendente vencer (o cadastro de novo dá 409). A senha é exigida, então ninguém de fora assume o
        cadastro, e a resposta só difere depois da senha certa: a entrada continua sem dizer se o e-mail existe.
        O segredo muda porque o antigo já foi entregue uma vez ("o segredo não aparece de novo")."""
        email = normalizar_email(email)
        with self.banco.transacao(escrita=True) as c:
            self._limpar(c, agora)
            linha = c.execute(
                "SELECT id, senha_hash, situacao FROM usuarios WHERE email = ? AND situacao IN ('ativa', 'pendente')",
                (email,),
            ).fetchone()
            falhas = self._falhas(c, linha["id"]) if linha else self._desconhecidos.de(email)
        _barrar(falhas, agora)
        if linha is None:
            regras.confere(regras.hash_de_mentira(), senha)  # o mesmo trabalho de uma conta que existe
            _somar_falha(falhas, agora)
            raise EntradaRecusada
        if not regras.confere(linha["senha_hash"], senha):
            self._falhou(linha["id"], agora)
            raise EntradaRecusada
        passe = _novo_token()
        expira = agora + PASSE
        pendente = linha["situacao"] == "pendente"
        with self.banco.transacao(escrita=True) as c:
            if regras.precisa_refazer(linha["senha_hash"]):
                c.execute(
                    "UPDATE usuarios SET senha_hash = ? WHERE id = ?",
                    (regras.gerar_hash(regras.normalizar(senha)), linha["id"]),
                )
            if not pendente:
                c.execute(
                    "INSERT INTO passes (hash, usuario_id, tipo, expira_em) VALUES (?, ?, 'entrada', ?)",
                    (_resumo(passe), linha["id"], _t(expira)),
                )
                return Entrada(passe, expira)
            segredo = totp.novo_segredo()
            # Só o passe novo vale; o cadastro pendente dura mais 30 min a partir daqui (não some no meio do passe).
            pendente_ate = _t(agora + PENDENTE)
            c.execute("DELETE FROM passes WHERE usuario_id = ?", (linha["id"],))
            c.execute(
                "UPDATE segundo_fator SET segredo = ?, ultimo_passo = 0 WHERE usuario_id = ?",
                (segredo, linha["id"]),
            )
            c.execute("UPDATE usuarios SET pendente_ate = ? WHERE id = ?", (pendente_ate, linha["id"]))
            c.execute(
                "INSERT INTO passes (hash, usuario_id, tipo, expira_em) VALUES (?, ?, 'ativacao', ?)",
                (_resumo(passe), linha["id"], _t(expira)),
            )
        return Entrada(passe, expira, Cadastro(passe, segredo, totp.endereco(segredo, email), expira))

    def confirmar_codigo(
        self, passe: str, codigo: str | None, recuperacao: str | None, agora: datetime
    ) -> tuple[NovaSessao, str | None]:
        """Segunda etapa: o código do aplicativo ou um código de recuperação. Com o de recuperação, ele deixa de
        valer, nasce outro no lugar (devolvido aqui, uma vez só) e a pessoa é avisada (NIST 4.2)."""
        usuario_id = self._usuario_do_passe(passe, "entrada", agora)
        with self.banco.transacao(escrita=True) as c:
            _barrar(self._falhas(c, usuario_id), agora)
            novo = None
            if recuperacao is not None:
                resumo = _resumo(normalizar_codigo_recuperacao(recuperacao))
                apagado = c.execute(
                    "DELETE FROM codigos_recuperacao WHERE hash = ? AND usuario_id = ?", (resumo, usuario_id)
                ).rowcount
                certo = apagado == 1
                if certo:
                    novo = _novo_codigo_recuperacao()
                    c.execute(
                        "INSERT INTO codigos_recuperacao (hash, usuario_id, criado_em) VALUES (?, ?, ?)",
                        (_resumo(novo), usuario_id, _t(agora)),
                    )
                    c.execute(
                        "INSERT INTO eventos_seguranca (id, usuario_id, tipo, em) VALUES (?, ?, ?, ?)",
                        (_novo_id(), usuario_id, "codigo-recuperacao-usado", _t(agora)),
                    )
            else:
                linha = c.execute(
                    "SELECT segredo, ultimo_passo FROM segundo_fator WHERE usuario_id = ?", (usuario_id,)
                ).fetchone()
                usado = totp.conferir(linha["segredo"], codigo or "", agora.timestamp(), linha["ultimo_passo"])
                certo = usado is not None
                if certo:
                    c.execute("UPDATE segundo_fator SET ultimo_passo = ? WHERE usuario_id = ?", (usado, usuario_id))
            if certo:
                c.execute("DELETE FROM passes WHERE usuario_id = ?", (usuario_id,))
                c.execute("DELETE FROM tentativas WHERE usuario_id = ?", (usuario_id,))
                sessao = self._abrir_sessao(c, usuario_id, agora)
        if not certo:
            self._falhou(usuario_id, agora)
            raise EntradaRecusada
        return sessao, novo

    def _usuario_do_passe(self, passe: str, tipo: str, agora: datetime) -> str:
        with self.banco.transacao() as c:
            linha = c.execute(
                "SELECT usuario_id FROM passes WHERE hash = ? AND tipo = ? AND expira_em > ?",
                (_resumo(passe), tipo, _t(agora)),
            ).fetchone()
        if linha is None:
            raise EntradaRecusada("O tempo para digitar o código acabou, ou o passo anterior não foi feito.")
        return str(linha["usuario_id"])

    # -- sessão -----------------------------------------------------------------------------------------

    def _abrir_sessao(self, c: sqlite3.Connection, usuario_id: str, agora: datetime) -> NovaSessao:
        organizacao = c.execute(
            "SELECT organizacao_id FROM membros WHERE usuario_id = ? ORDER BY desde LIMIT 1", (usuario_id,)
        ).fetchone()
        token = _novo_token()
        expira = agora + SESSAO_TOTAL
        c.execute(
            "INSERT INTO sessoes (hash, usuario_id, organizacao_id, criada_em, ultimo_uso, expira_em) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (_resumo(token), usuario_id, organizacao["organizacao_id"], _t(agora), _t(agora), _t(expira)),
        )
        return NovaSessao(token, expira)

    def sessao(self, token: str, agora: datetime) -> SessaoAtiva | None:
        """A sessão válida deste token, ou None (desconhecida, sem uso há 30 min ou com mais de 8 h)."""
        resumo = _resumo(token)
        with self.banco.transacao() as c:
            linha = c.execute(
                "SELECT s.usuario_id, s.organizacao_id, s.ultimo_uso, s.expira_em, u.email, m.papel "
                "FROM sessoes s JOIN usuarios u ON u.id = s.usuario_id "
                "JOIN membros m ON m.usuario_id = s.usuario_id AND m.organizacao_id = s.organizacao_id "
                "WHERE s.hash = ?",
                (resumo,),
            ).fetchone()
        if linha is None:
            return None
        ultimo, expira = _d(linha["ultimo_uso"]), _d(linha["expira_em"])
        if expira <= agora or ultimo + SESSAO_OCIOSA <= agora:
            with self.banco.transacao(escrita=True) as c:
                c.execute("DELETE FROM sessoes WHERE hash = ?", (resumo,))
            return None
        if agora - ultimo >= ATUALIZAR_USO:
            with self.banco.transacao(escrita=True) as c:
                c.execute("UPDATE sessoes SET ultimo_uso = ? WHERE hash = ?", (_t(agora), resumo))
        return SessaoAtiva(linha["usuario_id"], linha["organizacao_id"], linha["email"], linha["papel"], expira)

    def sair(self, token: str) -> None:
        with self.banco.transacao(escrita=True) as c:
            c.execute("DELETE FROM sessoes WHERE hash = ?", (_resumo(token),))

    def sair_de_todas(self, usuario_id: str) -> int:
        with self.banco.transacao(escrita=True) as c:
            return int(c.execute("DELETE FROM sessoes WHERE usuario_id = ?", (usuario_id,)).rowcount)

    # -- conta ------------------------------------------------------------------------------------------

    def conta(self, sessao: SessaoAtiva) -> Conta:
        with self.banco.transacao() as c:
            usuario = c.execute(
                "SELECT criado_em, termos_versao, termos_aceitos_em FROM usuarios WHERE id = ?", (sessao.usuario_id,)
            ).fetchone()
            org = c.execute("SELECT nome FROM organizacoes WHERE id = ?", (sessao.organizacao_id,)).fetchone()
            empresas = [
                r["cnpj"]
                for r in c.execute(
                    "SELECT cnpj FROM acessos_empresa WHERE organizacao_id = ? ORDER BY cnpj", (sessao.organizacao_id,)
                )
            ]
            restantes = c.execute(
                "SELECT count(*) AS n FROM codigos_recuperacao WHERE usuario_id = ?", (sessao.usuario_id,)
            ).fetchone()["n"]
            eventos = [
                (r["tipo"], _d(r["em"]))
                for r in c.execute(
                    "SELECT tipo, em FROM eventos_seguranca WHERE usuario_id = ? ORDER BY em DESC LIMIT 20",
                    (sessao.usuario_id,),
                )
            ]
        return Conta(
            sessao.email,
            _d(usuario["criado_em"]),
            sessao.organizacao_id,
            org["nome"],
            sessao.papel,
            empresas,
            restantes,
            eventos,
            (usuario["termos_versao"], _d(usuario["termos_aceitos_em"])) if usuario["termos_versao"] else None,
        )

    def empresas(self, organizacao_id: str) -> frozenset[str]:
        with self.banco.transacao() as c:
            return frozenset(
                r["cnpj"]
                for r in c.execute("SELECT cnpj FROM acessos_empresa WHERE organizacao_id = ?", (organizacao_id,))
            )

    def vincular_empresa(self, organizacao_id: str, cnpj: str, agora: datetime) -> None:
        """A organização passa a alcançar o CNPJ (C3-B, ADR 0017). O mesmo CNPJ pode estar em outra organização:
        não há como provar quem é o dono, e um CNPJ único deixaria alguém bloquear a empresa de outra pessoa
        cadastrando-a antes; os dados de cada organização ficam separados (plano v2.1, decisão 5 da C3)."""
        with self.banco.transacao(escrita=True) as c:
            c.execute(
                # Um acesso que sobrou (a empresa saiu do banco da organização numa falha) não trava o recadastro.
                "INSERT INTO acessos_empresa (organizacao_id, cnpj, desde) VALUES (?, ?, ?)"
                " ON CONFLICT (organizacao_id, cnpj) DO NOTHING",
                (organizacao_id, cnpj, _t(agora)),
            )

    def desvincular_empresa(self, organizacao_id: str, cnpj: str) -> None:
        with self.banco.transacao(escrita=True) as c:
            c.execute("DELETE FROM acessos_empresa WHERE organizacao_id = ? AND cnpj = ?", (organizacao_id, cnpj))

    def conferir_senha(self, usuario_id: str, senha: str, agora: datetime) -> None:
        """A senha de novo, antes de uma ação definitiva (excluir a conta ou a empresa) ou de baixar os dados. A
        senha errada conta como falha de entrada: a mesma espera e o mesmo bloqueio da entrada (NIST 3.2.2)."""
        with self.banco.transacao() as c:
            linha = c.execute("SELECT senha_hash FROM usuarios WHERE id = ?", (usuario_id,)).fetchone()
            _barrar(self._falhas(c, usuario_id), agora)
        if linha is None or not regras.confere(linha["senha_hash"], senha):
            self._falhou(usuario_id, agora)
            raise EntradaRecusada("Senha incorreta.")

    def excluir(self, sessao: SessaoAtiva, senha: str, agora: datetime) -> Exclusao:
        """Apaga a pessoa (LGPD, art. 18 VI). As organizações em que ela é a única integrante vão junto, todas (e
        não só a da sessão); se é a única dona de uma organização com outros membros, precisa passar a posse
        antes."""
        self.conferir_senha(sessao.usuario_id, senha, agora)
        with self.banco.transacao(escrita=True) as c:
            presa = c.execute(
                "SELECT 1 FROM membros m WHERE m.usuario_id = ? AND m.papel = 'dono' "
                "AND (SELECT count(*) FROM membros o WHERE o.organizacao_id = m.organizacao_id) > 1 "
                "AND (SELECT count(*) FROM membros d WHERE d.organizacao_id = m.organizacao_id "
                "AND d.papel = 'dono') = 1",
                (sessao.usuario_id,),
            ).fetchone()
            if presa:
                raise PosseNaoTransferida
            apagadas = self._apagar_usuario(c, sessao.usuario_id)
        return Exclusao(apagadas)

    def dados_da_pessoa(self, usuario_id: str, token: str) -> DadosDaPessoa:
        """Tudo o que o contas.db guarda da pessoa, numa leitura só. `token`: o da sessão que pede, para marcá-la."""
        atual = _resumo(token)
        with self.banco.transacao() as c:
            u = c.execute(
                "SELECT email, criado_em, situacao, termos_versao, termos_aceitos_em FROM usuarios WHERE id = ?",
                (usuario_id,),
            ).fetchone()
            fator = c.execute("SELECT confirmado_em FROM segundo_fator WHERE usuario_id = ?", (usuario_id,)).fetchone()
            restantes = c.execute(
                "SELECT count(*) AS n FROM codigos_recuperacao WHERE usuario_id = ?", (usuario_id,)
            ).fetchone()["n"]
            t = c.execute(
                "SELECT falhas_seguidas, espera_ate, bloqueada FROM tentativas WHERE usuario_id = ?", (usuario_id,)
            ).fetchone()
            eventos = [
                (r["tipo"], _d(r["em"]))
                for r in c.execute(
                    "SELECT tipo, em FROM eventos_seguranca WHERE usuario_id = ? ORDER BY em DESC, id", (usuario_id,)
                )
            ]
            sessoes = [
                (_d(r["criada_em"]), _d(r["ultimo_uso"]), _d(r["expira_em"]), r["hash"] == atual)
                for r in c.execute(
                    "SELECT hash, criada_em, ultimo_uso, expira_em FROM sessoes WHERE usuario_id = ? "
                    "ORDER BY criada_em DESC",
                    (usuario_id,),
                )
            ]
            organizacoes = []
            for o in c.execute(
                "SELECT o.id, o.nome, o.criada_em, m.papel, m.desde FROM membros m "
                "JOIN organizacoes o ON o.id = m.organizacao_id WHERE m.usuario_id = ? ORDER BY m.desde, o.id",
                (usuario_id,),
            ).fetchall():
                acessos = [
                    (r["cnpj"], _d(r["desde"]))
                    for r in c.execute(
                        "SELECT cnpj, desde FROM acessos_empresa WHERE organizacao_id = ? ORDER BY cnpj", (o["id"],)
                    )
                ]
                organizacoes.append(
                    OrganizacaoDaPessoa(o["id"], o["nome"], _d(o["criada_em"]), o["papel"], _d(o["desde"]), acessos)
                )
        return DadosDaPessoa(
            email=u["email"],
            criada_em=_d(u["criado_em"]),
            situacao=u["situacao"],
            termos=(u["termos_versao"], _d(u["termos_aceitos_em"])) if u["termos_versao"] else None,
            segundo_fator_confirmado_em=_d(fator["confirmado_em"]) if fator and fator["confirmado_em"] else None,
            codigos_restantes=restantes,
            tentativas=(
                (t["falhas_seguidas"], _d(t["espera_ate"]) if t["espera_ate"] else None, bool(t["bloqueada"]))
                if t
                else None
            ),
            eventos=eventos,
            sessoes=sessoes,
            organizacoes=organizacoes,
        )

    def organizacoes(self) -> frozenset[str]:
        """Os ids das organizações que existem (a limpeza dos bancos órfãos, na subida)."""
        with self.banco.transacao() as c:
            return frozenset(r["id"] for r in c.execute("SELECT id FROM organizacoes"))

    # -- administração ----------------------------------------------------------------------------------

    def desbloquear(self, email: str) -> bool:
        with self.banco.transacao(escrita=True) as c:
            linha = c.execute("SELECT id FROM usuarios WHERE email = ?", (normalizar_email(email),)).fetchone()
            if linha is None:
                return False
            c.execute("DELETE FROM tentativas WHERE usuario_id = ?", (linha["id"],))
        return True
