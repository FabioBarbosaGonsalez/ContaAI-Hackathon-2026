"""Mensagens de validação em português (E5, ADR 0009).

O FastAPI entrega os erros do Pydantic com a mensagem em inglês (`msg`). A tela mostra o `detail` e o
`detalhe` de cada campo como texto, então a frase precisa estar em português e ajudar quem preenche.

A tradução usa o `type` do erro (a lista estável do Pydantic, docs.pydantic.dev/latest/errors/validation_errors)
e o `ctx` dele, nunca o texto em inglês. A tabela cobre os tipos que as rotas do contrato geram, levantados com
entradas inválidas em todas as rotas (tests/test_mensagens.py). Tipo fora da tabela vira "Valor inválido." e
fica registrado no log (só o tipo, sem o valor enviado), para entrar na tabela.

Nada do que a pessoa enviou volta na mensagem: só os limites do contrato (tamanho, casas, valores aceitos).
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Mapping
from decimal import Decimal, InvalidOperation
from typing import Any

log = logging.getLogger("contaai")

GENERICA = "Valor inválido."

# Cada padrão (regex) do contrato com a frase que explica o formato. Padrão novo no contrato sem frase aqui
# reprova o teste test_todo_padrao_do_contrato_tem_frase.
PADROES: dict[str, str] = {
    r"^[0-9]{2}$": "Use exatamente 2 dígitos, sem pontos nem traços.",
    r"^[0-9]{3}$": "Use exatamente 3 dígitos, sem pontos nem traços.",
    r"^[0-9]{6}$": "Use exatamente 6 dígitos, sem pontos nem traços.",
    r"^[0-9]{8}$": "Use exatamente 8 dígitos, sem pontos nem traços.",
    r"^[0-9]{9}$": "Use exatamente 9 dígitos, sem pontos nem traços.",
    r"^[0-9]{14}$": "Use exatamente 14 dígitos, sem pontos nem traços.",
    r"^[A-Z]{2}$": "Use a sigla da UF com 2 letras maiúsculas (ex.: SP).",
    r"^(REG|VSN)-[0-9]{3}$": "Use um código de erro dos motores, como REG-011 ou VSN-015.",
    r"^[0-9a-f]{32}$": "Use o id do espaço de avaliação: 32 caracteres de 0 a 9 e de a a f.",
    r"^[a-z-]{3,40}$": "Use o nome de um tipo de problema: de 3 a 40 letras minúsculas ou hífens.",
    r"^[a-z0-9][a-z0-9-]{0,63}$": "Use até 64 letras minúsculas, dígitos ou hífens, sem começar com hífen.",
    r"^alerta-[0-9a-f]{16}$": "Use o id de um alerta: alerta- seguido de 16 caracteres de 0 a 9 e de a a f.",
    r"^[^@\s:]{1,64}@[^@\s:]+\.[^@\s:]+$": "Use um e-mail, como nome@empresa.com.br.",
    r"^[A-Za-z2-7]{4}-?[A-Za-z2-7]{4}-?[A-Za-z2-7]{5}$": "Use um código de recuperação, como ABCD-EFGH-IJKLM.",
}

# value_error que não nasce no ContaAI: o FastAPI recusa um campo de arquivo que veio como texto.
_VALUE_ERROR_EXTERNO: tuple[tuple[str, str], ...] = (("Expected UploadFile", "Envie um arquivo."),)


def _numero(valor: Any) -> str:
    """Limite do contrato no jeito brasileiro: 1000000000 → 1.000.000.000; 0.5 → 0,5."""
    try:
        d = Decimal(str(valor))
    except (InvalidOperation, ValueError):
        return str(valor)
    if not d.is_finite():
        return str(valor)
    texto = format(d.normalize() if d == d.to_integral_value() else d, "f")
    inteiro, _, frac = texto.partition(".")
    sinal = "-" if inteiro.startswith("-") else ""
    inteiro = inteiro.lstrip("-")
    grupos = f"{int(inteiro):,}".replace(",", ".")
    return f"{sinal}{grupos}" + (f",{frac}" if frac else "")


def _plural(n: Any, um: str, varios: str) -> str:
    return f"{n} {um}" if str(n) == "1" else f"{_numero(n)} {varios}"


def _valores(esperado: Any) -> str:
    """O ctx do Pydantic ("'a', 'b' or 'c'") vira "a, b ou c"."""
    itens = re.findall(r"'([^']*)'", str(esperado))
    if not itens:
        return str(esperado)
    return itens[0] if len(itens) == 1 else ", ".join(itens[:-1]) + " ou " + itens[-1]


def _padrao(ctx: Mapping[str, Any]) -> str:
    return PADROES.get(str(ctx.get("pattern", "")), "Formato inválido.")


def _value_error(ctx: Mapping[str, Any]) -> str:
    texto = str(ctx.get("error", "")).strip()
    for inicio, frase in _VALUE_ERROR_EXTERNO:
        if texto.startswith(inicio):
            return frase
    return texto or GENERICA  # as regras do contrato (model_validator) já falam português


_INTEIRO = "Informe um número inteiro."
_DECIMAL = "Informe um número, com ponto como separador decimal (ex.: 27.90)."
_DATA = "Informe uma data no formato AAAA-MM-DD (ex.: 2027-03-16)."
_BOOLEANO = "Informe true ou false."
_OBJETO = "Informe um objeto JSON."

TRADUCOES: dict[str, Callable[[Mapping[str, Any]], str]] = {
    "missing": lambda c: "Campo obrigatório.",
    "extra_forbidden": lambda c: "Campo que o contrato não prevê. Confira o nome.",
    "json_invalid": lambda c: "O corpo não é um JSON válido.",
    "model_attributes_type": lambda c: _OBJETO,
    "list_type": lambda c: "Informe uma lista.",
    "too_short": lambda c: f"Informe pelo menos {_plural(c.get('min_length'), 'item', 'itens')}.",
    "too_long": lambda c: f"Informe no máximo {_plural(c.get('max_length'), 'item', 'itens')}.",
    "string_type": lambda c: "Informe um texto.",
    "string_too_short": lambda c: f"Use pelo menos {_plural(c.get('min_length'), 'caractere', 'caracteres')}.",
    "string_too_long": lambda c: f"Use no máximo {_plural(c.get('max_length'), 'caractere', 'caracteres')}.",
    "string_pattern_mismatch": _padrao,
    "int_type": lambda c: _INTEIRO,
    "int_parsing": lambda c: _INTEIRO,
    "int_from_float": lambda c: _INTEIRO,
    "int_parsing_size": lambda c: "Número inteiro grande demais.",
    "decimal_type": lambda c: _DECIMAL,
    "decimal_parsing": lambda c: _DECIMAL,
    "finite_number": lambda c: "Informe um número finito (NaN e infinito não valem).",
    "decimal_max_places": lambda c: (
        f"Use no máximo {_plural(c.get('decimal_places'), 'casa decimal', 'casas decimais')}."
    ),
    "greater_than": lambda c: f"Informe um valor maior que {_numero(c.get('gt'))}.",
    "greater_than_equal": lambda c: f"Informe um valor maior ou igual a {_numero(c.get('ge'))}.",
    "less_than": lambda c: f"Informe um valor menor que {_numero(c.get('lt'))}.",
    "less_than_equal": lambda c: f"Informe um valor menor ou igual a {_numero(c.get('le'))}.",
    "bool_parsing": lambda c: _BOOLEANO,
    "date_type": lambda c: _DATA,
    "date_from_datetime_parsing": lambda c: _DATA,
    "date_from_datetime_inexact": lambda c: "Informe só a data (AAAA-MM-DD), sem a hora.",
    "enum": lambda c: f"Use um destes valores: {_valores(c.get('expected'))}.",
    "literal_error": lambda c: f"Use um destes valores: {_valores(c.get('expected'))}.",
    "value_error": _value_error,
}


def traduzir(erro: Mapping[str, Any]) -> str:
    """Frase em português para um erro do Pydantic (um item de `RequestValidationError.errors()`)."""
    tipo = str(erro.get("type", ""))
    traducao = TRADUCOES.get(tipo)
    if traducao is None:
        log.warning("Erro de validação sem tradução: %s", tipo)  # só o tipo: nunca o valor enviado
        return GENERICA
    return traducao(erro.get("ctx") or {})
