"""A "tomada" da IA (ADR 0006): uma interface e um registro de adaptadores.

Para ligar um provedor (Claude, Gemini, um compatível com a API da OpenAI etc.):
1. criar app/agente/provedores/<nome>.py com uma classe que implemente ProvedorLLM (traduzir
   Pedido → API do provedor → RespostaModelo), usando o httpx recebido (sem SDK do fornecedor);
2. registrar a fábrica em PROVEDORES abaixo;
3. configurar no backend/.env: CONTAAI_LLM_PROVEDOR, CONTAAI_LLM_MODELO, CONTAAI_LLM_CHAVE
   (e CONTAAI_LLM_URL, se o provedor precisar);
4. rodar tests/test_provedores.py, que vale para todo adaptador registrado, e a bateria de
   perguntas com o provedor real (uv run pytest -m llm), que gasta crédito.

Nada mais muda: ferramentas, loop, verificador e contrato são os mesmos para todos.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

import httpx

from app.agente.tipos import Pedido, RespostaModelo
from app.config import Configuracao


class ProvedorFalhou(Exception):
    """Falha do provedor (rede, limite, chave, formato). A mensagem vai ao usuário: sem chave nem URL."""

    def __init__(self, mensagem: str) -> None:
        super().__init__(mensagem)
        self.mensagem = mensagem


class ProvedorNaoConfigurado(ProvedorFalhou):
    pass


class ProvedorLLM(Protocol):
    nome: str

    async def responder(self, pedido: Pedido) -> RespostaModelo: ...


Fabrica = Callable[[Configuracao, httpx.AsyncClient], ProvedorLLM]


def _roteiro(cfg: Configuracao, http: httpx.AsyncClient) -> ProvedorLLM:
    from app.agente.provedores.roteiro import Roteiro

    return Roteiro()


# Provedores disponíveis. A IA real entra aqui quando o time escolher (ADR 0006).
PROVEDORES: dict[str, Fabrica] = {"roteiro": _roteiro}


def criar_provedor(cfg: Configuracao, http: httpx.AsyncClient) -> ProvedorLLM:
    fabrica = PROVEDORES.get(cfg.llm_provedor)
    if fabrica is None:
        raise ProvedorNaoConfigurado(
            f"Provedor de IA '{cfg.llm_provedor}' não está disponível. Opções: {', '.join(sorted(PROVEDORES))}."
        )
    return fabrica(cfg, http)
