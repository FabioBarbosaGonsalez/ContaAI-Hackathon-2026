"""Gera as NF-e de compra fictícias de data/demo/notas/ (E0-06).

- nfe-compra-1.xml (2027-03-02): sem grupo IBSCBS. Exercita o caminho em que o crédito
  das compras é calculado pelo motor sobre o custo (plano, E3).
- nfe-compra-2.xml (2027-03-16): a cerveja sobe de custo. Os grupos IS e IBSCBS de cada
  item e os totais são gerados pelo próprio motor RR (POST /calculadora/regime-geral e
  POST /calculadora/xml/generate?tipo=nfe) e validados no XSD oficial
  (POST /calculadora/xml/validate?tipo=nfe&subtipo=grupo) antes de gravar.

As notas seguem a ordem do leiaute oficial da NF-e 4.00 nos elementos incluídos, mas NÃO são
documentos fiscais válidos: não têm assinatura digital nem todos os campos obrigatórios, são de
ambiente de homologação (tpAmb 2), os CNPJs têm dígito verificador inválido de propósito e o
ICMS foi deixado de fora (simplificação registrada em data/demo/README.md).

Uso (motor RR de pé): cd backend && uv run python scripts/gerar_notas_demo.py
"""

from __future__ import annotations

import copy
import os
import sys
import xml.etree.ElementTree as ET
from datetime import date
from decimal import Decimal
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.dados_demo import PASTA_DEMO, Distribuidora, carregar_distribuidora  # noqa: E402
from app.motores.requisicoes import AliquotasPremissa, Linha, operacao_rr  # noqa: E402

MOTOR_RR_URL = os.environ.get("MOTOR_RR_URL", "http://127.0.0.1:8080/api")
NS = "http://www.portalfiscal.inf.br/nfe"
ET.register_namespace("", NS)

FORNECEDOR = {"cnpj": "71604258000156", "xNome": "Atacado Exemplo Ltda (fictício)", "CRT": "3"}

# (código do fornecedor, item do catálogo, quantidade, valor unitário) — valores fictícios
NOTAS = [
    {
        "arquivo": "nfe-compra-1.xml",
        "nNF": "1001",
        "dhEmi": "2027-03-02T09:00:00-03:00",
        "grupoTributacao": False,
        "itens": [
            ("AE-ARZ-5", "arroz-5kg", "500", "21.50"),
            ("AE-CRV-350", "cerveja-lata", "1440", "2.60"),
            ("AE-CHO-90", "chocolate-barra", "800", "4.10"),
            ("AE-BIS-140", "biscoito-pacote", "2600", "3.10"),
            ("AE-CRN-KG", "carne-bovina-kg", "120", "31.00"),
        ],
    },
    {
        "arquivo": "nfe-compra-2.xml",
        "nNF": "1002",
        "dhEmi": "2027-03-16T09:00:00-03:00",
        "grupoTributacao": True,
        "itens": [
            ("AE-CRV-350", "cerveja-lata", "1440", "3.05"),
            ("AE-CHO-90", "chocolate-barra", "800", "4.10"),
            ("AE-BIS-140", "biscoito-pacote", "2600", "3.10"),
        ],
    },
]


def q(tag: str) -> str:
    return f"{{{NS}}}{tag}"


def sub(pai: ET.Element, tag: str, texto: str | None = None, **attrs: str) -> ET.Element:
    el = ET.SubElement(pai, q(tag), attrs)
    if texto is not None:
        el.text = texto
    return el


def codigo_uf(cli: httpx.Client, sigla: str) -> str:
    ufs = cli.get(f"{MOTOR_RR_URL}/calculadora/dados-abertos/ufs").raise_for_status().json()
    achada = next(u for u in ufs if sigla in {str(v) for v in u.values()})
    return str(achada["codigo"])


def grupo_do_motor(cli: httpx.Client, demo: Distribuidora, nota: dict) -> ET.Element:
    """Calcula a compra no motor RR e devolve o XML oficial dos grupos de tributação.

    Usa POST /calculadora/regime-geral (e não a observabilidade) porque é a resposta que o
    /xml/generate aceita (docs/exemplos.md). É só para fabricar a nota fictícia do fornecedor:
    o backend do produto calcula pela observabilidade (P4).
    """
    al = demo.cenario.aliquotasNominais
    aliquotas = AliquotasPremissa(
        cbs=al.cbs,
        ibsEstadual=al.ibsEstadual,
        ibsMunicipal=al.ibsMunicipal,
        impostoSeletivoAdValorem=demo.cenario.impostoSeletivoAdValorem.valor,
    )
    linhas = [
        Linha(demo.item(item_id), Decimal(qtd), Decimal(qtd) * Decimal(vun)) for _, item_id, qtd, vun in nota["itens"]
    ]
    operacao = operacao_rr(
        linhas, date.fromisoformat(nota["dhEmi"][:10]), demo.empresa.uf, demo.empresa.municipio, aliquotas
    )
    calculo = cli.post(f"{MOTOR_RR_URL}/calculadora/regime-geral", json=operacao).raise_for_status()
    xml = cli.post(f"{MOTOR_RR_URL}/calculadora/xml/generate", params={"tipo": "nfe"}, json=calculo.json())
    return ET.fromstring(xml.raise_for_status().content)


