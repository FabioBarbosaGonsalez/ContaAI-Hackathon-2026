"""Exclusão e dados (C3-B, etapa 7; LGPD, arts. 18 II, V e VI, e 19): o arquivo dos dados da conta, excluir a empresa
sem excluir a conta, a exclusão da conta levando todas as organizações em que a pessoa era a única, a limpeza dos
bancos órfãos na subida e os registros do servidor sem dado pessoal."""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app import cadastro, main
from app.api import dependencias, middlewares, registro
from app.api.rotas import contas as rotas_contas
from app.config import Configuracao, configuracao
from app.contas.servico import Contas
from app.contrato import ContaDadosResposta
from app.main import app
from app.nfe.consultas import NaoEncontrado
from app.seguranca import LimitadorPorIp
from tests.test_contas import INICIO, SENHA, Relogio, codigo, navegador
from tests.test_contas import cadastrar as cadastrar_conta
from tests.test_empresa_propria import (
    ALFANUMERICO,
    CAXIAS,
    NUMERICO,
    cadastrar,
    com_conta,
    compra_anterior_mais_barata,
    corpo_item,
    importar,
    nota_da_empresa,
)
from tests.test_nfe import SERRA_AZUL

CLIENTE = "11444777000161"
TABELAS_DA_EMPRESA = (
    "empresas",
    "itens",
    "codigos_fornecedor",
    "notas",
    "custos",
    "precos",
    "alertas",
    "classificacoes",
    "clientes_b2b",
)


@pytest.fixture
def relogio(monkeypatch: pytest.MonkeyPatch) -> Relogio:
    r = Relogio()
    monkeypatch.setattr(rotas_contas, "agora_utc", r)
    monkeypatch.setattr(dependencias, "agora_utc", r)
    return r


@pytest.fixture
def real(motores_falsos, relogio: Relogio) -> Relogio:
    """Modo real (motores falsos) com a demonstração restaurada."""
    assert TestClient(app).post("/demo/restaurar").status_code == 200
    return relogio


def _servico() -> Contas:
    return dependencias.contas(configuracao())


def _organizacao(c: TestClient) -> str:
    return str(c.get("/conta").json()["organizacao"]["id"])


def _arquivo(org: str) -> Path:
    return configuracao().pasta_organizacoes / f"{org}.db"


def _empresa_completa(c: TestClient) -> str:
    """A empresa com um item, um item arquivado, duas notas (e o alerta), um cliente B2B e uma correção de
    classificação. Devolve o id do item da compra do cliente."""
    cadastrar(c)
    r = c.post("/catalogo/itens", json=corpo_item())
    assert r.status_code == 201, r.text
    item = r.json()["item"]["id"]
    outro = c.post("/catalogo/itens", json=corpo_item(descricao="Outro", codigoFornecedor="X-1")).json()["item"]["id"]
    assert c.post(f"/catalogo/{outro}/arquivar", json={"cnpj": NUMERICO}).status_code == 200
    assert importar(c, compra_anterior_mais_barata()).status_code == 200
    assert importar(c, nota_da_empresa()).status_code == 200
    cliente = {
        "cnpj": NUMERICO,
        "cnpjCliente": CLIENTE,
        "razaoSocial": "Padaria do Beto Ltda",
        "regime": "regime_regular",
        "uf": "RS",
        "municipio": CAXIAS,
        "compraMensal": [{"itemId": item, "quantidade": "10"}],
    }
    r = c.post("/clientes", json=cliente)
    assert r.status_code == 201, r.text
    return item


def _contar(org: str, cnpj: str) -> dict[str, int]:
    with sqlite3.connect(_arquivo(org)) as b:
        return {
            t: b.execute(f"SELECT count(*) FROM {t} WHERE cnpj = ?", (cnpj,)).fetchone()[0]  # noqa: S608
            for t in TABELAS_DA_EMPRESA
        }


def baixar(c: TestClient, senha: str = SENHA, status: int = 200) -> Any:
    r = c.post("/conta/dados", json={"senha": senha})
    assert r.status_code == status, r.text
    return r


