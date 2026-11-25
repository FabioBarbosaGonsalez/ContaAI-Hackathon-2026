"""E4 (ADR 0008): leitor seguro da NF-e, migrações, importação, alertas, catálogo, painel e proteções.

Rodam no CI com os motores falsos do conftest (valores fictícios). Os números reais da demonstração
(24,12% → 11,19% e R$ 3,97) são conferidos em tests/test_nfe_golden.py, contra os motores.
"""

from __future__ import annotations

import re
import sqlite3
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Configuracao, configuracao
from app.contrato import (
    AlertasResposta,
    AplicarAlertaResposta,
    CatalogoResposta,
    ChatResposta,
    NfeImportarResposta,
    PainelContadorResposta,
)
from app.dados_demo import PASTA_DEMO
from app.main import app
from app.nfe.leitor import MAX_ITENS, NotaInvalida, ler_nfe
from app.persistencia.banco import Banco, MigracaoAlterada

cliente = TestClient(app)
NOTAS = PASTA_DEMO / "notas"
SERRA_AZUL, VALE_VERDE, LAGOA = "36817420000113", "52918364000170", "41736592000102"
NOTA_1, NOTA_2, SEM_PAR = (NOTAS / n for n in ("nfe-compra-1.xml", "nfe-compra-2.xml", "nfe-item-sem-par.xml"))


def nota(caminho: Path) -> bytes:
    return caminho.read_bytes()


def importar(conteudo: bytes, status: int = 200, tipo: str = "text/xml", **headers: str) -> dict:
    r = cliente.post("/nfe/importar", files={"arquivo": ("nota.xml", conteudo, tipo)}, headers=headers)
    assert r.status_code == status, r.text
    return r.json()


@pytest.fixture
def demo(motores_falsos):
    """Modo real com os motores falsos e o estado restaurado às sementes."""
    r = cliente.post("/demo/restaurar")
    assert r.status_code == 200, r.text
    return motores_falsos


# ---------------------------------------------------------------------------
# Leitor


def test_le_as_notas_da_demo() -> None:
    n1, n2 = ler_nfe(nota(NOTA_1)), ler_nfe(nota(NOTA_2))
    assert (n1.numero, n1.temGrupoIbsCbs, len(n1.itens)) == ("1001", False, 5)
    assert (n2.numero, n2.temGrupoIbsCbs, n2.homologacao) == ("1002", True, True)
    cerveja = next(i for i in n2.itens if i.ncm == "22030000")
    assert cerveja.vUnCom == Decimal("3.05") and cerveja.ibscbs is not None
    assert cerveja.ibscbs.credito == Decimal("386.50") + Decimal("4.40")  # vCBS + vIBS do item


def test_aceita_a_nota_dentro_do_nfeproc() -> None:
    corpo = nota(NOTA_2).split(b"?>", 1)[1]
    proc = b'<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe" versao="4.00">' + corpo + b"</nfeProc>"
    assert ler_nfe(proc).numero == "1002"


BOMBA = b"""<?xml version="1.0"?>
<!DOCTYPE l [<!ENTITY a "aaaaaaaaaa"><!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;">]>
<NFe xmlns="http://www.portalfiscal.inf.br/nfe">&b;</NFe>"""
EXTERNA = b"""<?xml version="1.0"?>
<!DOCTYPE NFe [<!ENTITY x SYSTEM "file:///etc/passwd">]>
<NFe xmlns="http://www.portalfiscal.inf.br/nfe">&x;</NFe>"""
DTD_EXTERNO = b"""<?xml version="1.0"?><!DOCTYPE NFe SYSTEM "http://exemplo.invalido/x.dtd"><NFe/>"""


@pytest.mark.parametrize("conteudo", [BOMBA, EXTERNA, DTD_EXTERNO], ids=["billion-laughs", "externa", "dtd"])
def test_recusa_dtd_e_entidades(conteudo: bytes) -> None:
    with pytest.raises(NotaInvalida, match="DTD ou entidade"):
        ler_nfe(conteudo)


