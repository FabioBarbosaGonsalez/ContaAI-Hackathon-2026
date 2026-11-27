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

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal

from app.contrato import Alerta
from app.dados_demo import Cenario, ClienteB2B, Empresa, ItemCatalogo
from app.persistencia.banco import Banco

FonteCredito = Literal["nfe", "motor"]
OrigemPreco = Literal["semente", "alerta", "tela"]


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
class NotaListada:
    """Uma nota com o recibo gravado e a contagem atual dos alertas que ela gerou."""

    importada_em: datetime
    recibo_json: str
    alertas_gerados: int
    alertas_abertos: int


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

    def atualizar_empresa(self, empresa: Empresa, cenario: Cenario) -> None:
        """Configurações da empresa própria (C3-B). O CNPJ não muda."""
        self._c.execute(
            "UPDATE empresas SET razao_social = ?, regime_atual = ?, empresa_json = ?, cenario_json = ? WHERE cnpj = ?",
            (
                empresa.razaoSocial,
                empresa.regimeAtual,
                empresa.model_dump_json(),
                cenario.model_dump_json(),
                empresa.cnpj,
            ),
        )

    def apagar_empresa(self, cnpj: str) -> None:
        """Apaga a empresa e, em cascata, tudo o que é dela (itens, notas, custos, preços, alertas, clientes)."""
        self._c.execute("DELETE FROM empresas WHERE cnpj = ?", (cnpj,))

    def exportar_empresa(self, cnpj: str) -> dict[str, Any]:
        """Tudo o que o banco guarda da empresa, como está gravado (o arquivo dos dados da conta, LGPD art. 19, e
        app.contrato.EmpresaExportada). Os documentos JSON saem sem transformação; nenhum texto vira SQL."""
        c = self._c
        empresa = c.execute("SELECT empresa_json, cenario_json FROM empresas WHERE cnpj = ?", (cnpj,)).fetchone()
        return {
            "empresa": json.loads(empresa["empresa_json"]) if empresa else None,
            "cenario": json.loads(empresa["cenario_json"]) if empresa else None,
            "itens": [
                {
                    "itemId": r["item_id"],
                    "ncm": r["ncm"],
                    "unidade": r["unidade"],
                    "arquivadoEm": r["arquivado_em"],
                    "item": json.loads(r["item_json"]),
                }
                for r in c.execute(
                    "SELECT item_id, ncm, unidade, arquivado_em, item_json FROM itens WHERE cnpj = ? ORDER BY item_id",
                    (cnpj,),
                )
            ],
            "codigosFornecedor": [
                {"cnpjFornecedor": r["cnpj_fornecedor"], "codigo": r["codigo"], "itemId": r["item_id"]}
                for r in c.execute(
                    "SELECT cnpj_fornecedor, codigo, item_id FROM codigos_fornecedor WHERE cnpj = ? "
                    "ORDER BY cnpj_fornecedor, codigo",
                    (cnpj,),
                )
            ],
            "notas": [
                {
                    "id": r["id"],
                    "cnpjEmitente": r["cnpj_emitente"],
                    "serie": r["serie"],
                    "numero": r["numero"],
                    "dataEmissao": r["data_emissao"],
                    "sha256": r["sha256"],
                    "importadaEm": r["importada_em"],
                    "recibo": json.loads(r["recibo_json"]),
                }
                for r in c.execute(
                    "SELECT id, cnpj_emitente, serie, numero, data_emissao, sha256, importada_em, recibo_json "
                    "FROM notas WHERE cnpj = ? ORDER BY id",
                    (cnpj,),
                )
            ],
            "custos": [
                {
                    "id": r["id"],
                    "itemId": r["item_id"],
                    "notaId": r["nota_id"],
                    "data": r["data"],
                    "quantidade": r["quantidade"],
                    "custoUnitario": r["custo_unitario"],
                    "creditoUnitario": r["credito_unitario"],
                    "fonteCredito": r["fonte_credito"],
                }
                for r in c.execute(
                    "SELECT id, item_id, nota_id, data, quantidade, custo_unitario, credito_unitario, fonte_credito "
                    "FROM custos WHERE cnpj = ? ORDER BY id",
                    (cnpj,),
                )
            ],
            "precos": [
                {
                    "id": r["id"],
                    "itemId": r["item_id"],
                    "valorUnitario": r["valor_unitario"],
                    "vigenteDesde": r["vigente_desde"],
                    "origem": r["origem"],
                    "alertaId": r["alerta_id"],
                }
                for r in c.execute(
                    "SELECT id, item_id, valor_unitario, vigente_desde, origem, alerta_id FROM precos "
                    "WHERE cnpj = ? ORDER BY id",
                    (cnpj,),
                )
            ],
            "alertas": [
                {
                    "id": r["id"],
                    "itemId": r["item_id"],
                    "notaId": r["nota_id"],
                    "criadoEm": r["criado_em"],
                    "aplicadoEm": r["aplicado_em"],
                    "alerta": json.loads(r["alerta_json"]),
                }
                for r in c.execute(
                    "SELECT id, item_id, nota_id, criado_em, aplicado_em, alerta_json FROM alertas "
                    "WHERE cnpj = ? ORDER BY criado_em, id",
                    (cnpj,),
                )
            ],
            "classificacoes": [
                {
                    "id": r["id"],
                    "itemId": r["item_id"],
                    "cst": r["cst"],
                    "cClassTrib": r["cclasstrib"],
                    "fonte": r["fonte"],
                    "vigenteDesde": r["vigente_desde"],
                    "origem": r["origem"],
                }
                for r in c.execute(
                    "SELECT id, item_id, cst, cclasstrib, fonte, vigente_desde, origem FROM classificacoes "
                    "WHERE cnpj = ? ORDER BY id",
                    (cnpj,),
                )
            ],
            "clientesB2B": [
                {"cnpjCliente": r["cnpj_cliente"], "cliente": json.loads(r["cliente_json"])}
                for r in c.execute(
                    "SELECT cnpj_cliente, cliente_json FROM clientes_b2b WHERE cnpj = ? ORDER BY cnpj_cliente",
                    (cnpj,),
                )
            ],
        }

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
        """Cadastro dos itens, com a classificação atual. O preço atual não está aqui: é o último lançamento
        (`preco_atual`)."""
        linhas = self._c.execute(
            "SELECT item_json FROM itens WHERE cnpj = ? AND arquivado_em IS NULL ORDER BY rowid", (cnpj,)
        ).fetchall()
        return [self._com_classificacao(cnpj, ItemCatalogo.model_validate_json(r["item_json"])) for r in linhas]

    def item(self, cnpj: str, item_id: str) -> ItemCatalogo | None:
        linha = self._c.execute(
            "SELECT item_json FROM itens WHERE cnpj = ? AND item_id = ? AND arquivado_em IS NULL", (cnpj, item_id)
        ).fetchone()
        return (
            None
            if linha is None
            else self._com_classificacao(cnpj, ItemCatalogo.model_validate_json(linha["item_json"]))
        )

    def item_por_codigo(self, cnpj: str, cnpj_fornecedor: str, codigo: str) -> ItemCatalogo | None:
        linha = self._c.execute(
            "SELECT i.item_json FROM codigos_fornecedor c JOIN itens i ON i.cnpj = c.cnpj AND i.item_id = c.item_id"
            " WHERE c.cnpj = ? AND c.cnpj_fornecedor = ? AND c.codigo = ? AND i.arquivado_em IS NULL",
            (cnpj, cnpj_fornecedor, codigo),
        ).fetchone()
        return (
            None
            if linha is None
            else self._com_classificacao(cnpj, ItemCatalogo.model_validate_json(linha["item_json"]))
        )

    def item_do_cadastro(self, cnpj: str, item_id: str) -> ItemCatalogo | None:
        """O item como foi cadastrado, sem a classificação dos lançamentos: é o que `atualizar_item` regrava."""
        linha = self._c.execute(
            "SELECT item_json FROM itens WHERE cnpj = ? AND item_id = ? AND arquivado_em IS NULL", (cnpj, item_id)
        ).fetchone()
        return None if linha is None else ItemCatalogo.model_validate_json(linha["item_json"])

    def existe_item(self, cnpj: str, item_id: str) -> bool:
        """Também os arquivados: um id nunca volta a ser usado."""
        return (
            self._c.execute("SELECT 1 FROM itens WHERE cnpj = ? AND item_id = ?", (cnpj, item_id)).fetchone()
            is not None
        )

    def contar_itens(self, cnpj: str) -> int:
        """Os itens no catálogo (sem os arquivados)."""
        linha = self._c.execute(
            "SELECT count(*) AS n FROM itens WHERE cnpj = ? AND arquivado_em IS NULL", (cnpj,)
        ).fetchone()
        return int(linha["n"])

    def atualizar_item(self, cnpj: str, item: ItemCatalogo) -> None:
        """O cadastro do item (descrição, margem, fornecedor). A classificação e o preço continuam nos lançamentos
        deles; o JSON guarda a classificação do cadastro, que só vale sem lançamento."""
        self._c.execute(
            "UPDATE itens SET item_json = ? WHERE cnpj = ? AND item_id = ? AND arquivado_em IS NULL",
            (item.model_dump_json(by_alias=True), cnpj, item.id),
        )
        self._c.execute("DELETE FROM codigos_fornecedor WHERE cnpj = ? AND item_id = ?", (cnpj, item.id))
        self._c.execute(
            "INSERT INTO codigos_fornecedor (cnpj, cnpj_fornecedor, codigo, item_id) VALUES (?, ?, ?, ?)",
            (cnpj, item.cnpjFornecedor, item.codigoFornecedor, item.id),
        )

    def arquivar_item(self, cnpj: str, item_id: str, quando: datetime) -> bool:
        """O item sai do catálogo e o código do fornecedor fica livre para outro item. Custos, preços,
        classificações e alertas ficam: são o histórico."""
        cursor = self._c.execute(
            "UPDATE itens SET arquivado_em = ? WHERE cnpj = ? AND item_id = ? AND arquivado_em IS NULL",
            (_utc(quando), cnpj, item_id),
        )
        if cursor.rowcount != 1:
            return False
        self._c.execute("DELETE FROM codigos_fornecedor WHERE cnpj = ? AND item_id = ?", (cnpj, item_id))
        return True

    def _com_classificacao(self, cnpj: str, item: ItemCatalogo) -> ItemCatalogo:
        """A classificação atual é a do último lançamento da tela; sem lançamento, a do cadastro (0002)."""
        linha = self._c.execute(
            "SELECT cst, cclasstrib, fonte FROM classificacoes WHERE cnpj = ? AND item_id = ? ORDER BY id DESC LIMIT 1",
            (cnpj, item.id),
        ).fetchone()
        if linha is None:
            return item
        return item.model_copy(
            update={"cst": linha["cst"], "cClassTrib": linha["cclasstrib"], "classificacaoFonte": linha["fonte"]}
        )

    def lancar_classificacao(
        self, cnpj: str, item_id: str, cst: str, cclasstrib: str, fonte: str, vigente_desde: datetime
    ) -> None:
        self._c.execute(
            "INSERT INTO classificacoes (cnpj, item_id, cst, cclasstrib, fonte, vigente_desde, origem)"
            " VALUES (?, ?, ?, ?, ?, ?, 'tela')",
            (cnpj, item_id, cst, cclasstrib, fonte, _utc(vigente_desde)),
        )

    # -- clientes B2B --------------------------------------------------------

    def inserir_cliente_b2b(self, cnpj: str, cliente: ClienteB2B) -> None:
        self._c.execute(
            "INSERT INTO clientes_b2b (cnpj, cnpj_cliente, cliente_json) VALUES (?, ?, ?)",
            (cnpj, cliente.cliente.cnpj, cliente.model_dump_json(by_alias=True)),
        )

    def clientes_b2b(self, cnpj: str) -> list[ClienteB2B]:
        linhas = self._c.execute(
            "SELECT cliente_json FROM clientes_b2b WHERE cnpj = ? ORDER BY cnpj_cliente", (cnpj,)
        ).fetchall()
        return [ClienteB2B.model_validate_json(r["cliente_json"]) for r in linhas]

    def cliente_b2b(self, cnpj: str, cnpj_cliente: str) -> ClienteB2B | None:
        linha = self._c.execute(
            "SELECT cliente_json FROM clientes_b2b WHERE cnpj = ? AND cnpj_cliente = ?", (cnpj, cnpj_cliente)
        ).fetchone()
        return None if linha is None else ClienteB2B.model_validate_json(linha["cliente_json"])

    def contar_clientes_b2b(self, cnpj: str) -> int:
        linha = self._c.execute("SELECT count(*) AS n FROM clientes_b2b WHERE cnpj = ?", (cnpj,)).fetchone()
        return int(linha["n"])

    def atualizar_cliente_b2b(self, cnpj: str, cliente: ClienteB2B) -> None:
        """O CNPJ do cliente não muda: é a chave."""
        self._c.execute(
            "UPDATE clientes_b2b SET cliente_json = ? WHERE cnpj = ? AND cnpj_cliente = ?",
            (cliente.model_dump_json(by_alias=True), cnpj, cliente.cliente.cnpj),
        )

    def apagar_cliente_b2b(self, cnpj: str, cnpj_cliente: str) -> bool:
        """De vez: nenhuma outra tabela aponta para o cliente, e o ContaAI não guarda histórico de clientes."""
        cursor = self._c.execute("DELETE FROM clientes_b2b WHERE cnpj = ? AND cnpj_cliente = ?", (cnpj, cnpj_cliente))
        return cursor.rowcount == 1

    def clientes_que_compram(self, cnpj: str, item_id: str) -> list[ClienteB2B]:
        """Os clientes com o item na compra mensal. O JSON é lido em Python (sem json_each, que é do SQLite):
        são até 50 clientes por empresa."""
        return [c for c in self.clientes_b2b(cnpj) if any(i.itemId == item_id for i in c.compraMensal.itens)]

    # -- preços (lançamentos) ---------------------------------------------

    def lancar_preco(
        self,
        cnpj: str,
        item_id: str,
        valor_unitario: Decimal,
        vigente_desde: datetime,
        origem: OrigemPreco,
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
        if cursor.lastrowid is None:
            raise RuntimeError("O SQLite não devolveu o id da nota inserida.")
        return cursor.lastrowid

    def numeros_das_notas(self) -> list[str]:
        """Número de cada nota importada, na ordem de importação."""
        return [linha["numero"] for linha in self._c.execute("SELECT numero FROM notas ORDER BY id")]

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

    def notas(self, cnpj: str, limite: int) -> list[NotaListada]:
        """Da emissão mais recente para a mais antiga (pelo instante, com o fuso da nota). Uma nota ainda sem
        recibo fica de fora: o recibo entra na mesma transação da nota, então ninguém de fora a vê assim."""
        linhas = self._c.execute(
            # Abertos: sem preço aplicado e de item ainda no catálogo (o mesmo critério de `alertas`).
            "SELECT n.importada_em, n.recibo_json, COUNT(a.id) AS gerados,"
            " COUNT(CASE WHEN a.id IS NOT NULL AND a.aplicado_em IS NULL AND i.arquivado_em IS NULL THEN 1 END) AS abertos"
            " FROM notas n LEFT JOIN alertas a ON a.nota_id = n.id"
            " LEFT JOIN itens i ON i.cnpj = a.cnpj AND i.item_id = a.item_id"
            " WHERE n.cnpj = ? AND n.recibo_json <> '{}'"
            " GROUP BY n.id ORDER BY julianday(n.data_emissao) DESC, n.id DESC LIMIT ?",
            (cnpj, limite),
        ).fetchall()
        return [
            NotaListada(datetime.fromisoformat(r["importada_em"]), r["recibo_json"], r["gerados"], r["abertos"])
            for r in linhas
        ]

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
        # Sem os alertas de item arquivado: o item saiu do catálogo, não há preço para aplicar. Uma consulta só,
        # com o CNPJ opcional como parâmetro: nenhum SQL montado com texto.
        linhas = self._c.execute(
            "SELECT * FROM alertas WHERE (? IS NULL OR cnpj = ?) AND NOT EXISTS (SELECT 1 FROM itens i"
            " WHERE i.cnpj = alertas.cnpj AND i.item_id = alertas.item_id AND i.arquivado_em IS NOT NULL)"
            " ORDER BY criado_em DESC, rowid DESC",
            (cnpj, cnpj),
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
