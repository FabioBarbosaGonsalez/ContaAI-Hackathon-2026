"""Sementes do estado e restauração da demonstração (ADR 0008).

O manifesto `sementes.json` da pasta de dados (`CONTAAI_PASTA_DEMO`, padrão `data/demo`) lista as
empresas (arquivos no formato de distribuidora.json) e as notas iniciais.

Restaurar é atômico: o estado novo é montado num banco temporário, ao lado do principal, com as
empresas e as notas iniciais importadas pelo mesmo código do POST /nfe/importar (com os motores).
Só se tudo der certo o conteúdo substitui o do banco principal, numa operação só (`Banco.copiar_para`).
Se um motor cair no meio, o banco principal fica como estava. Rodar de novo dá o mesmo estado.

Uso (motores de pé): cd backend && uv run python -m app.persistencia.sementes
"""

from __future__ import annotations

import asyncio
import tempfile
from datetime import datetime
from pathlib import Path

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.contrato import NfeImportarResposta
from app.dados_demo import PASTA_DEMO, Distribuidora
from app.motores.cliente import ClienteMotores
from app.nfe.importacao import Relogio, agora_utc, importar_nota
from app.persistencia.banco import Banco
from app.persistencia.repositorio import Repositorio


class SementesInvalidas(Exception):
    """A pasta de dados não tem sementes legíveis. A mensagem não traz o caminho (vira 503 na API)."""

    def __init__(self, mensagem: str) -> None:
        super().__init__(mensagem)
        self.mensagem = mensagem


class Manifesto(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    aviso: str = Field(alias="_aviso")
    precosVigentesDesde: datetime
    empresas: list[str] = Field(min_length=1)
    notasIniciais: list[str]


def _dentro(pasta: Path, relativo: str) -> Path:
    """Caminho do manifesto sempre dentro da pasta de dados (sem '..' nem caminho absoluto)."""
    caminho = (pasta / relativo).resolve()
    if not caminho.is_relative_to(pasta.resolve()):
        raise SementesInvalidas("O manifesto das sementes aponta para fora da pasta de dados.")
    return caminho


def carregar_manifesto(pasta: Path = PASTA_DEMO) -> Manifesto:
    try:
        return Manifesto.model_validate_json((pasta / "sementes.json").read_text(encoding="utf-8"))
    except (OSError, ValidationError):
        raise SementesInvalidas("Sementes da demonstração não encontradas: confira CONTAAI_PASTA_DEMO.") from None


def _ler_sementes(pasta: Path) -> tuple[Manifesto, list[Distribuidora], list[bytes]]:
    manifesto = carregar_manifesto(pasta)
    try:
        empresas = [
            Distribuidora.model_validate_json(_dentro(pasta, nome).read_text(encoding="utf-8"))
            for nome in manifesto.empresas
        ]
        notas = [_dentro(pasta, nome).read_bytes() for nome in manifesto.notasIniciais]
    except (OSError, ValidationError):
        raise SementesInvalidas("Um arquivo das sementes da demonstração falta ou é inválido.") from None
    return manifesto, empresas, notas


def _carregar_empresas(repo: Repositorio, manifesto: Manifesto, empresas: list[Distribuidora]) -> None:
    with repo.escrita() as s:
        for d in empresas:
            s.inserir_empresa(d.empresa, d.cenario)
            for item in d.catalogo:
                s.inserir_item(d.empresa.cnpj, item)
                s.lancar_preco(d.empresa.cnpj, item.id, item.precoVenda, manifesto.precosVigentesDesde, "semente")


async def restaurar(
    repo: Repositorio, motores: ClienteMotores, pasta: Path = PASTA_DEMO, relogio: Relogio = agora_utc
) -> list[NfeImportarResposta]:
    manifesto, empresas, notas = await asyncio.to_thread(_ler_sementes, pasta)
    principal = repo.banco
    principal.caminho.parent.mkdir(parents=True, exist_ok=True)
    # Ao lado do principal (mesmo disco). ignore_cleanup_errors: no Windows o arquivo pode demorar a liberar.
    with tempfile.TemporaryDirectory(dir=principal.caminho.parent, ignore_cleanup_errors=True) as pasta_tmp:
        temporario = Banco(Path(pasta_tmp) / "restauracao.db", principal.pasta_migracoes)
        await asyncio.to_thread(temporario.migrar)
        repo_tmp = Repositorio(temporario)
        await asyncio.to_thread(_carregar_empresas, repo_tmp, manifesto, empresas)
        recibos = [await importar_nota(conteudo, repo_tmp, motores, relogio) for conteudo in notas]
        await asyncio.to_thread(temporario.copiar_para, principal)
    return recibos


def main() -> None:
    from app.config import configuracao

    cfg = configuracao()
    banco = Banco(cfg.banco_caminho)
    banco.migrar()

    async def rodar() -> list[NfeImportarResposta]:
        async with httpx.AsyncClient(timeout=cfg.timeout_calculo_s, trust_env=False) as http:
            motores = ClienteMotores(http, cfg.motor_rr_url, cfg.motor_sn_url)
            return await restaurar(Repositorio(banco), motores, cfg.pasta_demo)

    recibos = asyncio.run(rodar())
    print(f"Sementes carregadas em {cfg.banco_caminho}: {len(recibos)} nota(s) importada(s).")


if __name__ == "__main__":
    main()
