"""Espaços de avaliação (D2, ADR 0010): um SQLite por visitante, para que vários avaliadores testem ao mesmo
tempo sem mexer nos dados uns dos outros nem no estado da demonstração.

- O espaço nasce como cópia do banco-modelo (as sementes de data/demo já importadas), pela API de backup do
  SQLite (`Banco.copiar_para`): criar um espaço não chama os motores. O modelo é montado uma vez por processo,
  com o mesmo código da restauração, e por isso acompanha as migrações e as sementes da versão em execução.
- O identificador é sorteado pelo servidor (`secrets.token_hex`, 128 bits) e funciona como a chave do espaço:
  quem não o tem não chega aos dados. Ele só vira nome de arquivo depois de conferido pelo padrão.
- Validade fixa a partir da criação e teto de espaços ao mesmo tempo (configuráveis). A limpeza acontece ao
  criar e ao abrir um espaço; não há processo em segundo plano.
- O registro (id, criação, validade) fica num SQLite próprio, `registro.db`, na mesma pasta.
"""

from __future__ import annotations

import asyncio
import re
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.motores.cliente import ClienteMotores
from app.persistencia.banco import ESPERA_ESCRITA_MS, Banco
from app.persistencia.repositorio import Repositorio
from app.persistencia.sementes import restaurar

PADRAO_ID = r"^[0-9a-f]{32}$"
_ID = re.compile(PADRAO_ID)


@dataclass(frozen=True)
class Espaco:
    id: str
    criado_em: datetime
    expira_em: datetime


class EspacoInexistente(Exception):
    """Id fora do padrão, desconhecido ou já expirado. A mensagem não diz qual dos três."""


class EspacosEsgotados(Exception):
    def __init__(self, espera_s: int) -> None:
        super().__init__("Todos os espaços de avaliação estão em uso.")
        self.espera_s = espera_s


def _utc(quando: datetime) -> str:
    return quando.astimezone(UTC).isoformat()


class Espacos:
    def __init__(self, pasta: Path, validade: timedelta, maximo: int, pasta_migracoes: Path | None = None) -> None:
        self.pasta = pasta
        self.validade = validade
        self.maximo = maximo
        self._migracoes = pasta_migracoes
        self.modelo = self._novo_banco(pasta / "modelo.db")
        self._modelo_pronto = False
        self._trava = asyncio.Lock()

    def _novo_banco(self, caminho: Path) -> Banco:
        return Banco(caminho) if self._migracoes is None else Banco(caminho, self._migracoes)

    # -- banco-modelo -------------------------------------------------------------------------------

    async def garantir_modelo(self, motores: ClienteMotores, pasta_demo: Path) -> None:
        """Monta o modelo na primeira vez que o processo precisa dele (chama os motores, como a restauração)."""
        async with self._trava:
            if self._modelo_pronto:
                return
            await asyncio.to_thread(self.pasta.mkdir, parents=True, exist_ok=True)
            await asyncio.to_thread(self.modelo.migrar)
            await restaurar(Repositorio(self.modelo), motores, pasta_demo)
            self._modelo_pronto = True

    # -- registro -----------------------------------------------------------------------------------

    def _registro(self) -> sqlite3.Connection:
        self.pasta.mkdir(parents=True, exist_ok=True)
        conexao = sqlite3.connect(self.pasta / "registro.db", isolation_level=None, timeout=ESPERA_ESCRITA_MS / 1000)
        conexao.row_factory = sqlite3.Row
        conexao.execute(
            "CREATE TABLE IF NOT EXISTS espacos (id TEXT PRIMARY KEY, criado_em TEXT NOT NULL, expira_em TEXT NOT NULL)"
        )
        return conexao

    def banco(self, espaco_id: str) -> Banco:
        if not _ID.fullmatch(espaco_id):
            raise EspacoInexistente
        return self._novo_banco(self.pasta / f"{espaco_id}.db")

    def _apagar(self, espaco_id: str) -> None:
        """Apaga o arquivo do espaço (e os do WAL). Um arquivo preso (Windows) fica para a próxima limpeza."""
        base = self.pasta / f"{espaco_id}.db"
        for caminho in (base, base.with_name(base.name + "-wal"), base.with_name(base.name + "-shm")):
            try:
                caminho.unlink(missing_ok=True)
            except OSError:
                pass

    def _vencidos(self, conexao: sqlite3.Connection, agora: datetime) -> list[str]:
        linhas = conexao.execute("SELECT id FROM espacos WHERE julianday(expira_em) <= julianday(?)", (_utc(agora),))
        vencidos = [linha["id"] for linha in linhas]
        conexao.executemany("DELETE FROM espacos WHERE id = ?", [(i,) for i in vencidos])
        return vencidos

    def criar(self, agora: datetime) -> Espaco:
        """Novo espaço com a cópia do modelo. Chame garantir_modelo antes."""
        if not self._modelo_pronto:
            raise RuntimeError("Banco-modelo dos espaços ainda não montado.")
        conexao = self._registro()
        try:
            conexao.execute("BEGIN IMMEDIATE")
            try:
                vencidos = self._vencidos(conexao, agora)
                em_uso = conexao.execute("SELECT count(*) AS n, min(expira_em) AS proximo FROM espacos").fetchone()
                if em_uso["n"] >= self.maximo:
                    proximo = datetime.fromisoformat(em_uso["proximo"])
                    raise EspacosEsgotados(max(1, int((proximo - agora).total_seconds()) + 1))
                espaco = Espaco(secrets.token_hex(16), agora, agora + self.validade)
                try:
                    self.modelo.copiar_para(self.banco(espaco.id))
                    conexao.execute(
                        "INSERT INTO espacos (id, criado_em, expira_em) VALUES (?, ?, ?)",
                        (espaco.id, _utc(espaco.criado_em), _utc(espaco.expira_em)),
                    )
                except BaseException:
                    self._apagar(espaco.id)
                    raise
                conexao.execute("COMMIT")
            except BaseException:
                conexao.execute("ROLLBACK")
                raise
        finally:
            conexao.close()
        for espaco_id in vencidos:
            self._apagar(espaco_id)
        return espaco

    def abrir(self, espaco_id: str, agora: datetime) -> Espaco:
        """O espaço válido com este id. Um espaço vencido é apagado aqui mesmo."""
        if not _ID.fullmatch(espaco_id):
            raise EspacoInexistente
        conexao = self._registro()
        try:
            linha = conexao.execute(
                "SELECT id, criado_em, expira_em FROM espacos WHERE id = ?", (espaco_id,)
            ).fetchone()
            if linha is not None and datetime.fromisoformat(linha["expira_em"]) <= agora:
                conexao.execute("DELETE FROM espacos WHERE id = ?", (espaco_id,))
                linha = None
                vencido = True
            else:
                vencido = False
        finally:
            conexao.close()
        if vencido:
            self._apagar(espaco_id)
        if linha is None or not (self.pasta / f"{espaco_id}.db").exists():
            raise EspacoInexistente
        return Espaco(
            linha["id"], datetime.fromisoformat(linha["criado_em"]), datetime.fromisoformat(linha["expira_em"])
        )

    def restaurar(self, espaco_id: str) -> None:
        """Volta o espaço à cópia do modelo (sem chamar os motores). Chame garantir_modelo antes."""
        if not self._modelo_pronto:
            raise RuntimeError("Banco-modelo dos espaços ainda não montado.")
        self.modelo.copiar_para(self.banco(espaco_id))
