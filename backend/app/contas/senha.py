"""Senha (C1, ADR 0015): regras do NIST SP 800-63B-4 (3.1.1.2) e hash Argon2id (OWASP, Password Storage).

- No mínimo 8 caracteres, porque toda conta real tem segundo fator (o NIST permite 8 só para a senha que faz
  parte de uma autenticação de múltiplos fatores; sozinha, ela precisaria de 15). Até 128 aceitos (o NIST pede
  pelo menos 64). Sem regra de composição.
- A senha inteira é comparada com a lista de senhas comuns e com palavras do contexto (o produto e o e-mail).
- Normalização NFKC antes do hash, para que o mesmo texto digitado em teclados diferentes dê o mesmo resultado.
- Argon2id com os parâmetros mínimos do OWASP: 19 MiB, 2 passes, paralelismo 1.
"""

from __future__ import annotations

import gzip
import unicodedata
from functools import lru_cache
from pathlib import Path

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

MINIMO = 8
MAXIMO = 128
# Lista do SecLists (MIT): Passwords/Common-Credentials/100k-most-used-passwords-NCSC.txt, só as de 8 ou mais
# caracteres, em NFKC e minúsculas. Origem e conferência em app/contas/LEIA-ME.md.
LISTA = Path(__file__).with_name("senhas_comuns.txt.gz")
PALAVRAS_DO_PRODUTO = ("contaai", "conta ai", "contaai123", "serraazul", "serra azul")

_HASHER = PasswordHasher(time_cost=2, memory_cost=19 * 1024, parallelism=1, hash_len=32, salt_len=16)


class SenhaRecusada(ValueError):
    """A senha não pode ser usada. A mensagem vai para a pessoa."""


def normalizar(senha: str) -> str:
    return unicodedata.normalize("NFKC", senha)


@lru_cache(maxsize=1)
def senhas_comuns() -> frozenset[str]:
    with gzip.open(LISTA, "rt", encoding="utf-8") as arquivo:
        return frozenset(linha for linha in arquivo.read().splitlines() if linha)


def conferir_nova(senha: str, email: str) -> str:
    """A senha normalizada, ou SenhaRecusada com o motivo."""
    texto = normalizar(senha)
    if len(texto) < MINIMO:
        raise SenhaRecusada(f"A senha precisa ter pelo menos {MINIMO} caracteres.")
    if len(texto) > MAXIMO:
        raise SenhaRecusada(f"A senha pode ter no máximo {MAXIMO} caracteres.")
    comparada = texto.casefold()
    local = email.split("@", 1)[0].casefold()
    if comparada in senhas_comuns() or comparada in PALAVRAS_DO_PRODUTO or comparada in (email.casefold(), local):
        raise SenhaRecusada("Essa senha é muito comum ou fácil de adivinhar. Escolha outra.")
    if len(set(comparada)) == 1:
        raise SenhaRecusada("Essa senha é muito comum ou fácil de adivinhar. Escolha outra.")
    return texto


def gerar_hash(senha_normalizada: str) -> str:
    return _HASHER.hash(senha_normalizada)


def confere(hash_guardado: str, senha: str) -> bool:
    try:
        return _HASHER.verify(hash_guardado, normalizar(senha))
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def precisa_refazer(hash_guardado: str) -> bool:
    """Parâmetros mudaram desde o hash: refazer depois de uma entrada certa."""
    return _HASHER.check_needs_rehash(hash_guardado)


# Hash de uma senha qualquer, para que um e-mail sem conta passe pelo mesmo trabalho (e pelo mesmo tempo) que
# um e-mail com conta (OWASP, Authentication Cheat Sheet).
@lru_cache(maxsize=1)
def hash_de_mentira() -> str:
    return _HASHER.hash("senha de mentira para igualar o tempo")
