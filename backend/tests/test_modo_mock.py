"""O modo mock rota por rota (C3-B, etapa 10): cada rota do contrato tem um lugar, e o mock nunca grava.

Três grupos, que juntos cobrem o contrato inteiro:

- servidas pelo mock: respondem com os arquivos de `app/mocks/` e o cabeçalho `X-ContaAI-Mock: 1`
  (o conteúdo é conferido em `test_contrato.py`);
- fixas: não dependem do modo (a saúde, os tipos de problema e as premissas da simulação);
- só no modo real: mudam o estado, dependem de uma conta ou dos motores, e respondem 501 no mock.

Uma rota nova fica fora dos três grupos e o inventário falha até alguém decidir onde ela entra.
"""

from __future__ import annotations

import re
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.test_agente import contexto, item
from tests.test_clientes_b2b import CLIENTE, corpo_cliente
from tests.test_empresa_propria import NUMERICO, corpo_empresa, corpo_item

cliente = TestClient(app)
SENHA = "uma senha longa o bastante"

SERVIDAS_PELO_MOCK = {
    ("POST", "/carrinho/calcular"),
    ("POST", "/item/preco-alvo"),
    ("POST", "/regime/comparar"),
    ("POST", "/nfe/importar"),
    ("GET", "/alertas"),
    ("GET", "/catalogo"),
    ("GET", "/notas"),
    ("GET", "/contador/painel"),
    ("GET", "/busca/ncm"),
    ("GET", "/explicar/{item_id}"),
    ("GET", "/erros/{codigo}"),
    ("POST", "/chat"),
}

FIXAS = {
    ("GET", "/saude"),
    ("GET", "/problemas/{nome}"),
    ("GET", "/cenarios/presets"),
}

# O pedido válido de cada rota: o 501 vem depois da validação do FastAPI, então um corpo inválido daria 422
# e o teste não provaria nada. Rota nova sem pedido aqui faz o teste falhar.
SO_NO_MODO_REAL: dict[tuple[str, str], dict[str, Any]] = {
    ("POST", "/alertas/{alerta_id}/aplicar"): {"url": "/alertas/alerta-0123456789abcdef/aplicar"},
    ("POST", "/catalogo/{item_id}/preco"): {
        "url": "/catalogo/arroz-5kg/preco",
        "json": {"cnpj": NUMERICO, "valorUnitario": "27.90"},
    },
    ("POST", "/catalogo/{item_id}/classificacao"): {
        "url": "/catalogo/arroz-5kg/classificacao",
        "json": {"cnpj": NUMERICO, "cClassTrib": "000001"},
    },
    ("GET", "/referencias/ufs"): {"url": "/referencias/ufs"},
    ("GET", "/referencias/municipios"): {"url": "/referencias/municipios?uf=RS"},
    ("GET", "/referencias/atividades"): {"url": "/referencias/atividades"},
    ("POST", "/empresas"): {"url": "/empresas", "json": corpo_empresa()},
    ("GET", "/empresas/{cnpj}"): {"url": f"/empresas/{NUMERICO}"},
    ("PATCH", "/empresas/{cnpj}"): {"url": f"/empresas/{NUMERICO}", "json": {"razaoSocial": "Mercadinho Ltda"}},
    ("POST", "/empresas/{cnpj}/excluir"): {
        "url": f"/empresas/{NUMERICO}/excluir",
        "json": {"senha": SENHA, "cnpjConfirmacao": NUMERICO},
    },
    ("POST", "/catalogo/itens"): {"url": "/catalogo/itens", "json": corpo_item()},
    ("PATCH", "/catalogo/{item_id}"): {
        "url": "/catalogo/arroz-5kg",
        "json": {"cnpj": NUMERICO, "descricao": "Arroz 5 kg"},
    },
    ("POST", "/catalogo/{item_id}/arquivar"): {"url": "/catalogo/arroz-5kg/arquivar", "json": {"cnpj": NUMERICO}},
    ("POST", "/clientes"): {"url": "/clientes", "json": corpo_cliente(["arroz-5kg"])},
    ("PATCH", "/clientes/{cnpj_cliente}"): {
        "url": f"/clientes/{CLIENTE}",
        "json": {"cnpj": NUMERICO, "razaoSocial": "Mercado Ltda"},
    },
    ("POST", "/clientes/{cnpj_cliente}/excluir"): {"url": f"/clientes/{CLIENTE}/excluir", "json": {"cnpj": NUMERICO}},
    ("POST", "/espacos"): {"url": "/espacos"},
    ("GET", "/espacos/atual"): {"url": "/espacos/atual", "headers": {"X-ContaAI-Espaco": "a" * 32}},
    ("POST", "/contas"): {
        "url": "/contas",
        "json": {
            "email": "ana@exemplo.com.br",
            "senha": SENHA,
            "organizacao": "Mercadinho da Ana",
            "termosAceitos": "2026-11-26",
        },
    },
    ("POST", "/contas/ativar"): {"url": "/contas/ativar", "json": {"codigo": "123456"}},
    ("POST", "/sessoes"): {"url": "/sessoes", "json": {"email": "ana@exemplo.com.br", "senha": SENHA}},
    ("DELETE", "/sessoes"): {"url": "/sessoes"},
    ("POST", "/sessoes/codigo"): {"url": "/sessoes/codigo", "json": {"codigo": "123456"}},
    ("GET", "/conta"): {"url": "/conta"},
    ("DELETE", "/sessoes/atual"): {"url": "/sessoes/atual"},
    ("POST", "/conta/excluir"): {"url": "/conta/excluir", "json": {"senha": SENHA}},
    ("POST", "/conta/dados"): {"url": "/conta/dados", "json": {"senha": SENHA}},
    ("POST", "/explicar"): {
        "url": "/explicar",
        "json": {k: v for k, v in contexto(itens=["arroz-5kg"]).items() if k != "itens"} | {"item": item("arroz-5kg")},
    },
    ("POST", "/demo/restaurar"): {"url": "/demo/restaurar"},
}


