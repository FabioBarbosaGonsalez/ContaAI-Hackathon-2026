"""Conexão com o SQLite e migrações versionadas (ADR 0008).

- Migrações: arquivos `migracoes/NNNN_nome.sql`, aplicados em ordem, cada um numa transação, com o
  SHA-256 gravado em `schema_migrations`. Se um arquivo já aplicado mudar, o backend não sobe: mudança
  de esquema é sempre uma migração nova.
- Conexão por unidade de trabalho (`transacao`): chaves estrangeiras ligadas, espera de até 5 s por
  outra escrita e `BEGIN IMMEDIATE`, para que duas importações não se cruzem.
- Só consultas parametrizadas no repositório; nenhum texto de usuário entra no SQL.
"""

from __future__ import annotations

import hashlib
import re
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

PASTA_MIGRACOES = Path(__file__).with_name("migracoes")
_NOME_MIGRACAO = re.compile(r"^(\d{4})_[a-z0-9_]+\.sql$")
ESPERA_ESCRITA_MS = 5000


class MigracaoAlterada(RuntimeError):
    """Um arquivo de migração já aplicado mudou depois de aplicado."""


def _migracoes(pasta: Path) -> list[tuple[int, str, str]]:
    lista = []
    for arquivo in sorted(pasta.glob("*.sql")):
        achado = _NOME_MIGRACAO.match(arquivo.name)
        if achado is None:
            raise RuntimeError(f"Nome de migração fora do padrão NNNN_nome.sql: {arquivo.name}")
        lista.append((int(achado.group(1)), arquivo.name, arquivo.read_text(encoding="utf-8")))
    versoes = [v for v, _, _ in lista]
    if versoes != list(range(1, len(versoes) + 1)):
        raise RuntimeError("As migrações precisam ser numeradas em sequência a partir de 0001.")
    return lista


class Banco:
    def __init__(self, caminho: Path, pasta_migracoes: Path = PASTA_MIGRACOES) -> None:
        self.caminho = caminho
        self.pasta_migracoes = pasta_migracoes

    def _conectar(self) -> sqlite3.Connection:
        # isolation_level=None: sem transação implícita; cada unidade de trabalho abre a sua.
        conexao = sqlite3.connect(self.caminho, isolation_level=None, timeout=ESPERA_ESCRITA_MS / 1000)
        conexao.row_factory = sqlite3.Row
        conexao.execute("PRAGMA foreign_keys = ON")
        conexao.execute(f"PRAGMA busy_timeout = {ESPERA_ESCRITA_MS}")
        return conexao

    def migrar(self) -> list[str]:
        """Aplica as migrações que faltam. Devolve os nomes aplicados agora."""
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        aplicadas_agora = []
        conexao = self._conectar()
        try:
            conexao.execute("PRAGMA journal_mode = WAL")
            conexao.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("
                " versao INTEGER PRIMARY KEY, nome TEXT NOT NULL, sha256 TEXT NOT NULL, aplicada_em TEXT NOT NULL)"
            )
            ja = {r["versao"]: r for r in conexao.execute("SELECT versao, nome, sha256 FROM schema_migrations")}
            for versao, nome, sql in _migracoes(self.pasta_migracoes):
                resumo = hashlib.sha256(sql.encode("utf-8")).hexdigest()
                if versao in ja:
                    if ja[versao]["sha256"] != resumo:
                        raise MigracaoAlterada(f"A migração {nome} mudou depois de aplicada. Crie uma migração nova.")
                    continue
                # Procedimento de mudança de esquema da documentação do SQLite (lang_altertable.html, "Making
                # Other Kinds Of Table Schema Changes"): chaves estrangeiras desligadas fora da transação (o
                # PRAGMA não tem efeito dentro dela) e PRAGMA foreign_key_check antes do COMMIT. Com elas ligadas,
                # o DROP TABLE de uma tabela-mãe faz um DELETE implícito que dispara o ON DELETE CASCADE
                # (lang_droptable.html): reconstruir `empresas` apagaria itens, notas e clientes.
                conexao.execute("PRAGMA foreign_keys = OFF")
                conexao.execute("BEGIN IMMEDIATE")
                try:
                    for comando in _comandos(sql):
                        conexao.execute(comando)
                    if conexao.execute("PRAGMA foreign_key_check").fetchone() is not None:
                        raise RuntimeError(f"A migração {nome} deixaria chave estrangeira quebrada.")
                    conexao.execute(
                        "INSERT INTO schema_migrations (versao, nome, sha256, aplicada_em) VALUES (?, ?, ?, ?)",
                        (versao, nome, resumo, datetime.now(UTC).isoformat()),
                    )
                    conexao.execute("COMMIT")
                except BaseException:
                    conexao.execute("ROLLBACK")
                    raise
                finally:
                    conexao.execute("PRAGMA foreign_keys = ON")
                aplicadas_agora.append(nome)
        finally:
            conexao.close()
        return aplicadas_agora

    def copiar_para(self, destino: Banco) -> None:
        """Substitui todo o conteúdo do destino por este banco, numa operação só (API de backup do SQLite,
        `Connection.backup` com todas as páginas de uma vez). Quem lê o destino vê o conteúdo antigo ou o
        novo, nunca uma mistura."""
        origem, alvo = self._conectar(), destino._conectar()
        try:
            origem.backup(alvo)
        finally:
            origem.close()
            alvo.close()

    @contextmanager
    def transacao(self, escrita: bool = False) -> Iterator[sqlite3.Connection]:
        conexao = self._conectar()
        try:
            conexao.execute("BEGIN IMMEDIATE" if escrita else "BEGIN")
            try:
                yield conexao
                conexao.execute("COMMIT")
            except BaseException:
                conexao.execute("ROLLBACK")
                raise
        finally:
            conexao.close()


def _comandos(sql: str) -> list[str]:
    """Separa o script em comandos com sqlite3.complete_statement (gatilhos têm ';' no corpo).

    executescript não serve: ele faz COMMIT antes de rodar e quebraria a transação da migração.
    """
    comandos: list[str] = []
    atual: list[str] = []
    for linha in sql.splitlines():
        if not atual and (not linha.strip() or linha.lstrip().startswith("--")):
            continue
        atual.append(linha)
        texto = "\n".join(atual)
        if sqlite3.complete_statement(texto):
            comandos.append(texto)
            atual = []
    if atual and "\n".join(atual).strip():
        raise RuntimeError("Migração com comando incompleto no fim do arquivo.")
    return comandos
