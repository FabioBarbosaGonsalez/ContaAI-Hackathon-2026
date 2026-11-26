"""Administração das contas, só no servidor (não há rota HTTP para isto).

    uv run python -m app.contas desbloquear <e-mail>

Desbloqueia a conta depois das 100 falhas seguidas (NIST SP 800-63B-4, 3.2.2) e zera a espera. Confira antes,
por outro canal, que quem pede é a dona da conta.
"""

from __future__ import annotations

import sys

from app.config import configuracao
from app.contas.servico import Contas


def main(argumentos: list[str]) -> int:
    if len(argumentos) != 2 or argumentos[0] != "desbloquear":
        print(__doc__)
        return 2
    if Contas(configuracao().contas_caminho).desbloquear(argumentos[1]):
        print("Conta desbloqueada.")
        return 0
    print("Nenhuma conta com este e-mail.")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
