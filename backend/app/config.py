"""Configuração do backend por variáveis de ambiente (ou backend/.env, que fica fora do git)."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Configuracao(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CONTAAI_", env_file=".env", extra="ignore")

    modo: Literal["mock", "real"] = Field(
        default="mock",
        description="mock: rotas respondem com app/mocks. real: rotas já implementadas calculam pelos motores "
        "(E1: /carrinho/calcular); as demais respondem 501 até a sua etapa.",
    )
    motor_rr_url: str = Field(
        default="http://127.0.0.1:8080/api", validation_alias=AliasChoices("CONTAAI_MOTOR_RR_URL", "MOTOR_RR_URL")
    )
    motor_sn_url: str = Field(
        default="http://127.0.0.1:8082/api", validation_alias=AliasChoices("CONTAAI_MOTOR_SN_URL", "MOTOR_SN_URL")
    )
    # Versões fixadas (P5): os testes conferem que são as mesmas dos Dockerfiles.
    versao_rr: str = "1.7.2"
    versao_sn: str = "1.0.2"
    cors_origens: list[str] = ["http://localhost:3000"]
    timeout_motores_s: float = 3.0  # /saude
    timeout_calculo_s: float = 20.0  # chamadas de cálculo (a primeira depois da subida é mais lenta)
    cache_motores_itens: int = 512  # respostas dos motores guardadas em memória (0 desliga)
    tamanho_max_nfe_bytes: int = 1_000_000


@lru_cache
def configuracao() -> Configuracao:
    return Configuracao()
