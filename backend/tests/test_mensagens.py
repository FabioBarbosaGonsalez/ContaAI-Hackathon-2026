"""Mensagens de validação em português (app/api/mensagens.py, ADR 0009).

A sonda manda entradas inválidas, geradas do próprio OpenAPI, a toda rota do contrato e confere três coisas:
todo tipo de erro que aparece tem tradução, nenhuma mensagem sai em inglês e nenhuma repete o valor enviado.
Rota, campo ou restrição nova no contrato entra na sonda sem mexer neste arquivo.
"""

from __future__ import annotations

import copy
import json
import logging
import re
from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from typing import Annotated, Any, Literal

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.api import mensagens, problemas
from app.api.mensagens import GENERICA, PADROES, TRADUCOES, traduzir
from app.api.problemas import campos_invalidos
from app.contrato import Regime
from app.main import app

cliente = TestClient(app, raise_server_exceptions=False)
SEGREDO = "zz-valor-enviado-zz"
# Palavras das mensagens do Pydantic e do FastAPI em inglês ("Input should be...", "Field required").
INGLES = re.compile(r"\b(should|Input|Field required|Extra inputs|Value error|valid|characters|pattern|decode)\b")


# ---------------------------------------------------------------------------
# Sonda sobre o contrato


def _esquemas() -> dict[str, Any]:
    return app.openapi()["components"]["schemas"]


def _resolver(s: dict[str, Any], esquemas: dict[str, Any]) -> dict[str, Any]:
    while "$ref" in s:
        s = esquemas[s["$ref"].rsplit("/", 1)[-1]]
    return s


def _gerar(s: dict[str, Any], esquemas: dict[str, Any], prof: int = 0) -> Any:
    """Um valor com a forma do esquema (não precisa ser válido: o Pydantic acusa todo campo de uma vez)."""
    s = _resolver(s, esquemas)
    if prof > 8:
        return None
    if "const" in s:
        return s["const"]
    if "enum" in s:
        return s["enum"][0]
    for chave in ("anyOf", "oneOf"):
        if chave in s:
            opcoes = [x for x in s[chave] if _resolver(x, esquemas).get("type") != "null"]
            return _gerar(opcoes[0], esquemas, prof + 1) if opcoes else None
    tipo = s.get("type")
    if tipo == "object":
        obrig = s.get("required", [])
        return {k: _gerar(v, esquemas, prof + 1) for k, v in s.get("properties", {}).items() if k in obrig}
    if tipo == "array":
        return [_gerar(s.get("items", {}), esquemas, prof + 1)] * max(1, s.get("minItems", 1))
    if tipo == "string":
        return {"date": "2027-03-16", "date-time": "2027-03-16T10:00:00-03:00"}.get(
            s.get("format", ""), "1" * max(1, s.get("minLength", 1))
        )
    return {"integer": 1, "number": 1, "boolean": True}.get(tipo or "")


def _caminhos(s: dict[str, Any], esquemas: dict[str, Any], pre: tuple = (), prof: int = 0) -> Iterator[tuple]:
    s = _resolver(s, esquemas)
    if prof > 8:
        return
    yield pre, s
    for chave in ("anyOf", "oneOf", "allOf"):
        for x in s.get(chave, []):
            if _resolver(x, esquemas).get("type") != "null":
                yield from _caminhos(x, esquemas, pre, prof + 1)
    for k, v in s.get("properties", {}).items():
        yield from _caminhos(v, esquemas, (*pre, k), prof + 1)
    if "items" in s:
        yield from _caminhos(s["items"], esquemas, (*pre, 0), prof + 1)


def _trocar(corpo: Any, caminho: tuple, valor: Any) -> Any:
    novo = copy.deepcopy(corpo)
    atual = novo
    for k in caminho[:-1]:
        if isinstance(atual, dict):
            atual = atual.setdefault(k, {})
        elif isinstance(atual, list) and atual and isinstance(k, int):
            atual = atual[k]
        else:
            return None
    if isinstance(atual, dict):
        atual[caminho[-1]] = valor
    elif isinstance(atual, list) and atual and isinstance(caminho[-1], int):
        atual[caminho[-1]] = valor
    else:
        return None
    return novo


def _tipos(s: dict[str, Any], esquemas: dict[str, Any]) -> set[str]:
    opcoes = [_resolver(x, esquemas) for k in ("anyOf", "oneOf") for x in s.get(k, [])] or [s]
    return {str(o.get("type")) for o in opcoes} | {f"format={o['format']}" for o in opcoes if "format" in o}


