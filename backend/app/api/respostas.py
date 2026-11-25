"""Respostas de erro declaradas no OpenAPI. Todas saem como application/problem+json (ADR 0009); todo 422
também aceita ProblemaValidacao (ajuste feito em app.api.problemas.ajustar_openapi)."""

from __future__ import annotations

from typing import Any

from app.contrato import Problema, ProblemaCalculo, ProblemaMotor

Respostas = dict[int | str, dict[str, Any]]

MOTOR: Respostas = {
    422: {
        "model": ProblemaMotor,
        "description": "O motor recusou a operação (/problemas/motor-recusou, ex.: VSN-015) ou a entrada não "
        "segue o contrato (/problemas/entrada-invalida).",
    },
    502: {"model": ProblemaMotor, "description": "O motor devolveu uma resposta que o ContaAI não reconhece."},
    503: {"model": ProblemaMotor, "description": "Motor indisponível."},
}

CALCULO: Respostas = {
    **MOTOR,
    422: {
        "model": ProblemaCalculo | ProblemaMotor,
        "description": "Sem resposta para o cálculo pedido (/problemas/calculo-recusado: margem impossível, item que "
        "o motor não calcula, base do híbrido que não fecha, sem convergência), recusa do motor "
        "(/problemas/motor-recusou) ou entrada fora do contrato (/problemas/entrada-invalida).",
    },
}

TOKEN: Respostas = {401: {"description": "Token da demo ausente ou errado (header X-ContaAI-Token)."}}
LIMITE: Respostas = {429: {"description": "Limite de requisições por minuto atingido (header Retry-After)."}}
SO_MODO_REAL: Respostas = {501: {"description": "Rota que só funciona no modo real (CONTAAI_MODO=real)."}}

ESTADO: Respostas = {
    **TOKEN,
    404: {"description": "Empresa ou alerta não encontrado."},
    **LIMITE,
}

NFE: Respostas = {
    **MOTOR,
    **ESTADO,
    409: {
        "description": "A mesma nota (emitente, série e número) já foi importada com outro conteúdo, ou o estado "
        "mudou durante a importação (/problemas/nota-recusada)."
    },
    411: {"description": "Upload sem Content-Length."},
    413: {"description": "Arquivo maior que o limite para uma NF-e."},
    415: {"description": "O arquivo não é XML."},
    422: {
        "model": ProblemaMotor | Problema,
        "description": "XML que não é uma NF-e lida pelo ContaAI (/problemas/nota-invalida), destinatário que não "
        "é empresa cadastrada (/problemas/nota-recusada), recusa do motor ou entrada fora do contrato.",
    },
}

CHAT: Respostas = {
    **MOTOR,
    **TOKEN,
    429: {"description": "Limite de mensagens por minuto atingido (header Retry-After)."},
    503: {
        "model": ProblemaMotor | Problema,
        "description": "Motor (/problemas/motor-indisponivel) ou provedor de IA (/problemas/ia-indisponivel) "
        "indisponível.",
    },
}
