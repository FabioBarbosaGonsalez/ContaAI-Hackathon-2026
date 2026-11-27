"""Migração 0003 (C3-B, ADR 0017): CNPJ alfanumérico e item arquivado, sem perder nada de um banco já em uso."""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest

from app.persistencia.banco import PASTA_MIGRACOES, Banco

CNPJ = "36817420000113"
ITEM = "arroz-5kg"


def _banco_ate(pasta: Path, ultima: int) -> Banco:
    """Um banco migrado só até a versão `ultima`, com as migrações copiadas para uma pasta própria."""
    migracoes = pasta / "migracoes"
    migracoes.mkdir()
    for arquivo in sorted(PASTA_MIGRACOES.glob("*.sql"))[:ultima]:
        shutil.copy(arquivo, migracoes / arquivo.name)
    banco = Banco(pasta / "estado.db", migracoes)
    banco.migrar()
    return banco


def _povoar(banco: Banco) -> None:
    with banco.transacao(escrita=True) as c:
        c.execute("INSERT INTO empresas VALUES (?, 'Serra Azul', 'simples_tradicional', '{}', '{}')", (CNPJ,))
        c.execute("INSERT INTO itens VALUES (?, ?, '10063021', 'UN', '{}')", (CNPJ, ITEM))
        c.execute("INSERT INTO codigos_fornecedor VALUES (?, '71604258000156', 'AE-ARZ-5', ?)", (CNPJ, ITEM))
        c.execute(
            "INSERT INTO notas VALUES (1, ?, '71604258000156', '1', '1001', '2027-03-10T10:00:00-03:00', 'x',"
            " '2027-03-10T13:00:00+00:00', '{}')",
            (CNPJ,),
        )
        c.execute(
            "INSERT INTO custos VALUES (1, ?, ?, 1, '2027-03-10T10:00:00-03:00', '10', '20.00', NULL, NULL)",
            (CNPJ, ITEM),
        )
        c.execute(
            "INSERT INTO precos VALUES (1, ?, ?, '27.90', '2027-03-01T00:00:00+00:00', 'semente', NULL)", (CNPJ, ITEM)
        )
        c.execute("INSERT INTO clientes_b2b VALUES (?, '50291633000185', '{}')", (CNPJ,))


def _contagens(banco: Banco) -> dict[str, int]:
    tabelas = ("empresas", "itens", "codigos_fornecedor", "notas", "custos", "precos", "clientes_b2b")
    with banco.transacao() as c:
        return {t: c.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in tabelas}  # noqa: S608 (nomes fixos)


def test_a_0003_preserva_os_dados_e_as_cascatas(tmp_path: Path) -> None:
    antes_da_0003 = _banco_ate(tmp_path, 2)
    _povoar(antes_da_0003)
    contagens = _contagens(antes_da_0003)
    assert set(contagens.values()) == {1}

    migrado = Banco(antes_da_0003.caminho)
    assert migrado.migrar() == ["0003_empresa_propria.sql"]
    assert _contagens(migrado) == contagens
    with migrado.transacao() as c:
        assert c.execute("PRAGMA foreign_key_check").fetchall() == []
        alvos = {r["table"] for r in c.execute("PRAGMA foreign_key_list(itens)")}
        assert alvos == {"empresas"}
        assert c.execute("SELECT arquivado_em FROM itens").fetchone()[0] is None
    # As cascatas continuam ligadas: apagar a empresa leva tudo o que é dela.
    with migrado.transacao(escrita=True) as c:
        c.execute("DELETE FROM empresas WHERE cnpj = ?", (CNPJ,))
    assert set(_contagens(migrado).values()) == {0}


@pytest.mark.parametrize(
    ("cnpj", "aceito"),
    [
        ("12ABC34501DE35", True),
        ("36817420000113", True),
        ("12abc34501de35", False),
        ("12ABC34501DEAB", False),
        ("12ABC34501DE3", False),
    ],
)
def test_o_check_do_banco_segue_o_formato_oficial(tmp_path: Path, cnpj: str, aceito: bool) -> None:
    """O banco recusa sozinho o que o contrato já recusa (defesa em profundidade)."""
    banco = Banco(tmp_path / "estado.db")
    banco.migrar()

    def inserir() -> None:
        with banco.transacao(escrita=True) as c:
            c.execute("INSERT INTO empresas VALUES (?, 'X', 'simples_tradicional', '{}', '{}')", (cnpj,))
            c.execute("INSERT INTO clientes_b2b VALUES (?, ?, '{}')", (cnpj, cnpj))

    if aceito:
        inserir()
    else:
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            inserir()


def test_migracao_que_quebra_chave_estrangeira_nao_entra(tmp_path: Path) -> None:
    """Com as chaves desligadas durante a migração, o foreign_key_check é o que barra uma migração errada."""
    migracoes = tmp_path / "migracoes"
    migracoes.mkdir()
    (migracoes / "0001_mae.sql").write_text(
        "CREATE TABLE mae (id INTEGER PRIMARY KEY);\n"
        "CREATE TABLE filha (id INTEGER PRIMARY KEY, mae INTEGER REFERENCES mae (id));\n",
        encoding="utf-8",
    )
    (migracoes / "0002_quebra.sql").write_text("INSERT INTO filha VALUES (1, 99);\n", encoding="utf-8")
    banco = Banco(tmp_path / "estado.db", migracoes)
    with pytest.raises(RuntimeError, match="0002_quebra.sql deixaria chave estrangeira quebrada"):
        banco.migrar()
    with banco.transacao() as c:
        assert c.execute("SELECT count(*) FROM filha").fetchone()[0] == 0
        assert [r[0] for r in c.execute("SELECT versao FROM schema_migrations")] == [1]
        assert c.execute("PRAGMA foreign_keys").fetchone()[0] == 1