def _invalidos(s: dict[str, Any], esquemas: dict[str, Any]) -> list[Any]:
    """Poucos valores por campo, escolhidos pelo tipo: cada um provoca um tipo de erro diferente."""
    tipos = _tipos(s, esquemas)
    valores: list[Any] = [None, 123 if "string" in tipos else SEGREDO]
    if "string" in tipos:
        valores += [SEGREDO, "", []]
        if "maxLength" in s:
            valores.append(SEGREDO + "x" * s["maxLength"])
    if tipos & {"format=date", "format=date-time"}:
        valores += ["2027-13-45", "2027-03-16T10:00:00"]
    if "number" in tipos:
        valores += ["NaN", "1.12345678901234", -1e30, 1e30, []]
    if "integer" in tipos:
        valores += [1.5, "9" * 5000, []]
    if "boolean" in tipos:
        valores += ["talvez", []]
    if "array" in tipos:
        valores += ["x", []] + ([[None] * (s["maxItems"] + 1)] if "maxItems" in s else [])
    if "object" in tipos:
        valores.append("x")
    return valores


def _pedidos() -> Iterator[tuple[str, str, dict[str, Any]]]:
    api = app.openapi()
    esquemas = api["components"]["schemas"]
    # O mesmo campo (mesmo esquema) aparece em várias rotas e dá o mesmo erro: cada um é sondado uma vez.
    # Toda rota com corpo ainda recebe o JSON quebrado e o campo a mais.
    sondados: set[str] = set()
    for rota, operacoes in api["paths"].items():
        for metodo, op in operacoes.items():
            metodo = metodo.upper()
            url = re.sub(r"\{[^}]+\}", SEGREDO, rota)
            for prm in op.get("parameters", []):
                if prm["in"] in ("query", "header"):
                    for v in ("", SEGREDO, SEGREDO * 5, "2027-13-45", "talvez"):
                        lugar = "params" if prm["in"] == "query" else "headers"
                        yield metodo, url, {lugar: {prm["name"]: v}}
            conteudo = op.get("requestBody", {}).get("content", {})
            if "multipart/form-data" in conteudo:
                yield metodo, url, {}
                yield metodo, url, {"data": {"arquivo": SEGREDO}}
            if "application/json" not in conteudo:
                continue
            esquema = conteudo["application/json"]["schema"]
            base = _gerar(esquema, esquemas)
            json_cru = {"content-type": "application/json"}
            for cru in ("{", f'{{"a": "{SEGREDO}"', "[]", '"x"', "123", "null", ""):
                yield metodo, url, {"content": cru, "headers": json_cru}
            yield metodo, url, {"json": base | {"campoQueNaoExiste": SEGREDO}}
            for caminho, s in _caminhos(esquema, esquemas):
                chave = json.dumps(s, sort_keys=True)
                if not caminho or chave in sondados:
                    continue
                sondados.add(chave)
                for valor in _invalidos(s, esquemas):
                    corpo = _trocar(base, caminho, valor)
                    if corpo is not None:
                        yield metodo, url, {"json": corpo}
                sem = _trocar(base, caminho, None)
                if sem is not None:  # o campo removido
                    atual = sem
                    for k in caminho[:-1]:
                        atual = atual[k]
                    if isinstance(atual, dict):
                        atual.pop(caminho[-1])
                        yield metodo, url, {"json": sem}


_SONDA: list[tuple[str, dict[str, Any]]] = []
_TIPOS_DA_SONDA: set[str] = set()


@pytest.fixture
def respostas_422() -> list[tuple[str, dict[str, Any]]]:
    """Escopo de função (os limites por IP e o banco isolado do conftest valem por teste), com cache: a sonda
    roda uma vez por sessão."""
    if _SONDA:
        return _SONDA
    vistas = []
    original = problemas.traduzir

    def anotar(erro: Any) -> str:
        _TIPOS_DA_SONDA.add(str(erro.get("type")))
        return original(erro)

    problemas.traduzir = anotar  # type: ignore[assignment]
    try:
        pedidos = [(m, u, kw, cliente.request(m, u, **kw)) for m, u, kw in _pedidos()]
    finally:
        problemas.traduzir = original  # type: ignore[assignment]
    for metodo, url, _kw, r in pedidos:
        # 501: rota que muda o estado no modo mock (documentado). Nenhum 500.
        assert r.status_code < 500 or r.status_code == 501, (metodo, url, r.status_code)
        if r.status_code == 422 and r.json().get("type") == "/problemas/entrada-invalida":
            vistas.append((f"{metodo} {url}", r.json()))
    _SONDA.extend(vistas)
    return _SONDA


def test_sonda_cobre_as_rotas_com_entrada(respostas_422) -> None:
    rotas = {r for r, _ in respostas_422}
    com_entrada = [
        (m, c)
        for c, ops in app.openapi()["paths"].items()
        for m, op in ops.items()
        if op.get("parameters") or op.get("requestBody")
    ]
    assert len(rotas) >= len(com_entrada) - 3, sorted(rotas)  # algumas só têm header opcional
    assert len(respostas_422) > 300


