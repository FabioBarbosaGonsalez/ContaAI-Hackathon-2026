"""Dados de demonstração (E0-06): fictícios, coerentes entre si e com o leiaute oficial nos grupos RTC."""

from __future__ import annotations

import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from app.dados_demo import PASTA_DEMO, Distribuidora, carregar_cliente_b2b, carregar_distribuidora

NFE = "http://www.portalfiscal.inf.br/nfe"
NS = {"n": NFE}
NOTAS = sorted((PASTA_DEMO / "notas").glob("nfe-compra-*.xml"))  # as duas compras da Serra Azul
TODAS_AS_NOTAS = sorted(PASTA_DEMO.rglob("*.xml"))  # inclui o item sem par e a carteira do contador (E4)
EMPRESAS = [PASTA_DEMO / "distribuidora.json", *sorted((PASTA_DEMO / "carteira").glob("*.json"))]
BACKEND = Path(__file__).resolve().parents[1]
MOTOR_RR_URL = os.environ.get("MOTOR_RR_URL", "http://127.0.0.1:8080/api")


def digitos_verificadores(base12: str) -> str:
    """Dígitos verificadores do CNPJ (algoritmo módulo 11)."""

    def dv(numeros: str, pesos: list[int]) -> str:
        resto = sum(int(n) * p for n, p in zip(numeros, pesos, strict=True)) % 11
        return "0" if resto < 2 else str(11 - resto)

    d1 = dv(base12, [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    return d1 + dv(base12 + d1, [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])


def cnpj_valido(cnpj: str) -> bool:
    return cnpj[12:] == digitos_verificadores(cnpj[:12])


def infnfe(caminho: Path) -> ET.Element:
    raiz = ET.parse(caminho).getroot()
    assert raiz.tag == f"{{{NFE}}}NFe"
    return raiz.find("n:infNFe", NS)


def test_dados_validam_no_modelo_e_sao_coerentes() -> None:
    demo, cliente = carregar_distribuidora(), carregar_cliente_b2b()
    ids = [i.id for i in demo.catalogo]
    assert len(ids) == len(set(ids))
    assert {i.itemId for i in cliente.compraMensal.itens} <= set(ids)
    assert "fictício" in demo.aviso and "fictício" in cliente.aviso


def test_cnpjs_sao_propositalmente_invalidos() -> None:
    cnpjs = [carregar_cliente_b2b().cliente.cnpj]
    cnpjs += [Distribuidora.model_validate_json(p.read_text(encoding="utf-8")).empresa.cnpj for p in EMPRESAS]
    for caminho in TODAS_AS_NOTAS:
        inf = infnfe(caminho)
        cnpjs += [inf.findtext("n:emit/n:CNPJ", namespaces=NS), inf.findtext("n:dest/n:CNPJ", namespaces=NS)]
    for cnpj in cnpjs:
        assert len(cnpj) == 14 and cnpj.isdigit()
        assert not cnpj_valido(cnpj), f"CNPJ {cnpj} tem DV válido: poderia ser de uma empresa real"
    # Controle: o validador aceita a mesma base com os dígitos corretos (montados aqui, nunca gravados).
    base = carregar_distribuidora().empresa.cnpj[:12]
    assert cnpj_valido(base + digitos_verificadores(base))


def test_duas_notas_do_mesmo_fornecedor_casam_com_o_catalogo() -> None:
    demo = carregar_distribuidora()
    assert [p.name for p in NOTAS] == ["nfe-compra-1.xml", "nfe-compra-2.xml"]
    emitentes = {infnfe(p).findtext("n:emit/n:CNPJ", namespaces=NS) for p in NOTAS}
    assert len(emitentes) == 1
    pares = {(i.ncm, i.codigoFornecedor) for i in demo.catalogo}
    for caminho in NOTAS:
        for det in infnfe(caminho).findall("n:det", NS):
            p = det.find("n:prod", NS)
            assert (p.findtext("n:NCM", namespaces=NS), p.findtext("n:cProd", namespaces=NS)) in pares
            q, v = Decimal(p.findtext("n:qCom", namespaces=NS)), Decimal(p.findtext("n:vUnCom", namespaces=NS))
            assert Decimal(p.findtext("n:vProd", namespaces=NS)) == (q * v).quantize(Decimal("0.01"))


def test_nota_1_sem_grupo_ibscbs_e_nota_2_com_grupo() -> None:
    nota1, nota2 = (infnfe(p) for p in NOTAS)
    assert nota1.findall("n:det/n:imposto/n:IBSCBS", NS) == []
    assert len(nota2.findall("n:det/n:imposto/n:IBSCBS", NS)) == len(nota2.findall("n:det", NS))
    assert nota2.find("n:total/n:IBSCBSTot", NS) is not None


def test_cerveja_sobe_de_custo_na_nota_2_e_usa_o_is_da_revenda() -> None:
    def cerveja(caminho: Path) -> ET.Element:
        return next(
            d for d in infnfe(caminho).findall("n:det", NS) if d.findtext("n:prod/n:NCM", namespaces=NS) == "22030000"
        )

    c1, c2 = cerveja(NOTAS[0]), cerveja(NOTAS[1])
    assert Decimal(c2.findtext("n:prod/n:vUnCom", namespaces=NS)) > Decimal(
        c1.findtext("n:prod/n:vUnCom", namespaces=NS)
    )
    grupo_is = c2.find("n:imposto/n:IS", NS)
    assert grupo_is.findtext("n:CSTIS", namespaces=NS) == "200"
    assert grupo_is.findtext("n:cClassTribIS", namespaces=NS) == "200007"
    assert grupo_is.findtext("n:vIS", namespaces=NS) == "0.00"


def test_notas_sao_marcadas_como_ficticias() -> None:
    for caminho in TODAS_AS_NOTAS:
        inf = infnfe(caminho)
        assert inf.findtext("n:ide/n:tpAmb", namespaces=NS) == "2"  # homologação
        assert "SEM VALOR FISCAL" in inf.findtext("n:infAdic/n:infCpl", namespaces=NS)
        assert ET.parse(caminho).getroot().find("{http://www.w3.org/2000/09/xmldsig#}Signature") is None


@pytest.mark.golden
def test_grupos_da_nota_2_validam_no_xsd_oficial() -> None:
    inf = infnfe(NOTAS[1])
    doc = ET.Element(f"{{{NFE}}}infNFe")
    for det in inf.findall("n:det", NS):
        novo = ET.SubElement(doc, f"{{{NFE}}}det", nItem=det.get("nItem"))
        novo.append(det.find("n:imposto", NS))
    doc.append(inf.find("n:total", NS))
    resposta = httpx.post(
        f"{MOTOR_RR_URL}/calculadora/xml/validate",
        params={"tipo": "nfe", "subtipo": "grupo"},
        content=ET.tostring(doc, encoding="utf-8", xml_declaration=True),
        headers={"Content-Type": "application/xml"},
        timeout=30,
    )
    assert resposta.status_code == 200 and resposta.text.strip() == "true", resposta.text[:300]


@pytest.mark.golden
def test_notas_sao_reproduziveis_pelo_motor(tmp_path: Path) -> None:
    env = {**os.environ, "CONTAAI_SAIDA_NOTAS": str(tmp_path), "PYTHONIOENCODING": "utf-8"}
    subprocess.run(
        [sys.executable, "scripts/gerar_notas_demo.py"], cwd=BACKEND, env=env, check=True, capture_output=True
    )
    for caminho in TODAS_AS_NOTAS:
        relativo = caminho.relative_to(PASTA_DEMO)
        assert (tmp_path / relativo).read_bytes() == caminho.read_bytes(), str(relativo)


def test_carteira_do_contador_usa_so_itens_ja_verificados() -> None:
    """D1 (ADR 0008): as empresas novas reaproveitam a classificação e as fontes dos itens da Serra Azul."""
    base = {i.id: i for i in carregar_distribuidora().catalogo}
    cnpjs = set()
    for caminho in EMPRESAS:
        empresa = Distribuidora.model_validate_json(caminho.read_text(encoding="utf-8"))
        cnpjs.add(empresa.empresa.cnpj)
        assert "fictíc" in empresa.aviso
        for item in empresa.catalogo:
            original = base[item.id]
            campos = {"ncm", "cst", "cClassTrib", "classificacaoFonte", "impostoSeletivo", "codigoFornecedor"}
            assert item.model_dump(include=campos) == original.model_dump(include=campos), item.id
    assert len(cnpjs) == 3


def test_sementes_apontam_para_arquivos_existentes() -> None:
    from app.persistencia.sementes import carregar_manifesto

    manifesto = carregar_manifesto()
    for nome in [*manifesto.empresas, *manifesto.notasIniciais]:
        assert (PASTA_DEMO / nome).is_file(), nome
    # A nota 2 e a do item sem par ficam de fora para a demonstração ao vivo e para a banca.
    assert "notas/nfe-compra-2.xml" not in manifesto.notasIniciais
    assert "notas/nfe-item-sem-par.xml" not in manifesto.notasIniciais
