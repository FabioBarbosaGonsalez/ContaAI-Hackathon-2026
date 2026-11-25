"""Lote de referência: o único lugar que define quantas unidades vão em cada cálculo por item (ADR 0011).

Os motores arredondam cada tributo ao centavo. Calcular 100 unidades e dividir reduz esse efeito no valor
por unidade. Usam este lote o preço-alvo, as margens dos alertas, a explicação do catálogo, o gerador de
mocks e a tela (que o lê de `CatalogoResposta.loteReferencia`, nunca de uma cópia própria).
"""

from __future__ import annotations

from decimal import Decimal

LOTE = Decimal(100)