def test_recusa_xml_mal_formado_e_raiz_errada() -> None:
    with pytest.raises(NotaInvalida, match="bem formado"):
        ler_nfe(b"<NFe><sem-fechar>")
    with pytest.raises(NotaInvalida, match="não é uma NF-e"):
        ler_nfe(b'<?xml version="1.0"?><outra/>')


def test_recusa_aninhamento_profundo() -> None:
    profundo = b'<NFe xmlns="http://www.portalfiscal.inf.br/nfe">' + b"<a>" * 40 + b"</a>" * 40 + b"</NFe>"
    with pytest.raises(NotaInvalida, match="aninhamento"):
        ler_nfe(profundo)


def _trocar(conteudo: bytes, de: str, para: str) -> bytes:
    assert de.encode() in conteudo, de
    return conteudo.replace(de.encode(), para.encode(), 1)


@pytest.mark.parametrize(
    ("de", "para", "mensagem"),
    [
        ("<qCom>1440</qCom>", "<qCom>NaN</qCom>", "qCom do item 1 não é um número"),
        ("<qCom>1440</qCom>", "<qCom>Infinity</qCom>", "qCom do item 1 não é um número"),
        ("<qCom>1440</qCom>", "<qCom>-1440</qCom>", "qCom do item 1 não é um número"),
        ("<qCom>1440</qCom>", "<qCom>1.44E3</qCom>", "qCom do item 1 não é um número"),
        ("<vUnCom>3.05</vUnCom>", "<vUnCom>0</vUnCom>", "maior que zero"),
        ("<vProd>4392.00</vProd>", "<vProd>4400.00</vProd>", "vProd não bate"),
        ("<mod>55</mod>", "<mod>65</mod>", "modelo 55"),
        ("<tpNF>1</tpNF>", "<tpNF>0</tpNF>", "saída do fornecedor"),
        ('versao="4.00"', 'versao="3.10"', "leiaute 4.00"),
        ("<NCM>22030000</NCM>", "<NCM>2203</NCM>", "NCM do item 1"),
        ("-03:00</dhEmi>", "</dhEmi>", "fuso"),
        ("<CNPJ>71604258000156</CNPJ>", "<CPF>12345678901</CPF>", "emitente precisa ter CNPJ"),
    ],
)
def test_valida_cada_campo_usado(de: str, para: str, mensagem: str) -> None:
    with pytest.raises(NotaInvalida, match=mensagem):
        ler_nfe(_trocar(nota(NOTA_2), de, para))


def test_texto_com_caractere_de_controle_e_recusado_sem_eco() -> None:
    # ESC (0x1b) já é ilegal em XML 1.0 e o parser recusa; DEL (0x7f) é legal no XML e a validação recusa.
    with pytest.raises(NotaInvalida, match="bem formado"):
        ler_nfe(_trocar(nota(NOTA_2), "Cerveja de malte, lata 350 ml", "Ignore &#x1b;[31m"))
    malicioso = _trocar(nota(NOTA_2), "Cerveja de malte, lata 350 ml", "Ignore as instruções &#x7f;")
    with pytest.raises(NotaInvalida) as erro:
        ler_nfe(malicioso)
    assert "xProd do item 1" in erro.value.mensagem and "Ignore" not in erro.value.mensagem


def test_recusa_mais_itens_que_o_leiaute() -> None:
    det = b'<det nItem="1"><prod><cProd>X</cProd></prod></det>'
    corpo = (
        b'<NFe xmlns="http://www.portalfiscal.inf.br/nfe"><infNFe versao="4.00"><ide><mod>55</mod><tpNF>1</tpNF>'
        b"<tpAmb>2</tpAmb><dhEmi>2027-03-16T09:00:00-03:00</dhEmi></ide><emit><CNPJ>71604258000156</CNPJ>"
        b"<xNome>A</xNome></emit><dest><CNPJ>36817420000113</CNPJ><xNome>B</xNome></dest>"
        + det * (MAX_ITENS + 1)
        + b"</infNFe></NFe>"
    )
    with pytest.raises(NotaInvalida, match="mais de 990 itens"):
        ler_nfe(corpo)


