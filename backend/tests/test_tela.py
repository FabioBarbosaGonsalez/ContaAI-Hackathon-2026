"""Contrato para a tela da E5 (ADR 0011): cenário, clientes B2B e lote no catálogo; preço e classificação
gravados pela tela; explicação lida do estado; migração 0002.

Rodam no CI com os motores falsos do conftest (valores fictícios). O que se confere é a orquestração e a
regra "um fato, uma variável": a tela refaz as contas só com o que a API devolve.
"""

from __future__ import annotations

import shutil
import sqlite3
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.config import Configuracao, configuracao
from app.contrato import (
    AlertasResposta,
    AplicarPrecoResposta,
    CarrinhoResposta,
    CatalogoResposta,
    CorrigirClassificacaoResposta,
    ExplicarResposta,
    ItemCatalogoEstado,
    RegimeCompararResposta,
)
from app.dados_demo import PASTA_DEMO
from app.main import app
from app.persistencia.banco import PASTA_MIGRACOES, Banco
from app.persistencia.sementes import SementesInvalidas, _ler_sementes
from app.precificacao.lote import LOTE
from tests.test_nfe import NOTA_2, SERRA_AZUL, VALE_VERDE, importar, nota

cliente = TestClient(app)
ESPACO = "X-ContaAI-Espaco"


@pytest.fixture
def demo(motores_falsos):
    assert cliente.post("/demo/restaurar").status_code == 200
    return motores_falsos


def catalogo(cnpj: str = SERRA_AZUL, **headers: str) -> CatalogoResposta:
    r = cliente.get("/catalogo", params={"cnpj": cnpj}, headers=headers)
    assert r.status_code == 200, r.text
    return CatalogoResposta.model_validate(r.json())


def item_de(cat: CatalogoResposta, item_id: str) -> ItemCatalogoEstado:
    return next(i for i in cat.itens if i.id == item_id)


def entrada(i: ItemCatalogoEstado, quantidade: Decimal) -> dict:
    """O item do catálogo como a tela o manda ao carrinho: só campos que a API devolveu."""
    corpo = i.model_dump(
        mode="json", include={"id", "descricao", "ncm", "nbs", "cst", "cClassTrib", "impostoSeletivo", "unidade"}
    )
    corpo |= {"quantidade": str(quantidade), "valorUnitario": str(i.precoVenda)}
    if i.custoAtual is not None:
        corpo["custoUnitario"] = str(i.custoAtual.custoUnitario)
        if i.custoAtual.creditoCompraUnitario is not None:
            corpo["creditoCompraUnitario"] = str(i.custoAtual.creditoCompraUnitario)
    return corpo


def novo_espaco() -> str:
    r = cliente.post("/espacos")
    assert r.status_code == 201, r.text
    return r.json()["id"]


# ---------------------------------------------------------------------------
# Catálogo: cenário, clientes B2B e lote (L1, L2, L6)


def test_catalogo_traz_cenario_clientes_e_lote(demo) -> None:
    cat = catalogo()
    assert cat.loteReferencia == int(LOTE) == 100
    assert cat.cenario.descricao == "Simulação de março de 2027"
    op = cat.cenario.operacao
    assert op.data == cat.empresa.dataCenario and op.uf == cat.empresa.uf and op.municipio == cat.empresa.municipio
    assert op.aliquotasNominais is not None and op.aliquotasNominais.fonte
    assert op.premissasDas is not None and op.premissasDas.fonte
    [bom_preco] = cat.clientesB2B
    assert bom_preco.regime == "regime_regular" and bom_preco.cnpj == "50291633000185"
    ids = {i.id for i in cat.itens}
    assert {c.itemId for c in bom_preco.compraMensal} <= ids
    # Outra empresa não herda o cliente da distribuidora.
    assert catalogo(VALE_VERDE).clientesB2B == []


def test_a_tela_refaz_a_margem_do_alerta_so_com_o_catalogo(demo) -> None:
    """Um fato, uma variável: a margem da cerveja que a tela calcula com o catálogo é a do alerta."""
    importar(nota(NOTA_2))
    cat = catalogo()
    cerveja = item_de(cat, "cerveja-lata")
    corpo = cat.cenario.operacao.model_dump(mode="json", exclude_none=True) | {
        "regime": cat.empresa.regimeAtual.value,
        "itens": [entrada(cerveja, Decimal(cat.loteReferencia))],
    }
    r = cliente.post("/carrinho/calcular", json=corpo)
    assert r.status_code == 200, r.text
    margem = CarrinhoResposta.model_validate(r.json()).itens[0].margemPct
    alertas = AlertasResposta.model_validate(cliente.get("/alertas", params={"cnpj": SERRA_AZUL}).json()).alertas
    alerta = next(a for a in alertas if a.itemId == "cerveja-lata")
    assert margem == alerta.margemDepoisPct
    assert cerveja.precoVenda == alerta.precoAtual


