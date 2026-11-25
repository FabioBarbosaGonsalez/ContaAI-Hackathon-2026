"""Configuração do backend por variáveis de ambiente (ou backend/.env, que fica fora do git)."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Configuracao(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CONTAAI_", env_file=".env", extra="ignore")

    modo: Literal["mock", "real"] = Field(
        default="mock",
        description="mock: rotas respondem com app/mocks. real: rotas já implementadas calculam pelos motores "
        "(E1: carrinho e preço-alvo; E2: busca de NCM, explicação, erros e chat); as demais respondem 501 até a "
        "sua etapa.",
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

    # Agente (E2, ADR 0006). "roteiro" não usa IA nem chave: é o padrão gratuito e o dublê dos testes.
    llm_provedor: str = Field(default="roteiro", description="Nome registrado em app/agente/provedor.py.")
    llm_modelo: str | None = None
    llm_chave: SecretStr | None = Field(default=None, description="Só no backend/.env (fora do git). Nunca vai a log.")
    llm_url: str | None = Field(default=None, description="URL base da API, para provedores que precisam.")
    llm_timeout_s: float = 30.0  # cada chamada ao provedor
    llm_tempo_total_s: float = 90.0  # uma mensagem do chat inteira (todas as rodadas e ferramentas)
    llm_max_rodadas: int = 6  # respostas do provedor por mensagem (a última sem ferramentas)
    llm_max_chamadas: int = 16  # chamadas de ferramenta por mensagem
    llm_max_tokens: int = 1024  # teto de tokens de saída por resposta do provedor

    # Proteção da demo pública (ADR 0006): o provedor de IA custa dinheiro e cada pergunta chama os motores.
    token_demo: SecretStr | None = Field(
        default=None, description="Se definido, /chat exige o header X-ContaAI-Token com este valor."
    )
    limite_chat_por_minuto: int = 10  # por IP; 0 desliga
    limite_geral_por_minuto: int = 120  # por IP, nas rotas que chamam os motores; 0 desliga
    # Uma busca de NCM nova faz até ~430 consultas ao motor (3 NCMs × ~144 classificações): limite próprio.
    limite_busca_por_minuto: int = 20  # por IP, em GET /busca/ncm; 0 desliga

    @field_validator("llm_modelo", "llm_chave", "llm_url", "token_demo", mode="before")
    @classmethod
    def vazio_e_nao_definido(cls, valor: object) -> object:
        """CONTAAI_TOKEN_DEMO= (vazio, como no .env.example) vale como não definido, e não como token ''."""
        return None if isinstance(valor, str) and not valor.strip() else valor


@lru_cache
def configuracao() -> Configuracao:
    return Configuracao()