# -- o arquivo dos dados ------------------------------------------------------------------------------------


def test_o_arquivo_leva_a_conta_e_tudo_da_empresa(real) -> None:
    c = com_conta(real)
    _empresa_completa(c)
    r = baixar(c)
    assert r.headers["content-disposition"] == 'attachment; filename="contaai-dados-2026-11-26.json"'
    assert r.headers["cache-control"] == "no-store"
    dados = ContaDadosResposta.model_validate(r.json())
    assert dados.formato == "contaai-dados-1"
    assert dados.conta.email == "ana@exemplo.com.br" and dados.conta.situacao == "ativa"
    assert dados.conta.termos is not None and dados.conta.segundoFatorConfirmadoEm is not None
    assert dados.conta.codigosRecuperacaoRestantes == 10
    assert [s.atual for s in dados.conta.sessoes] == [True]
    [org] = dados.organizacoes
    assert org.papel == "dono" and org.nome == "Escritório da Ana"
    [empresa] = org.empresas
    assert empresa.cnpj == NUMERICO and empresa.empresa is not None
    assert empresa.empresa["razaoSocial"] == "Mercadinho da Ana Ltda"
    assert empresa.cenario is not None and empresa.cenario["origem"] == "empresa_propria"
    assert len(empresa.itens) == 2 and sum(i.arquivadoEm is not None for i in empresa.itens) == 1  # inclui o arquivado
    assert len(empresa.codigosFornecedor) == 1  # arquivar tira o código do fornecedor (a nota vira sem par)
    assert len(empresa.notas) == 2 and all(len(n.sha256) == 64 and n.recibo for n in empresa.notas)
    assert empresa.custos and empresa.precos and len(empresa.alertas) == 1
    [cliente] = empresa.clientesB2B
    assert cliente.cnpjCliente == CLIENTE and cliente.cliente["cliente"]["razaoSocial"] == "Padaria do Beto Ltda"
    assert any("XML" in frase for frase in dados.naoIncluido) and "arquivo fiscal" in dados.aviso


def test_o_arquivo_nao_leva_senha_segredo_nem_hash(real) -> None:
    c = navegador()
    segredo = cadastrar_conta(c).segredo
    r = c.post("/contas/ativar", json={"codigo": codigo(segredo, real.agora)})
    recuperacao = r.json()["codigosRecuperacao"]
    texto = baixar(c).text
    with sqlite3.connect(configuracao().contas_caminho) as b:
        guardados = [
            *(linha[0] for linha in b.execute("SELECT senha_hash FROM usuarios")),
            *(linha[0] for linha in b.execute("SELECT hash FROM sessoes")),
            *(linha[0] for linha in b.execute("SELECT hash FROM codigos_recuperacao")),
            *(linha[0] for linha in b.execute("SELECT segredo FROM segundo_fator")),
        ]
    for valor in [*guardados, segredo, SENHA, *recuperacao, c.cookies.get("__Host-contaai_sessao")]:
        assert valor and valor not in texto
    assert "hash" not in json.dumps(json.loads(texto)["conta"]).lower()


def test_baixar_pede_a_senha_e_a_errada_conta_como_falha(real) -> None:
    c = com_conta(real)
    baixar(c, "senha errada demais", 401)
    with sqlite3.connect(configuracao().contas_caminho) as b:
        assert b.execute("SELECT falhas_seguidas FROM tentativas").fetchone()[0] == 1
    for _ in range(4):
        baixar(c, "senha errada demais", 401)
    r = baixar(c, SENHA, 429)  # a quinta falha liga a espera: nem a senha certa passa antes do tempo
    assert "retry-after" in r.headers