def test_a_tela_monta_a_decisao_de_regime_com_o_cliente_do_catalogo(demo) -> None:
    cat = catalogo()
    [cliente_b2b] = cat.clientesB2B
    itens = [entrada(item_de(cat, c.itemId), c.quantidade) for c in cliente_b2b.compraMensal]
    corpo = cat.cenario.operacao.model_dump(mode="json", exclude_none=True) | {
        "cliente": {"nome": cliente_b2b.nome, "regime": cliente_b2b.regime},
        "itens": itens,
    }
    r = cliente.post("/regime/comparar", json=corpo)
    assert r.status_code == 200, r.text
    comp = RegimeCompararResposta.model_validate(r.json())
    esperado = sum(
        (c.quantidade * item_de(cat, c.itemId).precoVenda for c in cliente_b2b.compraMensal), start=Decimal(0)
    )
    assert comp.valorVenda == esperado and comp.cliente.nome == cliente_b2b.nome


def test_sementes_recusam_cliente_sem_empresa_ou_com_item_de_fora(tmp_path: Path) -> None:
    def copiar_e_trocar(de: str, para: str) -> None:
        shutil.copytree(PASTA_DEMO, tmp_path, dirs_exist_ok=True)
        arquivo = tmp_path / "sementes.json"
        arquivo.write_text(arquivo.read_text(encoding="utf-8").replace(de, para), encoding="utf-8")

    copiar_e_trocar('"empresa": "36817420000113"', '"empresa": "11111111111111"')
    with pytest.raises(SementesInvalidas, match="empresa que não está"):
        _ler_sementes(tmp_path)
    copiar_e_trocar('"empresa": "36817420000113"', '"empresa": "41736592000102"')  # o Empório Lagoa não vende biscoito
    with pytest.raises(SementesInvalidas, match="fora do catálogo"):
        _ler_sementes(tmp_path)


# ---------------------------------------------------------------------------
# POST /catalogo/{itemId}/preco (L4)


def test_aplicar_preco_no_espaco_sem_token(demo) -> None:
    espaco = novo_espaco()
    r = cliente.post(
        "/catalogo/cerveja-lata/preco", json={"cnpj": SERRA_AZUL, "valorUnitario": "4.15"}, headers={ESPACO: espaco}
    )
    assert r.status_code == 200, r.text
    corpo = AplicarPrecoResposta.model_validate(r.json())
    assert (corpo.precoAnterior, corpo.precoNovo) == (Decimal("3.79"), Decimal("4.15"))
    assert item_de(catalogo(**{ESPACO: espaco}), "cerveja-lata").precoVenda == Decimal("4.15")
    # A demonstração compartilhada não mudou.
    assert item_de(catalogo(), "cerveja-lata").precoVenda == Decimal("3.79")
    # O mesmo preço de novo é conflito; outro item de outra empresa não existe aqui.
    mesmo = cliente.post(
        "/catalogo/cerveja-lata/preco", json={"cnpj": SERRA_AZUL, "valorUnitario": "4.15"}, headers={ESPACO: espaco}
    )
    assert mesmo.status_code == 409
    alheio = cliente.post(
        "/catalogo/carne-bovina-kg/preco", json={"cnpj": VALE_VERDE, "valorUnitario": "9.99"}, headers={ESPACO: espaco}
    )
    assert alheio.status_code == 404


def test_preco_da_tela_nao_fecha_o_alerta_e_vale_para_a_proxima_nota(demo) -> None:
    importar(nota(NOTA_2))
    r = cliente.post("/catalogo/cerveja-lata/preco", json={"cnpj": SERRA_AZUL, "valorUnitario": "3.99"})
    assert r.status_code == 200
    abertos = AlertasResposta.model_validate(cliente.get("/alertas", params={"abertos": "true"}).json()).alertas
    assert any(a.itemId == "cerveja-lata" for a in abertos)


@pytest.mark.parametrize("valor", ["0", "-1", "4.155", "1000000000.01", "NaN", "Infinity", "1e999999", "abc"])
def test_preco_invalido_e_recusado(demo, valor: str) -> None:
    r = cliente.post("/catalogo/cerveja-lata/preco", json={"cnpj": SERRA_AZUL, "valorUnitario": valor})
    assert r.status_code == 422
    [campo] = r.json()["campos"]
    assert campo["campo"] == "#/valorUnitario" and set(campo) == {"origem", "campo", "detalhe"}  # sem o valor


