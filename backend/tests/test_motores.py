"""E1-01: modelos tipados e cliente dos motores.

Aceite do plano: os clientes tipados validam as respostas gravadas (tests/golden/).
"""

from __future__ import annotations

import asyncio
import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import ValidationError

from app.contrato import EstadoItem, ItemBase, Motor
from app.motores.cliente import (
    ClienteMotores,
    MotorIndisponivel,
    OperacaoRecusada,
    RespostaInvalida,
)
from app.motores.conversao import ler_rr, ler_sn
from app.motores.modelos import RespostaRR, RespostaSN
from app.motores.requisicoes import AliquotasPremissa, DasPremissa, Linha, operacao_rr

GOLDEN = Path(__file__).resolve().parent / "golden"
AL = AliquotasPremissa(cbs=Decimal("8.8"), ibsEstadual=Decimal("0.05"), ibsMunicipal=Decimal("0.05"))
DAS = DasPremissa(anexo="I", cAtivSN="01", pCBSSN=Decimal("1.1612"), pIBSSN=Decimal("0.0129"))
CHOCOLATE = ItemBase(id="c", descricao="Chocolate", ncm="18063210", cst="000", cClassTrib="000001", unidade="UN")
EDUCACAO = ItemBase(id="e", descricao="Educação", nbs="122011200", cst="200", cClassTrib="200028", unidade="UN")


def gravado(caso: str) -> dict[str, Any]:
    return json.loads((GOLDEN / f"{caso}.resposta.json").read_text(encoding="utf-8"))


def rodar(handler, chamada):
    async def executar():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            return await chamada(ClienteMotores(http, "http://rr.test/api", "http://sn.test/api"))

    return asyncio.run(executar())


def rr(cli: ClienteMotores, itens=(CHOCOLATE,)):
    return cli.regime_regular(
        [Linha(i, Decimal(1), Decimal("100.00")) for i in itens], date(2027, 3, 16), "RS", 4314902, AL
    )


def sn(cli: ClienteMotores):
    return cli.simples_nacional([Linha(CHOCOLATE, Decimal(1), Decimal("100.00"))], date(2027, 3, 16), DAS)


# ---------------------------------------------------------------------------
# Modelos × respostas gravadas


def test_resposta_rr_gravada_valida_no_modelo_e_bate_com_o_exemplo_oficial() -> None:
    registro = gravado("rr-exemplo-oficial")
    itens = ler_rr(RespostaRR.model_validate(registro["corpo"]))
    assert [i.estado for i in itens] == [EstadoItem.CALCULO_SIMULADO] * 3 + [EstadoItem.INCONSISTENCIA_ENTRADA]

    arroz, cerveja, educacao, carne = itens
    # Valores publicados em docs/exemplos.md da calculadora RR 1.7.2
    assert (educacao.tributos.cbs, educacao.tributos.ibs) == (Decimal("42.24"), Decimal("0.48"))
    assert educacao.reducaoPct == Decimal("60.00") and educacao.aliquotaEfetiva.cbs == Decimal("3.52")
    assert (arroz.tributos.cbs, arroz.reducaoPct) == (Decimal("0.00"), Decimal("100.00"))
    assert cerveja.tributos.impostoSeletivo == Decimal("15.00") and "impostoSeletivo" in cerveja.memoria
    assert [(e.codigo, e.campo) for e in carne.erros] == [("REG-011", "#/itens/3/ncm")]
    assert not carne.calculado and carne.tributos.cbs is None


def test_resposta_sn_gravada_valida_no_modelo() -> None:
    itens = ler_sn(RespostaSN.model_validate(gravado("sn-nao-assistido-anexo-i")["corpo"]))
    arroz, cerveja, carne = itens
    assert (arroz.tributos.cbs, arroz.tributos.ibs) == (Decimal("1.16"), Decimal("0.01"))
    assert arroz.aliquotaEfetiva.cbs == Decimal("1.1612") and arroz.reducaoPct is None
    assert cerveja.tributos.impostoSeletivo == Decimal("15.00")
    assert [e.codigo for e in carne.erros] == ["VSN-047"]