def test_baixar_exige_a_conta(real) -> None:
    espaco = TestClient(app).post("/espacos").json()["id"]
    assert TestClient(app).post("/conta/dados", json={"senha": SENHA}).status_code == 401
    r = TestClient(app).post("/conta/dados", json={"senha": SENHA}, headers={"X-ContaAI-Espaco": espaco})
    assert r.status_code == 401
    app.dependency_overrides[configuracao] = lambda: Configuracao(modo="mock")
    assert navegador().post("/conta/dados", json={"senha": SENHA}).status_code == 501


def test_o_membro_baixa_as_empresas_sem_o_email_dos_outros(real) -> None:
    ana = com_conta(real)
    _empresa_completa(ana)
    bia = com_conta(real, "bia@exemplo.com.br")
    org_ana = _organizacao(ana)
    with sqlite3.connect(configuracao().contas_caminho) as b:
        id_bia = b.execute("SELECT id FROM usuarios WHERE email = 'bia@exemplo.com.br'").fetchone()[0]
        b.execute(
            "INSERT INTO membros (organizacao_id, usuario_id, papel, desde) VALUES (?, ?, 'membro', ?)",
            (org_ana, id_bia, INICIO.isoformat()),
        )
    r = baixar(bia)
    assert "ana@exemplo.com.br" not in r.text
    dados = ContaDadosResposta.model_validate(r.json())
    da_ana = next(o for o in dados.organizacoes if o.id == org_ana)
    assert da_ana.papel == "membro" and [e.cnpj for e in da_ana.empresas] == [NUMERICO]
    assert next(o for o in dados.organizacoes if o.id != org_ana).empresas == []


def test_organizacao_sem_empresa_nao_cria_o_banco(real) -> None:
    c = com_conta(real)
    baixar(c)
    assert not _arquivo(_organizacao(c)).exists()


def test_acesso_que_sobrou_sai_no_arquivo_sem_dados(real) -> None:
    c = com_conta(real)
    c.get("/alertas")  # cria o banco da organização
    _servico().vincular_empresa(_organizacao(c), NUMERICO, real.agora)
    [empresa] = ContaDadosResposta.model_validate(baixar(c).json()).organizacoes[0].empresas
    assert empresa.cnpj == NUMERICO and empresa.empresa is None and empresa.itens == []


# -- excluir a empresa --------------------------------------------------------------------------------------


def excluir(c: TestClient, cnpj: str = NUMERICO, senha: str = SENHA, confirmacao: str | None = None) -> Any:
    return c.post(f"/empresas/{cnpj}/excluir", json={"senha": senha, "cnpjConfirmacao": confirmacao or cnpj})


def test_excluir_a_empresa_apaga_tudo_dela_e_a_conta_fica(real) -> None:
    demo_antes = TestClient(app).get(f"/catalogo?cnpj={SERRA_AZUL}").json()
    c = com_conta(real)
    _empresa_completa(c)
    cadastrar(c, ALFANUMERICO)
    org = _organizacao(c)
    assert all(_contar(org, NUMERICO)[t] for t in ("empresas", "itens", "notas", "custos", "alertas", "clientes_b2b"))
    r = excluir(c)
    assert r.status_code == 204, r.text
    assert r.content == b""
    assert set(_contar(org, NUMERICO).values()) == {0}
    assert c.get(f"/empresas/{NUMERICO}").status_code == 404
    assert c.get("/conta").json()["empresas"] == [ALFANUMERICO]  # a outra empresa e a conta continuam
    assert c.get(f"/empresas/{ALFANUMERICO}").status_code == 200
    cadastrar(c)  # o CNPJ pode voltar, do zero
    assert c.get(f"/catalogo?cnpj={NUMERICO}").json()["itens"] == []
    assert TestClient(app).get(f"/catalogo?cnpj={SERRA_AZUL}").json() == demo_antes