def montar_nota(cli: httpx.Client, demo: Distribuidora, nota: dict, cuf: str) -> ET.ElementTree:
    nfe = ET.Element(q("NFe"))
    inf = sub(nfe, "infNFe", versao="4.00", Id="NFe" + nota["nNF"].zfill(44))

    ide = sub(inf, "ide")
    for tag, valor in [
        ("cUF", cuf),
        ("natOp", "Venda de mercadoria"),
        ("mod", "55"),
        ("serie", "1"),
        ("nNF", nota["nNF"]),
        ("dhEmi", nota["dhEmi"]),
        ("tpNF", "1"),
        ("cMunFG", str(demo.empresa.municipio)),
        ("tpAmb", "2"),
    ]:
        sub(ide, tag, valor)

    emit = sub(inf, "emit")
    sub(emit, "CNPJ", FORNECEDOR["cnpj"])
    sub(emit, "xNome", FORNECEDOR["xNome"])
    sub(emit, "CRT", FORNECEDOR["CRT"])

    dest = sub(inf, "dest")
    sub(dest, "CNPJ", demo.empresa.cnpj)
    sub(dest, "xNome", demo.empresa.razaoSocial)

    grupo = grupo_do_motor(cli, demo, nota) if nota["grupoTributacao"] else None
    for numero, (cprod, item_id, qtd, vun) in enumerate(nota["itens"], start=1):
        cat = demo.item(item_id)
        det = sub(inf, "det", nItem=str(numero))
        prod = sub(det, "prod")
        sub(prod, "cProd", cprod)
        sub(prod, "xProd", cat.descricao)
        sub(prod, "NCM", cat.ncm)
        sub(prod, "uCom", cat.unidade)
        sub(prod, "qCom", qtd)
        sub(prod, "vUnCom", vun)
        sub(prod, "vProd", f"{Decimal(qtd) * Decimal(vun):.2f}")
        imposto = sub(det, "imposto")
        if grupo is not None:
            det_motor = grupo.find(f"{q('det')}[@nItem='{numero}']")
            for filho in det_motor.find(q("imposto")):
                imposto.append(copy.deepcopy(filho))

    total = sub(inf, "total")
    if grupo is not None:
        for filho in grupo.find(q("total")):
            total.append(copy.deepcopy(filho))

    adic = sub(inf, "infAdic")
    sub(adic, "infCpl", "DOCUMENTO FICTICIO PARA DEMONSTRACAO - SEM VALOR FISCAL. Dados sinteticos do projeto ContaAI.")
    arvore = ET.ElementTree(nfe)
    ET.indent(arvore, space="  ")
    return arvore


def validar_grupos(cli: httpx.Client, arvore: ET.ElementTree) -> None:
    """Monta só os grupos de tributação da nota e valida no XSD oficial (grupo.xsd do motor)."""
    inf = arvore.getroot().find(q("infNFe"))
    doc = ET.Element(q("infNFe"))
    for det in inf.findall(q("det")):
        novo = ET.SubElement(doc, q("det"), nItem=det.get("nItem"))
        imposto = ET.SubElement(novo, q("imposto"))
        for filho in det.find(q("imposto")):
            imposto.append(copy.deepcopy(filho))
    total = ET.SubElement(doc, q("total"))
    for filho in inf.find(q("total")):
        total.append(copy.deepcopy(filho))
    resposta = cli.post(
        f"{MOTOR_RR_URL}/calculadora/xml/validate",
        params={"tipo": "nfe", "subtipo": "grupo"},
        content=ET.tostring(doc, encoding="utf-8", xml_declaration=True),
        headers={"Content-Type": "application/xml"},
    )
    if resposta.status_code != 200 or resposta.text.strip() != "true":
        sys.exit(f"Grupos de tributação inválidos no XSD oficial: HTTP {resposta.status_code} {resposta.text[:500]}")


def main() -> None:
    demo = carregar_distribuidora()
    # CONTAAI_SAIDA_NOTAS permite gravar em outra pasta (o teste de reprodutibilidade usa isso).
    destino = Path(os.environ.get("CONTAAI_SAIDA_NOTAS") or PASTA_DEMO / "notas")
    destino.mkdir(exist_ok=True)
    with httpx.Client(timeout=30) as cli:
        cuf = codigo_uf(cli, demo.empresa.uf)
        for nota in NOTAS:
            arvore = montar_nota(cli, demo, nota, cuf)
            if nota["grupoTributacao"]:
                validar_grupos(cli, arvore)
            # Bytes, não texto: no Windows o modo texto grava CRLF e o repositório guarda LF (.gitattributes).
            (destino / nota["arquivo"]).write_bytes(
                ET.tostring(arvore.getroot(), encoding="UTF-8", xml_declaration=True)
            )
            print(
                f"{nota['arquivo']}: {len(nota['itens'])} itens"
                + (", grupos IS/IBSCBS validados no XSD" if nota["grupoTributacao"] else "")
            )


if __name__ == "__main__":
    main()
