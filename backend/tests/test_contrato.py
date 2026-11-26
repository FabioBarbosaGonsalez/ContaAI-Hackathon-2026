"""Contrato da API e mocks (E0-05): as rotas do plano respondem no formato do contrato."""

from __future__ import annotations

import importlib.util
import os
import re
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import mocks
from app.api.rotas.notas import TIPOS_XML
from app.config import Configuracao, configuracao
from app.contrato import (
    AVISO_LEGAL,
    AlertasResposta,
    BuscaNcmResposta,
    CarrinhoResposta,
    CatalogoResposta,
    ChatResposta,
    ExplicarResposta,
    NfeImportarResposta,
    PainelContadorResposta,
    PrecoAlvoResposta,
    Regime,
    RegimeCompararResposta,
    SaudeResposta,
)
from app.dados_demo import PASTA_DEMO, ItemCatalogo, carregar_distribuidora
from app.main import app
from tests.apoio_regime import assert_comparacao_fecha

BACKEND = Path(__file__).resolve().parents[1]
RAIZ = BACKEND.parent
DEMO = carregar_distribuidora()
cliente = TestClient(app)

OPERACAO = {
    "data": "2027-03-16",
    "uf": "RS",
    "municipio": 4314902,
    "aliquotasNominais": {
        "cbs": "8.8",
        "ibsEstadual": "0.05",
        "ibsMunicipal": "0.05",
        "impostoSeletivoAdValorem": "10.0",
    },
    "premissasDas": {"anexo": "I", "cAtivSN": "01", "pCBSSN": "1.1612", "pIBSSN": "0.0129"},
}


def item_base(cat: ItemCatalogo) -> dict:
    return {
        "id": cat.id,
        "descricao": cat.descricao,
        "ncm": cat.ncm,
        "cst": cat.cst,
        "cClassTrib": cat.cClassTrib,
        "impostoSeletivo": cat.impostoSeletivo.model_dump(exclude={"motivo"}, mode="json")
        if cat.impostoSeletivo
        else None,
        "unidade": cat.unidade,
    }


def item_entrada(cat: ItemCatalogo) -> dict:
    return {**item_base(cat), "quantidade": "100", "valorUnitario": str(cat.precoVenda)}


@pytest.fixture
def configurar() -> Iterator:
    def aplicar(**campos: object) -> None:
        app.dependency_overrides[configuracao] = lambda: Configuracao(**campos)

    yield aplicar
    app.dependency_overrides.clear()


def assert_mock(resposta) -> None:
    assert resposta.status_code == 200, resposta.text
    assert resposta.headers["X-ContaAI-Mock"] == "1"


def test_mocks_validam_no_contrato_e_cobrem_a_demo() -> None:
    m = mocks.carregar()
    assert set(m.carrinho) == set(Regime) and set(m.preco_alvo) == set(Regime)
    assert set(m.explicar) == {i.id for i in DEMO.catalogo}
    assert all(set(por_regime) == set(Regime) for por_regime in m.explicar.values())
    assert {"REG-011", "VSN-047"} <= set(m.erros)
    assert {"arroz", "cerveja", "chocolate", "carne"} == set(m.busca_ncm)


@pytest.mark.parametrize("regime", list(Regime))
def test_carrinho_calcular(regime: Regime) -> None:
    r = cliente.post(
        "/carrinho/calcular", json={**OPERACAO, "regime": regime, "itens": [item_entrada(c) for c in DEMO.catalogo]}
    )
    assert_mock(r)
    corpo = CarrinhoResposta.model_validate(r.json())
    assert corpo.regime == regime and corpo.simulado and corpo.avisoSimulacao and corpo.premissas
    calculados = [i for i in corpo.itens if i.precoCliente is not None]
    assert corpo.totais.itensCalculados == len(calculados) and corpo.totais.itensComErro == 1
    assert corpo.totais.valorProdutos == sum(i.valorProdutos for i in calculados)
    assert [e.codigo for e in next(i for i in corpo.itens if i.id == "carne-bovina-kg").erros] in (
        ["REG-011"],
        ["VSN-047"],
    )


def test_carrinho_rejeita_2027_sem_premissas() -> None:
    sem = {k: v for k, v in OPERACAO.items() if k != "aliquotasNominais"}
    r = cliente.post(
        "/carrinho/calcular", json={**sem, "regime": "simples_hibrido", "itens": [item_entrada(DEMO.catalogo[0])]}
    )
    assert r.status_code == 422 and "aliquotasNominais" in r.text