def test_excluir_a_empresa_confere_o_cnpj_antes_da_senha(real) -> None:
    c = com_conta(real)
    cadastrar(c)
    r = excluir(c, confirmacao=ALFANUMERICO)
    assert r.status_code == 422 and "não é o desta empresa" in r.json()["detail"], r.text
    assert excluir(c, confirmacao="11222333000182").status_code == 422
    assert c.post(f"/empresas/{NUMERICO}/excluir", json={"senha": SENHA}).status_code == 422  # sem a confirmação
    with sqlite3.connect(configuracao().contas_caminho) as b:
        assert b.execute("SELECT count(*) FROM tentativas").fetchone()[0] == 0  # o CNPJ errado não gastou a senha
    assert excluir(c, senha="senha errada demais").status_code == 401
    with sqlite3.connect(configuracao().contas_caminho) as b:
        assert b.execute("SELECT falhas_seguidas FROM tentativas").fetchone()[0] == 1
    assert c.get(f"/empresas/{NUMERICO}").status_code == 200


def test_so_o_dono_exclui_a_empresa_e_outra_conta_ve_404(real) -> None:
    ana = com_conta(real)
    cadastrar(ana)
    bia = com_conta(real, "bia@exemplo.com.br")
    assert excluir(bia).status_code == 404
    with _servico().banco.transacao(escrita=True) as conexao:
        conexao.execute("UPDATE membros SET papel = 'membro'")
    r = excluir(ana)
    assert r.status_code == 403 and "Só o dono" in r.json()["detail"]
    assert ana.get(f"/empresas/{NUMERICO}").status_code == 200


def test_excluir_a_empresa_sem_sessao_e_no_modo_mock(real) -> None:
    assert excluir(TestClient(app)).status_code == 401
    app.dependency_overrides[configuracao] = lambda: Configuracao(modo="mock")
    assert excluir(navegador()).status_code == 501


def test_falha_no_meio_deixa_so_o_acesso_e_o_recadastro_aceita(real, monkeypatch: pytest.MonkeyPatch) -> None:
    c = com_conta(real)
    cadastrar(c)
    org = _organizacao(c)

    def falhar(*_: object) -> None:
        raise RuntimeError("banco das contas indisponível (teste)")

    original = Contas.desvincular_empresa
    monkeypatch.setattr(Contas, "desvincular_empresa", falhar)
    r = excluir(c)  # o 500 tratado (C3-B, etapa 9), sem a mensagem da exceção
    assert r.status_code == 500 and "indisponível" not in r.text
    monkeypatch.setattr(Contas, "desvincular_empresa", original)
    assert _contar(org, NUMERICO)["empresas"] == 0
    assert c.get("/conta").json()["empresas"] == [NUMERICO]  # sobrou só o acesso
    assert excluir(c).status_code == 204  # a sobra também sai por aqui
    assert c.get("/conta").json()["empresas"] == []
    cadastrar(c)


def test_excluir_a_empresa_tem_csrf_e_limite_de_entrada(real, monkeypatch: pytest.MonkeyPatch) -> None:
    c = com_conta(real)
    cadastrar(c)
    sem_origin = TestClient(app, base_url="https://testserver", cookies=c.cookies)
    corpo = {"senha": SENHA, "cnpjConfirmacao": NUMERICO}
    assert sem_origin.post(f"/empresas/{NUMERICO}/excluir", json=corpo).status_code == 403
    assert sem_origin.post("/conta/dados", json={"senha": SENHA}).status_code == 403
    outro_site = {"Origin": "https://ataque.exemplo.test"}
    assert c.post(f"/empresas/{NUMERICO}/excluir", json=corpo, headers=outro_site).status_code == 403
    monkeypatch.setattr(middlewares, "LIMITE_ENTRADA", LimitadorPorIp(1))
    assert excluir(c, senha="senha errada demais").status_code == 401
    assert excluir(c).status_code == 429
    monkeypatch.setattr(middlewares, "LIMITE_ENTRADA", LimitadorPorIp(1))
    baixar(c)
    baixar(c, status=429)
    assert c.get(f"/empresas/{NUMERICO}").status_code == 200


