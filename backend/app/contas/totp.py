"""Segundo fator por TOTP (RFC 6238, sobre o HOTP da RFC 4226), só com a biblioteca padrão (C1, ADR 0015).

Os aplicativos autenticadores usam, por padrão, HMAC-SHA1, 6 dígitos e passo de 30 s: é o que vai no endereço
otpauth://. O SHA-1 aqui é o do HMAC, que a RFC 6238 define; não guarda senha.

Requisitos do NIST SP 800-63B-4 (3.1.4.1 e 3.1.4.2): segredo de pelo menos 112 bits (aqui, 160), saída de pelo
menos 6 dígitos, passo de no máximo 2 minutos, validade pelo desvio esperado do relógio (aqui, um passo para cada
lado) e cada código aceito uma vez só (o passo usado fica gravado; só vale um passo maior).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
from urllib.parse import quote, urlencode

DIGITOS = 6
PASSO_S = 30
TOLERANCIA_PASSOS = 1
BYTES_SEGREDO = 20  # 160 bits
EMISSOR = "ContaAI"


def novo_segredo() -> str:
    """Base32 sem o preenchimento '=', como os aplicativos esperam."""
    return base64.b32encode(secrets.token_bytes(BYTES_SEGREDO)).decode("ascii").rstrip("=")


def _chave(segredo: str) -> bytes:
    return base64.b32decode(segredo + "=" * (-len(segredo) % 8), casefold=True)


def hotp(chave: bytes, contador: int, digitos: int = DIGITOS) -> str:
    """RFC 4226, 5.3: HMAC-SHA1 do contador, truncamento dinâmico e módulo 10^dígitos."""
    mac = hmac.new(chave, struct.pack(">Q", contador), hashlib.sha1).digest()
    deslocamento = mac[-1] & 0x0F
    numero = struct.unpack(">I", mac[deslocamento : deslocamento + 4])[0] & 0x7FFFFFFF
    return str(numero % 10**digitos).zfill(digitos)


def passo(instante_s: float) -> int:
    return int(instante_s // PASSO_S)


def conferir(segredo: str, codigo: str, instante_s: float, ultimo_passo: int) -> int | None:
    """O passo em que o código vale (para gravar como último usado), ou None. Só aceita passo depois do último:
    o mesmo código, ou um mais antigo, não entra de novo."""
    # isascii: o isdigit() aceita dígitos de outras escritas (ex.: árabes), e o hmac.compare_digest recusa texto
    # fora do ASCII com TypeError.
    if len(codigo) != DIGITOS or not (codigo.isascii() and codigo.isdigit()):
        return None
    chave = _chave(segredo)
    atual = passo(instante_s)
    achado = None
    for candidato in range(atual - TOLERANCIA_PASSOS, atual + TOLERANCIA_PASSOS + 1):
        # Compara todos os candidatos, sem parar no primeiro: o tempo não depende de qual acertou.
        if hmac.compare_digest(hotp(chave, candidato), codigo) and candidato > ultimo_passo:
            achado = candidato
    return achado


def endereco(segredo: str, conta: str) -> str:
    """otpauth://totp/ContaAI:<conta>?secret=...: o QR code da tela (C2) é este texto."""
    rotulo = quote(f"{EMISSOR}:{conta}", safe="@")
    parametros = urlencode(
        {"secret": segredo, "issuer": EMISSOR, "algorithm": "SHA1", "digits": DIGITOS, "period": PASSO_S}
    )
    return f"otpauth://totp/{rotulo}?{parametros}"