def test_toda_mensagem_da_sonda_esta_em_portugues_e_sem_o_valor_enviado(respostas_422) -> None:
    for rota, corpo in respostas_422:
        textos = [corpo["detail"], *(c["detalhe"] for c in corpo["campos"])]
        for texto in textos:
            assert texto != GENERICA, (rota, corpo)  # todo tipo gerado pelas rotas tem tradução
            assert not INGLES.search(texto), (rota, texto)
            assert SEGREDO not in texto, (rota, texto)
        assert SEGREDO not in str(corpo), rota  # nem no ponteiro: campo vem do contrato, não do valor


def test_os_tipos_da_sonda_estao_na_tabela(respostas_422) -> None:
    assert _TIPOS_DA_SONDA, "a sonda não anotou tipos"
    assert _TIPOS_DA_SONDA <= set(TRADUCOES), _TIPOS_DA_SONDA - set(TRADUCOES)


def test_todo_padrao_do_contrato_tem_frase() -> None:
    padroes = set(re.findall(r'"pattern":\s*"((?:[^"\\]|\\.)*)"', cliente.get("/openapi.json").text))
    padroes = {p.encode().decode("unicode_escape") for p in padroes}
    assert padroes, "o contrato tem padrões"
    assert padroes <= set(PADROES), padroes - set(PADROES)


# ---------------------------------------------------------------------------
# Cada tipo, gerado pelo próprio Pydantic (o ctx vem como o FastAPI entrega)


class _Ex(BaseModel):
    model_config = ConfigDict(extra="forbid")

    texto: str = Field(default="ok", min_length=2, max_length=5, pattern=r"^[0-9]{2}$")
    inteiro: int = 0
    numero: Annotated[Decimal, Field(ge=0, le=Decimal("1000000000"), decimal_places=4)] = Decimal(0)
    positivo: Annotated[Decimal, Field(gt=0, lt=100)] = Decimal(1)
    dia: date = date(2027, 3, 16)
    sim: bool = True
    regime: Regime = Regime.SIMPLES_HIBRIDO
    anexo: Literal["I", "II", "III"] = "I"
    lista: list[int] = Field(default=[1], min_length=1, max_length=2)
    sub: _Sub | None = None
    regra: str | None = None

    @model_validator(mode="after")
    def _regra(self) -> _Ex:
        if self.regra == "x":
            raise ValueError("Informe NCM ou NBS, nunca os dois.")
        return self


class _Sub(BaseModel):
    a: int


_Ex.model_rebuild()


def _erro(**campos: Any) -> dict[str, Any]:
    with pytest.raises(ValidationError) as e:
        _Ex.model_validate(campos)
    (primeiro,) = e.value.errors()
    return dict(primeiro)


CASOS: list[tuple[dict[str, Any], str, str]] = [
    ({"texto": "1"}, "string_too_short", "Use pelo menos 2 caracteres."),
    ({"texto": "123456"}, "string_too_long", "Use no máximo 5 caracteres."),
    ({"texto": "ab"}, "string_pattern_mismatch", "Use exatamente 2 dígitos, sem pontos nem traços."),
    ({"texto": 1}, "string_type", "Informe um texto."),
    ({"inteiro": "a"}, "int_parsing", "Informe um número inteiro."),
    ({"inteiro": 1.5}, "int_from_float", "Informe um número inteiro."),
    ({"inteiro": []}, "int_type", "Informe um número inteiro."),
    ({"numero": "abc"}, "decimal_parsing", "Informe um número, com ponto como separador decimal (ex.: 27.90)."),
    ({"numero": []}, "decimal_type", "Informe um número, com ponto como separador decimal (ex.: 27.90)."),
    ({"numero": "NaN"}, "finite_number", "Informe um número finito (NaN e infinito não valem)."),
    ({"numero": "0.12345"}, "decimal_max_places", "Use no máximo 4 casas decimais."),
    ({"numero": "-1"}, "greater_than_equal", "Informe um valor maior ou igual a 0."),
    ({"numero": "2000000000"}, "less_than_equal", "Informe um valor menor ou igual a 1.000.000.000."),
    ({"positivo": "0"}, "greater_than", "Informe um valor maior que 0."),
    ({"positivo": "100"}, "less_than", "Informe um valor menor que 100."),
    ({"dia": "2027-13-45"}, "date_from_datetime_parsing", "Informe uma data no formato AAAA-MM-DD (ex.: 2027-03-16)."),
    ({"dia": "2027-03-16T10:00:00"}, "date_from_datetime_inexact", "Informe só a data (AAAA-MM-DD), sem a hora."),
    ({"dia": []}, "date_type", "Informe uma data no formato AAAA-MM-DD (ex.: 2027-03-16)."),
    ({"sim": "talvez"}, "bool_parsing", "Informe true ou false."),
    ({"regime": "lucro_real"}, "enum", "Use um destes valores: simples_tradicional ou simples_hibrido."),
    ({"anexo": "IX"}, "literal_error", "Use um destes valores: I, II ou III."),
    ({"lista": "x"}, "list_type", "Informe uma lista."),
    ({"lista": []}, "too_short", "Informe pelo menos 1 item."),
    ({"lista": [1, 2, 3]}, "too_long", "Informe no máximo 2 itens."),
    ({"sub": {}}, "missing", "Campo obrigatório."),
    ({"outro": 1}, "extra_forbidden", "Campo que o contrato não prevê. Confira o nome."),
    ({"regra": "x"}, "value_error", "Informe NCM ou NBS, nunca os dois."),
]