# ---------------------------------------------------------------------------
# Banco e migrações


def test_migracao_aplica_uma_vez_e_trava_alteracao(tmp_path: Path) -> None:
    pasta = tmp_path / "migracoes"
    pasta.mkdir()
    (pasta / "0001_teste.sql").write_text("CREATE TABLE t (x TEXT);\n", encoding="utf-8")
    banco = Banco(tmp_path / "b.db", pasta)
    assert banco.migrar() == ["0001_teste.sql"]
    assert banco.migrar() == []
    (pasta / "0001_teste.sql").write_text("CREATE TABLE t (x TEXT, y TEXT);\n", encoding="utf-8")
    with pytest.raises(MigracaoAlterada):
        banco.migrar()


def test_migracao_com_erro_nao_fica_pela_metade(tmp_path: Path) -> None:
    pasta = tmp_path / "migracoes"
    pasta.mkdir()
    (pasta / "0001_quebrada.sql").write_text("CREATE TABLE a (x TEXT);\nCREATE TABLE a (x TEXT);\n", encoding="utf-8")
    banco = Banco(tmp_path / "b.db", pasta)
    with pytest.raises(sqlite3.OperationalError):
        banco.migrar()
    with banco.transacao() as c:
        assert c.execute("SELECT name FROM sqlite_master WHERE name = 'a'").fetchone() is None
        assert c.execute("SELECT count(*) FROM schema_migrations").fetchone()[0] == 0


def test_lancamentos_de_custo_nao_se_alteram(demo) -> None:
    caminho = configuracao().banco_caminho
    with sqlite3.connect(caminho) as c, pytest.raises(sqlite3.IntegrityError, match="não se altera"):
        c.execute("UPDATE custos SET custo_unitario = '0.01'")


# ---------------------------------------------------------------------------
# Importação pela rota


def test_restaurar_carrega_as_tres_empresas_e_as_notas_iniciais(motores_falsos) -> None:
    r = cliente.post("/demo/restaurar")
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["empresas"] == 3 and corpo["notasImportadas"] == ["1001", "2001", "2002", "3001"]
    # Restaurar de novo dá o mesmo estado.
    assert cliente.post("/demo/restaurar").json() == corpo


def test_nota_2_gera_o_alerta_da_cerveja_com_preco_sugerido(demo) -> None:
    corpo = NfeImportarResposta.model_validate(importar(nota(NOTA_2)))
    assert not corpo.jaImportada and corpo.nota.numero == "1002" and corpo.nota.homologacao
    cerveja = next(i for i in corpo.itensCasados if i.itemId == "cerveja-lata")
    assert (cerveja.custoAnterior, cerveja.custoNovo, cerveja.variacaoPct) == (
        Decimal("2.60"),
        Decimal("3.05"),
        Decimal("17.31"),
    )
    assert cerveja.fonteCredito == "nfe" and cerveja.creditoCompraUnitario == Decimal("0.2715")
    [alerta] = corpo.alertas
    assert alerta.itemId == "cerveja-lata" and alerta.cnpj == SERRA_AZUL
    assert alerta.margemDepoisPct < alerta.margemAlvoPct < alerta.margemAntesPct
    assert alerta.precoSugerido is not None and alerta.precoSugerido > alerta.precoAtual == Decimal("3.79")
    assert alerta.simulado and alerta.avisoSimulacao and alerta.premissas
    assert any(p.nome == "Margem do alerta" for p in alerta.premissas)
    assert re.fullmatch(r"alerta-[0-9a-f]{16}", alerta.id)


