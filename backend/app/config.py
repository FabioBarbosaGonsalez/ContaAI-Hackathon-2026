"""Configuração do backend por variáveis de ambiente (ou backend/.env, que fica fora do git)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.dados_demo import PASTA_DEMO


class Configuracao(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CONTAAI_", env_file=".env", extra="ignore")

    modo: Literal["mock", "real"] = Field(
        default="mock",
        description="mock: rotas respondem com app/mocks (as que mudam o estado respondem 501). real: as rotas "
        "calculam pelos motores (E1: carrinho e preço-alvo; E2: busca de NCM, explicação, erros e chat; E3: "
        "comparação de regimes; E4: NF-e, alertas, catálogo e painel, com o estado no SQLite).",
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
    # Origens do frontend (CORS e checagem de Origin nos POST, ADR 0011). A tela da E5 roda na porta 3000.
    cors_origens: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    # Hosts aceitos no header Host (contra DNS rebinding, ADR 0011). No deploy, o domínio público (E6).
    hosts_permitidos: list[str] = ["127.0.0.1", "localhost"]
    # /docs, /redoc e /openapi.json. O Swagger carrega scripts de uma CDN: no deploy (E6), false.
    docs_publica: bool = True
    tamanho_max_json_bytes: int = Field(default=1_000_000, gt=0, description="Corpo máximo das rotas JSON.")
    timeout_motores_s: float = 3.0  # /saude
    timeout_calculo_s: float = 20.0  # chamadas de cálculo (a primeira depois da subida é mais lenta)
    cache_motores_itens: int = 512  # respostas dos motores guardadas em memória (0 desliga)
    tamanho_max_nfe_bytes: int = 1_000_000
    # Estado (E4, ADR 0008). Fora do git (.gitignore: .dados/ e *.db). No deploy, um volume do container.
    banco_caminho: Path = Field(default=Path(__file__).resolve().parents[1] / ".dados" / "contaai.db")
    semear_ao_subir: bool = True  # modo real com o banco vazio: carrega as sementes de data/demo na subida
    # Pasta com sementes.json, as empresas e as notas. No container do deploy, a pasta montada ou copiada.
    pasta_demo: Path = PASTA_DEMO
    # Espaços de avaliação (D2, ADR 0010): um SQLite por visitante, na pasta "espacos" ao lado do banco.
    espacos_max: int = Field(default=50, gt=0, description="Espaços válidos ao mesmo tempo (teto de disco).")
    espaco_validade_min: int = Field(default=120, gt=0, description="Minutos de vida de um espaço, desde a criação.")

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
    limite_espacos_por_minuto: int = 5  # por IP, em POST /espacos; 0 desliga

    @field_validator("banco_caminho", "pasta_demo", mode="before")
    @classmethod
    def caminho_do_banco(cls, valor: object) -> object:
        if isinstance(valor, str) and not valor.strip():
            raise ValueError("Caminho vazio: remova a linha do .env para usar o padrão.")
        return valor

    @field_validator("llm_modelo", "llm_chave", "llm_url", "token_demo", mode="before")
    @classmethod
    def vazio_e_nao_definido(cls, valor: object) -> object:
        """CONTAAI_TOKEN_DEMO= (vazio, como no .env.example) vale como não definido, e não como token ''."""
        return None if isinstance(valor, str) and not valor.strip() else valor


@lru_cache
def configuracao() -> Configuracao:
    return Configuracao()
