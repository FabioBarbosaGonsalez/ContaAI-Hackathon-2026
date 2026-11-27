"""Papéis na organização (C3-B, etapa 8; ADR 0017): só o dono cadastra, configura e exclui a empresa; o dono e o membro
mudam o catálogo, os clientes B2B, as notas, os preços, os alertas e as classificações; todo integrante lê.

A 3c traz os convites e o seletor de organização. Até lá, o membro entra pela tabela `membros` e a sessão dele é
levada à organização da dona (como em test_exclusao_e_dados)."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from typing import Any

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from httpx import Response
from starlette.routing import BaseRoute

from app.api import dependencias
from app.api.dependencias import PAPEIS_QUE_ADMINISTRAM, PAPEIS_QUE_EDITAM, RECUSA_EDICAO
from app.api.rotas import contas as rotas_contas
from app.api.rotas import empresa as rotas_empresa
from app.api.rotas.empresa import RECUSA_CONFIGURAR, RECUSA_EXCLUIR
from app.config import configuracao
from app.main import app
from app.seguranca import METODOS_INSEGUROS
from tests.test_clientes_b2b import CLIENTE, corpo_cliente
from tests.test_contas import SENHA, Relogio
from tests.test_empresa_propria import (
    NUMERICO,
    cadastrar,
    com_conta,
    compra_anterior_mais_barata,
    corpo_empresa,
    corpo_item,
    criar_item,
    importar,
    nota_da_empresa,
)

BIA = "bia@exemplo.com.br"
ALERTA_QUALQUER = "alerta-0000000000000000"

# Toda rota que muda o estado, pelo que ela muda. Uma rota nova (os convites do 3c, por exemplo) falha o inventário
# até entrar numa destas listas, e a de edição e a de administração têm teste de papel abaixo.
EDICAO = {
    "POST /catalogo/itens",
    "PATCH /catalogo/{item_id}",
    "POST /catalogo/{item_id}/arquivar",
    "POST /catalogo/{item_id}/preco",
    "POST /catalogo/{item_id}/classificacao",
    "POST /alertas/{alerta_id}/aplicar",
    "POST /nfe/importar",
    "POST /clientes",
    "PATCH /clientes/{cnpj_cliente}",
    "POST /clientes/{cnpj_cliente}/excluir",
}
ADMINISTRACAO = {"POST /empresas", "PATCH /empresas/{cnpj}", "POST /empresas/{cnpj}/excluir"}
# Não gravam no banco da organização: cálculos, a explicação e o chat (só leem), os espaços de avaliação, a
# restauração da demonstração (403 com a sessão) e a própria conta (cada pessoa só mexe na dela).
FORA_DO_BANCO_DA_ORGANIZACAO = {
    "POST /carrinho/calcular",
    "POST /item/preco-alvo",
    "POST /regime/comparar",
    "POST /explicar",
    "POST /chat",
    "POST /espacos",
    "POST /demo/restaurar",
    "POST /contas",
    "POST /contas/ativar",
    "POST /sessoes",
    "POST /sessoes/codigo",
    "DELETE /sessoes/atual",
    "DELETE /sessoes",
    "POST /conta/excluir",
    "POST /conta/dados",
}


@pytest.fixture
def real(motores_falsos, monkeypatch: pytest.MonkeyPatch) -> Relogio:
    """Modo real (motores falsos), a demonstração restaurada e o relógio das contas (como em test_clientes_b2b)."""
    r = Relogio()
    monkeypatch.setattr(rotas_contas, "agora_utc", r)
    monkeypatch.setattr(dependencias, "agora_utc", r)
    assert TestClient(app).post("/demo/restaurar").status_code == 200
    return r


def _sql(comando: str, *valores: object) -> Any:
    with dependencias.contas(configuracao()).banco.transacao(escrita=True) as conexao:
        return conexao.execute(comando, valores).fetchone()


def _organizacao(c: TestClient) -> str:
    return str(c.get("/conta").json()["organizacao"]["id"])


def membro_na_organizacao(dona: TestClient, relogio: Relogio) -> TestClient:
    """A Bia, com a conta dela, entra como membro na organização da dona e a sessão dela passa a valer lá."""
    org = _organizacao(dona)
    bia = com_conta(relogio, BIA)
    id_bia = _sql("SELECT id FROM usuarios WHERE email = ?", BIA)[0]
    _sql(
        "INSERT INTO membros (organizacao_id, usuario_id, papel, desde) VALUES (?, ?, 'membro', ?)",
        org,
        id_bia,
        relogio.agora.isoformat(),
    )
    _sql("UPDATE sessoes SET organizacao_id = ? WHERE usuario_id = ?", org, id_bia)
    conta = bia.get("/conta").json()["organizacao"]
    assert (conta["id"], conta["papel"]) == (org, "membro")
    return bia


def _papel(email: str, papel: str) -> None:
    _sql("UPDATE membros SET papel = ? WHERE usuario_id = (SELECT id FROM usuarios WHERE email = ?)", papel, email)


def _ok(r: Response, status: int = 200) -> dict[str, Any]:
    assert r.status_code == status, r.text
    return dict(r.json())


# -- a matriz -----------------------------------------------------------------------------------------------


def test_as_listas_de_papeis() -> None:
    """Quem pode, nunca quem não pode: o contador do 3c não muda nada até entrar numa lista de propósito."""
    assert PAPEIS_QUE_EDITAM == {"dono", "membro"}
    assert PAPEIS_QUE_ADMINISTRAM == {"dono"}


def test_o_membro_muda_os_dados_da_empresa(real) -> None:
    ana = com_conta(real)
    cadastrar(ana)
    bia = membro_na_organizacao(ana, real)

    item = criar_item(bia)["item"]
    assert importar(bia, compra_anterior_mais_barata()).status_code == 200
    assert importar(bia, nota_da_empresa()).status_code == 200
    alerta = bia.get(f"/alertas?cnpj={NUMERICO}").json()["alertas"][0]
    _ok(bia.post(f"/alertas/{alerta['id']}/aplicar"))
    _ok(bia.post(f"/catalogo/{item['id']}/preco", json={"cnpj": NUMERICO, "valorUnitario": "5.10"}))
    _ok(bia.patch(f"/catalogo/{item['id']}", json={"cnpj": NUMERICO, "descricao": "Chocolate 90 g (membro)"}))
    arroz = criar_item(bia, ncm="10063021", cClassTrib="200003", descricao="Arroz 5 kg", codigoFornecedor="ARZ")
    corrigir = {"cnpj": NUMERICO, "cClassTrib": "000001"}
    _ok(bia.post(f"/catalogo/{arroz['item']['id']}/classificacao", json=corrigir))
    _ok(bia.post("/clientes", json=corpo_cliente([item["id"]])), 201)
    _ok(bia.patch(f"/clientes/{CLIENTE}", json={"cnpj": NUMERICO, "razaoSocial": "Mercado do Bairro (membro)"}))
    _ok(bia.post(f"/clientes/{CLIENTE}/excluir", json={"cnpj": NUMERICO}))
    _ok(bia.post(f"/catalogo/{arroz['item']['id']}/arquivar", json={"cnpj": NUMERICO}))

    # A dona vê o que o membro mudou: é a mesma empresa, no mesmo banco.
    catalogo = ana.get(f"/catalogo?cnpj={NUMERICO}").json()
    assert [(i["descricao"], i["precoVenda"]) for i in catalogo["itens"]] == [("Chocolate 90 g (membro)", "5.10")]
    assert catalogo["clientesB2B"] == []


def test_o_membro_le_mas_nao_cadastra_configura_nem_exclui_a_empresa(real) -> None:
    ana = com_conta(real)
    cadastrar(ana)
    bia = membro_na_organizacao(ana, real)
    assert bia.get(f"/empresas/{NUMERICO}").status_code == 200
    assert bia.get(f"/catalogo?cnpj={NUMERICO}").status_code == 200
    assert bia.get(f"/notas?cnpj={NUMERICO}").status_code == 200

    r = bia.post("/empresas", json=corpo_empresa("12ABC34501DE35"))
    assert (r.status_code, r.json()["detail"]) == (403, RECUSA_CONFIGURAR)
    r = bia.patch(f"/empresas/{NUMERICO}", json={"razaoSocial": "Tomada pelo membro"})
    assert (r.status_code, r.json()["detail"]) == (403, RECUSA_CONFIGURAR)
    r = bia.post(f"/empresas/{NUMERICO}/excluir", json={"senha": SENHA, "cnpjConfirmacao": NUMERICO})
    assert (r.status_code, r.json()["detail"]) == (403, RECUSA_EXCLUIR)
    # O 403 vem antes da empresa e da senha: não diz se o CNPJ existe nem gasta uma tentativa.
    r = bia.patch("/empresas/12ABC34501DE35", json={"razaoSocial": "Outra"})
    assert (r.status_code, r.json()["detail"]) == (403, RECUSA_CONFIGURAR)
    assert _sql("SELECT count(*) FROM tentativas")[0] == 0

    assert ana.get(f"/empresas/{NUMERICO}").json()["empresa"]["razaoSocial"] == "Mercadinho da Ana Ltda"
    assert ana.get("/conta").json()["empresas"] == [NUMERICO]


def test_o_papel_vale_a_cada_pedido(real) -> None:
    """A sessão lê o papel no banco a cada pedido: rebaixar, promover ou tirar alguém vale na hora, sem sair."""
    ana = com_conta(real)
    cadastrar(ana)
    bia = membro_na_organizacao(ana, real)
    mudar = {"razaoSocial": "Mercadinho da Ana e da Bia Ltda"}
    assert bia.patch(f"/empresas/{NUMERICO}", json=mudar).status_code == 403
    _papel(BIA, "dono")
    _ok(bia.patch(f"/empresas/{NUMERICO}", json=mudar))
    _papel(BIA, "membro")
    assert bia.patch(f"/empresas/{NUMERICO}", json=mudar).status_code == 403

    # Fora da organização, a sessão deixa de valer nela: 401, e o cookie sai.
    _sql("DELETE FROM membros WHERE usuario_id = (SELECT id FROM usuarios WHERE email = ?) AND papel = 'membro'", BIA)
    r = bia.get(f"/catalogo?cnpj={NUMERICO}")
    assert r.status_code == 401
    assert ana.get(f"/catalogo?cnpj={NUMERICO}").status_code == 200


def _pedidos_de_edicao(item_id: str) -> dict[str, Callable[[TestClient], Response]]:
    cnpj = {"cnpj": NUMERICO}
    return {
        "POST /catalogo/itens": lambda c: c.post("/catalogo/itens", json=corpo_item(codigoFornecedor="OUTRO")),
        "PATCH /catalogo/{item_id}": lambda c: c.patch(f"/catalogo/{item_id}", json=cnpj | {"descricao": "Nova"}),
        "POST /catalogo/{item_id}/arquivar": lambda c: c.post(f"/catalogo/{item_id}/arquivar", json=cnpj),
        "POST /catalogo/{item_id}/preco": lambda c: c.post(
            f"/catalogo/{item_id}/preco", json=cnpj | {"valorUnitario": "9"}
        ),
        "POST /catalogo/{item_id}/classificacao": lambda c: c.post(
            f"/catalogo/{item_id}/classificacao", json=cnpj | {"cClassTrib": "000001"}
        ),
        "POST /alertas/{alerta_id}/aplicar": lambda c: c.post(f"/alertas/{ALERTA_QUALQUER}/aplicar"),
        "POST /nfe/importar": lambda c: importar(c, nota_da_empresa()),
        "POST /clientes": lambda c: c.post("/clientes", json=corpo_cliente([item_id])),
        "PATCH /clientes/{cnpj_cliente}": lambda c: c.patch(f"/clientes/{CLIENTE}", json=cnpj | {"razaoSocial": "X"}),
        "POST /clientes/{cnpj_cliente}/excluir": lambda c: c.post(f"/clientes/{CLIENTE}/excluir", json=cnpj),
    }


def test_papel_fora_da_lista_nao_muda_nada(real, monkeypatch: pytest.MonkeyPatch) -> None:
    """Com a lista de edição vazia, toda rota de edição recusa a própria dona com 403, antes de olhar o pedido, e
    nada muda. Prova que cada rota da lista EDICAO confere o papel (um papel novo do 3c cairia aqui)."""
    ana = com_conta(real)
    cadastrar(ana)
    item_id = criar_item(ana)["item"]["id"]
    antes = ana.get(f"/catalogo?cnpj={NUMERICO}").json()
    monkeypatch.setattr(dependencias, "PAPEIS_QUE_EDITAM", frozenset())
    pedidos = _pedidos_de_edicao(item_id)
    assert set(pedidos) == EDICAO
    for rota, pedir in pedidos.items():
        r = pedir(ana)
        assert (r.status_code, r.json()["detail"]) == (403, RECUSA_EDICAO), rota
    assert ana.get(f"/catalogo?cnpj={NUMERICO}").json() == antes
    assert ana.get(f"/notas?cnpj={NUMERICO}").json()["notas"] == []
    # A demonstração e os espaços não têm papel: o token e o espaço continuam sendo a proteção deles.
    espaco = TestClient(app).post("/espacos").json()["id"]
    r = TestClient(app).post(f"/alertas/{ALERTA_QUALQUER}/aplicar", headers={"X-ContaAI-Espaco": espaco})
    assert r.status_code == 404


def test_papel_fora_da_lista_nao_administra(real, monkeypatch: pytest.MonkeyPatch) -> None:
    ana = com_conta(real)
    cadastrar(ana)
    monkeypatch.setattr(rotas_empresa, "PAPEIS_QUE_ADMINISTRAM", frozenset())
    assert ana.patch(f"/empresas/{NUMERICO}", json={"razaoSocial": "Nova"}).status_code == 403
    assert ana.post("/empresas", json=corpo_empresa("12ABC34501DE35")).status_code == 403
    corpo = {"senha": SENHA, "cnpjConfirmacao": NUMERICO}
    assert ana.post(f"/empresas/{NUMERICO}/excluir", json=corpo).status_code == 403
    assert ana.get(f"/empresas/{NUMERICO}").status_code == 200


# -- inventário e contrato ----------------------------------------------------------------------------------


def _rotas(rotas: Iterable[BaseRoute], prefixo: str = "") -> Iterator[tuple[str, APIRoute]]:
    """Todas as rotas da API, com o prefixo de cada inclusão (no FastAPI 0.165, as de um APIRouter incluído ficam
    dentro de um `_IncludedRouter`, como em app.api.registro._modelos)."""
    for rota in rotas:
        original = getattr(rota, "original_router", None)
        if original is not None:
            contexto = getattr(rota, "include_context", None)
            yield from _rotas(original.routes, prefixo + str(getattr(contexto, "prefix", "") or ""))
        elif isinstance(rota, APIRoute):
            yield prefixo, rota


def _rotas_que_mudam() -> set[str]:
    achadas = {
        f"{metodo} {prefixo}{rota.path}"
        for prefixo, rota in _rotas(app.router.routes)
        for metodo in rota.methods
        if metodo in METODOS_INSEGUROS
    }
    assert achadas, "nenhuma rota achada: a estrutura das rotas do FastAPI mudou"
    return achadas


def test_toda_rota_que_muda_o_estado_esta_classificada() -> None:
    assert not EDICAO & ADMINISTRACAO and not (EDICAO | ADMINISTRACAO) & FORA_DO_BANCO_DA_ORGANIZACAO
    assert _rotas_que_mudam() == EDICAO | ADMINISTRACAO | FORA_DO_BANCO_DA_ORGANIZACAO


def test_o_contrato_declara_o_403_de_cada_papel_e_o_do_csrf() -> None:
    caminhos = app.openapi()["paths"]

    def recusa(rota: str) -> str | None:
        metodo, caminho = rota.split(" ", 1)
        resposta = caminhos[caminho][metodo.lower()]["responses"].get("403")
        return None if resposta is None else str(resposta["description"])

    for rota in EDICAO:
        descricao = recusa(rota)
        assert descricao is not None and "papel" in descricao and "contra CSRF" in descricao, rota
    for rota in ADMINISTRACAO:
        descricao = recusa(rota)
        assert descricao is not None and "Só o dono" in descricao and "contra CSRF" in descricao, rota
    for rota in FORA_DO_BANCO_DA_ORGANIZACAO:
        descricao = recusa(rota)
        assert descricao is not None and "contra CSRF" in descricao, rota  # o DELETE das sessões também
    # Ler a empresa não tem 403: todo integrante lê, e o GET não passa pela defesa contra CSRF.
    assert recusa("GET /empresas/{cnpj}") is None
