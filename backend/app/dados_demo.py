"""Modelos e leitura dos dados de demonstração em data/demo/ (só dados fictícios, princípio P10)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

PASTA_DEMO = Path(__file__).resolve().parents[2] / "data" / "demo"

Anexo = Literal["I", "II", "III", "IV", "V"]


class _Modelo(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class AtividadeSimples(_Modelo):
    anexo: Anexo
    cAtivSN: str = Field(pattern=r"^\d{2}$")
    descricaoAtividade: str
    fonte: str


class Empresa(_Modelo):
    razaoSocial: str
    cnpj: str = Field(pattern=r"^\d{14}$")
    regimeAtual: Literal["simples_tradicional", "simples_hibrido"]
    uf: str = Field(pattern=r"^[A-Z]{2}$")
    municipio: int
    municipioNome: str
    simples: AtividadeSimples


class AliquotasNominaisDemo(_Modelo):
    cbs: Decimal
    ibsEstadual: Decimal
    ibsMunicipal: Decimal
    fonte: str


class ValorComFonte(_Modelo):
    valor: Decimal
    fonte: str


class PremissasDasDemo(_Modelo):
    anexo: Anexo
    pCBSSN: Decimal
    pIBSSN: Decimal
    fonte: str


class Cenario(_Modelo):
    descricao: str
    data: date
    aliquotasNominais: AliquotasNominaisDemo
    impostoSeletivoAdValorem: ValorComFonte
    premissasDas: PremissasDasDemo
    cargaAtualPct: Decimal | None
    cargaAtualNota: str


class ImpostoSeletivoDemo(_Modelo):
    cst: str = Field(pattern=r"^\d{3}$")
    cClassTrib: str = Field(pattern=r"^\d{6}$")
    litrosPorUnidade: Decimal
    motivo: str


class ItemCatalogo(_Modelo):
    id: str
    descricao: str
    ncm: str = Field(pattern=r"^\d{8}$")
    ncmDescricaoOficial: str
    cst: str = Field(pattern=r"^\d{3}$")
    cClassTrib: str = Field(pattern=r"^\d{6}$")
    classificacaoFonte: str
    impostoSeletivo: ImpostoSeletivoDemo | None
    unidade: Literal["UN", "KG"]
    cnpjFornecedor: str = Field(pattern=r"^\d{14}$", description="O código do fornecedor só é único dentro dele.")
    codigoFornecedor: str = Field(min_length=1, max_length=60)
    precoVenda: Decimal = Field(gt=0)
    margemAlvoPct: Decimal = Field(gt=0, lt=100)
    papelNaDemo: str


class Distribuidora(_Modelo):
    aviso: str = Field(alias="_aviso")
    empresa: Empresa
    cenario: Cenario
    catalogo: list[ItemCatalogo]

    def item(self, item_id: str) -> ItemCatalogo:
        return next(i for i in self.catalogo if i.id == item_id)


class Cliente(_Modelo):
    razaoSocial: str
    cnpj: str = Field(pattern=r"^\d{14}$")
    regime: Literal["regime_regular"]
    uf: str = Field(pattern=r"^[A-Z]{2}$")
    municipio: int


class ItemCompraMensal(_Modelo):
    itemId: str
    quantidade: Decimal = Field(gt=0)


class CompraMensal(_Modelo):
    descricao: str
    itens: list[ItemCompraMensal]


class ClienteB2B(_Modelo):
    aviso: str = Field(alias="_aviso")
    cliente: Cliente
    compraMensal: CompraMensal


def carregar_distribuidora(pasta: Path = PASTA_DEMO) -> Distribuidora:
    return Distribuidora.model_validate_json((pasta / "distribuidora.json").read_text(encoding="utf-8"))


def carregar_cliente_b2b(pasta: Path = PASTA_DEMO) -> ClienteB2B:
    return ClienteB2B.model_validate_json((pasta / "cliente-b2b.json").read_text(encoding="utf-8"))
