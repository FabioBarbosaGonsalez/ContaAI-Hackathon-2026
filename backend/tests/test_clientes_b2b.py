"""Clientes B2B editáveis (C3-B, etapa 6, ADR 0017): criar, alterar e excluir o cliente empresa e a compra mensal dele,
e a trava que não deixa arquivar um item que está na compra de um cliente."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app import cadastro
from app.api import dependencias, middlewares
from app.api.rotas import contas as rotas_contas
from app.cnpj import digitos_verificadores
from app.config import Configuracao, configuracao
from app.contrato import ClienteResposta, ProblemaItemEmUso
from app.main import app
from app.seguranca import LimitadorPorIp
from tests.test_contas import Relogio
from tests.test_empresa_propria import CAXIAS, ESPACO, NUMERICO, PORTO_ALEGRE, cadastrar, com_conta, criar_item
from tests.test_nfe import SERRA_AZUL

CLIENTE = "334445550001" + digitos_verificadores("334445550001")
MERCADO_FICTICIO = "50291633000185"  # o cliente da demonstração, com o dígito errado de propósito


@pytest.fixture
def real(motores_falsos, monkeypatch: pytest.MonkeyPatch) -> Relogio:
    """Modo real (motores falsos), a demonstração restaurada e o relógio das contas (como em test_empresa_propria)."""
    r = Relogio()
    monkeypatch.setattr(rotas_contas, "agora_utc", r)
    monkeypatch.setattr(dependencias, "agora_utc", r)
    assert TestClient(app).post("/demo/restaurar").status_code == 200
    return r


def corpo_cliente(itens: list[str], cnpj: str = NUMERICO, **kw: Any) -> dict[str, Any]:
    return {
        "cnpj": cnpj,
        "cnpjCliente": CLIENTE,
        "razaoSocial": "Mercado do Bairro Ltda",
        "regime": "regime_regular",
        "uf": "RS",
        "municipio": PORTO_ALEGRE,
        "compraMensal": [{"itemId": i, "quantidade": "120"} for i in itens],
    } | kw


def criar_cliente(
    c: TestClient, itens: list[str], status: int = 201, headers: dict[str, str] | None = None, **kw: Any
) -> dict[str, Any]:
    r = c.post("/clientes", json=corpo_cliente(itens, **kw), headers=headers or {})
    assert r.status_code == status, r.text
    return r.json()


def empresa_com_item(relogio_: Any) -> tuple[TestClient, str]:
    c = com_conta(relogio_)
    cadastrar(c)
    return c, str(criar_item(c)["item"]["id"])


def clientes(c: TestClient, cnpj: str = NUMERICO, headers: dict[str, str] | None = None) -> list[dict[str, Any]]:
    return list(c.get(f"/catalogo?cnpj={cnpj}", headers=headers or {}).json()["clientesB2B"])


def test_no_modo_mock_as_rotas_de_clientes_respondem_501() -> None:
    c = TestClient(app)
    assert c.post("/clientes", json=corpo_cliente(["arroz-5kg"])).status_code == 501
    assert c.patch(f"/clientes/{CLIENTE}", json={"cnpj": NUMERICO, "razaoSocial": "x"}).status_code == 501
    assert c.post(f"/clientes/{CLIENTE}/excluir", json={"cnpj": NUMERICO}).status_code == 501


def test_criar_cliente_e_ele_entra_no_catalogo(real) -> None:
    c, item = empresa_com_item(real)
    cliente = ClienteResposta.model_validate(criar_cliente(c, [item])).cliente
    assert (cliente.cnpj, cliente.nome, cliente.regime) == (CLIENTE, "Mercado do Bairro Ltda", "regime_regular")
    assert cliente.compraMensalDescricao == cadastro.DESCRICAO_DA_COMPRA  # texto do backend, sem texto da pessoa
    assert [(i.itemId, str(i.quantidade)) for i in cliente.compraMensal] == [(item, "120")]
    assert clientes(c) == [cliente.model_dump(mode="json")]


@pytest.mark.parametrize(
    ("campos", "frase"),
    [
        ({"regime": "simples_nacional"}, "regime regular"),
        ({"cnpjCliente": MERCADO_FICTICIO}, "CNPJ do cliente inválido"),  # o fictício, fora da demonstração
        ({"cnpjCliente": NUMERICO}, "própria empresa"),
        ({"municipio": 3550308}, "Município não encontrado"),  # São Paulo, fora do RS
        ({"uf": "EX", "municipio": 9999999}, "UF não encontrada"),
    ],
)
def test_cliente_recusado_pelos_dados(real, campos: dict[str, Any], frase: str) -> None:
    c, item = empresa_com_item(real)
    assert frase in criar_cliente(c, [item], 422, **campos)["detail"]
    assert clientes(c) == []


def test_item_da_compra_fora_do_catalogo_e_recusado(real) -> None:
    c, item = empresa_com_item(real)
    assert "não está no catálogo" in criar_cliente(c, [item, "item-000000000000"], 422)["detail"]
    assert "não está no catálogo" in criar_cliente(c, ["arroz-5kg"], 422)["detail"]  # item da demonstração
    assert clientes(c) == []


@pytest.mark.parametrize(
    "campos",
    [
        {"compraMensal": []},
        {"compraMensal": [{"itemId": "a", "quantidade": "1"}, {"itemId": "a", "quantidade": "2"}]},
        {"compraMensal": [{"itemId": "a", "quantidade": "0"}]},
        {"compraMensal": [{"itemId": "a", "quantidade": "1.00001"}]},
        {"compraMensal": [{"itemId": "A B", "quantidade": "1"}]},
        {"compraMensal": [{"itemId": f"i{n}", "quantidade": "1"} for n in range(201)]},
        {"cnpjCliente": "33444555000l99"},
        {"razaoSocial": " "},
        {"razaoSocial": "Nome\x1b[31m"},
        {"regime": "simples_hibrido"},
        {"municipio": 123},
        {"extra": "campo"},
    ],
)
def test_cliente_fora_do_contrato(real, campos: dict[str, Any]) -> None:
    c, item = empresa_com_item(real)
    r = c.post("/clientes", json=corpo_cliente([item]) | campos)
    assert r.status_code == 422 and r.json()["type"] == "/problemas/entrada-invalida", r.text


def test_cliente_repetido_e_limite_por_empresa(real, monkeypatch: pytest.MonkeyPatch) -> None:
    c, item = empresa_com_item(real)
    criar_cliente(c, [item])
    assert "já está cadastrado" in criar_cliente(c, [item], 409)["detail"]
    monkeypatch.setattr(cadastro, "CLIENTES_POR_EMPRESA", 1)
    outro = "556667770001" + digitos_verificadores("556667770001")
    assert "limite por empresa" in criar_cliente(c, [item], 409, cnpjCliente=outro)["detail"]
    assert len(clientes(c)) == 1


def test_alterar_cliente(real) -> None:
    c, item = empresa_com_item(real)
    outro_item = str(criar_item(c, codigoFornecedor="AE-CHO-91", descricao="Chocolate 2")["item"]["id"])
    criar_cliente(c, [item])
    caminho = f"/clientes/{CLIENTE}"
    r = c.patch(caminho, json={"cnpj": NUMERICO, "razaoSocial": "Mercado Novo Ltda", "uf": "RS", "municipio": CAXIAS})
    assert r.status_code == 200, r.text
    assert (r.json()["cliente"]["nome"], r.json()["cliente"]["municipio"]) == ("Mercado Novo Ltda", CAXIAS)
    compra = [{"itemId": outro_item, "quantidade": "3.5"}, {"itemId": item, "quantidade": "10"}]
    r = c.patch(caminho, json={"cnpj": NUMERICO, "compraMensal": compra})
    assert [(i["itemId"], i["quantidade"]) for i in r.json()["cliente"]["compraMensal"]] == [
        (outro_item, "3.5"),
        (item, "10"),
    ]
    assert clientes(c)[0]["nome"] == "Mercado Novo Ltda"  # o nome não mudou com a compra
    assert "Nada mudou" in c.patch(caminho, json={"cnpj": NUMERICO, "compraMensal": compra}).json()["detail"]


@pytest.mark.parametrize(
    "corpo",
    [
        {"cnpj": NUMERICO},
        {"cnpj": NUMERICO, "uf": "RS"},
        {"cnpj": NUMERICO, "razaoSocial": None},
        {"cnpj": NUMERICO, "compraMensal": None},
        {"cnpj": NUMERICO, "cnpjCliente": CLIENTE},  # o CNPJ do cliente não muda
        {"cnpj": NUMERICO, "regime": "regime_regular"},
    ],
)
def test_alteracao_fora_do_contrato(real, corpo: dict[str, Any]) -> None:
    c, item = empresa_com_item(real)
    criar_cliente(c, [item])
    assert c.patch(f"/clientes/{CLIENTE}", json=corpo).status_code == 422


def test_alteracao_recusada_pelos_dados_e_cliente_inexistente(real) -> None:
    c, item = empresa_com_item(real)
    criar_cliente(c, [item])
    caminho = f"/clientes/{CLIENTE}"
    r = c.patch(caminho, json={"cnpj": NUMERICO, "uf": "RS", "municipio": 3550308})
    assert r.status_code == 422 and "Município não encontrado" in r.json()["detail"]
    r = c.patch(caminho, json={"cnpj": NUMERICO, "compraMensal": [{"itemId": "arroz-5kg", "quantidade": "1"}]})
    assert r.status_code == 422 and "não está no catálogo" in r.json()["detail"]
    outro = "556667770001" + digitos_verificadores("556667770001")
    assert c.patch(f"/clientes/{outro}", json={"cnpj": NUMERICO, "razaoSocial": "x"}).status_code == 404
    assert clientes(c)[0]["nome"] == "Mercado do Bairro Ltda"


def test_excluir_cliente_de_vez(real) -> None:
    c, item = empresa_com_item(real)
    criar_cliente(c, [item])
    r = c.post(f"/clientes/{CLIENTE}/excluir", json={"cnpj": NUMERICO})
    assert r.status_code == 200 and r.json()["cnpjCliente"] == CLIENTE, r.text
    assert clientes(c) == []
    assert c.post(f"/clientes/{CLIENTE}/excluir", json={"cnpj": NUMERICO}).status_code == 404
    criar_cliente(c, [item])  # o mesmo CNPJ volta como cliente novo


# -- a trava do item arquivado ----------------------------------------------------------------------------


def test_item_na_compra_de_um_cliente_nao_e_arquivado(real) -> None:
    c, item = empresa_com_item(real)
    outro_item = str(criar_item(c, codigoFornecedor="AE-CHO-91", descricao="Chocolate 2")["item"]["id"])
    criar_cliente(c, [item, outro_item])
    r = c.post(f"/catalogo/{item}/arquivar", json={"cnpj": NUMERICO})
    assert r.status_code == 409, r.text
    problema = ProblemaItemEmUso.model_validate(r.json())
    assert problema.type == "/problemas/item-em-uso"
    assert [(x.cnpj, x.nome) for x in problema.clientes] == [(CLIENTE, "Mercado do Bairro Ltda")]
    assert item in [i["id"] for i in c.get(f"/catalogo?cnpj={NUMERICO}").json()["itens"]]
    # Fora da compra, o item sai.
    c.patch(
        f"/clientes/{CLIENTE}", json={"cnpj": NUMERICO, "compraMensal": [{"itemId": outro_item, "quantidade": "1"}]}
    )
    assert c.post(f"/catalogo/{item}/arquivar", json={"cnpj": NUMERICO}).status_code == 200
    assert c.get("/problemas/item-em-uso").status_code == 200


def test_na_demonstracao_o_item_do_cliente_ficticio_tambem_fica(real) -> None:
    """O bug latente da etapa 5: arquivar o biscoito no espaço deixava a venda do Mercado Bom Preço sem item."""
    espaco = {ESPACO: TestClient(app).post("/espacos").json()["id"]}
    c = TestClient(app)
    r = c.post("/catalogo/biscoito-pacote/arquivar", json={"cnpj": SERRA_AZUL}, headers=espaco)
    assert r.status_code == 409, r.text
    assert [x["cnpj"] for x in r.json()["clientes"]] == [MERCADO_FICTICIO]
    assert c.post("/catalogo/arroz-5kg/arquivar", json={"cnpj": SERRA_AZUL}, headers=espaco).status_code == 200


# -- demonstração, espaços e outras contas ----------------------------------------------------------------


def test_no_espaco_o_cliente_ficticio_entra_e_a_demonstracao_nao_muda(real) -> None:
    espaco = {ESPACO: TestClient(app).post("/espacos").json()["id"]}
    c = TestClient(app)
    novo = "50291633000199"  # fictício, com o dígito errado: aceito fora da empresa da conta
    criar_cliente(c, ["arroz-5kg"], headers=espaco, cnpj=SERRA_AZUL, cnpjCliente=novo)
    assert len(clientes(c, SERRA_AZUL, espaco)) == 2
    # A compra reenviada igual guarda a descrição das sementes; só o nome muda.
    semente = next(x for x in clientes(c, SERRA_AZUL, espaco) if x["cnpj"] == MERCADO_FICTICIO)
    compra = [{"itemId": i["itemId"], "quantidade": i["quantidade"]} for i in semente["compraMensal"]]
    r = c.patch(
        f"/clientes/{MERCADO_FICTICIO}",
        json={"cnpj": SERRA_AZUL, "razaoSocial": "Mercado (fictício)", "compraMensal": compra},
        headers=espaco,
    )
    assert r.status_code == 200, r.text
    assert r.json()["cliente"]["compraMensalDescricao"] == semente["compraMensalDescricao"]
    assert c.post(f"/clientes/{novo}/excluir", json={"cnpj": SERRA_AZUL}, headers=espaco).status_code == 200
    assert [x["nome"] for x in clientes(c, SERRA_AZUL)] == ["Mercado Bom Preço Ltda (fictício)"]


def test_clientes_da_demonstracao_compartilhada_exigem_o_token(real) -> None:
    app.dependency_overrides[configuracao] = lambda: Configuracao(modo="real", token_demo="segredo-de-teste")
    c = TestClient(app)
    corpo = corpo_cliente(["arroz-5kg"], SERRA_AZUL, cnpjCliente="50291633000199")
    assert c.post("/clientes", json=corpo).status_code == 401
    alterar = {"cnpj": SERRA_AZUL, "razaoSocial": "x"}
    assert c.patch(f"/clientes/{MERCADO_FICTICIO}", json=alterar).status_code == 401
    assert c.post(f"/clientes/{MERCADO_FICTICIO}/excluir", json={"cnpj": SERRA_AZUL}).status_code == 401
    com_token = {"X-ContaAI-Token": "segredo-de-teste"}
    assert c.post("/clientes", json=corpo, headers=com_token).status_code == 201


def test_cliente_de_empresa_de_outra_conta_responde_404(real) -> None:
    ana, item = empresa_com_item(real)
    bia = com_conta(real, "bia@exemplo.com.br")
    criar_cliente(ana, [item])
    assert bia.post("/clientes", json=corpo_cliente([item])).status_code == 404
    assert bia.patch(f"/clientes/{CLIENTE}", json={"cnpj": NUMERICO, "razaoSocial": "x"}).status_code == 404
    assert bia.post(f"/clientes/{CLIENTE}/excluir", json={"cnpj": NUMERICO}).status_code == 404
    assert clientes(ana)[0]["nome"] == "Mercado do Bairro Ltda"


# -- segurança --------------------------------------------------------------------------------------------


def test_clientes_com_o_cookie_e_de_outra_origem_sao_recusados(real) -> None:
    c, item = empresa_com_item(real)
    criar_cliente(c, [item])
    outro_site = {"Origin": "https://ataque.exemplo.test"}
    assert c.post("/clientes", json=corpo_cliente([item]), headers=outro_site).status_code == 403
    assert (
        c.patch(f"/clientes/{CLIENTE}", json={"cnpj": NUMERICO, "razaoSocial": "x"}, headers=outro_site).status_code
        == 403
    )
    sem_origin = TestClient(app, base_url="https://testserver", cookies=c.cookies)
    assert sem_origin.post(f"/clientes/{CLIENTE}/excluir", json={"cnpj": NUMERICO}).status_code == 403
    assert clientes(c)[0]["nome"] == "Mercado do Bairro Ltda"


def test_clientes_tem_limite_por_ip_e_de_corpo(real, monkeypatch: pytest.MonkeyPatch) -> None:
    c, item = empresa_com_item(real)
    monkeypatch.setattr(middlewares, "LIMITE_GERAL", LimitadorPorIp(1))
    assert c.post("/clientes", json=corpo_cliente([item])).status_code == 201
    assert c.patch(f"/clientes/{CLIENTE}", json={"cnpj": NUMERICO, "razaoSocial": "Dois"}).status_code == 429
    monkeypatch.setattr(middlewares, "LIMITE_GERAL", LimitadorPorIp(100))
    app.dependency_overrides[configuracao] = lambda: Configuracao(modo="real", tamanho_max_json_bytes=200)
    r = c.patch(f"/clientes/{CLIENTE}", json={"cnpj": NUMERICO, "razaoSocial": "x" * 300})
    assert r.status_code == 413, r.text


def test_erros_de_clientes_nao_repetem_o_que_foi_enviado(real) -> None:
    c, item = empresa_com_item(real)
    marcador = "<script>alert(1)</script>"
    for r in (
        c.post("/clientes", json=corpo_cliente([item], razaoSocial=marcador, municipio=3550308)),
        c.post("/clientes", json=corpo_cliente([item], razaoSocial=marcador, regime="simples_nacional")),
        c.post("/clientes", json=corpo_cliente(["item-000000000000"], razaoSocial=marcador)),
    ):
        assert r.status_code == 422 and marcador not in r.text and "alert" not in r.text, r.text
