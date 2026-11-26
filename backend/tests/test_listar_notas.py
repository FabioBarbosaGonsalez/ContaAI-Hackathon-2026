"""GET /notas (E5, PR 3b): as NF-e de compra já importadas, para a tela de Notas.

Rodam no CI com os motores falsos do conftest. O que se confere: a ordem pela emissão (não pela importação),
as contagens lidas do recibo e do estado dos alertas, e o isolamento por empresa e por espaço.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.contrato import AlertasResposta, NfeImportarResposta, NotasResposta
from app.main import app
from tests.test_nfe import NOTA_2, SEM_PAR, SERRA_AZUL, VALE_VERDE, importar, nota
from tests.test_tela import ESPACO, novo_espaco

cliente = TestClient(app)


@pytest.fixture
def demo(motores_falsos):
    assert cliente.post("/demo/restaurar").status_code == 200
    return motores_falsos


def listar(cnpj: str = SERRA_AZUL, **params: object) -> NotasResposta:
    headers = {ESPACO: str(params.pop("espaco"))} if "espaco" in params else {}
    r = cliente.get("/notas", params={"cnpj": cnpj, **params}, headers=headers)
    assert r.status_code == 200, r.text
    assert "X-ContaAI-Mock" not in r.headers
    return NotasResposta.model_validate(r.json())


def numeros(resposta: NotasResposta) -> list[str]:
    return [n.nota.numero for n in resposta.notas]


def test_sementes_trazem_a_nota_1_sem_alertas(demo) -> None:
    corpo = listar()
    assert corpo.empresa.cnpj == SERRA_AZUL and corpo.aviso
    assert numeros(corpo) == ["1001"]
    n = corpo.notas[0]
    assert (n.itensCasados, n.itensSemPar, n.alertasGerados, n.alertasAbertos) == (5, 0, 0, 0)
    assert n.nota.destinatario is not None and n.nota.destinatario.cnpj == SERRA_AZUL
    assert n.importadaEm.utcoffset() is not None and n.importadaEm.utcoffset().total_seconds() == 0


def test_ordem_pela_emissao_e_nao_pela_importacao(demo) -> None:
    """Importadas na ordem 1001, 1003 (18/03), 1002 (16/03): a lista segue a data da nota."""
    importar(nota(SEM_PAR))
    importar(nota(NOTA_2))
    assert numeros(listar()) == ["1003", "1002", "1001"]
    assert numeros(listar(limite=1)) == ["1003"]


def test_contagens_vem_do_recibo_e_os_alertas_do_estado(demo) -> None:
    recibo = NfeImportarResposta.model_validate(importar(nota(NOTA_2)))
    sem_par = NfeImportarResposta.model_validate(importar(nota(SEM_PAR)))
    por_numero = {n.nota.numero: n for n in listar().notas}

    n2 = por_numero["1002"]
    assert n2.nota == recibo.nota
    assert (n2.itensCasados, n2.itensSemPar) == (len(recibo.itensCasados), len(recibo.itensSemPar))
    assert n2.alertasGerados == n2.alertasAbertos == len(recibo.alertas) >= 1
    assert por_numero["1003"].itensSemPar == len(sem_par.itensSemPar) >= 1

    alerta = recibo.alertas[0]
    assert cliente.post(f"/alertas/{alerta.id}/aplicar").status_code == 200
    depois = next(n for n in listar().notas if n.nota.numero == "1002")
    assert depois.alertasGerados == n2.alertasGerados and depois.alertasAbertos == n2.alertasAbertos - 1


def test_uma_nota_repetida_nao_aparece_duas_vezes(demo) -> None:
    importar(nota(NOTA_2))
    assert NfeImportarResposta.model_validate(importar(nota(NOTA_2))).jaImportada
    assert numeros(listar()) == ["1002", "1001"]


def test_cada_empresa_ve_so_as_suas_notas(demo) -> None:
    importar(nota(NOTA_2))
    vale = listar(VALE_VERDE)
    assert vale.empresa.cnpj == VALE_VERDE and vale.notas
    assert all(n.nota.destinatario.cnpj == VALE_VERDE for n in vale.notas)
    assert not {"1001", "1002"} & set(numeros(vale))


def test_o_espaco_tem_as_proprias_notas(demo) -> None:
    espaco = novo_espaco()
    importar(nota(NOTA_2), **{ESPACO: espaco})
    assert numeros(listar(espaco=espaco)) == ["1002", "1001"]
    assert numeros(listar()) == ["1001"]


def test_empresa_inexistente_e_parametros_invalidos(demo) -> None:
    r = cliente.get("/notas", params={"cnpj": "00000000000000"})
    assert r.status_code == 404 and r.headers["content-type"].startswith("application/problem+json")
    for params in ({}, {"cnpj": "123"}, {"cnpj": SERRA_AZUL, "limite": 0}, {"cnpj": SERRA_AZUL, "limite": 201}):
        assert cliente.get("/notas", params=params).status_code == 422, params
    assert cliente.get("/notas", params={"cnpj": SERRA_AZUL}, headers={ESPACO: "0" * 32}).status_code == 404


def test_notas_no_mock_batem_com_os_alertas_do_mock() -> None:
    """Um fato, uma variável: os alertas abertos de cada nota no mock são os alertas do mock com a mesma origem."""
    r = cliente.get("/notas", params={"cnpj": SERRA_AZUL})
    assert r.status_code == 200 and r.headers["X-ContaAI-Mock"] == "1"
    corpo = NotasResposta.model_validate(r.json())
    assert numeros(corpo) == ["1002", "1001"]
    alertas = AlertasResposta.model_validate(cliente.get("/alertas").json()).alertas
    for n in corpo.notas:
        da_nota = [a for a in alertas if a.cnpj == SERRA_AZUL and a.origem.numero == n.nota.numero]
        assert n.alertasAbertos == sum(a.aplicadoEm is None for a in da_nota)
        assert n.alertasGerados == len(da_nota)
