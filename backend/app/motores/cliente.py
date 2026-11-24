"""Cliente tipado dos dois motores oficiais (E1-01): httpx assíncrono + modelos Pydantic.

Só usa os endpoints de observabilidade (P4), que devolvem 200 com o estado de cada item. As
falhas viram exceções com mensagem própria, sem repassar URL, host ou corpo do motor:

- MotorIndisponivel: conexão recusada, tempo esgotado ou 5xx.
- OperacaoRecusada: 422 com a lista de erros do motor (ex.: VSN-015, VSN-039). Os erros vão
  ao usuário, porque descrevem a entrada dele.
- RespostaInvalida: 400 (requisição malformada, defeito nosso), status inesperado, corpo fora
  do modelo ou itens que não batem com os enviados.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

from app.contrato import ErroMotor, Motor
from app.motores.cache import CacheRespostas
from app.motores.conversao import LeituraItem, erro_do_contrato, ler_rr, ler_sn
from app.motores.modelos import (
    HEADER_SIMULADO,
    HEADER_VERSAO_APP,
    HEADER_VERSAO_BANCO,
    ProblemaMotor,
    RespostaRR,
    RespostaSN,
)
from app.motores.requisicoes import AliquotasPremissa, DasPremissa, Linha, operacao_rr, operacao_sn

log = logging.getLogger("contaai.motores")

ROTA_RR = "/calculadora/observabilidade/regime-geral"
ROTA_SN = "/calculadora/observabilidade/simples-nacional/nao-assistido"

NOME = {Motor.REGIME_REGULAR: "Regime Regular", Motor.SIMPLES_NACIONAL: "Simples Nacional"}


class FalhaMotor(Exception):
    def __init__(self, motor: Motor, mensagem: str) -> None:
        super().__init__(mensagem)
        self.motor = motor
        self.mensagem = mensagem


class MotorIndisponivel(FalhaMotor):
    pass


class RespostaInvalida(FalhaMotor):
    pass


class OperacaoRecusada(FalhaMotor):
    def __init__(self, motor: Motor, mensagem: str, erros: list[ErroMotor]) -> None:
        super().__init__(motor, mensagem)
        self.erros = erros


@dataclass(frozen=True)
class Calculo:
    """Resultado de uma chamada: itens na ordem enviada, versões e aviso de simulação do motor."""

    motor: Motor
    itens: list[LeituraItem]
    headers: dict[str, str]

    @property
    def simuladoPeloMotor(self) -> bool:
        return HEADER_SIMULADO in self.headers

    @property
    def versaoApp(self) -> str | None:
        return self.headers.get(HEADER_VERSAO_APP)

    @property
    def versaoBanco(self) -> str | None:
        return self.headers.get(HEADER_VERSAO_BANCO)


# Só os headers que o produto usa; o resto (servidor, segurança) não sai do cliente.
_HEADERS = (HEADER_SIMULADO, HEADER_VERSAO_APP, HEADER_VERSAO_BANCO)


class ClienteMotores:
    def __init__(self, http: httpx.AsyncClient, url_rr: str, url_sn: str, cache: CacheRespostas | None = None) -> None:
        self.http = http
        self.url_rr = url_rr.rstrip("/")
        self.url_sn = url_sn.rstrip("/")
        self.cache = cache

    async def regime_regular(
        self, linhas: list[Linha], data_fato: date, uf: str, municipio: int, aliquotas: AliquotasPremissa | None
    ) -> Calculo:
        corpo, headers = await self._post(
            Motor.REGIME_REGULAR,
            self.url_rr + ROTA_RR,
            operacao_rr(linhas, data_fato, uf, municipio, aliquotas),
            RespostaRR,
        )
        return self._calculo(Motor.REGIME_REGULAR, ler_rr(corpo), headers, len(linhas))

    async def simples_nacional(self, linhas: list[Linha], data_fato: date, das: DasPremissa) -> Calculo:
        corpo, headers = await self._post(
            Motor.SIMPLES_NACIONAL, self.url_sn + ROTA_SN, operacao_sn(linhas, data_fato, das), RespostaSN
        )
        return self._calculo(Motor.SIMPLES_NACIONAL, ler_sn(corpo), headers, len(linhas))

    @staticmethod
    def _calculo(motor: Motor, itens: list[LeituraItem], headers: dict[str, str], enviados: int) -> Calculo:
        if [i.numero for i in itens] != list(range(1, enviados + 1)):
            log.error("motor %s devolveu itens que não batem com os enviados", motor)
            raise RespostaInvalida(motor, f"O motor {NOME[motor]} devolveu itens diferentes dos enviados.")
        return Calculo(motor=motor, itens=itens, headers=headers)

    async def _post[M: BaseModel](
        self, motor: Motor, url: str, operacao: Mapping[str, Any], modelo: type[M]
    ) -> tuple[M, dict[str, str]]:
        nome = NOME[motor]
        chave = CacheRespostas.chave(motor.value, operacao) if self.cache is not None else ""
        if self.cache is not None and (guardado := self.cache.obter(chave)) is not None:
            conteudo, headers = guardado
            return modelo.model_validate_json(conteudo), dict(headers)
        try:
            r = await self.http.post(url, json=operacao)
        except httpx.HTTPError as e:
            log.warning("motor %s indisponível: %s", motor, type(e).__name__)
            raise MotorIndisponivel(motor, f"O motor {nome} está indisponível. Tente de novo em instantes.") from None

        if r.status_code >= 500:
            log.warning("motor %s respondeu %s", motor, r.status_code)
            raise MotorIndisponivel(motor, f"O motor {nome} está indisponível. Tente de novo em instantes.")
        if r.status_code == 422:
            problema = _validar(ProblemaMotor, r)
            if problema is not None and problema.errors:
                raise OperacaoRecusada(
                    motor,
                    f"O motor {nome} recusou a operação.",
                    [erro_do_contrato(e) for e in problema.errors],
                )
        if r.status_code != 200:
            log.error("motor %s respondeu %s", motor, r.status_code)
            raise RespostaInvalida(motor, f"O motor {nome} não aceitou a requisição do ContaAI.")

        corpo = _validar(modelo, r)
        if corpo is None:
            log.error("resposta do motor %s fora do modelo esperado", motor)
            raise RespostaInvalida(motor, f"O motor {nome} devolveu uma resposta em formato inesperado.")
        headers = {h: r.headers[h] for h in _HEADERS if h in r.headers}
        if self.cache is not None:
            self.cache.guardar(chave, r.content, headers)  # só respostas 200 dentro do modelo
        return corpo, headers


def _validar[M: BaseModel](modelo: type[M], r: httpx.Response) -> M | None:
    try:
        return modelo.model_validate_json(r.content)
    except ValidationError:
        return None
