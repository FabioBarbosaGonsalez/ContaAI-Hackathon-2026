"""Presets de alíquota para 2027 (plano 11.5). Só entram valores com fonte verificada (ADR 0005).

Nenhum deles é alíquota oficial em vigor (P6): um é entrada de exemplo da documentação do motor e
o outro é a referência calculada pelo TCU, que o Senado ainda fixa por resolução.
"""

from __future__ import annotations

from decimal import Decimal

from app.contrato import PresetAliquotas, PresetsResposta

PRESETS = [
    PresetAliquotas(
        id="exemplo-documentacao",
        rotulo="Exemplo da documentação da calculadora (8,8%)",
        cbs=Decimal("8.8"),
        ibsEstadual=Decimal("0.05"),
        ibsMunicipal=Decimal("0.05"),
        impostoSeletivoAdValorem=Decimal("10.0"),
        fonte="Entradas do exemplo oficial em docs/exemplos.md da calculadora-rtc-regime-regular, tag 1.7.2.",
        ressalva="São entradas de exemplo, não alíquotas oficiais.",
    ),
    PresetAliquotas(
        id="referencia-tcu-2027",
        rotulo="Referência da CBS calculada pelo TCU para 2027 (11,3%), pendente do Senado",
        cbs=Decimal("11.3"),
        fonte='TCU, decisão de 28/10/2026 no processo TC 006.529/2026-7: "TCU aprovou alíquota de referência de '
        '11,3% para a CBS" (portal.tcu.gov.br, notícia de 28/10/2026).',
        ressalva='O Senado fixa a alíquota de referência por resolução. Segundo o TCU, ela "não corresponde, '
        'necessariamente, ao percentual que será efetivamente cobrado". Não há referência de IBS para 2027 nas '
        "fontes lidas: informe o IBS.",
    ),
]

AVISO = (
    "Os campos de alíquota começam vazios. Um preset só preenche o que tem fonte; o resto é premissa sua. "
    "Nenhum valor aqui é alíquota oficial em vigor."
)


def presets() -> PresetsResposta:
    return PresetsResposta(presets=PRESETS, aviso=AVISO)
