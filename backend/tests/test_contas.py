"""Contas (C1, ADR 0015): senha, segundo fator (TOTP), entrada em duas etapas, sessão, tentativas, CSRF,
isolamento entre organizações e exclusão.

O relógio das rotas é trocado por um relógio de teste (fixture `relogio`): o TOTP, a validade da sessão e a espera
das tentativas dependem da hora, e um código só vale uma vez.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.api import dependencias, middlewares
from app.api.rotas import contas as rotas_contas
from app.config import Configuracao, configuracao
from app.contas import senha, totp
from app.contas.servico import (
    ESPERA_MAXIMA_S,
    FALHAS_PARA_BLOQUEAR,
    MENSAGEM_ENTRADA,
    AguardeParaTentar,
    Contas,
    EntradaRecusada,
    _espera,
    normalizar_codigo_recuperacao,
)
from app.contas.termos import MENSAGEM_VERSAO_ANTIGA, VERSAO_TERMOS
from app.contrato import AtivacaoResposta, CadastroResposta, ContaResposta, SegundaEtapaResposta
from app.main import app
from app.seguranca import LimitadorPorIp
from tests.test_nfe import NOTA_2, SERRA_AZUL, nota

SENHA = "cavalo bateria grampo"
ORIGEM = {"Origin": "http://localhost:3000"}
INICIO = datetime(2026, 11, 26, 12, 0, 0, tzinfo=UTC)


class Relogio:
    def __init__(self) -> None:
        self.agora = INICIO

    def __call__(self) -> datetime:
        return self.agora

    def andar(self, **kw: float) -> None:
        self.agora += timedelta(**kw)


@pytest.fixture
def relogio(monkeypatch: pytest.MonkeyPatch) -> Relogio:
    r = Relogio()
    monkeypatch.setattr(rotas_contas, "agora_utc", r)
    monkeypatch.setattr(dependencias, "agora_utc", r)
    return r


@pytest.fixture
def real(motores_falsos, relogio):
    """Modo real (motores falsos) com a demonstração restaurada e o relógio de teste."""
    assert TestClient(app).post("/demo/restaurar").status_code == 200
    return relogio


def navegador() -> TestClient:
    """HTTPS: o cliente só devolve um cookie Secure numa URL https (como o navegador)."""
    return TestClient(app, base_url="https://testserver", headers=ORIGEM)


def codigo(segredo: str, quando: datetime, passos: int = 0) -> str:
    return totp.hotp(totp._chave(segredo), totp.passo(quando.timestamp()) + passos)


def cadastrar(c: TestClient, email: str = "ana@exemplo.com.br", **kw: str) -> CadastroResposta:
    corpo = {"email": email, "senha": SENHA, "organizacao": "Escritório da Ana", "termosAceitos": VERSAO_TERMOS} | kw
    r = c.post("/contas", json=corpo)
    assert r.status_code == 201, r.text
    return CadastroResposta.model_validate(r.json())


def conta_ativa(c: TestClient, relogio: Relogio, email: str = "ana@exemplo.com.br") -> tuple[str, list[str]]:
    """Cadastra e ativa. Devolve o segredo do TOTP e os códigos de recuperação."""
    feito = cadastrar(c, email)
    r = c.post("/contas/ativar", json={"codigo": codigo(feito.segredo, relogio.agora)})
    assert r.status_code == 200, r.text
    return feito.segredo, AtivacaoResposta.model_validate(r.json()).codigosRecuperacao


def entrar(c: TestClient, email: str = "ana@exemplo.com.br", senha_: str = SENHA, status: int = 200):
    r = c.post("/sessoes", json={"email": email, "senha": senha_})
    assert r.status_code == status, r.text
    return r


def set_cookies(r) -> list[str]:
    return r.headers.get_list("set-cookie")


# -- senha --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("tentativa", "motivo"),
    [
        ("curta12", "pelo menos 8"),
        ("x" * 129, "no máximo 128"),
        ("password", "muito comum"),
        ("12345678", "muito comum"),
        ("PassWord", "muito comum"),  # a comparação ignora maiúsculas
        ("contaai123", "muito comum"),
        ("ana@exemplo.com.br", "muito comum"),  # o próprio e-mail
        ("aaaaaaaaaa", "muito comum"),
    ],
)
def test_senha_recusada(tentativa: str, motivo: str) -> None:
    with pytest.raises(senha.SenhaRecusada, match=motivo):
        senha.conferir_nova(tentativa, "ana@exemplo.com.br")


def test_senha_aceita_frase_longa_e_unicode_normalizado() -> None:
    assert senha.conferir_nova(SENHA, "ana@exemplo.com.br") == SENHA
    # NFKC: o "ﬁ" (ligadura) e "fi" dão o mesmo hash.
    h = senha.gerar_hash(senha.conferir_nova("ﬁgo maduro no pé", "x@y.com"))
    assert senha.confere(h, "figo maduro no pé")
    assert not senha.confere(h, "figo maduro no pe")


def test_hash_usa_argon2id_com_os_parametros_do_owasp() -> None:
    h = senha.gerar_hash(SENHA)
    assert h.startswith("$argon2id$v=19$m=19456,t=2,p=1$")
    assert not senha.precisa_refazer(h)


def test_lista_de_senhas_comuns_so_tem_8_ou_mais_em_minusculas() -> None:
    lista = senha.senhas_comuns()
    assert len(lista) > 40_000
    assert all(len(s) >= 8 and s == s.casefold() for s in lista)


# -- TOTP ---------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("instante", "esperado"),
    [
        (59, "94287082"),
        (1111111109, "07081804"),
        (1111111111, "14050471"),
        (1234567890, "89005924"),
        (2000000000, "69279037"),
        (20000000000, "65353130"),
    ],
)
def test_totp_vetores_da_rfc_6238(instante: int, esperado: str) -> None:
    """RFC 6238, Apêndice B (SHA-1, chave "12345678901234567890", 8 dígitos)."""
    assert totp.hotp(b"12345678901234567890", totp.passo(instante), 8) == esperado


def test_totp_um_passo_de_tolerancia_e_uso_unico() -> None:
    segredo = totp.novo_segredo()
    assert len(totp._chave(segredo)) == 20  # 160 bits
    t = INICIO.timestamp()
    atual = totp.passo(t)
    assert totp.conferir(segredo, codigo(segredo, INICIO), t, 0) == atual
    assert totp.conferir(segredo, codigo(segredo, INICIO, -1), t, 0) == atual - 1
    assert totp.conferir(segredo, codigo(segredo, INICIO, 1), t, 0) == atual + 1
    assert totp.conferir(segredo, codigo(segredo, INICIO, 2), t, 0) is None  # fora da tolerância
    assert totp.conferir(segredo, codigo(segredo, INICIO), t, atual) is None  # já usado
    assert totp.conferir(segredo, "12a456", t, 0) is None


def test_endereco_otpauth() -> None:
    e = totp.endereco("JBSWY3DPEHPK3PXP", "ana@exemplo.com.br")
    assert e.startswith("otpauth://totp/ContaAI%3Aana@exemplo.com.br?secret=JBSWY3DPEHPK3PXP&issuer=ContaAI")
    assert "digits=6" in e and "period=30" in e and "algorithm=SHA1" in e


# -- cadastro e ativação --------------------------------------------------------------------------------------


def test_cadastro_ativacao_e_cookies(real) -> None:
    c = navegador()
    r = c.post(
        "/contas",
        json={
            "email": "Ana@Exemplo.com.BR",
            "senha": SENHA,
            "organizacao": " Escritório ",
            "termosAceitos": VERSAO_TERMOS,
        },
    )
    assert r.status_code == 201, r.text
    feito = CadastroResposta.model_validate(r.json())
    assert feito.otpauth.startswith("otpauth://totp/ContaAI%3Aana@exemplo.com.br?")
    [passe] = set_cookies(r)
    assert passe.startswith("__Host-contaai_passe=")
    for atributo in ("HttpOnly", "Secure", "SameSite=strict", "Path=/", "Max-Age=300"):
        assert atributo in passe
    assert "Domain" not in passe

    # Antes de ativar, a conta não entra e GET /conta não existe.
    entrar(c, "ana@exemplo.com.br", status=401)
    assert c.get("/conta").status_code == 401

    assert c.post("/contas/ativar", json={"codigo": codigo(feito.segredo, real.agora, 3)}).status_code == 401
    r = c.post("/contas/ativar", json={"codigo": codigo(feito.segredo, real.agora)})
    assert r.status_code == 200, r.text
    ativ = AtivacaoResposta.model_validate(r.json())
    assert len(ativ.codigosRecuperacao) == 10 and len(set(ativ.codigosRecuperacao)) == 10
    assert ativ.conta.email == "ana@exemplo.com.br"
    assert ativ.conta.organizacao.nome == "Escritório" and ativ.conta.organizacao.papel == "dono"
    assert ativ.conta.empresas == [] and ativ.conta.codigosRecuperacaoRestantes == 10
    sessao = next(x for x in set_cookies(r) if x.startswith("__Host-contaai_sessao="))
    for atributo in ("HttpOnly", "Secure", "SameSite=strict", "Path=/", "Max-Age=28800"):
        assert atributo in sessao
    assert any(x.startswith("__Host-contaai_passe=;") and "Max-Age=0" in x for x in set_cookies(r))
    assert ContaResposta.model_validate(c.get("/conta").json()).email == "ana@exemplo.com.br"
    # O passe da ativação não serve de novo.
    assert c.post("/contas/ativar", json={"codigo": codigo(feito.segredo, real.agora, 1)}).status_code == 401


def test_nenhum_token_vai_no_corpo_e_o_banco_so_guarda_hashes(real) -> None:
    c = navegador()
    segredo, codigos = conta_ativa(c, real)
    token = c.cookies.get("__Host-contaai_sessao")
    assert token and token not in c.get("/conta").text
    caminho = configuracao().contas_caminho
    with sqlite3.connect(caminho) as b:
        conteudo = "\n".join(
            str(linha)
            for t in ("sessoes", "codigos_recuperacao", "usuarios")
            for linha in b.execute(f"SELECT * FROM {t}")  # noqa: S608 (nomes fixos do teste)
        )
    assert token not in conteudo
    assert all(x not in conteudo for x in codigos)
    assert SENHA not in conteudo and "$argon2id$" in conteudo


def test_email_repetido_e_cadastro_pendente_que_vence(real) -> None:
    c = navegador()
    cadastrar(c)
    r = navegador().post(
        "/contas",
        json={"email": "ANA@exemplo.com.br", "senha": SENHA, "organizacao": "Outra", "termosAceitos": VERSAO_TERMOS},
    )
    assert r.status_code == 409 and "já tem uma conta" in r.json()["detail"]
    real.andar(minutes=31)  # o cadastro pendente vence e o e-mail fica livre
    cadastrar(navegador())


def test_senha_recusada_no_cadastro_responde_422_com_a_frase(real) -> None:
    r = navegador().post(
        "/contas",
        json={"email": "b@exemplo.com", "senha": "password", "organizacao": "B", "termosAceitos": VERSAO_TERMOS},
    )
    assert r.status_code == 422 and "muito comum" in r.json()["detail"]


def test_cadastro_exige_o_aceite_da_versao_atual_dos_termos(real) -> None:
    corpo = {"email": "b@exemplo.com", "senha": SENHA, "organizacao": "B"}
    r = navegador().post("/contas", json=corpo)
    assert r.status_code == 422
    assert (
        r.json()["campos"][0]["campo"].endswith("termosAceitos")
        and r.json()["campos"][0]["detalhe"] == "Campo obrigatório."
    )
    # Uma aba aberta antes de uma mudança dos termos manda a versão antiga: a frase diz o que fazer.
    for antiga in ("2026-01-01", "", True):
        r = navegador().post("/contas", json=corpo | {"termosAceitos": antiga})
        assert r.status_code == 422, antiga
    r = navegador().post("/contas", json=corpo | {"termosAceitos": "2026-01-01"})
    assert r.json()["campos"][0]["detalhe"] == MENSAGEM_VERSAO_ANTIGA
    # Nada foi criado: o e-mail segue livre.
    cadastrar(navegador(), "b@exemplo.com")


def test_o_aceite_fica_gravado_com_a_versao_e_a_data(real) -> None:
    c = navegador()
    feito = cadastrar(c)
    r = c.post("/contas/ativar", json={"codigo": codigo(feito.segredo, real.agora)})
    termos = AtivacaoResposta.model_validate(r.json()).conta.termos
    assert termos is not None and termos.versao == VERSAO_TERMOS and termos.aceitosEm == real.agora
    with sqlite3.connect(configuracao().contas_caminho) as b:
        linha = b.execute("SELECT termos_versao, termos_aceitos_em FROM usuarios").fetchone()
    assert linha[0] == VERSAO_TERMOS and datetime.fromisoformat(linha[1]) == real.agora
    # O contrato leva a versão ao tipo gerado da tela (enum do OpenAPI).
    esquema = app.openapi()["components"]["schemas"]["CadastroRequisicao"]
    assert esquema["properties"]["termosAceitos"]["enum"] == [VERSAO_TERMOS]
    assert "termosAceitos" in esquema["required"]


def test_conta_de_antes_da_migracao_dos_termos_fica_sem_aceite(tmp_path) -> None:
    servico = Contas(tmp_path / "contas.db")
    feito = servico.cadastrar("ana@exemplo.com.br", SENHA, "Ana", VERSAO_TERMOS, INICIO)
    nova, _ = servico.ativar(feito.passe, codigo(feito.segredo, INICIO), INICIO)
    with sqlite3.connect(tmp_path / "contas.db") as b:
        b.execute("UPDATE usuarios SET termos_versao = NULL, termos_aceitos_em = NULL")
    sessao = servico.sessao(nova.token, INICIO)
    assert sessao is not None and servico.conta(sessao).termos is None


def test_ativacao_vence_em_5_minutos(real) -> None:
    c = navegador()
    feito = cadastrar(c)
    real.andar(minutes=5, seconds=1)
    r = c.post("/contas/ativar", json={"codigo": codigo(feito.segredo, real.agora)})
    assert r.status_code == 401 and "tempo para digitar o código acabou" in r.json()["detail"]


# -- entrada ------------------------------------------------------------------------------------------------


def test_entrada_em_duas_etapas_e_codigo_de_uso_unico(real) -> None:
    c = navegador()
    segredo, _ = conta_ativa(c, real)
    c.cookies.clear()
    r = entrar(c)
    assert r.json()["etapa"] == "codigo" and "token" not in r.text
    # O código da ativação (mesmo passo) não vale de novo; o do passo seguinte, sim.
    assert c.post("/sessoes/codigo", json={"codigo": codigo(segredo, real.agora)}).status_code == 401
    r = c.post("/sessoes/codigo", json={"codigo": codigo(segredo, real.agora, 1)})
    assert r.status_code == 200, r.text
    assert SegundaEtapaResposta.model_validate(r.json()).novoCodigoRecuperacao is None
    primeira = c.cookies.get("__Host-contaai_sessao")
    # Nova entrada: token novo (contra sessão fixada), e o antigo continua valendo até sair.
    real.andar(seconds=60)
    entrar(c)
    assert c.post("/sessoes/codigo", json={"codigo": codigo(segredo, real.agora)}).status_code == 200
    assert c.cookies.get("__Host-contaai_sessao") != primeira


def test_segunda_etapa_sem_passe_ou_com_os_dois_codigos(real) -> None:
    c = navegador()
    assert c.post("/sessoes/codigo", json={"codigo": "123456"}).status_code == 401
    r = c.post("/sessoes/codigo", json={"codigo": "123456", "codigoRecuperacao": "ABCD-EFGH-IJKLM"})
    assert r.status_code == 422


def test_senha_errada_e_email_sem_conta_tem_a_mesma_resposta(real) -> None:
    c = navegador()
    conta_ativa(c, real)
    errada = entrar(navegador(), senha_="outra senha qualquer", status=401).json()
    sem_conta = entrar(navegador(), "ninguem@exemplo.com.br", status=401).json()
    assert errada == sem_conta and errada["detail"] == MENSAGEM_ENTRADA


def test_codigo_de_recuperacao_vale_uma_vez_e_gera_outro(real) -> None:
    c = navegador()
    _, codigos = conta_ativa(c, real)
    c.cookies.clear()
    entrar(c)
    r = c.post("/sessoes/codigo", json={"codigoRecuperacao": codigos[0].replace("-", "").lower()})
    assert r.status_code == 200, r.text
    corpo = SegundaEtapaResposta.model_validate(r.json())
    assert corpo.novoCodigoRecuperacao and corpo.novoCodigoRecuperacao not in codigos
    assert corpo.aviso and "deixou de valer" in corpo.aviso
    assert corpo.conta.codigosRecuperacaoRestantes == 10
    assert [e.tipo for e in corpo.conta.eventos] == ["codigo-recuperacao-usado"]
    c.cookies.clear()
    entrar(c)
    assert c.post("/sessoes/codigo", json={"codigoRecuperacao": codigos[0]}).status_code == 401
    assert c.post("/sessoes/codigo", json={"codigoRecuperacao": corpo.novoCodigoRecuperacao}).status_code == 200


def test_codigo_de_recuperacao_tem_65_bits_em_base32() -> None:
    from app.contas.servico import _novo_codigo_recuperacao

    x = _novo_codigo_recuperacao()
    assert len(x) == 15 and x[4] == "-" and x[9] == "-"
    assert set(x.replace("-", "")) <= set("ABCDEFGHIJKLMNOPQRSTUVWXYZ234567")
    assert normalizar_codigo_recuperacao(x.lower().replace("-", " ")) == x


# -- tentativas ---------------------------------------------------------------------------------------------


def test_espera_crescente_a_partir_da_quinta_falha() -> None:
    assert [_espera(n) for n in (1, 4, 5, 6, 7, 11, 12, 99)] == [0, 0, 30, 60, 120, 1920, 3600, 3600]


def test_espera_e_igual_para_conta_e_para_email_sem_conta(real) -> None:
    conta_ativa(navegador(), real)
    for email in ("ana@exemplo.com.br", "ninguem@exemplo.com.br"):
        for _ in range(4):
            entrar(navegador(), email, "senha errada demais", status=401)
        entrar(navegador(), email, "senha errada demais", status=401)  # a 5ª falha começa a espera
        r = entrar(navegador(), email, SENHA, status=429)  # nem a senha certa entra durante a espera
        assert r.headers["Retry-After"] == "31"
        real.andar(seconds=31)
        entrar(navegador(), email, "senha errada demais", status=401)
        assert entrar(navegador(), email, SENHA, status=429).headers["Retry-After"] == "61"
        real.agora = INICIO  # o próximo e-mail começa na mesma hora
    real.agora = INICIO + timedelta(seconds=31 + 61)  # a espera da 6ª falha acabou
    entrar(navegador(), "ana@exemplo.com.br")


def test_codigo_errado_soma_falhas_e_sucesso_zera(real) -> None:
    c = navegador()
    segredo, _ = conta_ativa(c, real)
    for _ in range(4):
        entrar(c)
        assert c.post("/sessoes/codigo", json={"codigo": "000000"}).status_code == 401
    entrar(c)
    real.andar(seconds=30)
    assert c.post("/sessoes/codigo", json={"codigo": codigo(segredo, real.agora)}).status_code == 200
    # Zerou: quatro falhas de novo não dão espera.
    for _ in range(4):
        entrar(navegador(), senha_="senha errada demais", status=401)
    entrar(navegador())


def test_cem_falhas_bloqueiam_e_so_o_administrador_desbloqueia(tmp_path) -> None:
    servico = Contas(tmp_path / "contas.db")
    agora = INICIO
    feito = servico.cadastrar("ana@exemplo.com.br", SENHA, "Ana", VERSAO_TERMOS, agora)
    servico.ativar(feito.passe, codigo(feito.segredo, agora), agora)
    for _ in range(FALHAS_PARA_BLOQUEAR):
        with pytest.raises(EntradaRecusada):
            servico.entrar("ana@exemplo.com.br", "senha errada demais", agora)
        agora += timedelta(seconds=ESPERA_MAXIMA_S + 1)
    with pytest.raises(AguardeParaTentar, match="bloqueada"):
        servico.entrar("ana@exemplo.com.br", SENHA, agora + timedelta(days=30))
    assert servico.desbloquear("ANA@exemplo.com.br")
    assert servico.entrar("ana@exemplo.com.br", SENHA, agora)
    assert not servico.desbloquear("ninguem@exemplo.com.br")


def test_limite_por_ip_nas_rotas_de_entrada(real, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(middlewares, "LIMITE_ENTRADA", LimitadorPorIp(3))
    for _ in range(3):
        entrar(navegador(), "x@exemplo.com", "senha errada demais", status=401)
    assert entrar(navegador(), "x@exemplo.com", status=429).headers["Retry-After"]
    assert navegador().post("/contas", json={}).status_code == 429


# -- sessão -------------------------------------------------------------------------------------------------


def test_sessao_vence_com_30_minutos_sem_uso_e_8_horas_no_total(real) -> None:
    c = navegador()
    conta_ativa(c, real)
    real.andar(minutes=29)
    assert c.get("/conta").status_code == 200  # o uso renova os 30 min
    real.andar(minutes=29)
    assert c.get("/conta").status_code == 200
    real.andar(minutes=30)
    r = c.get("/conta")
    assert r.status_code == 401
    assert any(x.startswith("__Host-contaai_sessao=;") and "Max-Age=0" in x for x in set_cookies(r))

    c2 = navegador()
    conta_ativa(c2, real, "bia@exemplo.com.br")
    for _ in range(17):  # 17 × 29 min = 8 h 13 min, sempre com uso
        real.andar(minutes=29)
        if c2.get("/conta").status_code != 200:
            break
    assert real.agora - INICIO >= timedelta(hours=8)
    assert c2.get("/conta").status_code == 401


def test_sair_apaga_a_sessao_no_servidor(real) -> None:
    c = navegador()
    conta_ativa(c, real)
    token = c.cookies.get("__Host-contaai_sessao")
    r = c.delete("/sessoes/atual")
    assert r.status_code == 204
    outro = navegador()
    outro.cookies.set("__Host-contaai_sessao", token)
    r = outro.get("/conta")
    assert r.status_code == 401 and "Sessão encerrada" in r.json()["detail"]  # o cookie chegou e foi recusado


def test_sair_de_todos_os_aparelhos(real) -> None:
    a, b = navegador(), navegador()
    segredo, _ = conta_ativa(a, real)
    entrar(b)
    assert b.post("/sessoes/codigo", json={"codigo": codigo(segredo, real.agora, 1)}).status_code == 200
    assert a.delete("/sessoes").status_code == 204
    assert a.get("/conta").status_code == 401
    assert "Sessão encerrada" in b.get("/conta").json()["detail"]


def test_cookie_vencido_numa_rota_de_estado_responde_401_e_apaga_o_cookie(real) -> None:
    c = navegador()
    c.cookies.set("__Host-contaai_sessao", "inventado")
    r = c.get("/catalogo", params={"cnpj": SERRA_AZUL})
    assert r.status_code == 401
    assert any(x.startswith("__Host-contaai_sessao=;") for x in set_cookies(r))


# -- CSRF ---------------------------------------------------------------------------------------------------


def test_csrf_outro_site_origem_ruim_e_cookie_sem_origin(real) -> None:
    c = navegador()
    conta_ativa(c, real)
    r = c.delete("/sessoes/atual", headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403
    assert c.delete("/sessoes/atual", headers={"Origin": "https://malvado.example"}).status_code == 403
    sem_origin = TestClient(app, base_url="https://testserver")
    sem_origin.cookies = c.cookies
    assert sem_origin.post("/conta/excluir", json={"senha": SENHA}).status_code == 403
    assert c.get("/conta").status_code == 200  # nada disso encerrou a sessão
    # Sem cookie e sem Origin (curl, scripts) segue valendo, como antes.
    assert TestClient(app).post("/sessoes", json={"email": "x@y.com", "senha": "abc"}).status_code == 401


# -- isolamento entre organizações (S6) ---------------------------------------------------------------------


def test_quem_tem_conta_nao_ve_nem_mexe_na_demonstracao(real) -> None:
    anonimo = TestClient(app)
    alerta = anonimo.post("/nfe/importar", files={"arquivo": ("n.xml", nota(NOTA_2), "text/xml")}).json()["alertas"][0][
        "id"
    ]
    c = navegador()
    conta_ativa(c, real)
    assert c.get("/catalogo", params={"cnpj": SERRA_AZUL}).status_code == 404
    assert c.get("/notas", params={"cnpj": SERRA_AZUL}).status_code == 404
    assert c.get("/alertas", params={"cnpj": SERRA_AZUL}).status_code == 404
    assert c.get("/alertas").json() == {"alertas": []}
    assert c.get("/contador/painel").json()["empresas"] == []
    assert c.post(f"/alertas/{alerta}/aplicar").status_code == 404
    preco = {"cnpj": SERRA_AZUL, "valorUnitario": "10.00"}
    assert c.post("/catalogo/arroz-5kg/preco", json=preco).status_code == 404
    assert c.get("/explicar/arroz-5kg").status_code == 404
    r = c.post("/nfe/importar", files={"arquivo": ("n.xml", nota(NOTA_2), "text/xml")})
    assert r.status_code == 422 and "não é uma empresa cadastrada" in r.json()["detail"]
    r = c.post("/demo/restaurar")
    assert r.status_code == 403
    # O 404 de um CNPJ alheio é igual ao de um CNPJ que não existe.
    assert (
        c.get("/catalogo", params={"cnpj": "00000000000000"}).json()
        == c.get("/catalogo", params={"cnpj": SERRA_AZUL}).json()
    )
    # A demonstração segue igual para quem não entrou.
    assert anonimo.get("/catalogo", params={"cnpj": SERRA_AZUL}).status_code == 200
    assert len(anonimo.get("/alertas").json()["alertas"]) >= 1


def test_com_conta_o_espaco_de_avaliacao_continua_valendo(real) -> None:
    c = navegador()
    conta_ativa(c, real)
    espaco = c.post("/espacos").json()["id"]
    r = c.get("/catalogo", params={"cnpj": SERRA_AZUL}, headers={"X-ContaAI-Espaco": espaco})
    assert r.status_code == 200


def test_organizacoes_tem_bancos_de_estado_separados(real) -> None:
    a, b = navegador(), navegador()
    conta_ativa(a, real, "ana@exemplo.com.br")
    conta_ativa(b, real, "bia@exemplo.com.br")
    org_a = a.get("/conta").json()["organizacao"]["id"]
    org_b = b.get("/conta").json()["organizacao"]["id"]
    assert org_a != org_b
    a.get("/alertas")
    b.get("/alertas")
    pasta = configuracao().pasta_organizacoes
    assert sorted(p.name for p in pasta.glob("*.db")) == sorted([f"{org_a}.db", f"{org_b}.db"])


def test_id_de_organizacao_fora_do_padrao_nao_vira_arquivo() -> None:
    cfg = Configuracao(modo="real")
    with pytest.raises(ValueError, match="fora do padrão"):
        dependencias.banco_da_organizacao(cfg, "../../contaai")


# -- exclusão -----------------------------------------------------------------------------------------------


def test_excluir_a_conta_apaga_a_organizacao_e_o_banco(real) -> None:
    c = navegador()
    conta_ativa(c, real)
    org = c.get("/conta").json()["organizacao"]["id"]
    c.get("/alertas")  # cria o banco de estado da organização
    arquivo = configuracao().pasta_organizacoes / f"{org}.db"
    assert arquivo.exists()
    assert c.post("/conta/excluir", json={"senha": "senha errada demais"}).status_code == 401
    r = c.post("/conta/excluir", json={"senha": SENHA})
    assert r.status_code == 204, r.text
    assert not arquivo.exists()
    assert c.get("/conta").status_code == 401
    entrar(navegador(), status=401)
    with sqlite3.connect(configuracao().contas_caminho) as b:
        for tabela in ("usuarios", "organizacoes", "membros", "sessoes", "codigos_recuperacao", "segundo_fator"):
            assert b.execute(f"SELECT count(*) FROM {tabela}").fetchone()[0] == 0, tabela  # noqa: S608
    cadastrar(navegador())  # o e-mail fica livre


def test_unica_dona_com_outros_membros_precisa_passar_a_posse(real) -> None:
    a, b = navegador(), navegador()
    conta_ativa(a, real, "ana@exemplo.com.br")
    conta_ativa(b, real, "bia@exemplo.com.br")
    org_a = a.get("/conta").json()["organizacao"]["id"]
    with sqlite3.connect(configuracao().contas_caminho) as banco:
        bia = banco.execute("SELECT id FROM usuarios WHERE email = 'bia@exemplo.com.br'").fetchone()[0]
        banco.execute(
            "INSERT INTO membros (organizacao_id, usuario_id, papel, desde) VALUES (?, ?, 'membro', ?)",
            (org_a, bia, INICIO.isoformat()),
        )
    r = a.post("/conta/excluir", json={"senha": SENHA})
    assert r.status_code == 409 and "Passe a posse" in r.json()["detail"]
    # A integrante que não é a única dona sai sem levar a organização junto.
    assert b.post("/conta/excluir", json={"senha": SENHA}).status_code == 204
    assert a.get("/conta").json()["organizacao"]["id"] == org_a


# -- modo mock ----------------------------------------------------------------------------------------------


def test_contas_so_no_modo_real() -> None:
    app.dependency_overrides[configuracao] = lambda: Configuracao(modo="mock")
    try:
        c = navegador()
        assert (
            c.post(
                "/contas", json={"email": "a@b.com", "senha": SENHA, "organizacao": "A", "termosAceitos": VERSAO_TERMOS}
            ).status_code
            == 501
        )
        assert c.get("/conta").status_code == 501
    finally:
        app.dependency_overrides.clear()


def test_comando_do_administrador(capsys: pytest.CaptureFixture[str]) -> None:
    from app.contas.__main__ import main

    servico = Contas(configuracao().contas_caminho)
    feito = servico.cadastrar("ana@exemplo.com.br", SENHA, "Ana", VERSAO_TERMOS, INICIO)
    servico.ativar(feito.passe, codigo(feito.segredo, INICIO), INICIO)
    assert main(["desbloquear", "ana@exemplo.com.br"]) == 0
    assert main(["desbloquear", "ninguem@exemplo.com.br"]) == 1
    assert main([]) == 2
    saida = capsys.readouterr().out
    assert "Conta desbloqueada." in saida and "Nenhuma conta" in saida and "desbloquear <e-mail>" in saida
