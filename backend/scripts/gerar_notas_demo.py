"""Gera as NF-e de compra fictícias de data/demo/ (E0-06; carteira e item sem par na E4, ADR 0008).

- notas/nfe-compra-1.xml (2027-03-02): sem grupo IBSCBS. Exercita o caminho em que o crédito
  das compras é calculado pelo motor sobre o custo (plano, E3).
- notas/nfe-compra-2.xml (2027-03-16): a cerveja sobe de custo. Os grupos IS e IBSCBS de cada
  item e os totais são gerados pelo próprio motor RR (POST /calculadora/regime-geral e
  POST /calculadora/xml/generate?tipo=nfe) e validados no XSD oficial
  (POST /calculadora/xml/validate?tipo=nfe&subtipo=grupo) antes de gravar.
- notas/nfe-item-sem-par.xml (2027-03-18): um item que casa, um código sem cadastro e um código
  com NCM diferente da do cadastro, para testar os itens sem par (plano, seção 16).
- carteira/notas/*.xml: notas das outras duas empresas da carteira do contador (D1), com grupos.

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
from app.dados_demo import PASTA_DEMO, Distribuidora  # noqa: E402
from app.motores.requisicoes import AliquotasPremissa, Linha, operacao_rr  # noqa: E402

MOTOR_RR_URL = os.environ.get("MOTOR_RR_URL", "http://127.0.0.1:8080/api")
NS = "http://www.portalfiscal.inf.br/nfe"
ET.register_namespace("", NS)

FORNECEDOR = {"cnpj": "71604258000156", "xNome": "Atacado Exemplo Ltda (fictício)", "CRT": "3"}

# (código do fornecedor, item do catálogo, quantidade, valor unitário) — valores fictícios.
# Item fora do catálogo: (código, None, quantidade, valor unitário, xProd, NCM, unidade).
NOTAS = [
    {
        "empresa": "distribuidora.json",
        "arquivo": "notas/nfe-compra-1.xml",
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
        "empresa": "distribuidora.json",
        "arquivo": "notas/nfe-compra-2.xml",
        "nNF": "1002",
        "dhEmi": "2027-03-16T09:00:00-03:00",
        "grupoTributacao": True,
        "itens": [
            ("AE-CRV-350", "cerveja-lata", "1440", "3.05"),
            ("AE-CHO-90", "chocolate-barra", "800", "4.10"),
            ("AE-BIS-140", "biscoito-pacote", "2600", "3.10"),
        ],
    },
    {
        "empresa": "distribuidora.json",
        "arquivo": "notas/nfe-item-sem-par.xml",
        "nNF": "1003",
        "dhEmi": "2027-03-18T09:00:00-03:00",
        "grupoTributacao": False,
        "itens": [
            ("AE-CHO-90", "chocolate-barra", "400", "4.10"),
            # NCM 22021000 e 19059090 existem no índice oficial do motor RR 1.7.2 (banco V0073).
            ("AE-REF-2L", None, "240", "6.20", "Refrigerante de cola, garrafa 2 L", "22021000", "UN"),
            ("AE-BIS-140", None, "100", "3.10", "Biscoito doce, pacote 140 g", "19059090", "UN"),
        ],
    },
    {
        "empresa": "carteira/vale-verde.json",
        "arquivo": "carteira/notas/nfe-vale-verde-1.xml",
        "nNF": "2001",
        "dhEmi": "2027-03-04T10:00:00-03:00",
        "grupoTributacao": True,
        "itens": [
            ("AE-BIS-140", "biscoito-pacote", "1200", "3.10"),
            ("AE-CHO-90", "chocolate-barra", "400", "4.10"),
            ("AE-CRV-350", "cerveja-lata", "720", "2.60"),
        ],
    },
    {
        "empresa": "carteira/vale-verde.json",
        "arquivo": "carteira/notas/nfe-vale-verde-2.xml",
        "nNF": "2002",
        "dhEmi": "2027-03-15T10:00:00-03:00",
        "grupoTributacao": True,
        "itens": [
            ("AE-BIS-140", "biscoito-pacote", "1200", "3.70"),
            ("AE-CHO-90", "chocolate-barra", "400", "4.90"),
        ],
    },
    {
        "empresa": "carteira/lagoa.json",
        "arquivo": "carteira/notas/nfe-lagoa-1.xml",
        "nNF": "3001",
        "dhEmi": "2027-03-05T11:00:00-03:00",
        "grupoTributacao": True,
        "itens": [
            ("AE-CHO-90", "chocolate-barra", "300", "4.10"),
            ("AE-ARZ-5", "arroz-5kg", "200", "21.50"),
        ],
    },
]


def carregar_empresa(nome: str) -> Distribuidora:
    return Distribuidora.model_validate_json((PASTA_DEMO / nome).read_text(encoding="utf-8"))


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
        Linha(demo.item(item_id), Decimal(qtd), Decimal(qtd) * Decimal(vun))
        for _, item_id, qtd, vun, *_ in nota["itens"]
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
    for numero, (cprod, item_id, qtd, vun, *fora) in enumerate(nota["itens"], start=1):
        if item_id is None:
            descricao, ncm, unidade = fora
        else:
            cat = demo.item(item_id)
            descricao, ncm, unidade = cat.descricao, cat.ncm, cat.unidade
        det = sub(inf, "det", nItem=str(numero))
        prod = sub(det, "prod")
        sub(prod, "cProd", cprod)
        sub(prod, "xProd", descricao)
        sub(prod, "NCM", ncm)
        sub(prod, "uCom", unidade)
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
    # CONTAAI_SAIDA_NOTAS permite gravar em outra pasta (o teste de reprodutibilidade usa isso).
    destino = Path(os.environ.get("CONTAAI_SAIDA_NOTAS") or PASTA_DEMO)
    with httpx.Client(timeout=30) as cli:
        for nota in NOTAS:
            demo = carregar_empresa(nota["empresa"])
            cuf = codigo_uf(cli, demo.empresa.uf)
            arvore = montar_nota(cli, demo, nota, cuf)
            (destino / nota["arquivo"]).parent.mkdir(parents=True, exist_ok=True)
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