@pytest.mark.parametrize(("campos", "tipo", "frase"), CASOS, ids=[c[1] for c in CASOS])
def test_cada_tipo_vira_a_frase_em_portugues(campos: dict[str, Any], tipo: str, frase: str) -> None:
    erro = _erro(**campos)
    assert erro["type"] == tipo
    assert traduzir(erro) == frase


def test_a_tabela_nao_tem_tipo_sem_caso(respostas_422) -> None:
    """Todo tipo da tabela aparece na sonda (as rotas o geram) ou num caso acima."""
    assert set(TRADUCOES) == _TIPOS_DA_SONDA | {c[1] for c in CASOS}, set(TRADUCOES) ^ (
        _TIPOS_DA_SONDA | {c[1] for c in CASOS}
    )


def test_tipos_vistos_so_pelo_fastapi() -> None:
    assert traduzir({"type": "json_invalid", "ctx": {"error": "Expecting value"}}) == "O corpo não é um JSON válido."
    assert traduzir({"type": "model_attributes_type"}) == "Informe um objeto JSON."
    assert traduzir({"type": "int_parsing_size"}) == "Número inteiro grande demais."
    erro = {"type": "value_error", "ctx": {"error": ValueError("Expected UploadFile, received: <class 'str'>")}}
    assert traduzir(erro) == "Envie um arquivo."


def test_tipo_sem_traducao_vira_frase_generica_e_registra_so_o_tipo(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger="contaai"):
        assert traduzir({"type": "url_parsing", "input": SEGREDO, "msg": "Input should be a valid URL"}) == GENERICA
    assert "url_parsing" in caplog.text and SEGREDO not in caplog.text


def test_padrao_sem_frase_vira_formato_invalido() -> None:
    assert traduzir({"type": "string_pattern_mismatch", "ctx": {"pattern": r"^x$"}}) == "Formato inválido."


def test_numero_no_jeito_brasileiro() -> None:
    assert [mensagens._numero(v) for v in (0, 100, Decimal("1E+9"), Decimal("0.5"), -1500, "x")] == [
        "0",
        "100",
        "1.000.000.000",
        "0,5",
        "-1.500",
        "x",
    ]


# ---------------------------------------------------------------------------
# Pela API


def test_detail_diz_o_campo_e_a_origem_em_portugues() -> None:
    r = cliente.get("/busca/ncm", params={"q": "a"})
    assert r.status_code == 422
    assert r.json()["detail"] == "q (parâmetro): Use pelo menos 2 caracteres."
    assert r.json()["campos"] == [{"origem": "query", "campo": "#/q", "detalhe": "Use pelo menos 2 caracteres."}]


def test_varios_problemas_dizem_quantos_sobram() -> None:
    r = cliente.post("/carrinho/calcular", json={"regime": "lucro_real", "uf": "sp"})
    corpo = r.json()
    assert r.status_code == 422 and len(corpo["campos"]) > 1
    assert corpo["detail"].endswith(f" E mais {len(corpo['campos']) - 1} problema(s).")


def test_json_quebrado_aponta_o_corpo_inteiro() -> None:
    r = cliente.post("/carrinho/calcular", content="{", headers={"content-type": "application/json"})
    assert r.status_code == 422
    assert r.json()["campos"] == [{"origem": "body", "campo": "#", "detalhe": "O corpo não é um JSON válido."}]
    assert r.json()["detail"] == "O corpo não é um JSON válido."


def test_regra_do_contrato_sai_sem_o_prefixo_do_pydantic() -> None:
    campos = campos_invalidos([_erro(regra="x") | {"loc": ("body",)}])
    assert campos[0].detalhe == "Informe NCM ou NBS, nunca os dois."
