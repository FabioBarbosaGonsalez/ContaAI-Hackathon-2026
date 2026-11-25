"""Contrato da tela (ADR 0011) contra os motores em execução (marcador golden: uv run pytest -m golden).

Conferido em 2026-11-25 com os motores RR 1.7.2 e SN 1.0.2:
- a carne bovina da demo (NCM 02013000, cClassTrib 200035) volta INCONSISTENCIA_ENTRADA com REG-011;
- as candidatas oficiais para a NCM são 200003 (alimentação humana, CST 200) e 000001 (CST 000);
- corrigida para 200003 pela rota da tela, ela calcula: CALCULO_SIMULADO no híbrido e CALCULADO no
  tradicional (critério M3 do plano: "o item volta a CALCULADO depois da confirmação").
- a margem da cerveja que a tela refaz só com o catálogo é a do alerta da nota 2 (11,19%).
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.config import Configuracao, configuracao
from app.contrato import AlertasResposta, BuscaNcmResposta, CarrinhoResposta, CatalogoResposta, ItemCatalogoEstado
from app.dados_demo import PASTA_DEMO
from app.main import app

pytestmark = pytest.mark.golden

cliente = TestClient(app)
SERRA_AZUL = "36817420000113"


@pytest.fixture(autouse=True)
def estado_restaurado():
    app.dependency_overrides[configuracao] = lambda: Configuracao(modo="real")
    assert cliente.post("/demo/restaurar").status_code == 200
    yield
    app.dependency_overrides.clear()


def catalogo() -> CatalogoResposta:
    return CatalogoResposta.model_validate(cliente.get("/catalogo", params={"cnpj": SERRA_AZUL}).json())


def calcular(cat: CatalogoResposta, i: ItemCatalogoEstado, regime: str) -> CarrinhoResposta:
    """O carrinho como a tela o monta: só com o que o catálogo devolveu."""
    entrada = i.model_dump(
        mode="json", include={"id", "descricao", "ncm", "cst", "cClassTrib", "impostoSeletivo", "unidade"}
    ) | {"quantidade": str(cat.loteReferencia), "valorUnitario": str(i.precoVenda)}
    if i.custoAtual is not None:
        entrada["custoUnitario"] = str(i.custoAtual.custoUnitario)
        if i.custoAtual.creditoCompraUnitario is not None:
            entrada["creditoCompraUnitario"] = str(i.custoAtual.creditoCompraUnitario)
    corpo = cat.cenario.operacao.model_dump(mode="json", exclude_none=True) | {"regime": regime, "itens": [entrada]}
    r = cliente.post("/carrinho/calcular", json=corpo)
    assert r.status_code == 200, r.text
    return CarrinhoResposta.model_validate(r.json())


def test_correcao_do_reg_011_pela_tela_volta_a_calcular() -> None:
    cat = catalogo()
    carne = next(i for i in cat.itens if i.id == "carne-bovina-kg")
    antes = calcular(cat, carne, "simples_hibrido").itens[0]
    assert antes.estado.value == "INCONSISTENCIA_ENTRADA" and [e.codigo for e in antes.erros] == ["REG-011"]

    busca = cliente.get("/busca/ncm", params={"q": carne.ncm, "data": cat.cenario.operacao.data.isoformat()})
    candidatas = BuscaNcmResposta.model_validate(busca.json()).candidatos[0].classificacoes
    assert [(c.cClassTrib, c.cst) for c in candidatas] == [("200003", "200"), ("000001", "000")]

    r = cliente.post("/catalogo/carne-bovina-kg/classificacao", json={"cnpj": SERRA_AZUL, "cClassTrib": "200003"})
    assert r.status_code == 200, r.text
    cat = catalogo()
    carne = next(i for i in cat.itens if i.id == "carne-bovina-kg")
    assert (carne.cst, carne.cClassTrib) == ("200", "200003")
    hibrido = calcular(cat, carne, "simples_hibrido").itens[0]
    tradicional = calcular(cat, carne, "simples_tradicional").itens[0]
    assert hibrido.estado.value == "CALCULO_SIMULADO" and hibrido.erros == []
    assert tradicional.estado.value == "CALCULADO" and tradicional.erros == []


def test_margem_da_cerveja_refeita_pelo_catalogo_e_a_do_alerta() -> None:
    nota = (PASTA_DEMO / "notas" / "nfe-compra-2.xml").read_bytes()
    assert cliente.post("/nfe/importar", files={"arquivo": ("n.xml", nota, "text/xml")}).status_code == 200
    cat = catalogo()
    cerveja = next(i for i in cat.itens if i.id == "cerveja-lata")
    margem = calcular(cat, cerveja, cat.empresa.regimeAtual.value).itens[0].margemPct
    alerta = next(
        a
        for a in AlertasResposta.model_validate(cliente.get("/alertas", params={"cnpj": SERRA_AZUL}).json()).alertas
        if a.itemId == "cerveja-lata"
    )
    assert margem == alerta.margemDepoisPct == Decimal("11.19")