def test_erros_da_exclusao_nao_repetem_o_que_foi_enviado(real) -> None:
    c = com_conta(real)
    cadastrar(c)
    marcador = "<script>alert(1)</script>"
    for r in (
        excluir(c, senha=marcador),
        c.post(f"/empresas/{NUMERICO}/excluir", json={"senha": "x", "cnpjConfirmacao": marcador}),
        c.post("/conta/dados", json={"senha": marcador}),
    ):
        assert r.status_code in (401, 422) and marcador not in r.text and "alert" not in r.text, r.text


# -- exclusão da conta --------------------------------------------------------------------------------------


def test_excluir_a_conta_apaga_todas_as_organizacoes_em_que_era_a_unica(real) -> None:
    """Achado do mapa da etapa 7: só o banco da organização da sessão saía; o das outras ficava no disco."""
    c = com_conta(real)
    cadastrar(c)
    org = _organizacao(c)
    outra = "f" * 32
    with sqlite3.connect(configuracao().contas_caminho) as b:
        usuario = b.execute("SELECT id FROM usuarios").fetchone()[0]
        b.execute("INSERT INTO organizacoes (id, nome, criada_em) VALUES (?, 'Outra', ?)", (outra, INICIO.isoformat()))
        b.execute(
            "INSERT INTO membros (organizacao_id, usuario_id, papel, desde) VALUES (?, ?, 'dono', ?)",
            (outra, usuario, INICIO.isoformat()),
        )
    dependencias.banco_da_organizacao(configuracao(), outra)  # cria o banco dela
    assert _arquivo(org).exists() and _arquivo(outra).exists()
    assert c.post("/conta/excluir", json={"senha": SENHA}).status_code == 204
    assert not _arquivo(org).exists() and not _arquivo(outra).exists()
    assert _servico().organizacoes() == frozenset()


# -- limpeza na subida --------------------------------------------------------------------------------------


def test_limpeza_apaga_so_os_bancos_de_organizacoes_que_nao_existem(real, caplog: pytest.LogCaptureFixture) -> None:
    c = com_conta(real)
    cadastrar(c)
    org = _organizacao(c)
    pasta = configuracao().pasta_organizacoes
    orfa = "a" * 32
    for sufixo in (".db", ".db-wal", ".db-shm", ".db-journal"):
        (pasta / f"{orfa}{sufixo}").write_bytes(b"")
    (pasta / "anotacoes.txt").write_text("fora do padrão", encoding="utf-8")
    (pasta / f"{'B' * 32}.db").write_bytes(b"")  # maiúsculas: fora do padrão, fica
    with caplog.at_level(logging.INFO, logger="contaai"):
        apagados = dependencias.limpar_bancos_orfaos(configuracao())
    assert sorted(apagados) == sorted(f"{orfa}{s}" for s in (".db", ".db-wal", ".db-shm", ".db-journal"))
    restantes = sorted(p.name for p in pasta.iterdir())
    assert f"{org}.db" in restantes and "anotacoes.txt" in restantes and f"{'B' * 32}.db" in restantes
    assert not any(n.startswith(orfa) for n in restantes)
    assert "anotacoes.txt" in caplog.text
    assert c.get(f"/empresas/{NUMERICO}").status_code == 200  # a organização que existe não foi tocada


def test_limpeza_sem_a_pasta_nao_faz_nada() -> None:
    assert dependencias.limpar_bancos_orfaos(Configuracao(modo="real")) == []