def test_importar_de_novo_devolve_o_recibo_sem_gravar(demo) -> None:
    primeira = importar(nota(NOTA_2))
    segunda = importar(nota(NOTA_2))
    assert segunda["jaImportada"] is True
    assert {**segunda, "jaImportada": False} == primeira
    assert len(AlertasResposta.model_validate(cliente.get(f"/alertas?cnpj={SERRA_AZUL}").json()).alertas) == 1


def test_mesma_nota_com_outro_conteudo_e_conflito(demo) -> None:
    importar(nota(NOTA_2))
    alterada = _trocar(nota(NOTA_2), "<vUnCom>3.05</vUnCom>", "<vUnCom>3.10</vUnCom>")
    alterada = _trocar(alterada, "<vProd>4392.00</vProd>", "<vProd>4464.00</vProd>")
    assert "já foi importada com outro conteúdo" in importar(alterada, status=409)["detail"]


def test_destinatario_fora_das_empresas_e_recusado_sem_gravar(demo) -> None:
    alheia = _trocar(nota(NOTA_2), "<CNPJ>36817420000113</CNPJ>", "<CNPJ>11222333000181</CNPJ>")
    detalhe = importar(alheia, status=422)["detail"]
    assert "não é uma empresa cadastrada" in detalhe and "11222333000181" not in detalhe
    assert cliente.get("/alertas?cnpj=11222333000181").status_code == 404
    assert importar(nota(NOTA_2))["jaImportada"] is False  # nada da nota alheia ficou gravado


def test_itens_sem_par_viram_pergunta_com_motivo(demo) -> None:
    corpo = NfeImportarResposta.model_validate(importar(nota(SEM_PAR)))
    assert [i.itemId for i in corpo.itensCasados] == ["chocolate-barra"]
    motivos = {i.codigoFornecedor: i.motivo for i in corpo.itensSemPar}
    assert "sem cadastro" in motivos["AE-REF-2L"]
    assert "NCM da nota diferente" in motivos["AE-BIS-140"]
    # O chocolate saiu pelo motor (nota sem grupo IBSCBS), com a premissa impressa.
    assert corpo.itensCasados[0].fonteCredito == "motor"
    assert any("sem grupo IBSCBS" in p.nome for p in corpo.premissas)


def test_nota_mais_antiga_que_o_custo_atual_nao_muda_o_custo(demo) -> None:
    importar(nota(NOTA_2))
    antiga = _trocar(_trocar(nota(NOTA_2), "<nNF>1002</nNF>", "<nNF>999</nNF>"), "2027-03-16T09", "2027-02-10T09")
    corpo = NfeImportarResposta.model_validate(importar(antiga))
    assert all(not i.atualizaCusto for i in corpo.itensCasados) and corpo.alertas == []
    cat = CatalogoResposta.model_validate(cliente.get(f"/catalogo?cnpj={SERRA_AZUL}").json())
    cerveja = next(i for i in cat.itens if i.id == "cerveja-lata")
    assert cerveja.custoAtual.custoUnitario == Decimal("3.05") and cerveja.custoAtual.notaNumero == "1002"
    assert [h.notaNumero for h in cerveja.historicoCusto] == ["1002", "1001", "999"]


def test_aplicar_o_preco_atualiza_o_catalogo_e_so_uma_vez(demo) -> None:
    [alerta] = NfeImportarResposta.model_validate(importar(nota(NOTA_2))).alertas
    r = cliente.post(f"/alertas/{alerta.id}/aplicar")
    assert r.status_code == 200, r.text
    aplicado = AplicarAlertaResposta.model_validate(r.json())
    assert (aplicado.precoAnterior, aplicado.precoNovo) == (Decimal("3.79"), alerta.precoSugerido)
    assert aplicado.alerta.aplicadoEm is not None
    cat = CatalogoResposta.model_validate(cliente.get(f"/catalogo?cnpj={SERRA_AZUL}").json())
    assert next(i for i in cat.itens if i.id == "cerveja-lata").precoVenda == alerta.precoSugerido
    assert cliente.post(f"/alertas/{alerta.id}/aplicar").status_code == 409
    abertos = AlertasResposta.model_validate(cliente.get(f"/alertas?cnpj={SERRA_AZUL}&abertos=true").json())
    assert abertos.alertas == []
    assert cliente.post("/alertas/alerta-0000000000000000/aplicar").status_code == 404


