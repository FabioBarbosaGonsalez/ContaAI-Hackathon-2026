"""Ferramentas do agente (plano, seção 10; E2-01).

Cada ferramenta valida os argumentos (Pydantic, extra="forbid") e chama o mesmo código das rotas,
que chama os motores (P1). O resultado é JSON e é o que a IA vê: todo número que ela puder citar
precisa estar aqui (P2, verificador.py).

Regras que valem para qualquer provedor:
- Só os itens do contexto (confirmados pelo usuário, P3) são calculados, e por id. A IA não
  inventa classificação: buscar_ncm e listar_cclasstrib só PROPÕEM, e a tela pede a confirmação.
- Nenhuma ferramenta grava nada. As ações (confirmar, corrigir, aplicar preço) saem como propostas
  para o usuário clicar (loop.py).
- Erros viram resultado {"erro": ...} com mensagem própria, sem URL, host ou corpo do motor.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.agente.tipos import DefinicaoFerramenta
from app.classificacao.candidatos import buscar_candidatos, classificacoes_da_ncm
from app.contrato import (
    CarrinhoRequisicao,
    ClienteB2B,
    ContextoChat,
    ExplicarRequisicao,
    ItemBase,
    ItemEntrada,
    PrecoAlvoRequisicao,
    RegimeCompararRequisicao,
)
from app.explicacao import explicar_item
from app.motores.cliente import ClienteMotores, FalhaMotor, OperacaoRecusada
from app.motores.dados_abertos import DadosAbertos
from app.precificacao.carrinho import calcular_carrinho
from app.precificacao.preco_alvo import CalculoRecusado, calcular_preco_alvo
from app.regime.comparar import comparar_regimes

log = logging.getLogger("contaai.agente")

INDISPONIVEL_E4 = "Os alertas de margem a partir da NF-e entram na E4. Ainda não há alertas reais."
SEM_CONTEXTO = (
    "Sem contexto da operação (data, UF, município, regime e itens confirmados) não há o que calcular. "
    "Peça ao usuário para confirmar os itens na tela."
)


@dataclass(frozen=True)
class Ambiente:
    motores: ClienteMotores
    dados_abertos: DadosAbertos
    contexto: ContextoChat | None
    data_sem_contexto: date | None = None  # data das consultas quando não há contexto (padrão: hoje)
    usos: dict[str, int] = field(default_factory=dict)  # chamadas por ferramenta nesta mensagem

    @property
    def data(self) -> date:
        if self.contexto is not None:
            return self.contexto.data
        return self.data_sem_contexto or date.today()


class FalhaFerramenta(Exception):
    """Erro esperado: vira {"erro": mensagem} no resultado, que a IA explica ao usuário."""

    def __init__(self, mensagem: str, erros: list[dict[str, Any]] | None = None) -> None:
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.erros = erros or []


class _Args(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BuscarNcmArgs(_Args):
    texto: str = Field(min_length=2, max_length=120, description="Nome do produto como o usuário escreveu.")


class ListarCclasstribArgs(_Args):
    ncm: str = Field(pattern=r"^\d{8}$")


class SemArgs(_Args):
    pass


class CalcularCarrinhoArgs(_Args):
    itemIds: list[str] | None = Field(
        default=None, max_length=200, description="Ids dos itens do contexto. Vazio: todos os itens."
    )


class PrecoAlvoArgs(_Args):
    itemId: str = Field(max_length=64)
    margemAlvoPct: Decimal = Field(gt=0, lt=100, description="Margem desejada em % do preço ao cliente.")


class CompararRegimesArgs(_Args):
    itemIds: list[str] | None = Field(
        default=None, max_length=200, description="Ids dos itens do contexto vendidos ao cliente. Vazio: todos."
    )
    clienteNome: str | None = Field(
        default=None, max_length=120, description="Nome do cliente do regime regular, se o usuário disse."
    )


class ItemArgs(_Args):
    itemId: str = Field(max_length=64)


class ErroArgs(_Args):
    codigo: str = Field(pattern=r"^(REG|VSN)-\d{3}$")


Executor = Callable[[Any, Ambiente], Awaitable[dict[str, Any]]]

# Uma busca de NCM nova custa até ~430 consultas ao motor: no máximo 5 por mensagem (ADR 0006).
MAX_POR_MENSAGEM = {"buscar_ncm": 5}


@dataclass(frozen=True)
class Ferramenta:
    nome: str
    descricao: str
    argumentos: type[_Args]
    executar: Executor

    def definicao(self) -> DefinicaoFerramenta:
        esquema = self.argumentos.model_json_schema()
        esquema.pop("title", None)
        return DefinicaoFerramenta(nome=self.nome, descricao=self.descricao, esquema=esquema)


def _json(modelo: BaseModel, **excluir: Any) -> dict[str, Any]:
    return modelo.model_dump(mode="json", **excluir)


def _contexto(amb: Ambiente) -> ContextoChat:
    if amb.contexto is None:
        raise FalhaFerramenta(SEM_CONTEXTO)
    return amb.contexto


def _item(ctx: ContextoChat, item_id: str) -> ItemEntrada:
    item = next((i for i in ctx.itens if i.id == item_id), None)
    if item is None:
        raise FalhaFerramenta(f"Não há item confirmado com id '{item_id}'. Use listar_itens para ver os ids.")
    return item


def _operacao(ctx: ContextoChat) -> dict[str, Any]:
    return {
        "data": ctx.data,
        "uf": ctx.uf,
        "municipio": ctx.municipio,
        "aliquotasNominais": ctx.aliquotasNominais,
        "premissasDas": ctx.premissasDas,
        "regime": ctx.regime,
    }


async def _buscar_ncm(args: BuscarNcmArgs, amb: Ambiente) -> dict[str, Any]:
    return _json(await buscar_candidatos(amb.dados_abertos, args.texto, amb.data))


async def _listar_cclasstrib(args: ListarCclasstribArgs, amb: Ambiente) -> dict[str, Any]:
    if await amb.dados_abertos.ncm(args.ncm, amb.data) is None:
        raise FalhaFerramenta(f"A NCM {args.ncm} não existe ou não está vigente na data {amb.data.isoformat()}.")
    classificacoes = await classificacoes_da_ncm(amb.dados_abertos, args.ncm, amb.data)
    return {
        "ncm": args.ncm,
        "classificacoes": [_json(c) for c in classificacoes],
        "aviso": "Candidatas para o usuário escolher (P3).",
    }


async def _listar_itens(_: SemArgs, amb: Ambiente) -> dict[str, Any]:
    ctx = _contexto(amb)
    return {
        "regime": ctx.regime.value,
        "data": ctx.data.isoformat(),
        "itens": [
            _json(i, include={"id", "descricao", "ncm", "nbs", "cst", "cClassTrib", "valorUnitario", "custoUnitario"})
            for i in ctx.itens
        ],
    }


async def _calcular_carrinho(args: CalcularCarrinhoArgs, amb: Ambiente) -> dict[str, Any]:
    ctx = _contexto(amb)
    itens = ctx.itens if not args.itemIds else [_item(ctx, i) for i in args.itemIds]
    if not itens:
        raise FalhaFerramenta("Não há itens confirmados para calcular.")
    resposta = await calcular_carrinho(CarrinhoRequisicao(**_operacao(ctx), itens=itens), amb.motores)
    # A memória de cálculo fica para explicar_item: aqui só pesaria no contexto da IA.
    return _json(resposta, exclude={"itens": {"__all__": {"memoria"}}})


async def _preco_alvo(args: PrecoAlvoArgs, amb: Ambiente) -> dict[str, Any]:
    ctx = _contexto(amb)
    item = _item(ctx, args.itemId)
    if item.custoUnitario is None:
        raise FalhaFerramenta(f"O item '{item.id}' não tem custo informado: sem custo não há margem.")
    req = PrecoAlvoRequisicao(
        **_operacao(ctx),
        item=ItemBase.model_validate(item.model_dump(include=set(ItemBase.model_fields))),
        custoUnitario=item.custoUnitario,
        creditoCompraUnitario=item.creditoCompraUnitario,
        margemAlvoPct=args.margemAlvoPct,
    )
    return _json(await calcular_preco_alvo(req, amb.motores), exclude={"memoria"})


async def _explicar_item(args: ItemArgs, amb: Ambiente) -> dict[str, Any]:
    ctx = _contexto(amb)
    req = ExplicarRequisicao(**_operacao(ctx), item=_item(ctx, args.itemId))
    return _json(await explicar_item(req, amb.motores, amb.dados_abertos))


async def _explicar_erro(args: ErroArgs, amb: Ambiente) -> dict[str, Any]:
    achado = await amb.dados_abertos.erro(args.codigo)
    if achado is None:
        raise FalhaFerramenta(f"O código {args.codigo} não existe no catálogo de erros do motor.")
    motor, erro = achado
    return {"codigo": erro.codigo, "titulo": erro.titulo, "descricao": erro.descricao, "motor": motor.value}


CLIENTE_SEM_NOME = "Cliente do regime regular"


async def _comparar_regimes(args: CompararRegimesArgs, amb: Ambiente) -> dict[str, Any]:
    ctx = _contexto(amb)
    itens = ctx.itens if not args.itemIds else [_item(ctx, i) for i in args.itemIds]
    if not itens:
        raise FalhaFerramenta("Não há itens confirmados para comparar.")
    if ctx.premissasDas is None:
        raise FalhaFerramenta(
            "Sem as alíquotas efetivas do Simples (premissasDas) não há lado tradicional. Peça ao usuário para "
            "informá-las na tela."
        )
    operacao = {k: v for k, v in _operacao(ctx).items() if k != "regime"}
    req = RegimeCompararRequisicao(
        **operacao,
        cliente=ClienteB2B(nome=args.clienteNome or CLIENTE_SEM_NOME, regime="regime_regular"),
        itens=itens,
    )
    return _json(await comparar_regimes(req, amb.motores))


async def _listar_alertas(_: SemArgs, __: Ambiente) -> dict[str, Any]:
    return {"indisponivel": INDISPONIVEL_E4}


FERRAMENTAS: dict[str, Ferramenta] = {
    f.nome: f
    for f in [
        Ferramenta(
            "buscar_ncm",
            "Busca NCMs candidatas para um produto pelo nome, com as classificações (cClassTrib) válidas no motor. "
            "Só propõe: o usuário confirma na tela.",
            BuscarNcmArgs,
            _buscar_ncm,
        ),
        Ferramenta(
            "listar_cclasstrib",
            "Lista as classificações tributárias (cClassTrib) válidas para uma NCM, segundo o motor oficial.",
            ListarCclasstribArgs,
            _listar_cclasstrib,
        ),
        Ferramenta(
            "listar_itens",
            "Lista os itens já confirmados pelo usuário (ids, descrição, NCM, classificação, valor e custo).",
            SemArgs,
            _listar_itens,
        ),
        Ferramenta(
            "calcular_carrinho",
            "Calcula CBS, IBS, IS, preço ao cliente e margem dos itens confirmados, pelos motores oficiais.",
            CalcularCarrinhoArgs,
            _calcular_carrinho,
        ),
        Ferramenta(
            "preco_alvo",
            "Calcula o menor preço com a margem desejada para um item confirmado (precisa do custo).",
            PrecoAlvoArgs,
            _preco_alvo,
        ),
        Ferramenta(
            "explicar_item",
            "Memória de cálculo do motor, redução aplicada, fundamentação legal e premissas de um item confirmado.",
            ItemArgs,
            _explicar_item,
        ),
        Ferramenta(
            "explicar_erro",
            "Descrição oficial de um código de erro dos motores (REG-xxx ou VSN-xxx).",
            ErroArgs,
            _explicar_erro,
        ),
        Ferramenta(
            "comparar_regimes",
            "Compara Simples tradicional e híbrido numa venda dos itens confirmados a um cliente do regime regular: "
            "tributo e caixa da empresa, crédito que o cliente leva e custo líquido dele, com as premissas. Não "
            "recomenda regime.",
            CompararRegimesArgs,
            _comparar_regimes,
        ),
        Ferramenta(
            "listar_alertas",
            "Lista os alertas de margem gerados por notas de compra (disponível na E4).",
            SemArgs,
            _listar_alertas,
        ),
    ]
}


def definicoes() -> list[DefinicaoFerramenta]:
    return [f.definicao() for f in FERRAMENTAS.values()]


async def executar(nome: str, argumentos: dict[str, Any], amb: Ambiente) -> tuple[dict[str, Any], bool]:
    """Executa uma chamada da IA. Devolve (conteúdo, erro). Nunca levanta exceção para o loop."""
    ferramenta = FERRAMENTAS.get(nome)
    if ferramenta is None:
        return {"erro": f"Ferramenta '{nome}' não existe."}, True
    amb.usos[nome] = amb.usos.get(nome, 0) + 1
    if amb.usos[nome] > MAX_POR_MENSAGEM.get(nome, amb.usos[nome]):
        return {"erro": f"Limite de {MAX_POR_MENSAGEM[nome]} chamadas de {nome} por mensagem."}, True
    try:
        args = ferramenta.argumentos.model_validate(argumentos)
    except ValidationError as e:
        campos = sorted({".".join(str(p) for p in err["loc"]) or "argumentos" for err in e.errors()})
        return {"erro": f"Argumentos inválidos para {nome}: {', '.join(campos)}.", "argumentos": argumentos}, True
    try:
        return await ferramenta.executar(args, amb), False
    except FalhaFerramenta as e:
        return {"erro": e.mensagem, "argumentos": argumentos, **({"erros": e.erros} if e.erros else {})}, True
    except CalculoRecusado as e:
        erros = [_json(x) for x in e.erros]
        return {"erro": e.detalhe, "argumentos": argumentos, **({"erros": erros} if erros else {})}, True
    except OperacaoRecusada as e:
        return {"erro": e.mensagem, "argumentos": argumentos, "erros": [_json(x) for x in e.erros]}, True
    except FalhaMotor as e:
        return {"erro": e.mensagem}, True
    except ValueError as e:  # validação dos modelos do contrato montados a partir do contexto
        return {"erro": f"Entrada inválida para {nome}: {e}", "argumentos": argumentos}, True