def test_a_subida_limpa_os_bancos_orfaos(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CONTAAI_MODO", "real")
    monkeypatch.setenv("CONTAAI_SEMEAR_AO_SUBIR", "false")
    configuracao.cache_clear()
    cfg = configuracao()
    cfg.pasta_organizacoes.mkdir(parents=True)
    orfao = cfg.pasta_organizacoes / f"{'c' * 32}.db"
    orfao.write_bytes(b"")

    async def subir() -> None:
        async with main.ciclo_de_vida(app):
            pass

    asyncio.run(subir())
    assert not orfao.exists()


# -- registros sem dado pessoal -----------------------------------------------------------------------------


def test_o_log_de_acesso_do_uvicorn_fica_desligado() -> None:
    assert logging.getLogger("uvicorn.access").disabled


def test_o_log_de_acesso_grava_a_rota_modelo_sem_cnpj_nem_ip(real, caplog: pytest.LogCaptureFixture) -> None:
    c = com_conta(real)
    cadastrar(c, ALFANUMERICO)
    caplog.clear()
    with caplog.at_level(logging.INFO, logger="contaai.acesso"):
        c.get(f"/empresas/{ALFANUMERICO}")
        c.get(f"/clientes/{ALFANUMERICO}/nao-existe")
        c.delete(f"/empresas/{ALFANUMERICO}")  # o caminho existe, o método não (405)
    linhas = [r.getMessage() for r in caplog.records if r.name == "contaai.acesso"]
    assert linhas[0].startswith("GET /empresas/{cnpj} 200 ")
    assert linhas[1].startswith("GET - 404 ")
    assert linhas[2].startswith("DELETE /empresas/{cnpj} 405 ")
    texto = "\n".join(linhas)
    assert ALFANUMERICO not in texto and "testclient" not in texto and "127.0.0.1" not in texto


def test_o_log_de_acesso_registra_as_recusas_dos_middlewares(real, caplog: pytest.LogCaptureFixture) -> None:
    c = com_conta(real)
    caplog.clear()
    with caplog.at_level(logging.INFO, logger="contaai.acesso"):
        c.post(f"/empresas/{NUMERICO}/excluir", json={}, headers={"Origin": "https://ataque.exemplo.test"})
    assert [r.getMessage().split(" ms")[0].rsplit(" ", 1)[0] for r in caplog.records if r.name == "contaai.acesso"] == [
        "POST /empresas/{cnpj}/excluir 403"
    ]


def test_o_erro_500_vai_ao_log_sem_a_mensagem(
    real, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    c = com_conta(real)
    cadastrar(c)

    def quebrar(*_: object) -> None:
        raise ValueError("ana@exemplo.com.br 11222333000181")

    monkeypatch.setattr(cadastro, "ler_empresa", quebrar)
    sem_repassar = TestClient(app, base_url="https://testserver", cookies=c.cookies, raise_server_exceptions=False)
    with caplog.at_level(logging.INFO):
        r = sem_repassar.get(f"/empresas/{NUMERICO}")
    assert r.status_code == 500 and "ana@" not in r.text
    erro = [rec for rec in caplog.records if rec.name == "contaai" and "Erro não tratado" in rec.getMessage()]
    assert len(erro) == 1 and erro[0].exc_info is None
    assert "builtins.ValueError" in erro[0].getMessage() and "app/api/rotas/empresa.py" in erro[0].getMessage()
    do_servidor = " | ".join(r.getMessage() for r in caplog.records if r.name.startswith(("contaai", "uvicorn")))
    assert "ana@" not in do_servidor and NUMERICO not in do_servidor  # o httpx2 é o cliente de teste, não o servidor


def test_o_filtro_tira_a_mensagem_do_log_do_uvicorn(caplog: pytest.LogCaptureFixture) -> None:
    """O Starlette relança a exceção depois do 500, e o uvicorn grava a pilha: o filtro tira a mensagem."""
    try:
        raise NaoEncontrado("bia@exemplo.com.br")
    except NaoEncontrado as e:
        excecao = e
    with caplog.at_level(logging.ERROR, logger="uvicorn.error"):
        logging.getLogger("uvicorn.error").error("Exception in ASGI application\n", exc_info=excecao)
    [rec] = [r for r in caplog.records if r.name == "uvicorn.error"]
    assert rec.exc_info is None and "bia@" not in caplog.text
    assert rec.getMessage().startswith("Exception in ASGI application: app.nfe.consultas.NaoEncontrado (")
    assert "tests/test_exclusao_e_dados.py" in rec.getMessage()


def test_resumo_de_excecao_sem_pilha() -> None:
    assert registro.resumo_da_excecao(KeyError("segredo")) == "builtins.KeyError"