def test_painel_do_contador_poe_a_empresa_com_mais_alertas_primeiro(demo) -> None:
    painel = PainelContadorResposta.model_validate(cliente.get("/contador/painel").json())
    assert [e.empresa.cnpj for e in painel.empresas][0] == VALE_VERDE
    por_cnpj = {e.empresa.cnpj: e for e in painel.empresas}
    assert set(por_cnpj) == {SERRA_AZUL, VALE_VERDE, LAGOA}
    assert por_cnpj[VALE_VERDE].alertasAbertos == 2 and por_cnpj[LAGOA].alertasAbertos == 0
    assert por_cnpj[LAGOA].empresa.regimeAtual == "simples_hibrido"
    assert "fictícios" in painel.aviso


def test_importacao_dentro_do_tempo_do_plano(demo) -> None:
    """Plano, E4: a nota gera o alerta em menos de 5 s (aqui com motores falsos; o golden mede com os reais)."""
    import time

    inicio = time.perf_counter()
    importar(nota(NOTA_2))
    assert time.perf_counter() - inicio < 5


# ---------------------------------------------------------------------------
# Proteções


@pytest.fixture
def com_token(demo):
    app.dependency_overrides[configuracao] = lambda: Configuracao(modo="real", token_demo="segredo-de-teste")
    return demo


def test_rotas_que_mudam_o_estado_exigem_o_token(com_token) -> None:
    assert importar(nota(NOTA_2), status=401)["detail"] == "Token da demo ausente ou inválido."
    assert cliente.post("/demo/restaurar").status_code == 401
    assert cliente.post("/alertas/alerta-0000000000000000/aplicar").status_code == 401
    # Leituras não pedem token.
    assert cliente.get(f"/catalogo?cnpj={SERRA_AZUL}").status_code == 200
    corpo = importar(nota(NOTA_2), **{"X-ContaAI-Token": "segredo-de-teste"})
    assert len(corpo["alertas"]) == 1


def test_upload_que_nao_e_xml_e_recusado(demo) -> None:
    assert importar(b"%PDF-1.7", status=415, tipo="application/pdf")["detail"] == "Envie o arquivo XML da NF-e."


def test_cabecalhos_de_seguranca_em_toda_resposta(demo) -> None:
    for r in (cliente.get(f"/catalogo?cnpj={SERRA_AZUL}"), cliente.get("/alertas"), cliente.get("/saude")):
        assert r.headers["X-Content-Type-Options"] == "nosniff"
        assert r.headers["X-Frame-Options"] == "DENY"
        assert r.headers["Content-Security-Policy"] == "default-src 'none'; frame-ancestors 'none'"
        assert r.headers["Cache-Control"] == "no-store"
    docs = cliente.get("/docs")
    assert docs.status_code == 200 and "Content-Security-Policy" not in docs.headers


def test_erro_do_leitor_nao_repete_o_xml(demo) -> None:
    r = importar(BOMBA, status=422)
    assert "ENTITY" not in r["detail"] and "aaaa" not in r["detail"]


def test_cnpj_invalido_na_consulta_e_recusado(demo) -> None:
    assert cliente.get("/catalogo?cnpj=../../etc").status_code == 422
    assert cliente.get("/catalogo?cnpj=00000000000000").status_code == 404


# ---------------------------------------------------------------------------
# Agente (E4-05)