def operacoes() -> set[tuple[str, str]]:
    return {(metodo.upper(), caminho) for caminho, ops in app.openapi()["paths"].items() for metodo in ops}


def test_toda_rota_do_contrato_tem_um_lugar_no_modo_mock() -> None:
    grupos = [SERVIDAS_PELO_MOCK, FIXAS, set(SO_NO_MODO_REAL)]
    assert not (grupos[0] & grupos[1] or grupos[0] & grupos[2] or grupos[1] & grupos[2])
    sobra = operacoes() - set().union(*grupos)
    assert not sobra, f"Rota nova sem lugar no modo mock: {sorted(sobra)}"
    assert not set().union(*grupos) - operacoes(), "O inventário lista uma rota que não existe mais."


def test_so_as_rotas_do_modo_real_declaram_o_501() -> None:
    declaram = {
        (metodo.upper(), caminho)
        for caminho, ops in app.openapi()["paths"].items()
        for metodo, op in ops.items()
        if "501" in op["responses"]
    }
    assert declaram == set(SO_NO_MODO_REAL)


@pytest.mark.parametrize("operacao", sorted(SO_NO_MODO_REAL), ids=lambda o: f"{o[0]} {o[1]}")
def test_no_modo_mock_a_rota_do_modo_real_responde_501_sem_gravar(operacao: tuple[str, str]) -> None:
    pedido = SO_NO_MODO_REAL[operacao]
    r = cliente.request(operacao[0], pedido["url"], json=pedido.get("json"), headers=pedido.get("headers"))
    assert r.status_code == 501, r.text
    assert "X-ContaAI-Mock" not in r.headers and "set-cookie" not in r.headers
    assert r.headers["content-type"].startswith("application/problem+json")
    assert "modo real" in r.json()["detail"]
    # O pedido montado bate com o caminho da rota (um erro de digitação aqui testaria outra rota).
    modelo = re.sub(r"\{[^}]+\}", "[^/]+", operacao[1])
    assert re.fullmatch(modelo, pedido["url"].split("?")[0])


def test_nenhuma_rota_que_muda_o_estado_responde_2xx_no_mock_sem_o_marcador() -> None:
    """O mock nunca finge uma gravação: um método inseguro ou é do mock (marcado) ou é do modo real."""
    inseguras = {op for op in operacoes() if op[0] in {"POST", "PATCH", "PUT", "DELETE"}}
    assert inseguras <= SERVIDAS_PELO_MOCK | set(SO_NO_MODO_REAL)
    assert {op for op in inseguras if op in SERVIDAS_PELO_MOCK} == {
        ("POST", "/carrinho/calcular"),
        ("POST", "/item/preco-alvo"),
        ("POST", "/regime/comparar"),
        ("POST", "/nfe/importar"),
        ("POST", "/chat"),
    }  # calculam ou leem, sem gravar: a importação no mock devolve o recibo do mock (test_contrato.py)
