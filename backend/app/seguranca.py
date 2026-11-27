"""Proteção da demo pública (E2-08, ADR 0006): limite de requisições por IP e token do chat.

Sem dependência nova: janela deslizante de 60 s em memória, por processo. A tabela de IPs tem
tamanho máximo (os mais antigos saem), para que muitos IPs diferentes não esgotem a memória.

O IP é o da conexão (request.client.host). Atrás de um proxy reverso todos chegam com o IP do
proxy: nesse caso o limite vira global, o que ainda protege o crédito de IA. Ler X-Forwarded-For
só é seguro se o proxy for nosso e o sobrescrever (decisão da E6, no deploy).
"""

from __future__ import annotations

import secrets
import time
from collections import OrderedDict, deque

from pydantic import SecretStr

JANELA_S = 60.0
MAX_IPS = 10_000
# Métodos que mudam o estado: passam pela defesa contra CSRF (app.api.middlewares) e o OpenAPI declara o 403 dela
# (app.api.problemas.ajustar_openapi).
METODOS_INSEGUROS = ("POST", "PUT", "PATCH", "DELETE")


class LimitadorPorIp:
    def __init__(self, por_minuto: int, max_ips: int = MAX_IPS) -> None:
        self.por_minuto = por_minuto
        self.max_ips = max_ips
        self._vistos: OrderedDict[str, deque[float]] = OrderedDict()

    def permitir(self, ip: str, agora: float | None = None) -> tuple[bool, int]:
        """(permitido, segundos até liberar). por_minuto ≤ 0 desliga o limite."""
        if self.por_minuto <= 0:
            return True, 0
        agora = time.monotonic() if agora is None else agora
        fila = self._vistos.get(ip)
        if fila is None:
            fila = deque()
            self._vistos[ip] = fila
            while len(self._vistos) > self.max_ips:
                self._vistos.popitem(last=False)
        self._vistos.move_to_end(ip)
        while fila and agora - fila[0] >= JANELA_S:
            fila.popleft()
        if len(fila) >= self.por_minuto:
            return False, max(1, int(JANELA_S - (agora - fila[0])) + 1)
        fila.append(agora)
        return True, 0


def token_confere(esperado: SecretStr | None, recebido: str | None) -> bool:
    """Sem token configurado, o chat é aberto (desenvolvimento). Comparação em tempo constante."""
    if esperado is None:
        return True
    if not recebido:
        return False
    return secrets.compare_digest(esperado.get_secret_value().encode(), recebido.encode())
