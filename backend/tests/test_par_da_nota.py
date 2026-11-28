"""O item cadastrado a partir de uma linha sem par da nota (C3b, revisão no ADR 0017): o recibo guarda a unidade, o
custo e o crédito da linha, e o item nasce com o custo daquela nota. O alerta vem com a nota seguinte, porque ele só
nasce quando a margem cai em relação a um custo anterior (ADR 0008)."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api import dependencias
from app.api.rotas import contas as rotas_contas
from app.config import configuracao
from app.main import app
from app.persistencia.repositorio import Repositorio, Sessao
from tests.test_contas import Relogio
from tests.test_empresa_propria import (
    FORNECEDOR,
    NUMERICO,
    cadastrar,
    com_conta,
    compra_anterior_mais_barata,
    corpo_item,
    importar,
    nota_da_empresa,
)
from tests.test_nfe import NOTA_2, SERRA_AZUL, nota

CHOCOLATE = 2  # nItem do chocolate nas notas 1001 e 1002 da demonstração
CREDITO_DA_NOTA = Decimal("0.3649")  # (vCBS 288,64 + vIBS 3,28) ÷ 800, arredondado a 4 casas


@pytest.fixture
def relogio(monkeypatch: pytest.MonkeyPatch) -> Relogio:
    r = Relogio()
    monkeypatch.setattr(rotas_contas, "agora_utc", r)
    monkeypatch.setattr(dependencias, "agora_utc", r)
    return r


@pytest.fixture
def real(motores_falsos, relogio: Relogio) -> Relogio:
    """Modo real (motores falsos) com a demonstração restaurada."""
    assert TestClient(app).post("/demo/restaurar").status_code == 200
    return relogio


def _organizacao(c: TestClient) -> str:
    return str(c.get("/conta").json()["organizacao"]["id"])


def da_nota(numero: str = "1001", n_item: int = CHOCOLATE, serie: str = "1") -> dict[str, Any]:
    return {"serie": serie, "numero": numero, "nItem": n_item}


def linha(recibo: dict[str, Any], n_item: int) -> dict[str, Any]:
    return next(i for i in recibo["itensSemPar"] if i["nItem"] == n_item)


def sem_o_grupo_ibscbs(conteudo: bytes) -> bytes:
    """A mesma nota sem o grupo IBSCBS em nenhum item: o crédito vem do motor RR, como na importação."""
    texto = re.sub(r"<IBSCBS>.*?</IBSCBS>", "", conteudo.decode("utf-8"), flags=re.S)
    texto = re.sub(r"<IBSCBSTot>.*?</IBSCBSTot>", "", texto, flags=re.S)
    return texto.encode("utf-8")


def conta_com_a_nota(relogio_: Any, conteudo: bytes | None = None) -> tuple[TestClient, dict[str, Any]]:
    c = com_conta(relogio_)
    cadastrar(c)
    r = importar(c, conteudo or compra_anterior_mais_barata())
    assert r.status_code == 200, r.text
    return c, r.json()


def test_o_recibo_guarda_a_unidade_o_custo_e_o_credito_da_linha(real) -> None:
    _, recibo = conta_com_a_nota(real)
    chocolate = linha(recibo, CHOCOLATE)
    assert chocolate["causa"] == "semCadastro"
    assert chocolate["unidade"] == "UN"
    assert Decimal(chocolate["quantidade"]) == 800
    assert Decimal(chocolate["custoUnitario"]) == Decimal("3.50")
    assert Decimal(chocolate["valorTotal"]) == Decimal("2800.00")
    assert Decimal(chocolate["creditoCompraUnitario"]) == CREDITO_DA_NOTA
    assert chocolate["itemCadastrado"] is None


def test_o_item_nasce_com_o_custo_da_nota_e_o_alerta_vem_na_seguinte(real) -> None:
    c, _ = conta_com_a_nota(real)
    r = c.post("/catalogo/itens", json=corpo_item(daNota=da_nota()))
    assert r.status_code == 201, r.text
    item = r.json()["item"]
    custo = item["custoAtual"]
    assert Decimal(custo["custoUnitario"]) == Decimal("3.50")
    assert Decimal(custo["creditoCompraUnitario"]) == CREDITO_DA_NOTA
    assert custo["fonteCredito"] == "nfe" and custo["notaNumero"] == "1001"
    assert custo["data"].startswith("2027-03-15")

    # Reimportar a mesma nota devolve o recibo com o par, e a lista conta só as linhas ainda sem cadastro.
    de_novo = importar(c, compra_anterior_mais_barata()).json()
    assert de_novo["jaImportada"] is True
    assert linha(de_novo, CHOCOLATE)["itemCadastrado"] == item["id"]
    assert [n["itensSemPar"] for n in c.get(f"/notas?cnpj={NUMERICO}").json()["notas"]] == [2]

    # Sem custo anterior não há alerta; com a nota seguinte (4,10), a margem cai e ele nasce.
    assert c.get(f"/alertas?cnpj={NUMERICO}").json()["alertas"] == []
    seguinte = importar(c, nota_da_empresa())
    assert seguinte.status_code == 200, seguinte.text
    assert [i["itemId"] for i in seguinte.json()["itensCasados"]] == [item["id"]]
    assert [a["itemId"] for a in c.get(f"/alertas?cnpj={NUMERICO}").json()["alertas"]] == [item["id"]]


def test_sem_o_grupo_na_nota_o_credito_vem_do_motor(real, motores_falsos) -> None:
    c, recibo = conta_com_a_nota(real, sem_o_grupo_ibscbs(compra_anterior_mais_barata()))
    assert linha(recibo, CHOCOLATE)["creditoCompraUnitario"] is None
    antes = len(motores_falsos.chamadas_de("rr"))
    r = c.post("/catalogo/itens", json=corpo_item(daNota=da_nota()))
    assert r.status_code == 201, r.text
    custo = r.json()["item"]["custoAtual"]
    assert custo["fonteCredito"] == "motor" and Decimal(custo["creditoCompraUnitario"]) > 0
    chamada = motores_falsos.chamadas_de("rr")[antes]
    assert chamada["dhFatoGerador"].startswith("2027-03-15T")  # na data da nota, como na importação


@pytest.mark.parametrize(
    ("campos", "status", "frase"),
    [
        ({"daNota": da_nota(n_item=9)}, 404, "não tem um item sem par"),
        ({"daNota": da_nota(numero="1999")}, 404, "Nota não encontrada"),
        ({"daNota": da_nota(serie="2")}, 404, "Nota não encontrada"),
        ({"daNota": da_nota(), "codigoFornecedor": "OUTRO"}, 422, "precisam ser os da linha"),
        ({"daNota": da_nota(), "ncm": "10063021"}, 422, "precisam ser os da linha"),
        ({"daNota": da_nota(), "unidade": "KG"}, 422, "A unidade da nota (UN)"),
    ],
)
def test_linha_da_nota_recusada(real, campos: dict[str, Any], status: int, frase: str) -> None:
    c, _ = conta_com_a_nota(real)
    r = c.post("/catalogo/itens", json=corpo_item(**campos))
    assert r.status_code == status, r.text
    assert frase in r.json()["detail"]
    assert c.get(f"/catalogo?cnpj={NUMERICO}").json()["itens"] == []  # nada foi gravado


def test_nota_de_outro_fornecedor_responde_como_inexistente(real) -> None:
    c, _ = conta_com_a_nota(real)
    outro = "11444777000161"  # dígito certo, mas não é o emitente da nota
    r = c.post("/catalogo/itens", json=corpo_item(cnpjFornecedor=outro, daNota=da_nota()))
    assert r.status_code == 404, r.text


def test_a_linha_ja_cadastrada_nao_entra_de_novo(real) -> None:
    c, _ = conta_com_a_nota(real)
    assert c.post("/catalogo/itens", json=corpo_item(daNota=da_nota())).status_code == 201
    r = c.post("/catalogo/itens", json=corpo_item(daNota=da_nota()))
    assert r.status_code == 409 and "já foi cadastrado" in r.json()["detail"]


def test_so_a_linha_de_codigo_sem_cadastro_vira_item(real) -> None:
    """O chocolate cadastrado em KG não casa com a nota em UN: a linha é de unidade, não de código sem cadastro."""
    c = com_conta(real)
    cadastrar(c)
    assert c.post("/catalogo/itens", json=corpo_item(unidade="KG")).status_code == 201
    recibo = importar(c, compra_anterior_mais_barata()).json()
    assert linha(recibo, CHOCOLATE)["causa"] == "unidade"
    r = c.post("/catalogo/itens", json=corpo_item(codigoFornecedor="AE-CHO-90", daNota=da_nota()))
    assert r.status_code == 422 and "Só o item cujo código não está no catálogo" in r.json()["detail"]


def test_o_mesmo_codigo_duas_vezes_na_nota_e_recusado(real) -> None:
    conteudo = compra_anterior_mais_barata().replace(b"<cProd>AE-BIS-140</cProd>", b"<cProd>AE-CHO-90</cProd>", 1)
    c, _ = conta_com_a_nota(real, conteudo)
    r = c.post("/catalogo/itens", json=corpo_item(daNota=da_nota()))
    assert r.status_code == 422 and "mais de uma vez na nota" in r.json()["detail"]


def test_recibo_anterior_a_c3b_pede_o_cadastro_sem_a_nota(real) -> None:
    c, _ = conta_com_a_nota(real)
    banco = dependencias.banco_da_organizacao(configuracao(), _organizacao(c))
    with banco.transacao() as conexao:
        (bruto,) = conexao.execute("SELECT recibo_json FROM notas").fetchone()
        recibo = json.loads(bruto)
        campos = ("causa", "unidade", "quantidade", "custoUnitario", "valorTotal", "creditoCompraUnitario")
        recibo["itensSemPar"] = [{k: v for k, v in i.items() if k not in campos} for i in recibo["itensSemPar"]]
        conexao.execute("UPDATE notas SET recibo_json = ?", (json.dumps(recibo),))
    r = c.post("/catalogo/itens", json=corpo_item(daNota=da_nota()))
    assert r.status_code == 422 and "antes de o ContaAI guardar o custo" in r.json()["detail"]
    # Sem a nota, o mesmo item entra (e o custo vem com a próxima nota).
    assert c.post("/catalogo/itens", json=corpo_item()).status_code == 201


def test_recibo_trocado_no_meio_desfaz_o_item(real, monkeypatch: pytest.MonkeyPatch) -> None:
    c, _ = conta_com_a_nota(real)
    with monkeypatch.context() as m:
        m.setattr(Sessao, "trocar_recibo", lambda *_: False)
        r = c.post("/catalogo/itens", json=corpo_item(daNota=da_nota()))
    assert r.status_code == 409 and "A nota mudou durante o cadastro" in r.json()["detail"]
    catalogo = c.get(f"/catalogo?cnpj={NUMERICO}").json()
    assert catalogo["itens"] == []  # o item, o preço e o custo saíram juntos
    assert c.post("/catalogo/itens", json=corpo_item(daNota=da_nota())).status_code == 201


def test_o_par_da_nota_vale_no_espaco(real) -> None:
    """No espaço (cópia da demonstração, CNPJs fictícios aceitos), a linha sem cadastro vira item com o custo dela."""
    anonimo = TestClient(app)
    espaco = {"X-ContaAI-Espaco": anonimo.post("/espacos").json()["id"]}
    conteudo = nota(NOTA_2)
    for de, para in (
        (b"<nNF>1002</nNF>", b"<nNF>1009</nNF>"),
        (b"<cProd>AE-CHO-90</cProd>", b"<cProd>AE-CHO-NOVO</cProd>"),
    ):
        assert de in conteudo, de
        conteudo = conteudo.replace(de, para, 1)
    r = anonimo.post("/nfe/importar", files={"arquivo": ("n.xml", conteudo, "application/xml")}, headers=espaco)
    assert r.status_code == 200, r.text
    recibo = r.json()
    alvo = linha(recibo, CHOCOLATE)
    assert alvo["causa"] == "semCadastro"
    corpo = corpo_item(
        cnpj=SERRA_AZUL,
        cnpjFornecedor=recibo["nota"]["emitente"]["cnpj"],
        codigoFornecedor="AE-CHO-NOVO",
        daNota=da_nota(numero="1009"),
    )
    r = anonimo.post("/catalogo/itens", json=corpo, headers=espaco)
    assert r.status_code == 201, r.text
    item = r.json()["item"]
    assert Decimal(item["custoAtual"]["custoUnitario"]) == Decimal("4.10")
    # A demonstração compartilhada não mudou.
    assert item["id"] not in {i["id"] for i in anonimo.get(f"/catalogo?cnpj={SERRA_AZUL}").json()["itens"]}


def test_linha_monofasica_sem_cadastro_diz_a_causa_certa(real) -> None:
    """Sem o item no catálogo e com o gIBSCBSMono, a causa é a tributação: cadastrar não faria a nota casar."""
    conteudo = compra_anterior_mais_barata()
    det = conteudo.index(b'<det nItem="2">')
    fim = conteudo.index(b"</IBSCBS>", det)
    conteudo = conteudo[:fim] + b"<gIBSCBSMono></gIBSCBSMono>" + conteudo[fim:]
    c, recibo = conta_com_a_nota(real, conteudo)
    chocolate = linha(recibo, CHOCOLATE)
    assert chocolate["causa"] == "monofasico" and "monofásica" in chocolate["motivo"]
    assert chocolate["creditoCompraUnitario"] is None
    r = c.post("/catalogo/itens", json=corpo_item(daNota=da_nota()))
    assert r.status_code == 422 and "monofásica" in r.json()["detail"]


def test_a_troca_do_recibo_confere_o_que_foi_lido(real) -> None:
    """A troca só vale com o recibo lido: outro já trocado no meio, ou uma nota ainda sem recibo, ficam como estão."""
    c, _ = conta_com_a_nota(real)
    repo = Repositorio(dependencias.banco_da_organizacao(configuracao(), _organizacao(c)))
    with repo.escrita() as s:
        lida = s.nota(NUMERICO, FORNECEDOR, "1", "1001")
        assert lida is not None
        assert s.trocar_recibo(lida.id, '{"outro": 1}', '{"novo": 1}') is False
        assert s.trocar_recibo(lida.id, lida.recibo_json, lida.recibo_json + " ") is True
        sem_recibo = s.inserir_nota(NUMERICO, FORNECEDOR, "1", "1999", datetime.now(UTC), "0" * 64, datetime.now(UTC))
        assert s.trocar_recibo(sem_recibo, "{}", '{"novo": 1}') is False
