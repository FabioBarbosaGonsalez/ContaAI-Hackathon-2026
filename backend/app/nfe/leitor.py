"""Leitor do XML da NF-e de compra (E4-01, plano 11.3, ADR 0008).

O XML vem do upload e não é confiável. Proteções, além do limite de tamanho da rota:

- **Sem DTD nem entidade.** Uma NF-e não tem DOCTYPE. O parser recusa qualquer declaração de
  DOCTYPE, de entidade ou referência a entidade externa antes de montar a árvore. Isso fecha a
  expansão de entidades (billion laughs, quadratic blowup) e a entidade externa, que a documentação
  do Python lista como os riscos do ElementTree ("XML vulnerabilities", Python 3.12).
- **Expat mínimo 2.6.0** (`EXPAT_MINIMO`): a mesma documentação diz que o Expat 2.6.0 ou mais novo
  não é vulnerável aos "large tokens". A checagem roda na importação deste módulo, ou seja, na subida.
- **Limites de estrutura:** profundidade, número de elementos e de itens (o leiaute da NF-e 4.00
  admite até 990 itens).
- **Validação de cada campo usado:** padrões fixos para códigos, números só em notação decimal
  simples (sem NaN, infinito, expoente ou sinal), textos com tamanho máximo e sem caracteres de
  controle. vProd precisa bater com qCom × vUnCom.

Nenhuma mensagem de erro repete trecho do XML: diz só qual campo falhou.
"""

from __future__ import annotations

import pyexpat
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

NS = "http://www.portalfiscal.inf.br/nfe"
EXPAT_MINIMO = (2, 6, 0)
MAX_PROFUNDIDADE = 16
MAX_ELEMENTOS = 100_000
MAX_ITENS = 990  # leiaute da NF-e 4.00: nItem de 1 a 990
TOLERANCIA_VPROD = Decimal("0.01")  # |qCom × vUnCom − vProd|; escolha nossa, para o arredondamento ao centavo

_DECIMAL = re.compile(r"^[0-9]{1,15}(\.[0-9]{1,10})?$")
_CONTROLE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class NotaInvalida(Exception):
    """O arquivo não é uma NF-e que o ContaAI lê. Vira 422 com a mensagem (sem trecho do XML)."""

    def __init__(self, mensagem: str) -> None:
        super().__init__(mensagem)
        self.mensagem = mensagem


def conferir_expat() -> None:
    if pyexpat.version_info < EXPAT_MINIMO:
        minimo = ".".join(map(str, EXPAT_MINIMO))
        raise RuntimeError(f"Expat {pyexpat.EXPAT_VERSION} é antigo para ler XML de upload; o mínimo é {minimo}.")


conferir_expat()


# ---------------------------------------------------------------------------
# Parser


def _arvore(conteudo: bytes) -> ET.Element:
    """Monta a árvore com o expat direto, para recusar DTD e entidades antes de qualquer expansão."""
    construtor = ET.TreeBuilder()
    parser = pyexpat.ParserCreate(namespace_separator="}")
    parser.SetParamEntityParsing(pyexpat.XML_PARAM_ENTITY_PARSING_NEVER)
    contagem = {"profundidade": 0, "elementos": 0}

    def recusar_dtd(*_: object) -> None:
        raise NotaInvalida("O arquivo tem DTD ou entidade XML. Uma NF-e não tem: envie o XML original da nota.")

    def recusar_entidade_externa(*_: object) -> int:
        recusar_dtd()
        return 0

    def inicio(tag: str, atributos: dict[str, str]) -> None:
        contagem["profundidade"] += 1
        contagem["elementos"] += 1
        if contagem["profundidade"] > MAX_PROFUNDIDADE:
            raise NotaInvalida("O XML tem aninhamento profundo demais para uma NF-e.")
        if contagem["elementos"] > MAX_ELEMENTOS:
            raise NotaInvalida("O XML tem elementos demais para uma NF-e.")
        construtor.start("{" + tag if "}" in tag else tag, atributos)

    def fim(tag: str) -> None:
        contagem["profundidade"] -= 1
        construtor.end("{" + tag if "}" in tag else tag)

    parser.StartDoctypeDeclHandler = recusar_dtd
    parser.EntityDeclHandler = recusar_dtd
    parser.UnparsedEntityDeclHandler = recusar_dtd
    parser.ExternalEntityRefHandler = recusar_entidade_externa
    parser.SkippedEntityHandler = recusar_dtd
    parser.StartElementHandler = inicio
    parser.EndElementHandler = fim
    parser.CharacterDataHandler = construtor.data
    try:
        parser.Parse(conteudo, True)
    except pyexpat.ExpatError:
        raise NotaInvalida("O arquivo não é um XML bem formado.") from None
    return construtor.close()


