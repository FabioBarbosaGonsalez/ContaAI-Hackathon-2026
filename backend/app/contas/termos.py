"""A versão dos termos de uso que o cadastro exige aceitar (C2, B0; ADR 0015, revisão de 2026-11-26).

O texto dos termos fica na tela (`/termos`). A versão é a data em que esse texto passou a valer. Ela entra no
contrato como o único valor aceito em `termosAceitos` (enum do OpenAPI). Assim, o tipo gerado da tela
(`esquema.gen.ts`) só compila com a versão daqui.

Mudar o texto dos termos pede uma versão nova, aqui e na tela, no mesmo PR. Quem aceitou uma versão anterior
continua com ela gravada; pedir o aceite de novo fica para quando houver a primeira mudança.
"""

VERSAO_TERMOS = "2026-11-26"

MENSAGEM_VERSAO_ANTIGA = "Os termos de uso mudaram. Recarregue a página, leia a versão atual e aceite de novo."


def conferir_versao(versao: str) -> str:
    """Validador do contrato: só a versão atual passa. A frase vai como está para a tela (ADR 0009)."""
    if versao != VERSAO_TERMOS:
        raise ValueError(MENSAGEM_VERSAO_ANTIGA)
    return versao
