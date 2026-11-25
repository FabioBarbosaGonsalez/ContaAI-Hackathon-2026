"""Consultas GET aos dados abertos e ao catálogo de erros dos motores oficiais (E2-02).

Mesma regra do cliente de cálculo (app/motores/cliente.py): as falhas viram FalhaMotor sem URL,
host ou corpo do motor, e só os campos usados são lidos (modelos com extra="ignore").

As respostas são as tabelas oficiais da versão fixada do motor (P5), iguais para todo usuário:
ficam num cache LRU em memória pela URL + parâmetros. Não guarda nada do usuário.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections import OrderedDict
from datetime import date
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, TypeAdapter, ValidationError

from app.contrato import Motor
from app.motores.cliente import NOME, MotorIndisponivel, RespostaInvalida

log = logging.getLogger("contaai.dados_abertos")

DA = "/calculadora/dados-abertos"
ROTA_ERROS_RR = "/calculadora/observabilidade/erros"
ROTA_ERROS_SN = "/calculadora/observabilidade/simples-nacional/erros"
# NCM de máquina (cozinha industrial), sem benefício: o que vale para ela vale para quase todo produto.
# Usada para separar o que é específico da NCM consultada (método do ADR 0003).
NCM_NEUTRA = "84381000"
# Consultas paralelas ao motor local ao validar as classificações de uma NCM.
PARALELO = 16
_TAG = re.compile(r"<[^>]+>")


class _Lido(BaseModel):
    model_config = ConfigDict(extra="ignore")


class ClassificacaoOficial(_Lido):
    codigo: str
    descricao: str
    nomenclatura: str | None = None
    percentualReducaoCbs: float | None = None


class FundamentacaoOficial(_Lido):
    codigoClassificacaoTributaria: str
    codigoSituacaoTributaria: str
    textoCurto: str | None = None
    texto: str | None = None
    referenciaNormativa: str | None = None


class NcmOficial(_Lido):
    capitulo: str | None = None
    posicao: str | None = None
    subposicao: str | None = None
    item: str | None = None
    subitem: str | None = None
    tributadoPeloImpostoSeletivo: bool = False

    def hierarquia(self) -> str:
        """Posição, subposição, item e subitem, como o mock da E0 (sem o capítulo e sem HTML)."""
        partes = [self.posicao, self.subposicao, self.item, self.subitem]
        return " - ".join(sem_html(p).rstrip(".") for p in partes if p)


class Aplicavel(_Lido):
    valido: bool


class ErroCatalogo(_Lido):
    codigo: str
    titulo: str
    descricao: str


def sem_html(texto: str) -> str:
    """Os dados abertos trazem marcação em alguns nomes (ex.: <i>Thunnus maccoyii</i>)."""
    return _TAG.sub("", texto).strip()


class CacheConsultas:
    """LRU em memória das respostas JSON dos dados abertos (tabelas oficiais, iguais para todos)."""

    def __init__(self, max_itens: int = 4096) -> None:
        self.max_itens = max_itens
        self._itens: OrderedDict[str, Any] = OrderedDict()

    def obter(self, chave: str) -> Any | None:
        if chave in self._itens:
            self._itens.move_to_end(chave)
            return self._itens[chave]
        return None

    def guardar(self, chave: str, valor: Any) -> None:
        if self.max_itens <= 0:
            return
        self._itens[chave] = valor
        self._itens.move_to_end(chave)
        while len(self._itens) > self.max_itens:
            self._itens.popitem(last=False)


class DadosAbertos:
    def __init__(self, http: httpx.AsyncClient, url_rr: str, url_sn: str, cache: CacheConsultas | None = None) -> None:
        self.http = http
        self.url_rr = url_rr.rstrip("/")
        self.url_sn = url_sn.rstrip("/")
        self.cache = cache if cache is not None else CacheConsultas()
        self._paralelo = asyncio.Semaphore(PARALELO)

    async def _get(
        self, motor: Motor, url: str, params: dict[str, str], ausente_404: bool = False, guardar: bool = True
    ) -> Any | None:
        chave = url + "?" + "&".join(f"{k}={v}" for k, v in sorted(params.items()))
        guardado = self.cache.obter(chave)
        if guardado is not None:
            return guardado
        nome = NOME[motor]
        try:
            async with self._paralelo:
                r = await self.http.get(url, params=params)
        except httpx.HTTPError as e:
            log.warning("dados abertos do motor %s indisponíveis: %s", motor, type(e).__name__)
            raise MotorIndisponivel(motor, f"O motor {nome} está indisponível. Tente de novo em instantes.") from None
        if r.status_code >= 500:
            raise MotorIndisponivel(motor, f"O motor {nome} está indisponível. Tente de novo em instantes.")
        if r.status_code == 404 and ausente_404:
            return None
        if r.status_code != 200:
            log.error("dados abertos do motor %s responderam %s", motor, r.status_code)
            raise RespostaInvalida(motor, f"O motor {nome} não aceitou a consulta do ContaAI.")
        try:
            valor = r.json()
        except ValueError:
            raise RespostaInvalida(motor, f"O motor {nome} devolveu uma resposta em formato inesperado.") from None
        if guardar:
            self.cache.guardar(chave, valor)
        return valor

    @staticmethod
    def _ler(tipo: Any, valor: Any, motor: Motor) -> Any:
        try:
            return TypeAdapter(tipo).validate_python(valor)
        except ValidationError:
            log.error("dados abertos do motor %s fora do modelo esperado", motor)
            raise RespostaInvalida(
                motor, f"O motor {NOME[motor]} devolveu uma resposta em formato inesperado."
            ) from None

    async def classificacoes(self, data: date) -> list[ClassificacaoOficial]:
        rr = Motor.REGIME_REGULAR
        valor = await self._get(rr, f"{self.url_rr}{DA}/classificacoes-tributarias/cbs-ibs", {"data": data.isoformat()})
        return self._ler(list[ClassificacaoOficial], valor, rr)

    async def fundamentacoes(self, data: date) -> list[FundamentacaoOficial]:
        rr = Motor.REGIME_REGULAR
        valor = await self._get(rr, f"{self.url_rr}{DA}/fundamentacoes-legais", {"data": data.isoformat()})
        return self._ler(list[FundamentacaoOficial], valor, rr)

    async def ncm(self, ncm: str, data: date) -> NcmOficial | None:
        """None quando a NCM não existe (ou não está vigente) na data: o motor responde 404."""
        rr = Motor.REGIME_REGULAR
        valor = await self._get(rr, f"{self.url_rr}{DA}/ncm", {"ncm": ncm, "data": data.isoformat()}, ausente_404=True)
        return None if valor is None else self._ler(NcmOficial, valor, rr)

    async def aplicavel(self, cclasstrib: str, ncm: str, data: date) -> bool:
        rr = Motor.REGIME_REGULAR
        valor = await self._get(
            rr,
            f"{self.url_rr}{DA}/classificacoes-tributarias/ncm-aplicavel",
            {"cClassTrib": cclasstrib, "ncm": ncm, "dataOcorrenciaFatoGerador": data.isoformat()},
            guardar=False,  # o cache guarda o conjunto por NCM (validas_para_ncm), não as ~144 consultas
        )
        return self._ler(Aplicavel, valor, rr).valido

    async def validas_para_ncm(self, ncm: str, data: date) -> set[str]:
        """cClassTrib de mercadoria (nomenclatura NCM) válidos para a NCM na data, pelo próprio motor."""
        chave = f"validas|{ncm}|{data.isoformat()}"
        guardado = self.cache.obter(chave)
        if guardado is not None:
            return set(guardado)
        candidatas = [c.codigo for c in await self.classificacoes(data) if c.nomenclatura in ("NCM", "NBS ou NCM")]
        resultados = await asyncio.gather(*(self.aplicavel(c, ncm, data) for c in candidatas))
        validas = {c for c, ok in zip(candidatas, resultados, strict=True) if ok}
        self.cache.guardar(chave, sorted(validas))
        return validas

    async def erro(self, codigo: str) -> tuple[Motor, ErroCatalogo] | None:
        """Descrição oficial de um código de erro (REG-xxx no RR, VSN-xxx no SN); None se não existe."""
        motor = Motor.REGIME_REGULAR if codigo.startswith("REG-") else Motor.SIMPLES_NACIONAL
        url = self.url_rr + ROTA_ERROS_RR if motor == Motor.REGIME_REGULAR else self.url_sn + ROTA_ERROS_SN
        valor = await self._get(motor, url, {"codigo": codigo}, ausente_404=True)
        return None if valor is None else (motor, self._ler(ErroCatalogo, valor, motor))
