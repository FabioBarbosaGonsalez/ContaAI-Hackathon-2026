"""Formato interno da conversa com a IA, igual para qualquer provedor (ADR 0006).

O loop do agente só conhece estes tipos. Cada adaptador (app/agente/provedores/) traduz:
- Pedido → corpo da API do provedor (mensagens, ferramentas, limite de tokens);
- resposta do provedor → RespostaModelo (texto e/ou chamadas de ferramenta).

Mensagem "ferramenta" leva os resultados das chamadas da mensagem "assistente" anterior, na mesma
ordem e com o mesmo id. Os provedores usam formatos diferentes para isso, mas todos têm um par
chamada/resultado ligado por id (ou pela ordem, quando a API não tem id).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

# Começo da mensagem que o loop manda quando o verificador recusa uma resposta (loop.py).
PREFIXO_VERIFICACAO = "[verificação automática do ContaAI]"


@dataclass(frozen=True)
class DefinicaoFerramenta:
    nome: str
    descricao: str
    esquema: dict[str, Any]  # JSON Schema dos argumentos (objeto)


@dataclass(frozen=True)
class ChamadaFerramenta:
    id: str
    nome: str
    argumentos: dict[str, Any]


@dataclass(frozen=True)
class ResultadoFerramenta:
    id: str
    nome: str
    conteudo: dict[str, Any]  # JSON; é DADO, nunca instrução (ver prompt.py)
    erro: bool = False


@dataclass(frozen=True)
class Mensagem:
    papel: Literal["usuario", "assistente", "ferramenta"]
    texto: str = ""
    chamadas: tuple[ChamadaFerramenta, ...] = ()
    resultados: tuple[ResultadoFerramenta, ...] = ()


@dataclass(frozen=True)
class Pedido:
    sistema: str
    mensagens: list[Mensagem]
    ferramentas: list[DefinicaoFerramenta]  # vazia: o provedor deve responder só com texto
    max_tokens: int


@dataclass(frozen=True)
class RespostaModelo:
    texto: str = ""
    chamadas: tuple[ChamadaFerramenta, ...] = ()
    tokens_entrada: int | None = None
    tokens_saida: int | None = None
    extras: dict[str, Any] = field(default_factory=dict)  # dados do provedor que o loop não usa