def test_rotas_da_tela_exigem_o_token_fora_do_espaco_e_nao_existem_no_mock(demo) -> None:
    app.dependency_overrides[configuracao] = lambda: Configuracao(modo="real", token_demo=SecretStr("t"))
    preco = {"cnpj": SERRA_AZUL, "valorUnitario": "4.15"}
    classif = {"cnpj": SERRA_AZUL, "cClassTrib": "200003"}
    assert cliente.post("/catalogo/cerveja-lata/preco", json=preco).status_code == 401
    assert cliente.post("/catalogo/carne-bovina-kg/classificacao", json=classif).status_code == 401
    assert cliente.post("/catalogo/cerveja-lata/preco", json=preco, headers={"X-ContaAI-Token": "t"}).status_code == 200
    app.dependency_overrides[configuracao] = lambda: Configuracao(modo="mock")
    assert cliente.post("/catalogo/cerveja-lata/preco", json=preco).status_code == 501
    assert cliente.post("/catalogo/carne-bovina-kg/classificacao", json=classif).status_code == 501


@pytest.mark.parametrize("item_id", ["../x", "Cerveja", "a" * 65, "x y", "-x", "%2e%2e"])
def test_id_do_item_fora_do_padrao(demo, item_id: str) -> None:
    r = cliente.post(f"/catalogo/{item_id}/preco", json={"cnpj": SERRA_AZUL, "valorUnitario": "1.00"})
    assert r.status_code in (404, 422)


# ---------------------------------------------------------------------------
# POST /catalogo/{itemId}/classificacao (L4: correção do REG-011)


def test_corrigir_a_classificacao_da_carne(demo) -> None:
    antes = item_de(catalogo(), "carne-bovina-kg")
    assert (antes.cst, antes.cClassTrib) == ("200", "200035")
    r = cliente.post("/catalogo/carne-bovina-kg/classificacao", json={"cnpj": SERRA_AZUL, "cClassTrib": "000001"})
    assert r.status_code == 200, r.text
    corpo = CorrigirClassificacaoResposta.model_validate(r.json())
    assert (corpo.cstAnterior, corpo.cClassTribAnterior) == ("200", "200035")
    # O CST vem da fundamentação oficial (dados abertos), não da tela.
    assert (corpo.item.cst, corpo.item.cClassTrib) == ("000", "000001") == (corpo.classificacao.cst, "000001")
    assert "confirmação do usuário (P3)" in corpo.item.classificacaoFonte
    depois = item_de(catalogo(), "carne-bovina-kg")
    assert (depois.cst, depois.cClassTrib) == ("000", "000001")
    # De novo a mesma: conflito.
    de_novo = cliente.post("/catalogo/carne-bovina-kg/classificacao", json={"cnpj": SERRA_AZUL, "cClassTrib": "000001"})
    assert de_novo.status_code == 409


@pytest.mark.parametrize(
    "codigo",
    [
        "410999",  # vale para qualquer NCM: não é candidata (método do ADR 0003)
        "900001",  # só de serviço
        "123456",  # não existe
    ],
)
def test_classificacao_fora_das_candidatas_e_recusada(demo, codigo: str) -> None:
    r = cliente.post("/catalogo/carne-bovina-kg/classificacao", json={"cnpj": SERRA_AZUL, "cClassTrib": codigo})
    assert r.status_code == 422, r.text
    assert item_de(catalogo(), "carne-bovina-kg").cClassTrib == "200035"


def test_classificacao_corrigida_vale_para_o_calculo_e_a_explicacao(demo) -> None:
    r = cliente.post("/catalogo/carne-bovina-kg/classificacao", json={"cnpj": SERRA_AZUL, "cClassTrib": "200003"})
    assert r.status_code == 200
    demo.chamadas.clear()
    x = cliente.get("/explicar/carne-bovina-kg", params={"regime": "simples_hibrido", "cnpj": SERRA_AZUL})
    assert x.status_code == 200, x.text
    assert ExplicarResposta.model_validate(x.json()).itemId == "carne-bovina-kg"
    enviados = [i for corpo in demo.chamadas_de("rr") for i in corpo["itens"]]
    assert enviados and all(i["cClassTrib"] == "200003" for i in enviados)


def test_lancamento_de_classificacao_nao_se_altera(demo) -> None:
    cliente.post("/catalogo/carne-bovina-kg/classificacao", json={"cnpj": SERRA_AZUL, "cClassTrib": "000001"})
    banco = configuracao().banco_caminho
    with sqlite3.connect(banco) as c, pytest.raises(sqlite3.IntegrityError, match="não se altera"):
        c.execute("UPDATE classificacoes SET cclasstrib = '200003'")


# ---------------------------------------------------------------------------
# GET /explicar/{itemId} lê o estado (L3)


