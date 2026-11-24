"""Busca de NCM por texto num índice local (E2-02; pendência 3 do ADR 0003).

O índice (indice-ncm.json.gz) é gerado por scripts/gerar_indice_ncm.py a partir dos dados abertos
do motor RR, com a hierarquia oficial de cada NCM. A busca é por palavras, sem IA e sem sinônimos:
"cerveja" acha "Cervejas de malte", mas "refrigerante" não acha as bebidas da posição 22.02, cujo
nome oficial não usa essa palavra. Por isso o resultado é sempre uma lista de candidatos para o
usuário confirmar (P3), nunca a classificação.
"""

from __future__ import annotations

import gzip
import json
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

ARQUIVO_INDICE = Path(__file__).resolve().parent / "indice-ncm.json.gz"

# Palavras que não ajudam a achar a NCM (artigos, preposições, embalagens e unidades).
_IGNORAR = frozenset(
    "a o as os um uma de da do das dos e em no na nos nas para por com sem tipo marca "
    "pacote pct lata garrafa caixa cx barra unidade unidades un fardo saco kg g gr ml l lt litro litros".split()
)
_PALAVRA = re.compile(r"[a-z0-9]+")
_NCM = re.compile(r"^\d{8}$")
PESO_DESCRICAO, PESO_CAPITULO = 3, 1


def normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return sem_acento.lower().strip()


def palavras(texto: str) -> list[str]:
    return [p for p in _PALAVRA.findall(normalizar(texto)) if p not in _IGNORAR and not p.isdigit() and len(p) > 1]


@dataclass(frozen=True)
class NcmIndexada:
    ncm: str
    descricao: str
    capitulo: str
    tributadoPeloImpostoSeletivo: bool
    _desc: tuple[str, ...]
    _cap: tuple[str, ...]


@dataclass(frozen=True)
class Indice:
    fonte: str
    versaoApp: str
    versaoDb: str
    dataVigencia: str
    ncms: tuple[NcmIndexada, ...]

    def por_codigo(self, ncm: str) -> NcmIndexada | None:
        return next((n for n in self.ncms if n.ncm == ncm), None)


@lru_cache
def carregar(arquivo: Path = ARQUIVO_INDICE) -> Indice:
    bruto = json.loads(gzip.decompress(arquivo.read_bytes()).decode("utf-8"))
    return Indice(
        fonte=bruto["fonte"],
        versaoApp=bruto["versaoApp"],
        versaoDb=bruto["versaoDb"],
        dataVigencia=bruto["dataVigencia"],
        ncms=tuple(
            NcmIndexada(
                ncm=n["ncm"],
                descricao=n["descricao"],
                capitulo=n["capitulo"],
                tributadoPeloImpostoSeletivo=n["is"],
                _desc=tuple(palavras(n["descricao"])),
                _cap=tuple(palavras(n["capitulo"])),
            )
            for n in bruto["ncms"]
        ),
    )


def _casa_termo(consulta: str, termo: str) -> bool:
    """Prefixo nos dois sentidos, para plural e singular ("cerveja" × "cervejas", "chocolates" × "chocolate")."""
    return termo.startswith(consulta) or (len(termo) >= 5 and consulta.startswith(termo))


def _casa(consulta: str, termos: tuple[str, ...]) -> bool:
    return any(_casa_termo(consulta, t) for t in termos)


def _pontos(consulta: list[str], n: NcmIndexada) -> int:
    """3 por ocorrência na descrição (até 2 por palavra), mais 3 se a descrição começa por ela; 1 se só o capítulo casa."""
    pontos = 0
    for p in consulta:
        ocorrencias = sum(1 for t in n._desc if _casa_termo(p, t))
        if ocorrencias:
            pontos += PESO_DESCRICAO * min(ocorrencias, 2) + (
                PESO_DESCRICAO if n._desc and _casa_termo(p, n._desc[0]) else 0
            )
        elif _casa(p, n._cap):
            pontos += PESO_CAPITULO
    return pontos


def buscar(texto: str, limite: int = 3, indice: Indice | None = None) -> list[NcmIndexada]:
    """As NCMs que mais casam com as palavras do texto, das mais específicas para as menos.

    Um código de 8 dígitos é procurado direto. Uma NCM só entra se ao menos uma palavra casar na
    descrição (não basta o capítulo).
    """
    idx = indice or carregar()
    limpo = texto.strip().replace(".", "")
    if _NCM.match(limpo):
        achada = idx.por_codigo(limpo)
        return [achada] if achada else []
    consulta = palavras(texto)
    if not consulta:
        return []
    pontuadas = []
    for n in idx.ncms:
        if not any(_casa(p, n._desc) for p in consulta):
            continue
        # Empate: a descrição mais curta é a mais específica; depois, a ordem do código.
        pontuadas.append((-_pontos(consulta, n), len(n._desc), n.ncm, n))
    pontuadas.sort(key=lambda t: t[:3])
    return [n for *_, n in pontuadas[:limite]]
