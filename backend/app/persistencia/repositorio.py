"""Repositório: a única porta das rotas para o estado (ADR 0008).

As rotas e os serviços falam com `Repositorio` e `Sessao`, nunca com SQL. Trocar o SQLite por outro
banco é trocar esta implementação. Uma `Sessao` é uma unidade de trabalho: tudo o que ela grava
entra junto, ou nada entra.

Dinheiro e quantidades entram e saem como Decimal (texto no banco); datas como datetime com fuso.

Datas (convenção do ADR 0003, revisada na E4):
- instantes do sistema (importação, criação e aplicação de alerta, vigência de preço) são gravados e
  devolvidos em UTC;
- datas copiadas do documento (emissão da nota) são gravadas como vieram, com o fuso da nota, e
  ordenadas pelo instante (`julianday`, que converte o fuso). Duas notas de fusos diferentes (ex.: RS e
  AM) ficam na ordem certa sem perder o horário local impresso na nota.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

from app.contrato import Alerta
from app.dados_demo import Cenario, Empresa, ItemCatalogo
from app.persistencia.banco import Banco

FonteCredito = Literal["nfe", "motor"]


@dataclass(frozen=True)
class EmpresaRegistro:
    empresa: Empresa
    cenario: Cenario


@dataclass(frozen=True)
class LancamentoCusto:
    """Um custo lançado por uma nota. `id` vem do banco (None antes de gravar)."""

    item_id: str
    nota_id: int
    data: datetime
    quantidade: Decimal
    custo_unitario: Decimal
    credito_unitario: Decimal | None
    fonte_credito: FonteCredito | None
    id: int | None = None


@dataclass(frozen=True)
class NotaRegistro:
    id: int
    sha256: str
    recibo_json: str


@dataclass(frozen=True)
class AlertaRegistro:
    alerta: Alerta
    nota_id: int
    aplicado_em: datetime | None


def _dec(valor: str | None) -> Decimal | None:
    return None if valor is None else Decimal(valor)


def _utc(quando: datetime) -> str:
    """Instante do sistema, sempre gravado em UTC."""
    return _com_fuso(quando).astimezone(UTC).isoformat()


def _documento(quando: datetime) -> str:
    """Data copiada do documento, gravada com o fuso da nota (ordenada por julianday no SQL)."""
    return _com_fuso(quando).isoformat()


def _com_fuso(quando: datetime) -> datetime:
    if quando.tzinfo is None:
        raise ValueError("Data sem fuso horário.")
    return quando


def _texto(valor: Decimal | None) -> str | None:
    return None if valor is None else format(valor, "f")


class Sessao:
    def __init__(self, conexao: sqlite3.Connection) -> None:
        self._c = conexao

    # -- empresas e catálogo ------------------------------------------------

    def inserir_empresa(self, empresa: Empresa, cenario: Cenario) -> None:
        self._c.execute(
            "INSERT INTO empresas (cnpj, razao_social, regime_atual, empresa_json, cenario_json) VALUES (?, ?, ?, ?, ?)",
            (
                empresa.cnpj,
                empresa.razaoSocial,
                empresa.regimeAtual,
                empresa.model_dump_json(),
                cenario.model_dump_json(),
            ),
        )

    def empresa(self, cnpj: str) -> EmpresaRegistro | None:
        linha = self._c.execute("SELECT empresa_json, cenario_json FROM empresas WHERE cnpj = ?", (cnpj,)).fetchone()
        if linha is None:
            return None
        return EmpresaRegistro(
            Empresa.model_validate_json(linha["empresa_json"]), Cenario.model_validate_json(linha["cenario_json"])
        )

    def empresas(self) -> list[EmpresaRegistro]:
        linhas = self._c.execute("SELECT empresa_json, cenario_json FROM empresas ORDER BY razao_social").fetchall()
        return [
            EmpresaRegistro(
                Empresa.model_validate_json(r["empresa_json"]), Cenario.model_validate_json(r["cenario_json"])
            )
            for r in linhas
        ]

    def inserir_item(self, cnpj: str, item: ItemCatalogo) -> None:
        self._c.execute(
            "INSERT INTO itens (cnpj, item_id, ncm, unidade, item_json) VALUES (?, ?, ?, ?, ?)",
            (cnpj, item.id, item.ncm, item.unidade, item.model_dump_json(by_alias=True)),
        )
        self._c.execute(
            "INSERT INTO codigos_fornecedor (cnpj, cnpj_fornecedor, codigo, item_id) VALUES (?, ?, ?, ?)",
            (cnpj, item.cnpjFornecedor, item.codigoFornecedor, item.id),
        )

    def itens(self, cnpj: str) -> list[ItemCatalogo]:
        """Cadastro dos itens. O preço atual não está aqui: é o último lançamento (`preco_atual`)."""
        linhas = self._c.execute("SELECT item_json FROM itens WHERE cnpj = ? ORDER BY rowid", (cnpj,)).fetchall()
        return [ItemCatalogo.model_validate_json(r["item_json"]) for r in linhas]

    def item(self, cnpj: str, item_id: str) -> ItemCatalogo | None:
        linha = self._c.execute(
            "SELECT item_json FROM itens WHERE cnpj = ? AND item_id = ?", (cnpj, item_id)
        ).fetchone()
        return None if linha is None else ItemCatalogo.model_validate_json(linha["item_json"])

    def item_por_codigo(self, cnpj: str, cnpj_fornecedor: str, codigo: str) -> ItemCatalogo | None:
        linha = self._c.execute(
            "SELECT i.item_json FROM codigos_fornecedor c JOIN itens i ON i.cnpj = c.cnpj AND i.item_id = c.item_id"
            " WHERE c.cnpj = ? AND c.cnpj_fornecedor = ? AND c.codigo = ?",
            (cnpj, cnpj_fornecedor, codigo),
        ).fetchone()
        return None if linha is None else ItemCatalogo.model_validate_json(linha["item_json"])

    # -- preços (lançamentos) ---------------------------------------------

    def lancar_preco(
        self,
        cnpj: str,
        item_id: str,
        valor_unitario: Decimal,
        vigente_desde: datetime,
        origem: Literal["semente", "alerta"],
        alerta_id: str | None = None,
    ) -> None:
        self._c.execute(
            "INSERT INTO precos (cnpj, item_id, valor_unitario, vigente_desde, origem, alerta_id)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (cnpj, item_id, _texto(valor_unitario), _utc(vigente_desde), origem, alerta_id),
        )

    def preco_atual(self, cnpj: str, item_id: str) -> Decimal | None:
        """O último preço lançado (ordem de registro). Um preço vale a partir do lançamento; a data simulada
        das sementes (2027) não pode vencer um preço aplicado hoje."""
        linha = self._c.execute(
            "SELECT valor_unitario FROM precos WHERE cnpj = ? AND item_id = ? ORDER BY id DESC",
            (cnpj, item_id),
        ).fetchone()
        return None if linha is None else Decimal(linha["valor_unitario"])

    # -- notas e custos ----------------------------------------------------

    def nota(self, cnpj: str, cnpj_emitente: str, serie: str, numero: str) -> NotaRegistro | None:
        linha = self._c.execute(
            "SELECT id, sha256, recibo_json FROM notas WHERE cnpj = ? AND cnpj_emitente = ? AND serie = ? AND numero = ?",
            (cnpj, cnpj_emitente, serie, numero),
        ).fetchone()
        return None if linha is None else NotaRegistro(linha["id"], linha["sha256"], linha["recibo_json"])

    def inserir_nota(
        self,
        cnpj: str,
        cnpj_emitente: str,
        serie: str,
        numero: str,
        data_emissao: datetime,
        sha256: str,
        importada_em: datetime,
    ) -> int:
        cursor = self._c.execute(
            "INSERT INTO notas (cnpj, cnpj_emitente, serie, numero, data_emissao, sha256, importada_em, recibo_json)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, '{}')",
            (cnpj, cnpj_emitente, serie, numero, _documento(data_emissao), sha256, _utc(importada_em)),
        )
        assert cursor.lastrowid is not None
        return cursor.lastrowid

    def numero_da_nota(self, cnpj: str, nota_id: int) -> str | None:
        linha = self._c.execute("SELECT numero FROM notas WHERE cnpj = ? AND id = ?", (cnpj, nota_id)).fetchone()
        return None if linha is None else linha["numero"]

    def ultima_nota(self, cnpj: str) -> datetime | None:
        """Emissão da nota mais recente, com o fuso da nota."""
        linha = self._c.execute(
            "SELECT data_emissao FROM notas WHERE cnpj = ? ORDER BY julianday(data_emissao) DESC, id DESC LIMIT 1",
            (cnpj,),
        ).fetchone()
        return None if linha is None else datetime.fromisoformat(linha["data_emissao"])

    def gravar_recibo(self, nota_id: int, recibo_json: str) -> None:
        """O recibo é gravado na mesma transação da nota, depois de montado (ele cita os alertas criados)."""
        self._c.execute("UPDATE notas SET recibo_json = ? WHERE id = ? AND recibo_json = '{}'", (recibo_json, nota_id))

    def lancar_custo(self, cnpj: str, lanc: LancamentoCusto) -> None:
        self._c.execute(
            "INSERT INTO custos (cnpj, item_id, nota_id, data, quantidade, custo_unitario, credito_unitario,"
            " fonte_credito) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                cnpj,
                lanc.item_id,
                lanc.nota_id,
                _documento(lanc.data),
                _texto(lanc.quantidade),
                _texto(lanc.custo_unitario),
                _texto(lanc.credito_unitario),
                lanc.fonte_credito,
            ),
        )

    def custo_atual(self, cnpj: str, item_id: str) -> LancamentoCusto | None:
        """O lançamento mais recente pela data da nota (uma nota antiga importada depois não muda o custo)."""
        historico = self.historico_custo(cnpj, item_id, limite=1)
        return historico[0] if historico else None

    def historico_custo(self, cnpj: str, item_id: str, limite: int = 50) -> list[LancamentoCusto]:
        """Do mais recente para o mais antigo."""
        linhas = self._c.execute(
            "SELECT * FROM custos WHERE cnpj = ? AND item_id = ? ORDER BY julianday(data) DESC, id DESC LIMIT ?",
            (cnpj, item_id, limite),
        ).fetchall()
        return [
            LancamentoCusto(
                item_id=r["item_id"],
                nota_id=r["nota_id"],
                data=datetime.fromisoformat(r["data"]),
                quantidade=Decimal(r["quantidade"]),
                custo_unitario=Decimal(r["custo_unitario"]),
                credito_unitario=_dec(r["credito_unitario"]),
                fonte_credito=r["fonte_credito"],
                id=r["id"],
            )
            for r in linhas
        ]

    # -- alertas -------------------------------------------------------------

    def inserir_alerta(self, cnpj: str, alerta: Alerta, nota_id: int) -> None:
        self._c.execute(
            "INSERT INTO alertas (id, cnpj, item_id, nota_id, criado_em, alerta_json) VALUES (?, ?, ?, ?, ?, ?)",
            (alerta.id, cnpj, alerta.itemId, nota_id, _utc(alerta.criadoEm), alerta.model_dump_json()),
        )

    def alerta(self, alerta_id: str) -> tuple[str, AlertaRegistro] | None:
        linha = self._c.execute(
            "SELECT cnpj, nota_id, alerta_json, aplicado_em FROM alertas WHERE id = ?", (alerta_id,)
        ).fetchone()
        return None if linha is None else (linha["cnpj"], self._alerta(linha))

    def alertas(self, cnpj: str | None = None) -> list[AlertaRegistro]:
        """Do mais recente para o mais antigo."""
        if cnpj is None:
            linhas = self._c.execute("SELECT * FROM alertas ORDER BY criado_em DESC, rowid DESC").fetchall()
        else:
            linhas = self._c.execute(
                "SELECT * FROM alertas WHERE cnpj = ? ORDER BY criado_em DESC, rowid DESC", (cnpj,)
            ).fetchall()
        return [self._alerta(r) for r in linhas]

    def marcar_aplicado(self, alerta_id: str, quando: datetime) -> bool:
        cursor = self._c.execute(
            "UPDATE alertas SET aplicado_em = ? WHERE id = ? AND aplicado_em IS NULL", (_utc(quando), alerta_id)
        )
        return cursor.rowcount == 1

    @staticmethod
    def _alerta(linha: sqlite3.Row) -> AlertaRegistro:
        return AlertaRegistro(
            alerta=Alerta.model_validate_json(linha["alerta_json"]),
            nota_id=linha["nota_id"],
            aplicado_em=None if linha["aplicado_em"] is None else datetime.fromisoformat(linha["aplicado_em"]),
        )


class Repositorio:
    def __init__(self, banco: Banco) -> None:
        self.banco = banco

    @contextmanager
    def leitura(self) -> Iterator[Sessao]:
        with self.banco.transacao(escrita=False) as conexao:
            yield Sessao(conexao)

    @contextmanager
    def escrita(self) -> Iterator[Sessao]:
        with self.banco.transacao(escrita=True) as conexao:
            yield Sessao(conexao)
