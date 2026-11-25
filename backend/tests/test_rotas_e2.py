"""Rotas que passaram a calcular de verdade na E2: busca de NCM, erros e explicação (modo real)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import httpx
import pytest
from fastapi.testclient import TestClient
from test_agente import contexto, item

from app.agente import provedor
from app.config import Configuracao
from app.contrato import BuscaNcmResposta, ErroDescricao, ExplicarResposta
from app.main import app
from app.motores.cliente import MotorIndisponivel
from app.motores.dados_abertos import DadosAbertos, sem_html
from app.motores.requisicoes import AliquotasPremissa, Linha, operacao_rr

cliente = TestClient(app)


def test_busca_real_usa_indice_e_valida_no_motor(motores_falsos) -> None:
    r = cliente.get("/busca/ncm", params={"q": "Cerveja de malte", "data": "2027-03-16"})
    assert r.status_code == 200 and "X-ContaAI-Mock" not in r.headers
    corpo = BuscaNcmResposta.model_validate(r.json())
    assert corpo.candidatos[0].ncm == "22030000" and corpo.candidatos[0].tributadoPeloImpostoSeletivo
    assert "Índice local de NCM" in (corpo.fonte or "") and "2027-03-16" in (corpo.fonte or "")
    # NCMs fora do recorte falso respondem 404 no motor e ficam de fora (não estão vigentes na data).
    assert all(c.ncm in {"22030000", "10063021", "02013000", "18063210", "84381000"} for c in corpo.candidatos)


def test_busca_sem_resultado(motores_falsos) -> None:
    corpo = BuscaNcmResposta.model_validate(cliente.get("/busca/ncm", params={"q": "xyzwq"}).json())
    assert corpo.candidatos == []


def test_classificacoes_ficam_em_cache(motores_falsos) -> None:
    cliente.get("/busca/ncm", params={"q": "22030000", "data": "2027-03-16"})
    antes = len(motores_falsos.consultas)
    cliente.get("/busca/ncm", params={"q": "22030000", "data": "2027-03-16"})
    assert len(motores_falsos.consultas) == antes  # tabela oficial: a segunda busca não chama o motor


def test_erros_reais_dos_dois_motores(motores_falsos) -> None:
    rr = ErroDescricao.model_validate(cliente.get("/erros/REG-011").json())
    sn = ErroDescricao.model_validate(cliente.get("/erros/VSN-047").json())
    assert (rr.motor.value, sn.motor.value) == ("regime_regular", "simples_nacional")
    assert cliente.get("/erros/REG-999").status_code == 404


def test_explicar_post_e_get_demo(motores_falsos) -> None:
    ctx = contexto(itens=["arroz-5kg"])
    corpo = {k: v for k, v in ctx.items() if k != "itens"} | {"item": item("arroz-5kg")}
    r = ExplicarResposta.model_validate(cliente.post("/explicar", json=corpo).json())
    assert r.motor.value == "regime_regular" and r.reducaoPct == Decimal("100.00")
    assert [f.cClassTrib for f in r.fundamentacoes] == ["200003"] and r.memoria
    # O GET lê o item do estado (ADR 0011): sem as sementes, a empresa não existe.
    assert cliente.get("/explicar/arroz-5kg").status_code == 404
    assert cliente.post("/demo/restaurar").status_code == 200
    g = cliente.get("/explicar/arroz-5kg", params={"regime": "simples_tradicional"})
    assert g.status_code == 200 and ExplicarResposta.model_validate(g.json()).motor.value == "simples_nacional"
    assert cliente.get("/explicar/nao-existe").status_code == 404


def test_explicar_post_no_modo_mock_e_501() -> None:
    ctx = contexto(itens=["arroz-5kg"])
    corpo = {k: v for k, v in ctx.items() if k != "itens"} | {"item": item("arroz-5kg")}
    assert cliente.post("/explicar", json=corpo).status_code == 501


def test_motor_fora_do_ar_nos_dados_abertos_vira_503_sem_url(motores_falsos) -> None:
    def fora(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("recusada")

    async def consultar() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(fora)) as http:
            await DadosAbertos(http, "http://rr.interno.test/api", "http://sn").classificacoes(date(2027, 3, 16))

    import asyncio

    with pytest.raises(MotorIndisponivel) as e:
        asyncio.run(consultar())
    assert "interno" not in e.value.mensagem


def test_sem_html_nos_nomes() -> None:
    assert sem_html("Atum (<i>Thunnus maccoyii</i>)") == "Atum (Thunnus maccoyii)"


def test_is_da_revenda_vai_como_premissa_zero(motores_falsos) -> None:
    """Decisão 2 do usuário (ADR 0006): sem alíquota de IS informada, a revenda (CST 200 do IS) vai com 0%."""

    class Cerveja:
        ncm, cst, cClassTrib, unidade = "22030000", "000", "000001", "UN"

        class impostoSeletivo:  # noqa: N801
            cst, cClassTrib, litrosPorUnidade = "200", "200007", Decimal("0.35")

    aliq = AliquotasPremissa(Decimal("8.8"), Decimal("0.05"), Decimal("0.05"))
    op = operacao_rr([Linha(Cerveja, Decimal(1), Decimal("3.79"))], date(2027, 3, 16), "RS", 4314902, aliq)
    assert op["itens"][0]["aliquotasNominais"]["impostoSeletivo"] == {"adValorem": 0.0}

    r = cliente.post("/carrinho/calcular", json={**contexto(itens=["cerveja-lata"])})
    premissas = {p["nome"]: p for p in r.json()["premissas"]}
    assert premissas["Alíquota do Imposto Seletivo na revenda"]["valor"].startswith("0% enviada ao motor")


def test_is_com_incidencia_nao_recebe_premissa() -> None:
    class Bebida:
        ncm, cst, cClassTrib, unidade = "22030000", "000", "000001", "UN"

        class impostoSeletivo:  # noqa: N801
            cst, cClassTrib, litrosPorUnidade = "000", "000001", None

    aliq = AliquotasPremissa(Decimal("8.8"), Decimal("0.05"), Decimal("0.05"))
    op = operacao_rr([Linha(Bebida, Decimal(1), Decimal("3.79"))], date(2027, 3, 16), "RS", 4314902, aliq)
    assert "impostoSeletivo" not in op["itens"][0]["aliquotasNominais"]  # o REG-035 continua aparecendo


def test_registro_de_provedores() -> None:
    assert "roteiro" in provedor.PROVEDORES
    with pytest.raises(provedor.ProvedorNaoConfigurado):
        provedor.criar_provedor(Configuracao(llm_provedor="nao-existe"), None)  # type: ignore[arg-type]


@pytest.mark.parametrize("nome", sorted(provedor.PROVEDORES))
def test_todo_provedor_registrado_segue_a_interface(nome: str) -> None:
    """Vale para qualquer adaptador novo: nome e responder(Pedido) → RespostaModelo."""
    import asyncio

    from app.agente.tipos import Mensagem, Pedido, RespostaModelo

    async def rodar() -> RespostaModelo:
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(503))) as http:
            p = provedor.criar_provedor(Configuracao(llm_provedor=nome), http)
            assert isinstance(p.nome, str) and p.nome
            pedido = Pedido(
                sistema="s", mensagens=[Mensagem(papel="usuario", texto="oi")], ferramentas=[], max_tokens=64
            )
            try:
                return await p.responder(pedido)
            except provedor.ProvedorFalhou as e:  # adaptador de API real: a falha 503 vira ProvedorFalhou
                assert "http" not in e.mensagem.lower()
                return RespostaModelo(texto="falhou como esperado")

    assert isinstance(asyncio.run(rodar()), RespostaModelo)


@pytest.mark.golden
def test_busca_e_erros_com_os_motores() -> None:
    from app.config import configuracao

    app.dependency_overrides[configuracao] = lambda: Configuracao(modo="real")
    try:
        corpo = BuscaNcmResposta.model_validate(
            cliente.get("/busca/ncm", params={"q": "Arroz polido não parboilizado", "data": "2027-03-16"}).json()
        )
        arroz = corpo.candidatos[0]
        assert arroz.ncm == "10063021"
        assert [c.cClassTrib for c in arroz.classificacoes] == ["200003", "200038", "515001", "000001"]
        e = ErroDescricao.model_validate(cliente.get("/erros/REG-011").json())
        assert e.titulo == "NCM não vinculada"
        # O GET lê o item do estado (ADR 0011): primeiro as sementes, com os motores reais.
        assert cliente.post("/demo/restaurar").status_code == 200
        x = ExplicarResposta.model_validate(cliente.get("/explicar/cerveja-lata?regime=simples_hibrido").json())
        assert x.estado.value == "CALCULO_SIMULADO" and x.erros == []
    finally:
        app.dependency_overrides.clear()


def test_cache_guarda_o_conjunto_por_ncm_e_nao_cada_consulta(motores_falsos) -> None:
    cliente.get("/busca/ncm", params={"q": "22030000", "data": "2027-03-16"})
    chaves = list(motores_falsos.cache_dados._itens)
    assert "validas|22030000|2027-03-16" in chaves and "validas|84381000|2027-03-16" in chaves
    assert not any("ncm-aplicavel" in c for c in chaves)