def test_explicacao_usa_o_preco_atual_e_o_lote(demo) -> None:
    espaco = novo_espaco()
    cliente.post(
        "/catalogo/arroz-5kg/preco", json={"cnpj": SERRA_AZUL, "valorUnitario": "30.00"}, headers={ESPACO: espaco}
    )
    demo.chamadas.clear()
    r = cliente.get("/explicar/arroz-5kg", params={"regime": "simples_hibrido"}, headers={ESPACO: espaco})
    assert r.status_code == 200, r.text
    bases = [Decimal(str(i["baseCalculo"])) for corpo in demo.chamadas_de("rr") for i in corpo["itens"]]
    assert bases == [Decimal("30.00") * LOTE]


def test_explicacao_de_outra_empresa_e_de_item_inexistente(demo) -> None:
    assert cliente.get("/explicar/biscoito-pacote", params={"cnpj": VALE_VERDE}).status_code == 200
    assert cliente.get("/explicar/carne-bovina-kg", params={"cnpj": VALE_VERDE}).status_code == 404
    assert cliente.get("/explicar/arroz-5kg", params={"cnpj": "123"}).status_code == 422


# ---------------------------------------------------------------------------
# Migração 0002


def test_migracao_0002_preserva_os_precos_e_as_regras(tmp_path: Path) -> None:
    so_0001 = tmp_path / "migracoes"
    so_0001.mkdir()
    shutil.copy(PASTA_MIGRACOES / "0001_inicial.sql", so_0001)
    caminho = tmp_path / "antigo.db"
    Banco(caminho, so_0001).migrar()
    with sqlite3.connect(caminho) as c:
        c.execute("PRAGMA foreign_keys = ON")
        c.execute("INSERT INTO empresas VALUES ('36817420000113', 'X', 'simples_tradicional', '{}', '{}')")
        c.execute("INSERT INTO itens VALUES ('36817420000113', 'a', '10063021', 'UN', '{}')")
        c.execute(
            "INSERT INTO precos (cnpj, item_id, valor_unitario, vigente_desde, origem)"
            " VALUES ('36817420000113', 'a', '27.90', '2027-03-01T03:00:00+00:00', 'semente')"
        )
    assert Banco(caminho).migrar() == ["0002_tela.sql"]
    with sqlite3.connect(caminho) as c:
        assert c.execute("SELECT valor_unitario, origem FROM precos").fetchall() == [("27.90", "semente")]
        with pytest.raises(sqlite3.IntegrityError, match="não se altera"):
            c.execute("UPDATE precos SET valor_unitario = '1.00'")
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):  # preço de alerta sem alerta
            c.execute(
                "INSERT INTO precos (cnpj, item_id, valor_unitario, vigente_desde, origem)"
                " VALUES ('36817420000113', 'a', '1.00', '2027-03-01T03:00:00+00:00', 'alerta')"
            )
        c.execute(
            "INSERT INTO precos (cnpj, item_id, valor_unitario, vigente_desde, origem)"
            " VALUES ('36817420000113', 'a', '29.90', '2027-03-02T03:00:00+00:00', 'tela')"
        )
        indices = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type IN ('index', 'trigger')")}
        assert {"precos_por_item", "precos_sem_alteracao", "classificacoes_sem_alteracao"} <= indices


def test_espaco_copiado_antes_da_0002_recebe_a_migracao_ao_abrir(demo, tmp_path: Path) -> None:
    """Um espaço criado por um processo da versão anterior (só com a 0001) continua funcionando."""
    from app.api.dependencias import espacos

    espaco = novo_espaco()
    so_0001 = tmp_path / "migracoes"
    so_0001.mkdir()
    shutil.copy(PASTA_MIGRACOES / "0001_inicial.sql", so_0001)
    antigo = tmp_path / "antigo.db"
    Banco(antigo, so_0001).migrar()
    # O conteúdo das sementes, mas no esquema antigo: copia as tabelas da 0001 do espaço novo.
    destino = espacos(configuracao()).banco(espaco)
    c = sqlite3.connect(antigo, isolation_level=None)
    try:
        c.execute("ATTACH DATABASE ? AS novo", (str(destino.caminho),))
        c.execute("BEGIN")
        for tabela in ("empresas", "itens", "codigos_fornecedor", "notas", "custos", "alertas", "precos"):
            c.execute(f"INSERT INTO {tabela} SELECT * FROM novo.{tabela}")  # noqa: S608 (nomes fixos do teste)
        c.execute("COMMIT")
        c.execute("DETACH DATABASE novo")
    finally:
        c.close()
    Banco(antigo, so_0001).copiar_para(destino)  # API de backup do SQLite (o arquivo está em WAL)
    r = cliente.post(
        "/catalogo/cerveja-lata/preco", json={"cnpj": SERRA_AZUL, "valorUnitario": "4.15"}, headers={ESPACO: espaco}
    )
    assert r.status_code == 200, r.text
