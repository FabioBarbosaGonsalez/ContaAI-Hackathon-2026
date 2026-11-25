"""Provedor "roteiro": responde sem IA, por regras, às frases do roteiro da demo (ADR 0006).

Serve para três coisas: dublê determinístico nos testes do CI (sem chave, sem custo), plano B da
demo se o crédito de IA acabar (ordem de corte 5 do plano) e frontend trabalhando desde já.

Ele se comporta como uma IA com tool use: lê a conversa, pede ferramentas e, com os resultados,
escreve o texto. Todo número do texto é copiado do JSON das ferramentas (P2). Entende pouco: uma
intenção por mensagem, reconhecida por palavras-chave; o resto recebe a mensagem de ajuda.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from app.agente.tipos import (
    PREFIXO_VERIFICACAO,
    ChamadaFerramenta,
    Mensagem,
    Pedido,
    RespostaModelo,
    ResultadoFerramenta,
)
from app.classificacao.indice import normalizar, palavras

AJUDA = (
    "Sou o copiloto de preço e margem do ContaAI. Posso buscar a NCM e a classificação de um produto para você "
    "confirmar, calcular o impacto da CBS e do IBS nos itens confirmados, achar o preço para uma margem, explicar "
    "um cálculo ou um erro do motor. Toda conta vem das calculadoras oficiais da Receita Federal."
)
SOBRE_ALIQUOTA = (
    "Não apresento alíquota de CBS ou IBS de 2027 como oficial. No ContaAI, as alíquotas de 2027 em diante são "
    "premissas que você informa (a tela tem presets rotulados com a fonte), e todo resultado com elas aparece "
    "como simulação."
)
CONFIRMAR = (
    "Confira os cartões e confirme: a classificação fiscal é decisão sua ou do seu contador, e eu só calculo "
    "depois da confirmação."
)
SEM_CONFERENCIA = "Não consegui conferir os números desta resposta. Os resultados estão nos cartões e na tabela."
NOME_MOTOR = {"regime_regular": "Regime Regular", "simples_nacional": "Simples Nacional"}

# Palavras de comando que não fazem parte do nome do produto.
_COMANDO = frozenset(
    normalizar(p)
    for p in (
        "cadastra cadastrar cadastre adiciona adicionar adicione inclui incluir inclua quero queria vender vendo "
        "venda me diga mostre qual quais classificação classificacao classifica classificar certa correta ncm "
        "produto produtos item itens meus minhas meu minha também tambem favor por busca buscar procura procurar "
        "o a os as do da dos das de um uma"
    ).split()
)
_PCT = re.compile(r"(\d+(?:[.,]\d+)?)\s*%")
_CODIGO = re.compile(r"\b(REG|VSN)-\d{3}\b", re.IGNORECASE)


def br(valor: Any) -> str:
    """Escreve um número do JSON no formato brasileiro sem mudar os dígitos ("1234.50" → "1.234,50")."""
    texto = str(valor)
    negativo = texto.startswith("-")
    inteiro, _, decimais = texto.lstrip("-").partition(".")
    grupos = []
    while len(inteiro) > 3:
        grupos.insert(0, inteiro[-3:])
        inteiro = inteiro[:-3]
    grupos.insert(0, inteiro)
    saida = ".".join(grupos) + ("," + decimais if decimais else "")
    return ("-" if negativo else "") + saida


def reais(valor: Any) -> str:
    """Dinheiro na tela, em centavos ("5.5758" → "5,58"). Só arredonda para mostrar; o JSON segue igual."""
    return br(Decimal(str(valor)).quantize(Decimal("0.01"), ROUND_HALF_UP))


def _contem(texto: str, *termos: str) -> bool:
    return any(t in texto for t in termos)


def _fragmentos(texto: str) -> list[str]:
    """Nomes de produto numa frase: "Cadastra arroz, cerveja e chocolate" → arroz, cerveja, chocolate."""
    saida = []

    def comando(p: str) -> bool:
        return normalizar(p).strip(".?!:") in _COMANDO

    for parte in re.split(r",|;|\be\b|\n", texto):
        termos = parte.split()
        # Só nas pontas: "cerveja de malte" mantém o "de"; "me diga a classificação do chocolate" vira "chocolate".
        while termos and comando(termos[0]):
            termos.pop(0)
        while termos and comando(termos[-1]):
            termos.pop()
        limpo = " ".join(termos).strip(" .?!:")
        if len(limpo) >= 2 and palavras(limpo):
            saida.append(limpo)
    return saida[:5]


class _Turno:
    """A mensagem do usuário e os resultados das ferramentas desde ela."""

    def __init__(self, mensagens: list[Mensagem]) -> None:
        inicio = max(i for i, m in enumerate(mensagens) if m.papel == "usuario")
        self.texto = mensagens[inicio].texto
        self.norm = normalizar(self.texto)
        self.resultados: list[ResultadoFerramenta] = [
            r for m in mensagens[inicio + 1 :] if m.papel == "ferramenta" for r in m.resultados
        ]
        self._n = 0

    def de(self, nome: str) -> list[ResultadoFerramenta]:
        return [r for r in self.resultados if r.nome == nome]

    def chamar(self, *pedidos: tuple[str, dict[str, Any]]) -> RespostaModelo:
        chamadas = []
        for nome, args in pedidos:
            self._n += 1
            chamadas.append(
                ChamadaFerramenta(id=f"roteiro-{len(self.resultados)}-{self._n}", nome=nome, argumentos=args)
            )
        return RespostaModelo(chamadas=tuple(chamadas))

    def item_citado(self) -> dict[str, Any] | None:
        """O item do contexto cujo nome mais casa com a mensagem (precisa de listar_itens antes)."""
        lista = self.de("listar_itens")
        if not lista or lista[-1].erro:
            return None
        consulta = palavras(self.texto)
        melhor, pontos = None, 0
        for item in lista[-1].conteudo.get("itens", []):
            termos = palavras(item["descricao"])
            p = sum(1 for c in consulta if any(t.startswith(c) or c.startswith(t) for t in termos if len(t) >= 4))
            if p > pontos:
                melhor, pontos = item, p
        return melhor


def _texto(r: RespostaModelo | str) -> RespostaModelo:
    return r if isinstance(r, RespostaModelo) else RespostaModelo(texto=r)


def _erro(r: ResultadoFerramenta) -> str:
    return str(r.conteudo.get("erro", "a consulta falhou"))


class Roteiro:
    nome = "roteiro"

    async def responder(self, pedido: Pedido) -> RespostaModelo:
        turno = _Turno(pedido.mensagens)
        if turno.texto.startswith(PREFIXO_VERIFICACAO):
            return RespostaModelo(texto=SEM_CONFERENCIA)  # o roteiro não sabe reescrever
        if not pedido.ferramentas and not turno.resultados:
            return RespostaModelo(texto=AJUDA)
        return _texto(self._decidir(turno))

    def _decidir(self, t: _Turno) -> RespostaModelo | str:
        n = t.norm
        fluxos: list[tuple[bool, Callable[[_Turno], RespostaModelo | str]]] = [
            (bool(_CODIGO.search(t.texto)), _fluxo_erro),
            (
                _contem(n, "aliquota oficial", "aliquotas oficiais", "aliquota de 2027", "aliquota em 2027"),
                lambda _: SOBRE_ALIQUOTA,
            ),
            (_contem(n, "regime", "hibrido", "tradicional", "bom preco"), _fluxo_regime),
            (_contem(n, "alerta", "mudou", "nota fiscal", "nf-e"), _fluxo_alertas),
            (_contem(n, "corrig", "erro", "inconsist"), _fluxo_corrigir),
            ("margem" in n and bool(_PCT.search(t.texto)), _fluxo_preco),
            (_contem(n, "por que", "porque", "explica", "como foi calculad", "memoria"), _fluxo_explicar),
            (
                _contem(n, "calcul", "impacto", "quanto", "cbs", "ibs", "imposto", "tributo", "carrinho", "margem"),
                _fluxo_calcular,
            ),
            (_contem(n, "cadastr", "adicion", "inclu", "vend", "classifica", "ncm", "busca", "procur"), _fluxo_buscar),
        ]
        for condicao, fluxo in fluxos:
            if condicao:
                return fluxo(t)
        return AJUDA


# ---------------------------------------------------------------------------
# Fluxos


def _fluxo_erro(t: _Turno) -> RespostaModelo | str:
    codigo = _CODIGO.search(t.texto).group(0).upper()  # type: ignore[union-attr]
    feitos = t.de("explicar_erro")
    if not feitos:
        return t.chamar(("explicar_erro", {"codigo": codigo}))
    r = feitos[-1]
    if r.erro:
        return f"Não achei {codigo} no catálogo de erros dos motores: {_erro(r)}"
    c = r.conteudo
    return f"{c['codigo']} ({NOME_MOTOR.get(c['motor'], c['motor'])}): {c['titulo']}. {c['descricao']}"


def _fluxo_regime(t: _Turno) -> RespostaModelo | str:
    feitos = t.de("comparar_regimes")
    if not feitos:
        return t.chamar(("comparar_regimes", {}))
    r = feitos[-1]
    if r.erro:
        return f"Não consegui comparar os regimes: {_erro(r)} {CONTADOR_REGIME}"
    c = r.conteudo
    trad, hib = c["tradicional"], c["hibrido"]
    texto = (
        f"Na venda de R$ {reais(c['valorVenda'])} a {c['cliente']['nome']}: no Simples tradicional, a CBS/IBS no DAS "
        f"é R$ {reais(trad['tributo'])} e o cliente leva R$ {reais(trad['creditoCliente'])} de crédito (custo "
        f"líquido dele R$ {reais(trad['custoLiquidoCliente'])}). No híbrido, o débito é R$ {reais(hib['debito'])}, "
        f"o crédito das compras R$ {reais(hib['creditoCompras'])} e o tributo líquido R$ "
        f"{reais(hib['tributoLiquido'])}; o cliente leva R$ {reais(hib['creditoCliente'])} de crédito (custo "
        f"líquido dele R$ {reais(hib['custoLiquidoCliente'])})."
    )
    diferenca = Decimal(str(c["diferencaCaixa"]))
    if diferenca > 0:
        texto += f" A preço igual, o híbrido deixa R$ {reais(diferenca)} a mais de caixa com a empresa."
    elif diferenca < 0:
        texto += " A preço igual, o híbrido deixa menos caixa com a empresa que o tradicional."
    else:
        texto += " A preço igual, o caixa da empresa é o mesmo nos dois regimes."
    empate = c.get("empateTradicional")
    if empate and Decimal(str(empate["descontoNecessario"])) > 0:
        texto += (
            f" Para o cliente ter no tradicional o mesmo custo líquido que teria num concorrente do regime regular "
            f"com o mesmo preço, o preço precisaria ser R$ {reais(empate['precoCliente'])} (R$ "
            f"{reais(empate['descontoNecessario'])} a menos)."
        )
    return f"{texto}{_fim_simulacao(c)} Os números valem para as premissas listadas. {CONTADOR_REGIME}"


CONTADOR_REGIME = "A decisão de regime deve ser validada com o seu contador."


def _fluxo_alertas(t: _Turno) -> RespostaModelo | str:
    feitos = t.de("listar_alertas")
    if not feitos:
        return t.chamar(("listar_alertas", {}))
    return feitos[-1].conteudo.get("indisponivel") or _erro(feitos[-1])


def _fluxo_buscar(t: _Turno) -> RespostaModelo | str:
    fragmentos = _fragmentos(t.texto)
    if not fragmentos:
        return "Diga o nome dos produtos, por exemplo: cadastra arroz polido, cerveja de malte e chocolate."
    feitos = t.de("buscar_ncm")
    if not feitos:
        return t.chamar(*(("buscar_ncm", {"texto": f}) for f in fragmentos))
    linhas = []
    for r in feitos:
        if r.erro:
            linhas.append(f"Não consegui buscar agora: {_erro(r)}")
            continue
        c = r.conteudo
        if not c["candidatos"]:
            linhas.append(
                f"Para “{c['consulta']}” não achei NCM pelo nome oficial. Tente outro nome ou informe o código da NCM."
            )
            continue
        primeiro = c["candidatos"][0]
        outros = len(c["candidatos"]) - 1
        extra = f", e mais {outros} candidata(s)" if outros else ""
        linhas.append(
            f"Para “{c['consulta']}”, a NCM mais provável é {primeiro['ncm']} ({primeiro['descricao']}), com "
            f"{len(primeiro['classificacoes'])} classificação(ões) válida(s) no motor{extra}."
        )
    return " ".join(linhas) + " " + CONFIRMAR


def _precisa_itens(t: _Turno) -> RespostaModelo | str | None:
    lista = t.de("listar_itens")
    if not lista:
        return t.chamar(("listar_itens", {}))
    if lista[-1].erro:
        return _erro(lista[-1])
    return None


def _linha_item(item: dict[str, Any]) -> str:
    nome = item["descricao"]
    if item["erros"]:
        e = item["erros"][0]
        return f"{nome}: o motor devolveu {e['codigo']} ({e['titulo']}), sem cálculo."
    if item["precoCliente"] is None:
        motivo = item.get("motivoEstado") or "sem cálculo"
        return f"{nome}: estado {item['estado']}, {motivo}."
    trib = item["tributos"]
    partes = [f"CBS R$ {reais(trib['cbs'])}", f"IBS R$ {reais(trib['ibs'])}"]
    if trib.get("impostoSeletivo") not in (None, "0.00"):
        partes.append(f"IS R$ {reais(trib['impostoSeletivo'])}")
    frase = f"{nome}: {', '.join(partes)}; preço ao cliente R$ {reais(item['precoCliente'])}"
    if item.get("margemPct") is not None:
        frase += f"; margem de {br(item['margemPct'])}%"
    return frase + "."


def _fim_simulacao(c: dict[str, Any]) -> str:
    return f" {c['avisoSimulacao']}." if c.get("simulado") and c.get("avisoSimulacao") else ""


def _fluxo_calcular(t: _Turno) -> RespostaModelo | str:
    if (pendente := _precisa_itens(t)) is not None:
        return pendente
    item = t.item_citado()
    feitos = t.de("calcular_carrinho")
    if not feitos:
        return t.chamar(("calcular_carrinho", {"itemIds": [item["id"]]} if item else {}))
    r = feitos[-1]
    if r.erro:
        return f"Não consegui calcular: {_erro(r)}"
    c = r.conteudo
    if item:
        return _linha_item(c["itens"][0]) + _fim_simulacao(c)
    tot = c["totais"]
    texto = (
        f"Calculei {tot['itensCalculados']} item(ns) nas calculadoras oficiais: CBS R$ {reais(tot['tributos']['cbs'])}, "
        f"IBS R$ {reais(tot['tributos']['ibs'])} e preço ao cliente de R$ {reais(tot['precoCliente'])} no total."
    )
    com_erro = [i for i in c["itens"] if i["precoCliente"] is None]
    if com_erro:
        texto += " Sem cálculo: " + " ".join(_linha_item(i) for i in com_erro)
    return texto + _fim_simulacao(c)


def _fluxo_preco(t: _Turno) -> RespostaModelo | str:
    if (pendente := _precisa_itens(t)) is not None:
        return pendente
    item = t.item_citado()
    if item is None:
        return "De qual item confirmado você quer o preço? Diga o nome do produto junto com a margem."
    feitos = t.de("preco_alvo")
    if not feitos:
        margem = Decimal(_PCT.search(t.texto).group(1).replace(",", "."))  # type: ignore[union-attr]
        return t.chamar(("preco_alvo", {"itemId": item["id"], "margemAlvoPct": str(margem)}))
    r = feitos[-1]
    if r.erro:
        alvo = br(r.conteudo.get("argumentos", {}).get("margemAlvoPct", ""))
        return f"Não há preço para {alvo}% de margem no item {item['descricao']}: {_erro(r)}"
    c = r.conteudo
    metodo = "ajuste afim" if c["metodo"] == "afim" else "bisseção"
    return (
        f"Para {br(c['margemAlvoPct'])}% de margem no item {item['descricao']}, o valor unitário é "
        f"R$ {reais(c['valorUnitario'])} (preço ao cliente R$ {reais(c['precoCliente'])}), com margem obtida de "
        f"{br(c['margemObtidaPct'])}%, em {c['chamadas']} avaliações do motor ({metodo}). Aplique no cartão se "
        f"quiser.{_fim_simulacao(c)}"
    )


def _primeira_frase(texto: str, limite: int = 320) -> str:
    """Corta no fim de uma frase, para nunca partir um número ao meio."""
    texto = " ".join(texto.split())
    if len(texto) <= limite:
        return texto
    corte = texto.rfind(". ", 0, limite)
    return texto[: corte + 1] if corte > 40 else texto[:limite].rsplit(" ", 1)[0] + "…"


def _fluxo_explicar(t: _Turno) -> RespostaModelo | str:
    if (pendente := _precisa_itens(t)) is not None:
        return pendente
    item = t.item_citado()
    if item is None:
        return "Qual item confirmado você quer que eu explique? Diga o nome do produto."
    feitos = t.de("explicar_item")
    if not feitos:
        return t.chamar(("explicar_item", {"itemId": item["id"]}))
    r = feitos[-1]
    if r.erro:
        return f"Não consegui explicar o item: {_erro(r)}"
    c = r.conteudo
    frases = [f"O item {item['descricao']} foi calculado pelo motor {NOME_MOTOR[c['motor']]}, estado {c['estado']}."]
    if c.get("reducaoPct") not in (None, "0.00"):
        frases.append(f"A classificação {item['cClassTrib']} tem redução de {br(c['reducaoPct'])}% na alíquota.")
    for e in c.get("erros", [])[:1]:
        frases.append(f"O motor devolveu {e['codigo']}: {e['titulo']}.")
    memoria = c.get("memoria") or {}
    for chave in list(memoria)[:2]:
        frases.append(f"Memória do motor ({chave}): {_primeira_frase(memoria[chave])}")
    for f in c.get("fundamentacoes", [])[:1]:
        trecho = _primeira_frase(f["texto"])
        frases.append(f"Fundamentação: {f['textoCurto']}. {trecho}{'' if trecho.endswith(('.', '…')) else '.'}")
    nomes = [p["nome"] for p in c.get("premissas", [])]
    if nomes:
        frases.append("Premissas usadas: " + "; ".join(nomes) + ".")
    return " ".join(frases[:6])


def _fluxo_corrigir(t: _Turno) -> RespostaModelo | str:
    feitos = t.de("calcular_carrinho")
    if not feitos:
        return t.chamar(("calcular_carrinho", {}))
    r = feitos[-1]
    if r.erro:
        return f"Não consegui calcular para achar os erros: {_erro(r)}"
    com_erro = [i for i in r.conteudo["itens"] if any(e["codigo"] in ("REG-011", "VSN-047") for e in i["erros"])]
    if not com_erro:
        outros = [i for i in r.conteudo["itens"] if i["erros"]]
        if outros:
            return "Nenhum item tem erro de classificação. " + " ".join(_linha_item(i) for i in outros)
        return "Nenhum item voltou com erro do motor."
    if not t.de("explicar_erro"):
        codigos = sorted({e["codigo"] for i in com_erro for e in i["erros"] if e["codigo"] in ("REG-011", "VSN-047")})
        return t.chamar(*(("explicar_erro", {"codigo": c}) for c in codigos))
    if not t.de("listar_itens"):
        return t.chamar(("listar_itens", {}))
    itens = {i["id"]: i for i in t.de("listar_itens")[-1].conteudo.get("itens", [])}
    if not t.de("listar_cclasstrib"):
        ncms = sorted({itens[i["id"]]["ncm"] for i in com_erro if itens.get(i["id"], {}).get("ncm")})
        if ncms:
            return t.chamar(*(("listar_cclasstrib", {"ncm": n}) for n in ncms))
    descricoes = {r.conteudo["codigo"]: r.conteudo["descricao"] for r in t.de("explicar_erro") if not r.erro}
    frases = []
    for i in com_erro:
        e = next(e for e in i["erros"] if e["codigo"] in ("REG-011", "VSN-047"))
        frases.append(f"O item {i['descricao']} voltou com {e['codigo']}: {descricoes.get(e['codigo'], e['titulo'])}")
    frases.append(
        "Separei no cartão até 3 classificações válidas para a NCM do item, segundo o motor. Escolha uma (ou "
        "confirme com o seu contador) e eu recalculo só esse item."
    )
    return " ".join(frases)
