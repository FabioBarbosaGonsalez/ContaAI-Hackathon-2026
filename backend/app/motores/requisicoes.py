"""Monta as operações enviadas aos motores RR (observabilidade/regime-geral) e SN (não assistido).

Os itens podem ser do catálogo de demonstração ou da API: basta terem ncm, cst, cClassTrib,
unidade e impostoSeletivo (cst, cClassTrib, litrosPorUnidade).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Protocol


class ImpostoSeletivoItem(Protocol):
    cst: str
    cClassTrib: str
    litrosPorUnidade: Decimal | None


class ItemClassificado(Protocol):
    """ncm ou nbs (o catálogo de demonstração só tem ncm; ver _nbs)."""

    ncm: str | None
    cst: str
    cClassTrib: str
    unidade: str
    impostoSeletivo: ImpostoSeletivoItem | None


@dataclass(frozen=True)
class Linha:
    """Um item a calcular: o produto, a quantidade e a base (valor dos produtos da linha).

    valorImpostoSeletivo só é usado pelo motor SN, quando o IS incide na operação: deve ser o vIS
    devolvido pelo motor RR. Na revenda (IS com CST 200) fica vazio e vai como zero.
    """

    item: ItemClassificado
    quantidade: Decimal
    base: Decimal
    valorImpostoSeletivo: Decimal | None = None


@dataclass(frozen=True)
class AliquotasPremissa:
    """Alíquotas informadas pelo usuário (obrigatórias no RR a partir de 2027, P6)."""

    cbs: Decimal
    ibsEstadual: Decimal
    ibsMunicipal: Decimal
    impostoSeletivoAdValorem: Decimal | None = None


@dataclass(frozen=True)
class DasPremissa:
    """Linha de alíquotas efetivas do contribuinte no Simples (premissa rotulada, P8)."""

    anexo: str
    cAtivSN: str
    pCBSSN: Decimal
    pIBSSN: Decimal


# IS sem nova incidência (ex.: revenda 200007). A partir de 2027 o motor RR exige uma alíquota de IS
# para a NCM sujeita ao IS mesmo nesse caso (REG-035). Conferido no motor RR 1.7.2 (cerveja 22030000,
# 200007, 2027-03-16): com 0% e com 10% o vIS sai 0,00 e a CBS é a mesma. Então, quando o usuário não
# informa, o backend envia 0% e a premissa sai impressa (ADR 0006).
CST_IS_SEM_INCIDENCIA = "200"
IS_REVENDA_PREMISSA = Decimal(0)


def _numero(valor: Decimal) -> float:
    # O motor RR recebe números JSON; os valores têm no máximo 4 casas, sem perda na conversão.
    return float(valor)


def _nbs(item: ItemClassificado) -> str | None:
    return getattr(item, "nbs", None)


def operacao_rr(
    linhas: list[Linha], data_fato: date, uf: str, municipio: int, aliquotas: AliquotasPremissa | None
) -> dict[str, Any]:
    itens = []
    for numero, linha in enumerate(linhas, start=1):
        item = linha.item
        entrada: dict[str, Any] = {
            "numero": numero,
            "cst": item.cst,
            "cClassTrib": item.cClassTrib,
            "baseCalculo": _numero(linha.base),
            "quantidade": _numero(linha.quantidade),
            "unidade": item.unidade,
        }
        # Serviço vai com nbs, mercadoria com ncm (formato do exemplo oficial, docs/exemplos.md).
        if _nbs(item) is not None:
            entrada["nbs"] = _nbs(item)
        else:
            entrada["ncm"] = item.ncm
        nominais: dict[str, Any] | None = None
        if aliquotas is not None:
            nominais = {
                "cbs": _numero(aliquotas.cbs),
                "ibsEstadual": _numero(aliquotas.ibsEstadual),
                "ibsMunicipal": _numero(aliquotas.ibsMunicipal),
            }
        if item.impostoSeletivo is not None:
            litros_por_unidade = item.impostoSeletivo.litrosPorUnidade
            if litros_por_unidade is not None:
                qtd_is, unidade_is = linha.quantidade * litros_por_unidade, "LT"
            else:
                qtd_is, unidade_is = linha.quantidade, item.unidade
            entrada["quantidade"], entrada["unidade"] = _numero(qtd_is), unidade_is
            entrada["impostoSeletivo"] = {
                "cst": item.impostoSeletivo.cst,
                "cClassTrib": item.impostoSeletivo.cClassTrib,
                "baseCalculo": _numero(linha.base),
                "quantidade": _numero(qtd_is),
                "unidade": unidade_is,
            }
            if nominais is not None and aliquotas is not None:
                ad_valorem = aliquotas.impostoSeletivoAdValorem
                if ad_valorem is None and item.impostoSeletivo.cst == CST_IS_SEM_INCIDENCIA:
                    ad_valorem = IS_REVENDA_PREMISSA  # premissa rotulada (ADR 0006); sem ela, REG-035
                if ad_valorem is not None:
                    nominais["impostoSeletivo"] = {"adValorem": _numero(ad_valorem)}
        if nominais is not None:
            entrada["aliquotasNominais"] = nominais
        itens.append(entrada)
    return {
        "id": "contaai",
        "versao": "1.0.0",
        "dhFatoGerador": f"{data_fato.isoformat()}T10:00:00-03:00",
        "municipio": municipio,
        "uf": uf,
        "itens": itens,
    }


def _valor_is_sn(linha: Linha) -> str:
    if linha.valorImpostoSeletivo is not None:
        return f"{linha.valorImpostoSeletivo:.2f}"
    is_item = linha.item.impostoSeletivo
    if is_item is None or is_item.cst == "200":
        # Sem IS, ou IS sem nova incidência (CST 200, ex.: revenda 200007): o motor SN exige "0.00".
        return "0.00"
    raise ValueError("Item com IS tributado: informe em valorImpostoSeletivo o vIS devolvido pelo motor RR.")


def operacao_sn(linhas: list[Linha], data_fato: date, das: DasPremissa) -> dict[str, Any]:
    """Operação do modo não assistido (ADR 0001): NF-e (tpDoc 55), Simples (CRT 1)."""
    anexo = {"pCBSSN": str(das.pCBSSN), "pIBSSN": str(das.pIBSSN)}
    itens = [
        {
            "numero": numero,
            "cAtivSN": das.cAtivSN,
            "cClassTrib": linha.item.cClassTrib,
            "ncm": linha.item.ncm,
            "baseCalculo": f"{linha.base:.2f}",
            "valorImpostoSeletivo": _valor_is_sn(linha),
        }
        for numero, linha in enumerate(linhas, start=1)
    ]
    return {
        "id": "contaai",
        "versao": "3.0.0",
        "data": data_fato.isoformat(),
        "tpDoc": "55",
        "CRT": "1",
        "aliquotasEfetivas": {f"anexo{das.anexo}": anexo},
        "itens": itens,
    }