def test_agente_lista_os_alertas_sem_numero_inventado(demo) -> None:
    importar(nota(NOTA_2))
    corpo = {
        "mensagens": [{"papel": "usuario", "texto": "O que mudou este mês?"}],
        "contexto": {
            "data": "2027-03-16",
            "uf": "RS",
            "municipio": 4314902,
            "aliquotasNominais": {"cbs": "8.8", "ibsEstadual": "0.05", "ibsMunicipal": "0.05"},
            "premissasDas": {"anexo": "I", "cAtivSN": "01", "pCBSSN": "1.1612", "pIBSSN": "0.0129"},
            "regime": "simples_tradicional",
            "itens": [],
            "cnpj": SERRA_AZUL,
        },
    }
    r = ChatResposta.model_validate(cliente.post("/chat", json=corpo).json())
    assert r.ferramentasChamadas == ["listar_alertas"] and r.verificacao == "aprovada"
    assert "Cerveja de malte" in r.resposta and "nota 1002 de 16/03/2027" in r.resposta
    assert "R$ 3,79" in r.resposta  # o preço atual, que está no JSON da ferramenta


# ---------------------------------------------------------------------------
# Pacote A (antes do commit da E4): restauração atômica, checagem otimista, pasta das sementes e datas


def _estado_serra_azul() -> dict:
    return cliente.get(f"/catalogo?cnpj={SERRA_AZUL}").json()


def test_restauracao_com_motor_caindo_no_meio_nao_muda_o_estado(demo) -> None:
    importar(nota(NOTA_2))
    antes = _estado_serra_azul()
    from app.motores.cache import CacheRespostas

    demo.cache = CacheRespostas()  # sem cache: as chamadas da restauração precisam chegar ao motor
    demo.resposta_rr = (500, {"title": "falha interna do motor"})  # o motor RR cai durante a restauração
    r = cliente.post("/demo/restaurar")
    assert r.status_code in (502, 503), r.text
    demo.resposta_rr = None
    assert _estado_serra_azul() == antes  # a nota 2 continua lá: o banco principal não foi tocado
    assert len(AlertasResposta.model_validate(cliente.get(f"/alertas?cnpj={SERRA_AZUL}").json()).alertas) == 1


def _nota_concorrente(numero: str, dia: str) -> bytes:
    """Outra nota do mesmo fornecedor e da mesma cerveja, emitida antes da nota 2."""
    outra = _trocar(nota(NOTA_2), "<nNF>1002</nNF>", f"<nNF>{numero}</nNF>")
    return _trocar(outra, "2027-03-16T09", f"2027-03-{dia}T09")


def test_nota_concorrente_no_meio_refaz_a_importacao_com_o_custo_novo(demo, monkeypatch) -> None:
    """A3: outra nota do mesmo item entra enquanto esta chama os motores; a gravação percebe e refaz."""
    from app.api.dependencias import banco
    from app.nfe import importacao
    from app.persistencia.repositorio import Repositorio

    original, chamadas = importacao.margens, {"n": 0}

    async def margens_com_concorrente(motores, reg, linhas):
        chamadas["n"] += 1
        if chamadas["n"] == 1:  # só na primeira tentativa: grava a nota 1500, de 10/03, no meio
            repo = Repositorio(banco(configuracao().banco_caminho))
            await importacao.importar_nota(_nota_concorrente("1500", "10"), repo, motores)
        return await original(motores, reg, linhas)

    monkeypatch.setattr(importacao, "margens", margens_com_concorrente)
    corpo = NfeImportarResposta.model_validate(importar(nota(NOTA_2)))
    cerveja = next(i for i in corpo.itensCasados if i.itemId == "cerveja-lata")
    # Refeita: o custo anterior é o da nota 1500 (concorrente), e não o da 1001 lido na primeira tentativa.
    historico = next(i for i in CatalogoResposta.model_validate(_estado_serra_azul()).itens if i.id == "cerveja-lata")
    assert [h.notaNumero for h in historico.historicoCusto] == ["1002", "1500", "1001"]
    assert cerveja.custoAnterior == Decimal("3.05")  # a nota 1500 é cópia da 1002 com outra data