def test_estado_desconhecido_nao_passa_no_modelo() -> None:
    with pytest.raises(ValidationError):
        RespostaRR.model_validate({"objetos": [{"nObj": 1, "estadoItem": "ESTADO_NOVO"}]})


def test_erro_do_motor_nao_carrega_o_host_interno() -> None:
    itens = ler_sn(RespostaSN.model_validate(gravado("sn-nao-assistido-anexo-i")["corpo"]))
    assert "127.0.0.1" not in itens[2].erros[0].model_dump_json()


# ---------------------------------------------------------------------------
# Requisição montada


def test_servico_vai_com_nbs_e_mercadoria_com_ncm() -> None:
    op = operacao_rr(
        [Linha(EDUCACAO, Decimal(1), Decimal("1200.00")), Linha(CHOCOLATE, Decimal(1), Decimal("5.99"))],
        date(2027, 3, 10),
        "RS",
        4314902,
        AL,
    )
    educacao, chocolate = op["itens"]
    assert educacao["nbs"] == "122011200" and "ncm" not in educacao
    assert chocolate["ncm"] == "18063210" and "nbs" not in chocolate


# ---------------------------------------------------------------------------
# Cliente: respostas e falhas


def test_cliente_le_itens_versoes_e_aviso_de_simulacao() -> None:
    corpo = gravado("rr-exemplo-oficial")["corpo"]
    headers = {"x-calc-app-version": "1.7.2", "x-calc-db-version": "V0073", "x-warning-dados-simulados": "6"}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=corpo, headers={**headers, "server": "interno"})

    calculo = rodar(handler, lambda cli: rr(cli, [CHOCOLATE] * 4))
    assert calculo.motor == Motor.REGIME_REGULAR and len(calculo.itens) == 4
    assert calculo.simuladoPeloMotor and calculo.versaoApp == "1.7.2" and calculo.versaoBanco == "V0073"
    assert "server" not in calculo.headers  # só os headers que o produto usa


def test_recusa_do_motor_vira_operacao_recusada_com_os_erros() -> None:
    problema = {
        "type": "about:blank",
        "title": "Erros no processamento",
        "status": 422,
        "errors": [
            {
                "type": "http://127.0.0.1/erros?codigo=VSN-015",
                "title": "Tipo de documento fiscal (tpDoc) não suportado",
                "code": "VSN-015",
                "pointer": "#/tpDoc",
                "detail": "Tipo de documento não suportado, recebido: '55'.",
            }
        ],
    }
    with pytest.raises(OperacaoRecusada) as exc:
        rodar(lambda r: httpx.Response(422, json=problema), sn)
    assert [e.codigo for e in exc.value.erros] == ["VSN-015"] and exc.value.motor == Motor.SIMPLES_NACIONAL
    assert "127.0.0.1" not in str(exc.value) + "".join(e.model_dump_json() for e in exc.value.erros)


@pytest.mark.parametrize(
    ("resposta", "excecao"),
    [
        (httpx.Response(500, text="stack trace interno"), MotorIndisponivel),
        (httpx.Response(503), MotorIndisponivel),
        (httpx.Response(400, json={"detail": "JSON parse error"}), RespostaInvalida),
        (httpx.Response(422, json={"detail": "sem lista de erros"}), RespostaInvalida),
        (httpx.Response(404), RespostaInvalida),
        (httpx.Response(200, text="não é json"), RespostaInvalida),
        (httpx.Response(200, json={"objetos": [{"nObj": 1, "estadoItem": "OUTRO"}]}), RespostaInvalida),
        (httpx.Response(200, json={"objetos": []}), RespostaInvalida),  # itens diferentes dos enviados
    ],
)
def test_falhas_viram_excecoes_sem_detalhe_interno(resposta: httpx.Response, excecao: type) -> None:
    with pytest.raises(excecao) as exc:
        rodar(lambda r: resposta, rr)
    assert "rr.test" not in exc.value.mensagem and "stack" not in exc.value.mensagem


def test_motor_fora_do_ar() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("conexão recusada", request=request)

    with pytest.raises(MotorIndisponivel) as exc:
        rodar(handler, rr)
    assert exc.value.mensagem == "O motor Regime Regular está indisponível. Tente de novo em instantes."
