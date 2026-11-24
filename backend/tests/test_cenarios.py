"""E1-04: presets de 2027, rótulo das premissas e carga atual (P6, P8)."""

from __future__ import annotations

from decimal import Decimal

from fastapi.testclient import TestClient

from app.contrato import CarrinhoResposta, PresetsResposta
from app.main import app

cliente = TestClient(app)

ITEM = {
    "id": "a",
    "descricao": "Chocolate",
    "ncm": "18063210",
    "cst": "000",
    "cClassTrib": "000001",
    "unidade": "UN",
    "quantidade": "10",
    "valorUnitario": "5.99",
}


def test_presets_so_trazem_valor_com_fonte_e_nada_como_aliquota_oficial() -> None:
    r = cliente.get("/cenarios/presets")
    assert r.status_code == 200
    corpo = PresetsResposta.model_validate(r.json())
    por_id = {p.id: p for p in corpo.presets}
    assert set(por_id) == {"exemplo-documentacao", "referencia-tcu-2027"}

    exemplo = por_id["exemplo-documentacao"]
    assert (exemplo.cbs, exemplo.ibsEstadual, exemplo.ibsMunicipal) == (
        Decimal("8.8"),
        Decimal("0.05"),
        Decimal("0.05"),
    )
    assert "não alíquotas oficiais" in exemplo.ressalva

    tcu = por_id["referencia-tcu-2027"]
    assert tcu.cbs == Decimal("11.3") and "TC 006.529/2026-7" in tcu.fonte
    assert tcu.ibsEstadual is None and tcu.ibsMunicipal is None  # sem fonte para o IBS de 2027
    assert "Senado" in tcu.ressalva and "pendente do Senado" in tcu.rotulo
    assert "Nenhum valor aqui é alíquota oficial" in corpo.aviso


def test_fonte_com_tamanho_limitado() -> None:
    corpo = {
        "data": "2027-03-16",
        "uf": "RS",
        "municipio": 4314902,
        "regime": "simples_hibrido",
        "aliquotasNominais": {"cbs": "8.8", "ibsEstadual": "0.05", "ibsMunicipal": "0.05", "fonte": "x" * 201},
        "itens": [ITEM],
    }
    assert cliente.post("/carrinho/calcular", json=corpo).status_code == 422


def test_rotulo_do_das_e_carga_atual_no_carrinho(motores_falsos) -> None:
    corpo = {
        "data": "2027-03-16",
        "uf": "RS",
        "municipio": 4314902,
        "regime": "simples_tradicional",
        "aliquotasNominais": {"cbs": "8.8", "ibsEstadual": "0.05", "ibsMunicipal": "0.05"},
        "premissasDas": {
            "anexo": "I",
            "cAtivSN": "01",
            "pCBSSN": "1.1612",
            "pIBSSN": "0.0129",
            "fonte": "Exemplo do esquema do motor SN",
        },
        "cargaAtualPct": "4.5",
        "itens": [ITEM],
    }
    r = cliente.post("/carrinho/calcular", json=corpo)
    assert r.status_code == 200, r.text
    c = CarrinhoResposta.model_validate(r.json())
    das = next(p for p in c.premissas if p.nome.startswith("Alíquotas efetivas do Simples"))
    assert das.fonte.startswith("Exemplo do esquema do motor SN.") and "apuração do Simples" in das.fonte
    assert c.cargaAtualPct == Decimal("4.5")
    carga = next(p for p in c.premissas if p.nome == "Carga atual informada")
    assert carga.valor == "4,5% do preço" and "Não entra em nenhuma conta" in carga.fonte


def test_sem_carga_atual_nao_ha_premissa(motores_falsos) -> None:
    corpo = {
        "data": "2026-11-24",
        "uf": "RS",
        "municipio": 4314902,
        "regime": "simples_hibrido",
        "itens": [ITEM],
    }
    c = CarrinhoResposta.model_validate(cliente.post("/carrinho/calcular", json=corpo).json())
    assert c.cargaAtualPct is None and "Carga atual informada" not in [p.nome for p in c.premissas]
