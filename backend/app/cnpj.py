"""CNPJ numérico e alfanumérico (C3, ADR 0017).

Fontes, lidas em 2026-11-27:
- Receita Federal, página "CNPJ Alfanumérico" (gov.br): "O CNPJ Alfanumérico será atribuído, a partir de Julho de
  2026, exclusivamente a novas inscrições." e "Os números de CNPJ já existentes não sofrerão nenhuma alteração".
- Receita Federal, "Perguntas e respostas" do CNPJ alfanumérico: 14 posições, "AA.AAA.AAA/AAAA-DV", onde A "Poderá
  ser numerais de 0 a 9 e letras maiúsculas de A até Z" e DV é o dígito verificador pelo módulo 11.
- Serpro, "Cálculo dos dígitos verificadores de CNPJ alfanumérico": doze caracteres alfanuméricos e dois dígitos
  verificadores numéricos; o valor de cada caractere é o código ASCII menos 48; pesos de 2 a 9 da direita para a
  esquerda, recomeçando depois do oitavo; resto 0 ou 1 dá 0, senão 11 - resto. Exemplo do manual: 12ABC34501DE35.

O CNPJ numérico é o mesmo cálculo: para os dígitos, ASCII menos 48 é o próprio dígito.

Só letras maiúsculas: a Receita não fala em minúsculas. A tela converte o que a pessoa digita; a API recebe o CNPJ
já no formato oficial, sem pontos, barra nem traço.
"""

from __future__ import annotations

import re

PADRAO_CNPJ = r"^[0-9A-Z]{12}[0-9]{2}$"
_FORMATO = re.compile(PADRAO_CNPJ)


def _digito(base: str) -> str:
    soma = sum((ord(c) - 48) * (2 + i % 8) for i, c in enumerate(reversed(base)))
    resto = soma % 11
    return "0" if resto < 2 else str(11 - resto)


def digitos_verificadores(base: str) -> str:
    """Os dois DV dos 12 primeiros caracteres (já em maiúsculas)."""
    if not re.fullmatch(r"[0-9A-Z]{12}", base):
        raise ValueError("A base do CNPJ tem 12 caracteres: dígitos ou letras maiúsculas.")
    primeiro = _digito(base)
    return primeiro + _digito(base + primeiro)


def cnpj_valido(cnpj: str) -> bool:
    """Formato oficial (14 posições, as duas últimas numéricas) e os dois dígitos verificadores certos."""
    return bool(_FORMATO.fullmatch(cnpj)) and digitos_verificadores(cnpj[:12]) == cnpj[12:]
