"""Cache em memória das respostas dos motores (E1-03).

Os motores são determinísticos para a mesma operação e a mesma versão, que é fixa (P5). A chave
é o motor + a operação em JSON canônico, e o valor é o corpo e os headers de uma resposta 200.
Fica só na memória do processo: não vai a disco nem a log, e some quando o backend reinicia
(é o que acontece ao trocar a versão de um motor). Ninguém lê o dado de outra pessoa: só é
reaproveitada a resposta do motor para uma operação idêntica.
"""

from __future__ import annotations

import json
from collections import OrderedDict
from collections.abc import Mapping
from typing import Any


class CacheRespostas:
    def __init__(self, max_itens: int = 512) -> None:
        self.max_itens = max_itens
        self._itens: OrderedDict[str, tuple[bytes, dict[str, str]]] = OrderedDict()
        self.acertos = 0
        self.faltas = 0

    @staticmethod
    def chave(motor: str, operacao: Mapping[str, Any]) -> str:
        return motor + "|" + json.dumps(operacao, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    def obter(self, chave: str) -> tuple[bytes, dict[str, str]] | None:
        achado = self._itens.get(chave)
        if achado is None:
            self.faltas += 1
            return None
        self._itens.move_to_end(chave)
        self.acertos += 1
        return achado

    def guardar(self, chave: str, corpo: bytes, headers: dict[str, str]) -> None:
        if self.max_itens <= 0:
            return
        self._itens[chave] = (corpo, dict(headers))
        self._itens.move_to_end(chave)
        while len(self._itens) > self.max_itens:
            self._itens.popitem(last=False)

    def __len__(self) -> int:
        return len(self._itens)