@pytest.mark.parametrize("regime", list(Regime))
def test_preco_alvo(regime: Regime) -> None:
    cerveja = DEMO.item("cerveja-lata")
    pedido = {**OPERACAO, "regime": regime, "item": item_base(cerveja), "custoUnitario": "3.05", "margemAlvoPct": "15"}
    r = cliente.post("/item/preco-alvo", json=pedido)
    assert_mock(r)
    corpo = PrecoAlvoResposta.model_validate(r.json())
    assert corpo.chamadas <= 3 and corpo.metodo == "afim"
    assert corpo.margemObtidaPct >= corpo.margemAlvoPct


def test_regime_comparar_fecha_as_contas() -> None:
    pedido = {
        **OPERACAO,
        "cliente": {"nome": "Mercado Bom Preço Ltda (fictício)", "regime": "regime_regular"},
        "itens": [
            {**item_entrada(DEMO.item(i)), "custoUnitario": "1.00"}
            for i in ("arroz-5kg", "cerveja-lata", "chocolate-barra")
        ],
    }
    r = cliente.post("/regime/comparar", json=pedido)
    assert_mock(r)
    c = RegimeCompararResposta.model_validate(r.json())
    assert_comparacao_fecha(c)


def test_nfe_importar_gera_o_alerta_da_cerveja() -> None:
    xml = (PASTA_DEMO / "notas" / "nfe-compra-2.xml").read_bytes()
    r = cliente.post("/nfe/importar", files={"arquivo": ("nfe-compra-2.xml", xml, "application/xml")})
    assert_mock(r)
    corpo = NfeImportarResposta.model_validate(r.json())
    assert corpo.nota.temGrupoIbsCbs and [a.itemId for a in corpo.alertas] == ["cerveja-lata"]
    alerta = corpo.alertas[0]
    assert alerta.margemDepoisPct < alerta.margemAlvoPct < alerta.margemAntesPct
    assert alerta.precoSugerido > alerta.precoAtual


def test_nfe_importar_recusa_arquivo_grande(configurar) -> None:
    configurar(tamanho_max_nfe_bytes=10)
    r = cliente.post("/nfe/importar", files={"arquivo": ("nota.xml", b"<x>" + b"a" * 100 + b"</x>", "application/xml")})
    assert r.status_code == 413


def test_alertas() -> None:
    r = cliente.get("/alertas")
    assert_mock(r)
    assert r.json()["alertas"][0]["itemId"] == "cerveja-lata"


def test_catalogo_e_painel_do_contador_no_mock() -> None:
    """Um fato, uma variável (inventário da E5): o preço atual do alerta é o do catálogo, e o custo novo
    do alerta é o custo atual do catálogo."""
    r = cliente.get("/catalogo?cnpj=36817420000113")
    assert_mock(r)
    cat = CatalogoResposta.model_validate(r.json())
    cerveja = next(i for i in cat.itens if i.id == "cerveja-lata")
    alerta = next(
        a for a in AlertasResposta.model_validate(cliente.get("/alertas").json()).alertas if a.itemId == "cerveja-lata"
    )
    assert cerveja.precoVenda == alerta.precoAtual and cerveja.custoAtual.custoUnitario == alerta.custoNovo
    painel = cliente.get("/contador/painel")
    assert_mock(painel)
    corpo = PainelContadorResposta.model_validate(painel.json())
    assert len(corpo.empresas) == 3 and corpo.empresas[0].alertasAbertos >= corpo.empresas[-1].alertasAbertos


def test_busca_ncm() -> None:
    r = cliente.get("/busca/ncm", params={"q": "Arroz 5 kg"})
    assert_mock(r)
    corpo = BuscaNcmResposta.model_validate(r.json())
    especificas = {c.cClassTrib for c in corpo.candidatos[0].classificacoes if c.especificaDoProduto}
    assert "200003" in especificas and corpo.consulta == "Arroz 5 kg"
    assert cliente.get("/busca/ncm", params={"q": "martelo"}).json()["candidatos"] == []


def test_explicar() -> None:
    r = cliente.get("/explicar/cerveja-lata", params={"regime": "simples_hibrido"})
    assert_mock(r)
    corpo = ExplicarResposta.model_validate(r.json())
    assert corpo.memoria and corpo.fundamentacoes and corpo.aviso
    assert cliente.get("/explicar/nao-existe").status_code == 404


def test_erros() -> None:
    r = cliente.get("/erros/REG-011")
    assert_mock(r)
    assert r.json()["titulo"] == "NCM não vinculada"
    assert cliente.get("/erros/REG-999").status_code == 404
    assert cliente.get("/erros/qualquer-coisa").status_code == 422


def test_chat_propoe_e_nao_calcula() -> None:
    r = cliente.post("/chat", json={"mensagens": [{"papel": "usuario", "texto": "Vendo arroz, cerveja e chocolate"}]})
    assert_mock(r)
    corpo = ChatResposta.model_validate(r.json())
    assert all(a.tipo == "confirmar_classificacao" for a in corpo.acoesPropostas)
    assert not re.search(r"R\$|%", corpo.resposta)  # P2: o texto não traz valores