# ---------------------------------------------------------------------------
# Campos


def _q(caminho: str) -> str:
    return "/".join(f"{{{NS}}}{parte}" for parte in caminho.split("/"))


def _texto(pai: ET.Element, caminho: str, nome: str, maximo: int, obrigatorio: bool = True) -> str | None:
    el = pai.find(_q(caminho))
    valor = None if el is None or el.text is None else el.text.strip()
    if not valor:
        if obrigatorio:
            raise NotaInvalida(f"Campo {nome} ausente.")
        return None
    if len(valor) > maximo or _CONTROLE.search(valor):
        raise NotaInvalida(f"Campo {nome} inválido (tamanho ou caracteres).")
    return valor


def _padrao(pai: ET.Element, caminho: str, nome: str, padrao: str) -> str:
    valor = _texto(pai, caminho, nome, 60)
    if valor is None:  # _texto já recusa o campo obrigatório ausente; sem assert, que some com python -O
        raise NotaInvalida(f"Campo {nome} ausente.")
    if not re.fullmatch(padrao, valor):
        raise NotaInvalida(f"Campo {nome} fora do formato da NF-e.")
    return valor


def _decimal(pai: ET.Element, caminho: str, nome: str, positivo: bool = True) -> Decimal:
    valor = _texto(pai, caminho, nome, 30)
    if valor is None:  # _texto já recusa o campo obrigatório ausente; sem assert, que some com python -O
        raise NotaInvalida(f"Campo {nome} ausente.")
    if not _DECIMAL.fullmatch(valor):
        raise NotaInvalida(f"Campo {nome} não é um número decimal válido.")
    numero = Decimal(valor)
    if positivo and numero <= 0:
        raise NotaInvalida(f"Campo {nome} precisa ser maior que zero.")
    return numero


# ---------------------------------------------------------------------------
# Modelo lido


@dataclass(frozen=True)
class GrupoIbsCbs:
    """O grupo IBSCBS do item, quando a nota traz. credito = vCBS + vIBS do item (ADR 0003)."""

    cst: str
    cClassTrib: str
    vCBS: Decimal
    vIBS: Decimal
    monofasico: bool

    @property
    def credito(self) -> Decimal:
        return self.vCBS + self.vIBS


@dataclass(frozen=True)
class ItemLido:
    nItem: int
    cProd: str
    xProd: str
    ncm: str
    uCom: str
    qCom: Decimal
    vUnCom: Decimal
    vProd: Decimal
    ibscbs: GrupoIbsCbs | None


@dataclass(frozen=True)
class Participante:
    cnpj: str
    nome: str


@dataclass(frozen=True)
class NotaLida:
    serie: str
    numero: str
    dataEmissao: datetime
    emitente: Participante
    destinatario: Participante
    homologacao: bool
    itens: list[ItemLido]

    @property
    def temGrupoIbsCbs(self) -> bool:
        return any(i.ibscbs is not None for i in self.itens)


def _grupo(det: ET.Element, n: int) -> GrupoIbsCbs | None:
    grupo = det.find(_q("imposto/IBSCBS"))
    if grupo is None:
        return None
    cst = _padrao(grupo, "CST", f"IBSCBS/CST do item {n}", r"[0-9]{3}")
    cclass = _padrao(grupo, "cClassTrib", f"IBSCBS/cClassTrib do item {n}", r"[0-9]{6}")
    monofasico = grupo.find(_q("gIBSCBSMono")) is not None
    valores = grupo.find(_q("gIBSCBS"))
    if valores is None:
        # Sem o subgrupo de valores (ex.: operação sem incidência): não há CBS nem IBS destacados.
        return GrupoIbsCbs(cst, cclass, Decimal(0), Decimal(0), monofasico)
    return GrupoIbsCbs(
        cst=cst,
        cClassTrib=cclass,
        vCBS=_decimal(valores, "gCBS/vCBS", f"vCBS do item {n}", positivo=False),
        vIBS=_decimal(valores, "vIBS", f"vIBS do item {n}", positivo=False),
        monofasico=monofasico,
    )


