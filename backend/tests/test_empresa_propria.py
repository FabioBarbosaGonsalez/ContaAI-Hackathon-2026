"""Empresa própria (C3-B, ADR 0017): referências oficiais, cadastro e configurações da empresa da conta, o catálogo
editável e a saída da C3 no backend (cadastrar, importar uma nota e ver o alerta, sem tocar na demonstração)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app import cadastro
from app.api import dependencias, middlewares
from app.api.rotas import contas as rotas_contas
from app.cnpj import digitos_verificadores
from app.config import Configuracao, configuracao
from app.contas.servico import Contas
from app.contrato import EmpresaResposta, ItemResposta
from app.empresa import FONTE_ALIQUOTAS_SIMULACAO, FONTE_DAS_EMPRESA, FONTE_DAS_SIMULACAO
from app.main import app
from app.nfe.consultas import AVISO_DEMO, AVISO_EMPRESA_PROPRIA
from app.seguranca import LimitadorPorIp
from tests.test_contas import Relogio, conta_ativa, navegador
from tests.test_nfe import NOTA_2, SERRA_AZUL, nota

NUMERICO = "11222333000181"
ALFANUMERICO = "12ABC34501DE35"  # o exemplo do manual do Serpro
FORNECEDOR = "AB12CD34EF56" + digitos_verificadores("AB12CD34EF56")
PORTO_ALEGRE, CAXIAS = 4314902, 4305108
ESPACO = "X-ContaAI-Espaco"


@pytest.fixture
def relogio(monkeypatch: pytest.MonkeyPatch) -> Relogio:
    """O relógio de teste das contas (tests/test_contas.py): o TOTP e a validade da sessão dependem da hora."""
    r = Relogio()
    monkeypatch.setattr(rotas_contas, "agora_utc", r)
    monkeypatch.setattr(dependencias, "agora_utc", r)
    return r


@pytest.fixture
def real(motores_falsos, relogio: Relogio) -> Relogio:
    """Modo real (motores falsos) com a demonstração restaurada."""
    assert TestClient(app).post("/demo/restaurar").status_code == 200
    return relogio


def corpo_empresa(cnpj: str = NUMERICO, **kw: Any) -> dict[str, Any]:
    return {
        "cnpj": cnpj,
        "razaoSocial": "Mercadinho da Ana Ltda",
        "regimeAtual": "simples_tradicional",
        "uf": "RS",
        "municipio": PORTO_ALEGRE,
        "cAtivSN": "01",
    } | kw


def com_conta(relogio: Relogio, email: str = "ana@exemplo.com.br") -> TestClient:
    c = navegador()
    conta_ativa(c, relogio, email)
    return c


def cadastrar(c: TestClient, cnpj: str = NUMERICO, status: int = 201, **kw: Any) -> dict[str, Any]:
    r = c.post("/empresas", json=corpo_empresa(cnpj, **kw))
    assert r.status_code == status, r.text
    return r.json()


def corpo_item(cnpj: str = NUMERICO, **kw: Any) -> dict[str, Any]:
    return {
        "cnpj": cnpj,
        "descricao": "Chocolate ao leite 90 g",
        "ncm": "18063210",
        "cClassTrib": "000001",
        "unidade": "UN",
        "cnpjFornecedor": FORNECEDOR,
        "codigoFornecedor": "AE-CHO-90",
        "precoVenda": "4.20",
        "margemAlvoPct": "20",
    } | kw


def nota_da_empresa(destinatario: str = NUMERICO) -> bytes:
    """A nota 2 da demonstração com CNPJs de dígito certo: o fornecedor e a empresa da conta."""
    conteudo = nota(NOTA_2)
    conteudo = conteudo.replace(b"<CNPJ>71604258000156</CNPJ>", f"<CNPJ>{FORNECEDOR}</CNPJ>".encode(), 1)
    return conteudo.replace(f"<CNPJ>{SERRA_AZUL}</CNPJ>".encode(), f"<CNPJ>{destinatario}</CNPJ>".encode(), 1)


def compra_anterior_mais_barata() -> bytes:
    """A mesma nota, de um dia antes, com outro número e o chocolate a 3,50: a nota 2 depois dela derruba a margem.
    O alerta nasce só quando a margem cai em relação ao custo anterior (ADR 0008)."""
    conteudo = nota_da_empresa()
    for de, para in (
        (b"<nNF>1002</nNF>", b"<nNF>1001</nNF>"),
        (b"<dhEmi>2027-03-16T09:00:00-03:00</dhEmi>", b"<dhEmi>2027-03-15T09:00:00-03:00</dhEmi>"),
        (b"<vUnCom>4.10</vUnCom>", b"<vUnCom>3.50</vUnCom>"),
        (b"<vProd>3280.00</vProd>", b"<vProd>2800.00</vProd>"),
    ):
        assert de in conteudo, de
        conteudo = conteudo.replace(de, para, 1)
    return conteudo


def importar(c: TestClient, conteudo: bytes, **headers: str):
    return c.post("/nfe/importar", files={"arquivo": ("nota.xml", conteudo, "application/xml")}, headers=headers)


# -- referências ------------------------------------------------------------------------------------------


def test_referencias_vem_dos_motores(real) -> None:
    c = TestClient(app)
    ufs = c.get("/referencias/ufs").json()
    assert [u["sigla"] for u in ufs["ufs"]] == ["RS", "SP"]
    assert "motor RR" in ufs["fonte"]
    municipios = c.get("/referencias/municipios?uf=RS").json()
    assert {m["codigo"] for m in municipios["municipios"]} == {PORTO_ALEGRE, CAXIAS}
    assert c.get("/referencias/municipios?uf=AM").status_code == 404
    assert c.get("/referencias/municipios?uf=EX").status_code == 404  # exterior: não é UF de empresa
    assert c.get("/referencias/municipios?uf=rs").status_code == 422
    atividades = c.get("/referencias/atividades").json()
    # Só as admissíveis na NF-e, com anexo e sem fator R: fora o serviço (05), o fator R (09) e o sem anexo (90).
    assert [(a["cAtivSN"], a["anexo"]) for a in atividades["atividades"]] == [("01", "I"), ("03", "II")]
    assert atividades["data"] == "2027-03-16" and "tpDoc=55" in atividades["fonte"]


def test_no_modo_mock_as_rotas_novas_respondem_501() -> None:
    c = TestClient(app)
    assert c.get("/referencias/ufs").status_code == 501
    assert c.post("/empresas", json=corpo_empresa()).status_code == 501
    assert c.post("/catalogo/itens", json=corpo_item()).status_code == 501


# -- cadastro ---------------------------------------------------------------------------------------------


def test_cadastro_exige_a_sessao(real) -> None:
    assert TestClient(app).post("/empresas", json=corpo_empresa()).status_code == 401
    assert TestClient(app).get(f"/empresas/{NUMERICO}").status_code == 401


def test_cadastro_com_cnpj_numerico_e_o_cenario_de_simulacao(real) -> None:
    c = com_conta(real)
    feito = EmpresaResposta.model_validate(cadastrar(c))
    assert feito.empresa.cnpj == NUMERICO and feito.empresa.municipioNome == "Porto Alegre"
    assert (feito.atividade.cAtivSN, feito.atividade.anexo) == ("01", "I")
    assert "motor SN" in feito.atividade.fonte
    assert feito.premissasDasOrigem == "simulacao" and feito.aviso == AVISO_EMPRESA_PROPRIA
    op = feito.cenario.operacao
    assert op.aliquotasNominais is not None and op.aliquotasNominais.fonte == FONTE_ALIQUOTAS_SIMULACAO
    assert op.premissasDas is not None and op.premissasDas.fonte == FONTE_DAS_SIMULACAO
    assert feito.cenario.cargaAtualPct is None
    assert c.get("/conta").json()["empresas"] == [NUMERICO]
    catalogo = c.get(f"/catalogo?cnpj={NUMERICO}").json()
    assert catalogo["itens"] == [] and catalogo["aviso"] == AVISO_EMPRESA_PROPRIA
    assert c.get(f"/empresas/{NUMERICO}").json() == feito.model_dump(mode="json")


def test_cadastro_com_cnpj_alfanumerico(real) -> None:
    c = com_conta(real)
    assert cadastrar(c, ALFANUMERICO)["empresa"]["cnpj"] == ALFANUMERICO
    assert c.get(f"/catalogo?cnpj={ALFANUMERICO}").status_code == 200


@pytest.mark.parametrize(
    ("corpo", "frase"),
    [
        (corpo_empresa("11222333000182"), "dígitos verificadores"),
        (corpo_empresa(SERRA_AZUL), "dígitos verificadores"),  # o CNPJ fictício da demo não entra
        (corpo_empresa(municipio=3550308), "Município não encontrado nesta UF"),
        (corpo_empresa(uf="AM", municipio=1302603), "UF não encontrada"),
        (corpo_empresa(uf="EX", municipio=9999999), "UF não encontrada"),
        (corpo_empresa(cAtivSN="05"), "Atividade do Simples que o ContaAI não calcula"),
        (corpo_empresa(cAtivSN="90"), "Atividade do Simples que o ContaAI não calcula"),
    ],
)
def test_cadastro_recusado_pelos_dados(real, corpo: dict[str, Any], frase: str) -> None:
    c = com_conta(real)
    r = c.post("/empresas", json=corpo)
    assert r.status_code == 422 and frase in r.json()["detail"], r.text
    assert c.get("/conta").json()["empresas"] == []


@pytest.mark.parametrize(
    "corpo",
    [
        corpo_empresa("12abc34501de35"),
        corpo_empresa("12.ABC.345/01DE-35"),
        corpo_empresa(razaoSocial="   "),
        corpo_empresa(razaoSocial="Nome\x1b[31m"),
        corpo_empresa(razaoSocial="x" * 151),
        corpo_empresa(regimeAtual="regime_regular"),
        corpo_empresa(municipio=123),
        corpo_empresa(extra="campo"),
    ],
)
def test_cadastro_fora_do_contrato(real, corpo: dict[str, Any]) -> None:
    r = com_conta(real).post("/empresas", json=corpo)
    assert r.status_code == 422 and r.json()["type"].endswith("entrada-invalida"), r.text


def test_mesma_empresa_duas_vezes_e_limite_por_conta(real) -> None:
    c = com_conta(real)
    cadastrar(c)
    assert "já está cadastrada" in cadastrar(c, status=409)["detail"]
    for n in range(1, cadastro.EMPRESAS_POR_ORGANIZACAO):
        base = f"{n:08d}0001"
        cadastrar(c, base + digitos_verificadores(base))
    base = "999999990001"
    assert "limite por conta" in cadastrar(c, base + digitos_verificadores(base), status=409)["detail"]
    assert len(c.get("/conta").json()["empresas"]) == cadastro.EMPRESAS_POR_ORGANIZACAO


def test_o_mesmo_cnpj_em_duas_contas_fica_separado(real) -> None:
    """Decisão 5 da C3: sem prova de quem é o dono do CNPJ, um CNPJ único deixaria alguém bloquear a empresa de
    outra pessoa. Cada conta vê só a própria cópia."""
    ana, bia = com_conta(real), com_conta(real, "bia@exemplo.com.br")
    cadastrar(ana)
    assert bia.get(f"/empresas/{NUMERICO}").status_code == 404
    cadastrar(bia, razaoSocial="Outra razão social")
    assert ana.get(f"/empresas/{NUMERICO}").json()["empresa"]["razaoSocial"] == "Mercadinho da Ana Ltda"
    assert bia.get(f"/empresas/{NUMERICO}").json()["empresa"]["razaoSocial"] == "Outra razão social"


def test_so_o_dono_cadastra_e_configura(real) -> None:
    c = com_conta(real)
    cadastrar(c)
    servico: Contas = dependencias.contas(configuracao())
    with servico.banco.transacao(escrita=True) as conexao:
        conexao.execute("UPDATE membros SET papel = 'membro'")
    assert c.post("/empresas", json=corpo_empresa(ALFANUMERICO)).status_code == 403
    assert c.patch(f"/empresas/{NUMERICO}", json={"razaoSocial": "Nova"}).status_code == 403
    assert c.get(f"/empresas/{NUMERICO}").status_code == 200  # ler, o membro lê


def test_falha_ao_dar_o_acesso_desfaz_a_empresa(real, monkeypatch: pytest.MonkeyPatch) -> None:
    """Os dois bancos não têm transação em comum: sem o acesso, a empresa sai do banco da organização."""
    c = com_conta(real)

    def falhar(*_: object) -> None:
        raise RuntimeError("banco das contas indisponível (teste)")

    original = Contas.vincular_empresa
    monkeypatch.setattr(Contas, "vincular_empresa", falhar)
    with pytest.raises(RuntimeError, match="indisponível"):  # o TestClient repassa a exceção do servidor (500)
        c.post("/empresas", json=corpo_empresa())
    monkeypatch.setattr(Contas, "vincular_empresa", original)  # undo() desfaria também o relógio de teste
    cadastrar(c)  # sem sobra do primeiro: entra de novo


def test_acesso_que_sobrou_nao_trava_o_recadastro(real) -> None:
    c = com_conta(real)
    servico: Contas = dependencias.contas(configuracao())
    servico.vincular_empresa(_organizacao(c), NUMERICO, real.agora)  # o acesso sem a empresa no banco
    assert c.get(f"/empresas/{NUMERICO}").status_code == 404
    cadastrar(c)
    assert c.get("/conta").json()["empresas"] == [NUMERICO]


def test_o_header_do_espaco_nao_cadastra_empresa(real) -> None:
    espaco = TestClient(app).post("/espacos").json()["id"]
    r = TestClient(app).post("/empresas", json=corpo_empresa(), headers={ESPACO: espaco})
    assert r.status_code == 401


# -- configurações ----------------------------------------------------------------------------------------


def test_configuracoes_mudam_so_o_enviado(real) -> None:
    c = com_conta(real)
    cadastrar(c)
    r = c.patch(f"/empresas/{NUMERICO}", json={"razaoSocial": "Mercadinho Novo", "uf": "RS", "municipio": CAXIAS})
    assert r.status_code == 200, r.text
    feito = EmpresaResposta.model_validate(r.json())
    assert (feito.empresa.razaoSocial, feito.empresa.municipioNome) == ("Mercadinho Novo", "Caxias do Sul")
    assert feito.empresa.regimeAtual == "simples_tradicional"

    feito = EmpresaResposta.model_validate(
        c.patch(f"/empresas/{NUMERICO}", json={"regimeAtual": "simples_hibrido", "cAtivSN": "03"}).json()
    )
    assert feito.empresa.regimeAtual == "simples_hibrido" and feito.atividade.anexo == "II"
    assert feito.cenario.operacao.premissasDas is not None and feito.cenario.operacao.premissasDas.anexo == "II"


def test_premissas_do_das_da_empresa_e_a_volta_a_simulacao(real) -> None:
    c = com_conta(real)
    simulacao = EmpresaResposta.model_validate(cadastrar(c)).cenario.operacao.premissasDas
    r = c.patch(
        f"/empresas/{NUMERICO}", json={"premissasDas": {"pCBSSN": "2.1", "pIBSSN": "0.5"}, "cargaAtualPct": "9.5"}
    )
    feito = EmpresaResposta.model_validate(r.json())
    das = feito.cenario.operacao.premissasDas
    assert das is not None and (das.pCBSSN, das.pIBSSN, das.fonte) == (
        Decimal("2.1"),
        Decimal("0.5"),
        FONTE_DAS_EMPRESA,
    )
    assert feito.premissasDasOrigem == "usuario" and feito.cenario.cargaAtualPct == Decimal("9.5")
    # O catálogo (e todo cálculo da empresa) usa as mesmas premissas.
    assert c.get(f"/catalogo?cnpj={NUMERICO}").json()["cenario"]["operacao"]["premissasDas"]["pCBSSN"] == "2.1"

    volta = EmpresaResposta.model_validate(
        c.patch(f"/empresas/{NUMERICO}", json={"premissasDas": None, "cargaAtualPct": None}).json()
    )
    assert volta.premissasDasOrigem == "simulacao" and volta.cenario.operacao.premissasDas == simulacao
    assert volta.cenario.cargaAtualPct is None


@pytest.mark.parametrize(
    "corpo",
    [
        {},
        {"uf": "RS"},
        {"municipio": CAXIAS},
        {"razaoSocial": None},
        {"cnpj": ALFANUMERICO},
        {"premissasDas": {"pCBSSN": "100", "pIBSSN": "0"}},
        {"cargaAtualPct": "-1"},
    ],
)
def test_configuracoes_fora_do_contrato(real, corpo: dict[str, Any]) -> None:
    c = com_conta(real)
    cadastrar(c)
    r = c.patch(f"/empresas/{NUMERICO}", json=corpo)
    assert r.status_code == 422, r.text


def test_configurar_empresa_de_outra_conta_responde_404(real) -> None:
    ana, bia = com_conta(real), com_conta(real, "bia@exemplo.com.br")
    cadastrar(ana)
    assert bia.patch(f"/empresas/{NUMERICO}", json={"razaoSocial": "Invasão"}).status_code == 404
    assert ana.get(f"/empresas/{NUMERICO}").json()["empresa"]["razaoSocial"] == "Mercadinho da Ana Ltda"


# -- a saída da C3 no backend -----------------------------------------------------------------------------


def test_conta_nova_cadastra_a_empresa_importa_a_nota_e_ve_o_alerta(real) -> None:
    demo_antes = TestClient(app).get(f"/catalogo?cnpj={SERRA_AZUL}").json()
    c = com_conta(real)
    cadastrar(c)
    r = c.post("/catalogo/itens", json=corpo_item())
    assert r.status_code == 201, r.text
    item = ItemResposta.model_validate(r.json()).item
    assert item.id.startswith("item-") and item.precoVenda == Decimal("4.20") and item.cst == "000"

    assert importar(c, compra_anterior_mais_barata()).status_code == 200
    assert c.get(f"/alertas?cnpj={NUMERICO}").json()["alertas"] == []
    r = importar(c, nota_da_empresa())
    assert r.status_code == 200, r.text
    recibo = r.json()
    assert [i["itemId"] for i in recibo["itensCasados"]] == [item.id]
    assert {i["codigoFornecedor"] for i in recibo["itensSemPar"]} == {"AE-CRV-350", "AE-BIS-140"}  # sem cadastro
    alertas = c.get(f"/alertas?cnpj={NUMERICO}").json()["alertas"]
    assert [a["itemId"] for a in alertas] == [item.id]
    painel = c.get("/contador/painel").json()
    assert painel["aviso"] == AVISO_EMPRESA_PROPRIA
    assert [(e["empresa"]["cnpj"], e["alertasAbertos"]) for e in painel["empresas"]] == [(NUMERICO, 1)]
    # A demonstração não mudou.
    assert TestClient(app).get(f"/catalogo?cnpj={SERRA_AZUL}").json() == demo_antes
    assert demo_antes["aviso"] == AVISO_DEMO


def test_nota_de_outra_empresa_continua_recusada_na_conta(real) -> None:
    c = com_conta(real)
    cadastrar(c)
    assert importar(c, nota(NOTA_2)).status_code == 422  # destinatário Serra Azul: não é da conta


def test_configuracao_nao_vaza_entre_estados(real) -> None:
    """O espaço e a demonstração não enxergam a empresa da conta, e a conta não enxerga a demonstração."""
    c = com_conta(real)
    cadastrar(c)
    espaco = TestClient(app).post("/espacos").json()["id"]
    assert TestClient(app).get(f"/catalogo?cnpj={NUMERICO}").status_code == 404
    assert TestClient(app).get(f"/catalogo?cnpj={NUMERICO}", headers={ESPACO: espaco}).status_code == 404
    assert c.get(f"/catalogo?cnpj={SERRA_AZUL}").status_code == 404


# -- catálogo editável ------------------------------------------------------------------------------------


def criar_item(c: TestClient, status: int = 201, headers: dict[str, str] | None = None, **kw: Any) -> dict[str, Any]:
    r = c.post("/catalogo/itens", json=corpo_item(**kw), headers=headers or {})
    assert r.status_code == status, r.text
    return r.json()


def _organizacao(c: TestClient) -> str:
    return str(c.get("/conta").json()["organizacao"]["id"])


@pytest.mark.parametrize(
    ("campos", "frase"),
    [
        ({"ncm": "99999999"}, "NCM não encontrada"),
        ({"ncm": "22030000"}, "Imposto Seletivo"),
        ({"cClassTrib": "200003"}, "Classificação não válida"),  # vale para o arroz, não para o chocolate
        ({"cClassTrib": "900001"}, "Classificação não válida"),  # só de serviço
        ({"cnpjFornecedor": "71604258000156"}, "CNPJ do fornecedor inválido"),  # o fictício, fora da demo
    ],
)
def test_item_recusado_pelos_dados(real, campos: dict[str, str], frase: str) -> None:
    c = com_conta(real)
    cadastrar(c)
    assert frase in criar_item(c, 422, **campos)["detail"]
    assert c.get(f"/catalogo?cnpj={NUMERICO}").json()["itens"] == []


@pytest.mark.parametrize(
    "campos",
    [
        {"unidade": "CX"},
        {"precoVenda": "0"},
        {"precoVenda": "4.205"},
        {"margemAlvoPct": "100"},
        {"descricao": " "},
        {"codigoFornecedor": "A" * 61},
        {"codigoFornecedor": "AE\x00CHO"},
        {"ncm": "1806321"},
        {"cnpjFornecedor": "12abc34501de35"},
    ],
)
def test_item_fora_do_contrato(real, campos: dict[str, str]) -> None:
    c = com_conta(real)
    cadastrar(c)
    criar_item(c, 422, **campos)


def test_item_com_a_classificacao_e_a_fonte_montadas_pelo_backend(real) -> None:
    c = com_conta(real)
    cadastrar(c)
    item = ItemResposta.model_validate(criar_item(c, ncm="10063021", cClassTrib="200003", descricao="Arroz 5 kg")).item
    assert (item.cst, item.cClassTrib) == ("200", "200003")  # o CST é o da fundamentação oficial
    assert "Escolhida no cadastro do item" in item.classificacaoFonte and "200003" in item.classificacaoFonte
    assert item.ncmDescricaoOficial == "Arroz - Arroz polido (teste)"  # a hierarquia oficial do motor
    assert item.custoAtual is None and item.historicoCusto == []
    assert [i["id"] for i in c.get(f"/catalogo?cnpj={NUMERICO}").json()["itens"]] == [item.id]


def test_codigo_do_fornecedor_repetido_e_limite_de_itens(real, monkeypatch: pytest.MonkeyPatch) -> None:
    c = com_conta(real)
    cadastrar(c)
    criar_item(c)
    assert "outro item" in criar_item(c, 409, descricao="Outro chocolate")["detail"]
    criar_item(c, codigoFornecedor="AE-CHO-91")  # outro código do mesmo fornecedor
    monkeypatch.setattr(cadastro, "ITENS_POR_EMPRESA", 2)
    assert "limite por empresa" in criar_item(c, 409, codigoFornecedor="AE-CHO-92")["detail"]


def test_alterar_item(real) -> None:
    c = com_conta(real)
    cadastrar(c)
    item = criar_item(c)["item"]
    caminho = f"/catalogo/{item['id']}"
    r = c.patch(caminho, json={"cnpj": NUMERICO, "descricao": "Chocolate 90 g", "margemAlvoPct": "25"})
    assert r.status_code == 200, r.text
    novo = r.json()["item"]
    assert (novo["descricao"], novo["margemAlvoPct"], novo["precoVenda"]) == ("Chocolate 90 g", "25", "4.20")
    assert c.patch(caminho, json={"cnpj": NUMERICO, "margemAlvoPct": "25"}).status_code == 409
    for corpo in (
        {"cnpj": NUMERICO},
        {"cnpj": NUMERICO, "codigoFornecedor": "X"},
        {"cnpj": NUMERICO, "descricao": None},
        {"cnpj": NUMERICO, "ncm": "10063021"},  # NCM não muda: outro item
        {"cnpj": NUMERICO, "unidade": "KG"},
    ):
        assert c.patch(caminho, json=corpo).status_code == 422, corpo
    assert c.patch("/catalogo/item-000000000000", json={"cnpj": NUMERICO, "descricao": "x"}).status_code == 404


def test_trocar_o_fornecedor_muda_o_casamento_da_nota(real) -> None:
    c = com_conta(real)
    cadastrar(c)
    item = criar_item(c)["item"]
    outro = "112223330002" + digitos_verificadores("112223330002")
    corpo = {"cnpj": NUMERICO, "cnpjFornecedor": outro, "codigoFornecedor": "CHO"}
    assert c.patch(f"/catalogo/{item['id']}", json=corpo).status_code == 200
    assert importar(c, nota_da_empresa()).json()["itensCasados"] == []  # a nota é do fornecedor antigo
    errado = {"cnpj": NUMERICO, "cnpjFornecedor": "11222333000299", "codigoFornecedor": "CHO"}
    assert "dígitos verificadores" in c.patch(f"/catalogo/{item['id']}", json=errado).json()["detail"]


def test_a_classificacao_corrigida_sobrevive_a_alteracao(real) -> None:
    """A alteração regrava o cadastro do item, não a classificação dos lançamentos."""
    c = com_conta(real)
    cadastrar(c)
    item = criar_item(c, ncm="10063021", cClassTrib="200003", descricao="Arroz 5 kg", codigoFornecedor="ARZ")["item"]
    r = c.post(f"/catalogo/{item['id']}/classificacao", json={"cnpj": NUMERICO, "cClassTrib": "000001"})
    assert r.status_code == 200, r.text
    novo = c.patch(f"/catalogo/{item['id']}", json={"cnpj": NUMERICO, "descricao": "Arroz tipo 1"}).json()["item"]
    assert (novo["cClassTrib"], novo["descricao"]) == ("000001", "Arroz tipo 1")


def test_arquivar_item_guarda_o_historico_e_tira_das_listas(real) -> None:
    c = com_conta(real)
    cadastrar(c)
    item = criar_item(c)["item"]
    importar(c, compra_anterior_mais_barata())
    importar(c, nota_da_empresa())
    alerta = c.get(f"/alertas?cnpj={NUMERICO}").json()["alertas"][0]
    r = c.post(f"/catalogo/{item['id']}/arquivar", json={"cnpj": NUMERICO})
    assert r.status_code == 200, r.text
    assert c.get(f"/catalogo?cnpj={NUMERICO}").json()["itens"] == []
    assert c.get(f"/alertas?cnpj={NUMERICO}").json()["alertas"] == []
    assert c.get("/contador/painel").json()["empresas"][0]["alertasAbertos"] == 0
    assert all(n["alertasAbertos"] == 0 for n in c.get(f"/notas?cnpj={NUMERICO}").json()["notas"])
    assert c.post(f"/alertas/{alerta['id']}/aplicar").status_code == 409
    assert c.post(f"/catalogo/{item['id']}/preco", json={"cnpj": NUMERICO, "valorUnitario": "5"}).status_code == 404
    assert c.post(f"/catalogo/{item['id']}/arquivar", json={"cnpj": NUMERICO}).status_code == 404
    # O histórico fica no banco: os custos das duas notas e o alerta do item arquivado.
    with dependencias.banco_da_organizacao(configuracao(), _organizacao(c)).transacao() as conexao:
        assert conexao.execute("SELECT count(*) FROM custos WHERE item_id = ?", (item["id"],)).fetchone()[0] == 2
        assert conexao.execute("SELECT count(*) FROM alertas WHERE item_id = ?", (item["id"],)).fetchone()[0] == 1
    # O código do fornecedor fica livre: um item novo com ele casa a próxima nota, e o id não se repete.
    novo = criar_item(c, descricao="Chocolate (novo cadastro)")["item"]
    assert novo["id"] != item["id"]


def test_catalogo_editavel_no_espaco_aceita_os_cnpjs_ficticios(real) -> None:
    """No espaço (cópia da demonstração), o fornecedor fictício entra: o dígito só é exigido na empresa da conta."""
    espaco = {ESPACO: TestClient(app).post("/espacos").json()["id"]}
    c = TestClient(app)
    criar_item(c, headers=espaco, cnpj=SERRA_AZUL, cnpjFornecedor="71604258000156", codigoFornecedor="NOVO")
    assert len(c.get(f"/catalogo?cnpj={SERRA_AZUL}", headers=espaco).json()["itens"]) == 6
    assert len(c.get(f"/catalogo?cnpj={SERRA_AZUL}").json()["itens"]) == 5  # a demonstração não mudou


def test_catalogo_da_demonstracao_compartilhada_exige_o_token(real) -> None:
    app.dependency_overrides[configuracao] = lambda: Configuracao(modo="real", token_demo="segredo-de-teste")
    c = TestClient(app)
    corpo = corpo_item(SERRA_AZUL, cnpjFornecedor="71604258000156", codigoFornecedor="NOVO")
    assert c.post("/catalogo/itens", json=corpo).status_code == 401
    item = "arroz-5kg"
    assert c.patch(f"/catalogo/{item}", json={"cnpj": SERRA_AZUL, "descricao": "x"}).status_code == 401
    assert c.post(f"/catalogo/{item}/arquivar", json={"cnpj": SERRA_AZUL}).status_code == 401
    com_token = {"X-ContaAI-Token": "segredo-de-teste"}
    assert c.post(f"/catalogo/{item}/arquivar", json={"cnpj": SERRA_AZUL}, headers=com_token).status_code == 200


def test_item_de_empresa_de_outra_conta_responde_404(real) -> None:
    ana, bia = com_conta(real), com_conta(real, "bia@exemplo.com.br")
    cadastrar(ana)
    item = criar_item(ana)["item"]
    assert bia.post("/catalogo/itens", json=corpo_item()).status_code == 404
    assert bia.patch(f"/catalogo/{item['id']}", json={"cnpj": NUMERICO, "descricao": "x"}).status_code == 404
    assert bia.post(f"/catalogo/{item['id']}/arquivar", json={"cnpj": NUMERICO}).status_code == 404
    assert len(ana.get(f"/catalogo?cnpj={NUMERICO}").json()["itens"]) == 1


# -- segurança das rotas novas ----------------------------------------------------------------------------


def test_patch_com_o_cookie_e_sem_origin_e_recusado(real) -> None:
    """CSRF (ADR 0015): o PATCH também passa pela defesa dos métodos que mudam o estado."""
    c = com_conta(real)
    cadastrar(c)
    sem_origin = TestClient(app, base_url="https://testserver", cookies=c.cookies)
    assert sem_origin.patch(f"/empresas/{NUMERICO}", json={"razaoSocial": "CSRF"}).status_code == 403
    outro_site = {"Origin": "https://ataque.exemplo.test"}
    assert c.patch(f"/empresas/{NUMERICO}", json={"razaoSocial": "CSRF"}, headers=outro_site).status_code == 403
    assert (
        c.patch(
            f"/empresas/{NUMERICO}", json={"razaoSocial": "CSRF"}, headers={"Sec-Fetch-Site": "cross-site"}
        ).status_code
        == 403
    )
    assert c.get(f"/empresas/{NUMERICO}").json()["empresa"]["razaoSocial"] == "Mercadinho da Ana Ltda"


def test_patch_com_corpo_grande_e_recusado_antes_de_ser_lido(real) -> None:
    """O limite de corpo valia só para o POST; o PATCH entrou junto (achado da C3-B)."""
    c = com_conta(real)
    cadastrar(c)
    app.dependency_overrides[configuracao] = lambda: Configuracao(modo="real", tamanho_max_json_bytes=200)
    r = c.patch(f"/empresas/{NUMERICO}", json={"razaoSocial": "x" * 300})
    assert r.status_code == 413, r.text
    r = c.patch("/catalogo/arroz-5kg", json={"cnpj": NUMERICO, "descricao": "x" * 300})
    assert r.status_code == 413, r.text


def test_rotas_novas_tem_limite_por_ip(real, monkeypatch: pytest.MonkeyPatch) -> None:
    c = com_conta(real)
    cadastrar(c)
    monkeypatch.setattr(middlewares, "LIMITE_GERAL", LimitadorPorIp(1))
    assert c.get("/referencias/ufs").status_code == 200
    assert c.get("/referencias/ufs").status_code == 429
    monkeypatch.setattr(middlewares, "LIMITE_GERAL", LimitadorPorIp(1))
    assert c.patch(f"/empresas/{NUMERICO}", json={"razaoSocial": "Um"}).status_code == 200
    assert c.patch(f"/empresas/{NUMERICO}", json={"razaoSocial": "Dois"}).status_code == 429
    monkeypatch.setattr(middlewares, "LIMITE_GERAL", LimitadorPorIp(1))
    assert c.post("/catalogo/itens", json=corpo_item()).status_code == 201
    assert c.post("/catalogo/itens", json=corpo_item(codigoFornecedor="B")).status_code == 429


def test_erros_nao_repetem_o_que_foi_enviado(real) -> None:
    c = com_conta(real)
    cadastrar(c)
    marcador = "<script>alert(1)</script>"
    for r in (
        c.post("/empresas", json=corpo_empresa(razaoSocial=marcador, municipio=3550308)),
        c.post("/catalogo/itens", json=corpo_item(descricao=marcador, ncm="99999999")),
        c.patch(f"/empresas/{NUMERICO}", json={"razaoSocial": marcador, "uf": "RS", "municipio": 3550308}),
    ):
        assert r.status_code == 422 and marcador not in r.text and "alert" not in r.text, r.text
