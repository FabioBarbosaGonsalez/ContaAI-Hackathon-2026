"""GET /notas/{cnpj_emitente}/{serie}/{numero} (C3b): o recibo de uma nota já importada, sem enviar o XML de novo,
para cadastrar depois os itens sem par. E o fornecedor de cada item no GET /catalogo, que o PATCH muda.

Rodam no CI com os motores falsos do conftest (os do modo mock, sem fixture, leem os mocks).
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api import dependencias
from app.api.rotas import contas as rotas_contas
from app.contrato import CatalogoResposta, NfeImportarResposta, NotasResposta, ReciboDaNotaResposta
from app.dados_demo import carregar_distribuidora
from app.main import app
from tests.test_contas import Relogio
from tests.test_empresa_propria import (
    FORNECEDOR,
    NUMERICO,
    cadastrar,
    com_conta,
    compra_anterior_mais_barata,
    corpo_item,
)
from tests.test_empresa_propria import importar as importar_na_conta
from tests.test_nfe import NOTA_2, SEM_PAR, SERRA_AZUL, VALE_VERDE, importar, nota
from tests.test_par_da_nota import da_nota, linha
from tests.test_tela import ESPACO, novo_espaco

cliente = TestClient(app)
EMITENTE_DEMO = "71604258000156"
CHOCOLATE = 2


@pytest.fixture
def relogio(monkeypatch: pytest.MonkeyPatch) -> Relogio:
    r = Relogio()
    monkeypatch.setattr(rotas_contas, "agora_utc", r)
    monkeypatch.setattr(dependencias, "agora_utc", r)
    return r


@pytest.fixture
def real(motores_falsos, relogio: Relogio) -> Relogio:
    """Modo real (motores falsos) com a demonstração restaurada, e o relógio das contas."""
    assert cliente.post("/demo/restaurar").status_code == 200
    return relogio


@pytest.fixture
def demo(motores_falsos):
    assert cliente.post("/demo/restaurar").status_code == 200
    return motores_falsos


def url(numero: str, emitente: str = EMITENTE_DEMO, serie: str = "1") -> str:
    return f"/notas/{emitente}/{serie}/{numero}"


def ler(numero: str, cnpj: str = SERRA_AZUL, c: TestClient = cliente, **headers: str) -> Any:
    return c.get(url(numero), params={"cnpj": cnpj}, headers=headers)


def test_o_recibo_e_o_da_importacao(demo) -> None:
    importado = NfeImportarResposta.model_validate(importar(nota(NOTA_2)))
    r = ler("1002")
    assert r.status_code == 200, r.text
    assert "X-ContaAI-Mock" not in r.headers
    corpo = ReciboDaNotaResposta.model_validate(r.json())
    assert corpo.recibo == importado
    assert corpo.recibo.jaImportada is False
    assert corpo.importadaEm.utcoffset() is not None and corpo.importadaEm.utcoffset().total_seconds() == 0
    lista = NotasResposta.model_validate(cliente.get("/notas", params={"cnpj": SERRA_AZUL}).json())
    assert next(n for n in lista.notas if n.nota.numero == "1002").importadaEm == corpo.importadaEm


def test_os_alertas_vem_com_o_estado_atual(demo) -> None:
    """O recibo gravado diz que o alerta estava aberto; depois de aplicado, a leitura diz quando."""
    alerta = NfeImportarResposta.model_validate(importar(nota(NOTA_2))).alertas[0]
    assert cliente.post(f"/alertas/{alerta.id}/aplicar").status_code == 200
    lido = ReciboDaNotaResposta.model_validate(ler("1002").json())
    achado = next(a for a in lido.recibo.alertas if a.id == alerta.id)
    assert achado.aplicadoEm is not None
    assert all(a.aplicadoEm is None for a in lido.recibo.alertas if a.id != alerta.id)


def test_as_linhas_sem_par_de_uma_nota_antiga(demo) -> None:
    sem_par = NfeImportarResposta.model_validate(importar(nota(SEM_PAR)))
    lido = ReciboDaNotaResposta.model_validate(ler(sem_par.nota.numero).json())
    assert lido.recibo.itensSemPar == sem_par.itensSemPar and lido.recibo.itensSemPar


def test_a_linha_cadastrada_depois_cita_o_item(real) -> None:
    """O caminho da tela: a conta importa a nota, cadastra o item a partir da leitura (sem o XML) e lê de novo."""
    c = com_conta(real)
    cadastrar(c)
    assert importar_na_conta(c, compra_anterior_mais_barata()).status_code == 200
    antes = c.get(url("1001", FORNECEDOR), params={"cnpj": NUMERICO})
    assert antes.status_code == 200, antes.text
    assert linha(antes.json()["recibo"], CHOCOLATE)["itemCadastrado"] is None

    criado = c.post("/catalogo/itens", json=corpo_item(daNota=da_nota()))
    assert criado.status_code == 201, criado.text
    depois = c.get(url("1001", FORNECEDOR), params={"cnpj": NUMERICO}).json()
    assert linha(depois["recibo"], CHOCOLATE)["itemCadastrado"] == criado.json()["item"]["id"]


def test_nota_que_nao_existe_ou_de_outra_empresa_responde_404(demo) -> None:
    importar(nota(NOTA_2))
    for pedido in (
        ler("1009"),
        cliente.get(url("1002", serie="2"), params={"cnpj": SERRA_AZUL}),
        cliente.get(url("1002", emitente=SERRA_AZUL), params={"cnpj": SERRA_AZUL}),
        # A nota é da Serra Azul: pela Vale Verde, a mesma resposta de uma nota que não existe.
        ler("1002", VALE_VERDE),
        ler("1002", "00000000000000"),
    ):
        assert pedido.status_code == 404, pedido.text
        assert pedido.headers["content-type"].startswith("application/problem+json")


def test_o_espaco_le_so_as_proprias_notas(demo) -> None:
    espaco = novo_espaco()
    importar(nota(NOTA_2), **{ESPACO: espaco})
    assert ler("1002", **{ESPACO: espaco}).status_code == 200
    assert ler("1002").status_code == 404
    assert ler("1002", **{ESPACO: "0" * 32}).status_code == 404


def test_a_conta_nao_le_a_nota_de_outra_conta(real) -> None:
    dona = com_conta(real)
    cadastrar(dona)
    assert importar_na_conta(dona, compra_anterior_mais_barata()).status_code == 200
    outra = com_conta(real, "bia@exemplo.com.br")
    assert outra.get(url("1001", FORNECEDOR), params={"cnpj": NUMERICO}).status_code == 404


@pytest.mark.parametrize(
    "caminho",
    [
        "/notas/123/1/1002",
        "/notas/71604258000156/1234/1002",
        "/notas/71604258000156/a/1002",
        "/notas/71604258000156/1/0123",
        "/notas/71604258000156/1/1234567890",
    ],
)
def test_o_caminho_fora_do_contrato_responde_422(demo, caminho: str) -> None:
    assert cliente.get(caminho, params={"cnpj": SERRA_AZUL}).status_code == 422


def test_sem_o_cnpj_da_empresa_responde_422(demo) -> None:
    assert cliente.get(url("1001")).status_code == 422


# -- modo mock ---------------------------------------------------------------------------------------------


def test_no_mock_cada_nota_da_lista_tem_o_recibo() -> None:
    lista = NotasResposta.model_validate(cliente.get("/notas", params={"cnpj": SERRA_AZUL}).json())
    for n in lista.notas:
        r = cliente.get(url(n.nota.numero, n.nota.emitente.cnpj, n.nota.serie or ""), params={"cnpj": SERRA_AZUL})
        assert r.status_code == 200 and r.headers["X-ContaAI-Mock"] == "1"
        lido = ReciboDaNotaResposta.model_validate(r.json())
        assert lido.recibo.nota == n.nota and lido.importadaEm == n.importadaEm
        assert len(lido.recibo.itensSemPar) == n.itensSemPar


def test_no_mock_a_nota_mais_recente_e_a_do_mock_da_importacao() -> None:
    importacao = NfeImportarResposta.model_validate(
        cliente.post("/nfe/importar", files={"arquivo": ("n.xml", nota(NOTA_2), "text/xml")}).json()
    )
    lido = ReciboDaNotaResposta.model_validate(ler("1002").json())
    assert lido.recibo == importacao


def test_no_mock_nota_de_fora_ou_de_outra_empresa_responde_404() -> None:
    assert ler("1009").status_code == 404
    assert ler("1002", VALE_VERDE).status_code == 404


# -- o fornecedor no catálogo (C3b) ------------------------------------------------------------------------


def test_o_catalogo_traz_o_fornecedor_de_cada_item(demo) -> None:
    cat = CatalogoResposta.model_validate(cliente.get("/catalogo", params={"cnpj": SERRA_AZUL}).json())
    sementes = {i.id: i for i in carregar_distribuidora().catalogo}
    assert cat.itens
    for item in cat.itens:
        assert (item.fornecedor.cnpj, item.fornecedor.codigo) == (
            sementes[item.id].cnpjFornecedor,
            sementes[item.id].codigoFornecedor,
        )


def test_o_fornecedor_alterado_aparece_no_catalogo_e_casa_a_nota(real) -> None:
    c = com_conta(real)
    cadastrar(c)
    criado = c.post("/catalogo/itens", json=corpo_item())
    assert criado.status_code == 201, criado.text
    item = criado.json()["item"]
    assert item["fornecedor"] == {"cnpj": FORNECEDOR, "codigo": corpo_item()["codigoFornecedor"]}

    r = c.patch(
        f"/catalogo/{item['id']}", json={"cnpj": NUMERICO, "cnpjFornecedor": FORNECEDOR, "codigoFornecedor": "X9"}
    )
    assert r.status_code == 200, r.text
    assert r.json()["item"]["fornecedor"] == {"cnpj": FORNECEDOR, "codigo": "X9"}
    lido = CatalogoResposta.model_validate(c.get("/catalogo", params={"cnpj": NUMERICO}).json())
    assert next(i for i in lido.itens if i.id == item["id"]).fornecedor.codigo == "X9"


def test_no_mock_o_catalogo_traz_o_fornecedor_das_sementes() -> None:
    cat = CatalogoResposta.model_validate(cliente.get("/catalogo", params={"cnpj": SERRA_AZUL}).json())
    sementes = {i.id: i for i in carregar_distribuidora().catalogo}
    assert {i.id: i.fornecedor.codigo for i in cat.itens} == {k: v.codigoFornecedor for k, v in sementes.items()}