def _item(det: ET.Element) -> ItemLido:
    n_texto = det.get("nItem", "")
    if not re.fullmatch(r"[1-9][0-9]{0,2}", n_texto) or int(n_texto) > MAX_ITENS:
        raise NotaInvalida("Atributo nItem de um item fora do formato da NF-e.")
    n = int(n_texto)
    prod = det.find(_q("prod"))
    if prod is None:
        raise NotaInvalida(f"Item {n} sem o grupo prod.")
    q_com = _decimal(prod, "qCom", f"qCom do item {n}")
    v_un = _decimal(prod, "vUnCom", f"vUnCom do item {n}")
    v_prod = _decimal(prod, "vProd", f"vProd do item {n}")
    if abs((q_com * v_un).quantize(Decimal("0.01"), ROUND_HALF_UP) - v_prod) > TOLERANCIA_VPROD:
        raise NotaInvalida(f"Item {n}: vProd não bate com qCom × vUnCom.")
    return ItemLido(
        nItem=n,
        cProd=_texto(prod, "cProd", f"cProd do item {n}", 60) or "",
        xProd=_texto(prod, "xProd", f"xProd do item {n}", 120) or "",
        ncm=_padrao(prod, "NCM", f"NCM do item {n}", r"[0-9]{8}"),
        uCom=_texto(prod, "uCom", f"uCom do item {n}", 6) or "",
        qCom=q_com,
        vUnCom=v_un,
        vProd=v_prod,
        ibscbs=_grupo(det, n),
    )


def ler_nfe(conteudo: bytes) -> NotaLida:
    """Lê a NF-e (raiz NFe ou nfeProc). Recusa o que não for NF-e modelo 55 de saída do emitente."""
    raiz = _arvore(conteudo)
    if raiz.tag == f"{{{NS}}}nfeProc":
        nfe = raiz.find(_q("NFe"))
        if nfe is None:
            raise NotaInvalida("nfeProc sem a NF-e.")
        raiz = nfe
    if raiz.tag != f"{{{NS}}}NFe":
        raise NotaInvalida("O arquivo não é uma NF-e (raiz NFe no namespace do portal fiscal).")
    inf = raiz.find(_q("infNFe"))
    if inf is None:
        raise NotaInvalida("NF-e sem infNFe.")
    if inf.get("versao") != "4.00":
        raise NotaInvalida("Só a NF-e do leiaute 4.00 é lida.")

    if _padrao(inf, "ide/mod", "mod", r"[0-9]{2}") != "55":
        raise NotaInvalida("Só a NF-e modelo 55 é lida (a NFC-e, modelo 65, não é nota de compra entre empresas).")
    if _padrao(inf, "ide/tpNF", "tpNF", r"[01]") != "1":
        raise NotaInvalida("A nota não é de saída do fornecedor (tpNF diferente de 1).")
    tp_amb = _padrao(inf, "ide/tpAmb", "tpAmb", r"[12]")
    dh_texto = _texto(inf, "ide/dhEmi", "dhEmi", 25) or ""
    try:
        dh_emi = datetime.fromisoformat(dh_texto)
    except ValueError:
        raise NotaInvalida("Campo dhEmi fora do formato da NF-e.") from None
    if dh_emi.tzinfo is None:
        raise NotaInvalida("Campo dhEmi sem fuso horário.")

    if inf.find(_q("emit/CNPJ")) is None:
        raise NotaInvalida("O emitente precisa ter CNPJ (fornecedor pessoa jurídica).")
    if inf.find(_q("dest/CNPJ")) is None:
        raise NotaInvalida("O destinatário precisa ter CNPJ.")
    emitente = Participante(
        cnpj=_padrao(inf, "emit/CNPJ", "CNPJ do emitente", r"[0-9]{14}"),
        nome=_texto(inf, "emit/xNome", "xNome do emitente", 60) or "",
    )
    destinatario = Participante(
        cnpj=_padrao(inf, "dest/CNPJ", "CNPJ do destinatário", r"[0-9]{14}"),
        nome=_texto(inf, "dest/xNome", "xNome do destinatário", 60) or "",
    )

    dets = inf.findall(_q("det"))
    if not dets:
        raise NotaInvalida("A nota não tem itens.")
    if len(dets) > MAX_ITENS:
        raise NotaInvalida(f"A nota tem mais de {MAX_ITENS} itens.")
    itens = [_item(d) for d in dets]
    if len({i.nItem for i in itens}) != len(itens):
        raise NotaInvalida("A nota tem nItem repetido.")

    return NotaLida(
        serie=_padrao(inf, "ide/serie", "serie", r"[0-9]{1,3}"),
        numero=_padrao(inf, "ide/nNF", "nNF", r"[1-9][0-9]{0,8}"),
        dataEmissao=dh_emi,
        emitente=emitente,
        destinatario=destinatario,
        homologacao=tp_amb == "2",
        itens=itens,
    )