def test_estado_que_muda_nas_duas_tentativas_da_409_sem_gravar(demo, monkeypatch) -> None:
    from app.api.dependencias import banco
    from app.nfe import importacao
    from app.persistencia.repositorio import Repositorio

    original, numeros, chamadas = importacao.margens, iter(["1501", "1502"]), {"n": 0}

    async def sempre_concorrente(motores, reg, linhas):
        chamadas["n"] += 1
        if chamadas["n"] % 2 == 1:  # na 1ª chamada (margem "antes") de cada tentativa, outra nota entra no meio
            repo = Repositorio(banco(configuracao().banco_caminho))
            monkeypatch.setattr(importacao, "margens", original)
            await importacao.importar_nota(_nota_concorrente(next(numeros), "11"), repo, motores)
            monkeypatch.setattr(importacao, "margens", sempre_concorrente)
        return await original(motores, reg, linhas)

    monkeypatch.setattr(importacao, "margens", sempre_concorrente)
    assert "mudou durante a importação" in importar(nota(NOTA_2), status=409)["detail"]
    monkeypatch.setattr(importacao, "margens", original)
    assert importar(nota(NOTA_2))["jaImportada"] is False  # a nota 2 não ficou gravada pela metade


def test_pasta_das_sementes_configuravel_e_erro_sem_caminho(motores_falsos, tmp_path) -> None:
    app.dependency_overrides[configuracao] = lambda: Configuracao(modo="real", pasta_demo=tmp_path / "nada")
    r = cliente.post("/demo/restaurar")
    assert r.status_code == 503 and "CONTAAI_PASTA_DEMO" in r.json()["detail"]
    assert str(tmp_path) not in r.text and "nada" not in r.text


def test_manifesto_nao_sai_da_pasta_de_dados(tmp_path) -> None:
    import asyncio

    from app.persistencia.sementes import SementesInvalidas, _ler_sementes

    (tmp_path / "sementes.json").write_text(
        '{"_aviso": "x", "precosVigentesDesde": "2027-03-01T00:00:00-03:00", "empresas": ["../fora.json"],'
        ' "notasIniciais": []}',
        encoding="utf-8",
    )
    with pytest.raises(SementesInvalidas, match="fora da pasta"):
        asyncio.run(asyncio.to_thread(_ler_sementes, tmp_path))


def test_datas_de_fusos_diferentes_ficam_na_ordem_do_instante(demo) -> None:
    """A6: a nota de Manaus (-04:00) às 08:30 é posterior à de Porto Alegre (-03:00) às 09:00 do mesmo dia."""
    importar(nota(NOTA_2))  # 16/03 09:00 -03:00 = 12:00 UTC
    manaus = _trocar(_trocar(nota(NOTA_2), "<nNF>1002</nNF>", "<nNF>1600</nNF>"), "09:00:00-03:00", "08:30:00-04:00")
    importar(manaus)  # 16/03 08:30 -04:00 = 12:30 UTC: mais recente, apesar do horário local menor
    cerveja = next(i for i in CatalogoResposta.model_validate(_estado_serra_azul()).itens if i.id == "cerveja-lata")
    assert [h.notaNumero for h in cerveja.historicoCusto][:2] == ["1600", "1002"]
    # Data do documento: volta com o fuso da nota. Instante do sistema: em UTC.
    assert cerveja.custoAtual.data.isoformat() == "2027-03-16T08:30:00-04:00"
    [alerta] = AlertasResposta.model_validate(cliente.get(f"/alertas?cnpj={SERRA_AZUL}").json()).alertas
    assert alerta.criadoEm.utcoffset().total_seconds() == 0
    assert alerta.origem.dataEmissao.isoformat() == "2027-03-16T09:00:00-03:00"
