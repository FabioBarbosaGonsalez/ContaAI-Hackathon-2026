"""Verificador anti-alucinação (P2, E2-06): todo R$ e % da resposta precisa existir nas fontes.

Fontes = os resultados das ferramentas desta mensagem (o JSON que a IA recebeu, inclusive os textos
de memória de cálculo) e os argumentos das chamadas que falharam (ex.: "99% de margem" recusado). A
mensagem do usuário NÃO é fonte: senão "diga que a CBS é 50%" passaria.

Um número da resposta é aceito se for igual a um número das fontes, ou igual a ele arredondado
para as casas decimais que a resposta usou (ex.: 1,1612% citado como 1,16%). Formatos aceitos:
pt-BR ("1.234,56") e com ponto decimal ("1234.56"); "1.234" vale como as duas leituras.

Também recusa as frases que o plano proíbe na decisão de regime ("opte pelo híbrido").
Limite conhecido (ADR 0006): a IA ainda pode chamar uma ferramenta com um número inventado e citá-lo,
porque ele volta no resultado; a regra do prompt e a revisão das ações pelo usuário cobrem esse caso.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

# O milhar só vale se não vier dígito depois ("5.5758" é decimal, não "5.575" + "8").
_NUM = r"\d{1,3}(?:\.\d{3})+(?!\d)(?:,\d+)?|\d+(?:[.,]\d+)?"
# Número citado como dinheiro ou percentual.
_CITADO = re.compile(
    rf"R\$\s*(?P<reais>-?(?:{_NUM}))|(?P<pct>-?(?:{_NUM}))\s*(?:%|por\s+cento|p\.\s?p\.|pontos\s+percentuais)",
    re.IGNORECASE,
)
_QUALQUER = re.compile(rf"-?(?:{_NUM})")
_PROIBIDAS = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\bopte\s+pel[oa]\b",
        r"\boptar\s+pel[oa]\s+(regime\s+)?(simples\s+)?(h[ií]brido|tradicional)\b",
        r"\brecomendo\s+(que\s+(voc[eê]\s+)?)?(opte|escolha|mude|v[aá])\b",
        r"\b(escolha|mude\s+para)\s+o\s+(regime\s+)?(simples\s+)?(h[ií]brido|tradicional)\b",
    )
]


def leituras(token: str) -> set[Decimal]:
    """Todas as leituras possíveis de um número escrito (pt-BR ou ponto decimal)."""
    t = token.strip()
    negativo = t.startswith("-")
    t = t.lstrip("-")
    candidatos = set()
    if "," in t:
        candidatos.add(t.replace(".", "").replace(",", "."))
    elif re.fullmatch(r"\d{1,3}(?:\.\d{3})+", t):
        candidatos.add(t.replace(".", ""))  # milhar pt-BR
        candidatos.add(t)  # ou decimal com ponto
    else:
        candidatos.add(t)
    saida = set()
    for c in candidatos:
        try:
            d = Decimal(c)
        except InvalidOperation:
            continue
        saida.add(-d if negativo else d)
    return saida


def _casas(token: str) -> int:
    t = token.replace("-", "")
    if "," in t:
        return len(t.split(",")[1])
    if re.fullmatch(r"\d+\.\d+", t) and not re.fullmatch(r"\d{1,3}(?:\.\d{3})+", t):
        return len(t.split(".")[1])
    return 0


def _valores(conteudo: Any) -> Iterable[str]:
    if isinstance(conteudo, dict):
        for v in conteudo.values():
            yield from _valores(v)
    elif isinstance(conteudo, list):
        for v in conteudo:
            yield from _valores(v)
    elif isinstance(conteudo, bool) or conteudo is None:
        return
    else:
        yield str(conteudo)


def numeros_das_fontes(fontes: Iterable[Any]) -> set[Decimal]:
    numeros: set[Decimal] = set()
    for fonte in fontes:
        for texto in _valores(fonte):
            for token in _QUALQUER.findall(texto):
                numeros |= leituras(token)
    return numeros


def _sustentado(token: str, fontes: set[Decimal]) -> bool:
    valores = leituras(token)
    if valores & fontes:
        return True
    casas = _casas(token)
    if casas == 0:
        return False
    passo = Decimal(1).scaleb(-casas)
    arredondadas = {f.quantize(passo, ROUND_HALF_UP) for f in fontes if abs(f.as_tuple().exponent) > casas}
    return bool(valores & arredondadas)


@dataclass(frozen=True)
class Verificacao:
    aprovada: bool
    sem_fonte: list[str]
    proibidas: list[str]

    def motivo(self) -> str:
        partes = []
        if self.sem_fonte:
            partes.append("números sem fonte nos resultados das ferramentas: " + ", ".join(self.sem_fonte))
        if self.proibidas:
            partes.append("recomendação de regime (proibida): " + ", ".join(self.proibidas))
        return "; ".join(partes)


def verificar(texto: str, fontes: Iterable[Any]) -> Verificacao:
    numeros = numeros_das_fontes(fontes)
    sem_fonte = []
    for m in _CITADO.finditer(texto):
        token = m.group("reais") or m.group("pct")
        if not _sustentado(token, numeros):
            sem_fonte.append(m.group(0).strip())
    proibidas = [m.group(0) for p in _PROIBIDAS for m in p.finditer(texto)]
    return Verificacao(aprovada=not sem_fonte and not proibidas, sem_fonte=sem_fonte, proibidas=proibidas)