def test_cors_so_libera_o_frontend_configurado() -> None:
    estranho = cliente.get("/alertas", headers={"Origin": "https://exemplo-malicioso.test"})
    assert "access-control-allow-origin" not in estranho.headers
    local = cliente.get("/alertas", headers={"Origin": "http://localhost:3000"})
    assert local.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_modo_mock_nao_muda_o_estado(configurar) -> None:
    """Aplicar preço e restaurar a demo só existem no modo real: o mock nunca finge uma gravação."""
    configurar(modo="mock")
    assert cliente.post("/alertas/alerta-0123456789abcdef/aplicar").status_code == 501
    assert cliente.post("/demo/restaurar").status_code == 501


def test_saude_sem_motores_fica_degradada(configurar) -> None:
    configurar(motor_rr_url="http://127.0.0.1:9/api", motor_sn_url="http://127.0.0.1:9/api", timeout_motores_s=0.5)
    corpo = SaudeResposta.model_validate(cliente.get("/saude").json())
    assert corpo.status == "degradado" and not any(m.ok for m in corpo.motores)
    assert all(m.detalhe == "Motor indisponível." for m in corpo.motores)  # sem expor URL interna


@pytest.mark.golden
def test_saude_com_os_motores() -> None:
    corpo = SaudeResposta.model_validate(cliente.get("/saude").json())
    assert corpo.status == "ok" and all(m.ok and m.coerente for m in corpo.motores)


def test_versoes_da_configuracao_sao_as_dos_dockerfiles() -> None:
    def arg(dockerfile: str, nome: str) -> str:
        texto = (RAIZ / "motores" / dockerfile / "Dockerfile").read_text(encoding="utf-8")
        return re.search(rf"^ARG {nome}=(\S+)$", texto, re.MULTILINE).group(1)

    cfg = Configuracao()
    assert cfg.versao_rr == arg("regime-regular", "RR_TAG")
    assert cfg.versao_sn == arg("simples-nacional", "SN_TAG")


def test_openapi_exportado_esta_atualizado() -> None:
    spec = importlib.util.spec_from_file_location("exportar_openapi", BACKEND / "scripts" / "exportar_openapi.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    arquivo = RAIZ / "docs" / "contrato" / "openapi.json"
    assert arquivo.read_text(encoding="utf-8") == modulo.gerar(), (
        "O contrato mudou: rode 'uv run python scripts/exportar_openapi.py' e revise a diferença."
    )


def test_aviso_legal_da_tela_e_o_do_backend() -> None:
    """P9: o rodapé da tela mostra o mesmo aviso legal da API (frontend/src/shell/aviso.ts)."""
    arquivo = RAIZ / "frontend" / "src" / "shell" / "aviso.ts"
    achado = re.search(r"AVISO_LEGAL\s*=\s*'([^']+)'", arquivo.read_text(encoding="utf-8"))
    assert achado is not None, "AVISO_LEGAL não encontrado em frontend/src/shell/aviso.ts"
    assert achado.group(1) == AVISO_LEGAL, "O aviso legal da tela divergiu de AVISO_LEGAL em app/contrato.py."


def test_limite_da_nota_na_tela_e_o_do_backend() -> None:
    """A tela confere o tamanho do XML antes de enviar (frontend/src/api/upload.ts) com o mesmo limite padrão."""
    arquivo = RAIZ / "frontend" / "src" / "api" / "upload.ts"
    achado = re.search(r"TAMANHO_MAX_NOTA_BYTES\s*=\s*([\d_]+);", arquivo.read_text(encoding="utf-8"))
    assert achado is not None, "TAMANHO_MAX_NOTA_BYTES não encontrado em frontend/src/api/upload.ts"
    padrao = Configuracao.model_fields["tamanho_max_nfe_bytes"].default
    assert int(achado.group(1).replace("_", "")) == padrao

    tipos = re.search(r"TIPOS_ACEITOS = new Set\(\[([^\]]*)\]\)", arquivo.read_text(encoding="utf-8"))
    assert tipos is not None, "TIPOS_ACEITOS não encontrado em frontend/src/api/upload.ts"
    assert set(re.findall(r"'([^']*)'", tipos.group(1))) == TIPOS_XML


@pytest.mark.golden
def test_mocks_sao_reproduziveis_pelos_motores(tmp_path: Path) -> None:
    env = {**os.environ, "CONTAAI_SAIDA_MOCKS": str(tmp_path), "PYTHONIOENCODING": "utf-8"}
    subprocess.run([sys.executable, "scripts/gerar_mocks.py"], cwd=BACKEND, env=env, check=True, capture_output=True)
    for arquivo in sorted(mocks.PASTA.glob("*.json")):
        assert (tmp_path / arquivo.name).read_bytes() == arquivo.read_bytes(), arquivo.name
