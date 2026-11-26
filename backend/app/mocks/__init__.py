"""Mocks da API (Etapa 0), gerados por scripts/gerar_mocks.py a partir dos motores em execução.

Todo valor de tributo nestes arquivos veio dos motores oficiais; nada foi digitado à mão.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.contrato import (
    AlertasResposta,
    BuscaNcmResposta,
    CarrinhoResposta,
    CatalogoResposta,
    ChatResposta,
    ErroDescricao,
    ExplicarResposta,
    NfeImportarResposta,
    NotasResposta,
    PainelContadorResposta,
    PrecoAlvoResposta,
    Regime,
    RegimeCompararResposta,
)

PASTA = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Mocks:
    carrinho: dict[Regime, CarrinhoResposta]
    preco_alvo: dict[Regime, PrecoAlvoResposta]
    regime_comparar: RegimeCompararResposta
    nfe_importar: NfeImportarResposta
    alertas: AlertasResposta
    catalogo: CatalogoResposta
    contador_painel: PainelContadorResposta
    notas: NotasResposta
    busca_ncm: dict[str, BuscaNcmResposta]
    explicar: dict[str, dict[Regime, ExplicarResposta]]
    erros: dict[str, ErroDescricao]
    chat: ChatResposta


def _ler(nome: str) -> Any:
    return json.loads((PASTA / nome).read_text(encoding="utf-8"))


@lru_cache
def carregar() -> Mocks:
    """Lê e valida todos os mocks no contrato. Um mock fora do contrato derruba a subida."""
    return Mocks(
        carrinho={Regime(k): CarrinhoResposta.model_validate(v) for k, v in _ler("carrinho.json").items()},
        preco_alvo={Regime(k): PrecoAlvoResposta.model_validate(v) for k, v in _ler("preco-alvo.json").items()},
        regime_comparar=RegimeCompararResposta.model_validate(_ler("regime-comparar.json")),
        nfe_importar=NfeImportarResposta.model_validate(_ler("nfe-importar.json")),
        alertas=AlertasResposta.model_validate(_ler("alertas.json")),
        catalogo=CatalogoResposta.model_validate(_ler("catalogo.json")),
        contador_painel=PainelContadorResposta.model_validate(_ler("contador-painel.json")),
        notas=NotasResposta.model_validate(_ler("notas.json")),
        busca_ncm={k: BuscaNcmResposta.model_validate(v) for k, v in _ler("busca-ncm.json").items()},
        explicar={
            item: {Regime(r): ExplicarResposta.model_validate(e) for r, e in por_regime.items()}
            for item, por_regime in _ler("explicar.json").items()
        },
        erros={k: ErroDescricao.model_validate(v) for k, v in _ler("erros.json").items()},
        chat=ChatResposta.model_validate(_ler("chat.json")),
    )
