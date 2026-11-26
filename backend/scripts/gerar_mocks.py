"""Gera os mocks da API (backend/app/mocks/*.json) a partir dos motores em execução (E0-05).

"Mocks servidos a partir das respostas gravadas" (plano, E0): todo valor de tributo vem dos motores,
chamados aqui com os dados de demonstração (data/demo). Margens, preço-alvo e comparação de regimes
usam as fórmulas do ADR 0003 sobre esses valores, só com soma, subtração e divisão (P1).

É a implementação de referência que as etapas E1 a E4 substituem pelo código de produção, com testes.
Carrinho, preço-alvo, explicação, chat e comparação de regimes já saem do código de produção (E1 a E3,
ADR 0007), e desde a E4 também NF-e, alertas, catálogo, painel do contador e notas (ADR 0008), num banco
temporário com as sementes. O carrinho, o preço-alvo e a importação da nota 2 de referência continuam
aqui como conferência: se a produção divergir deles, nenhum mock é gravado.

Uso (motores de pé): cd backend && uv run python scripts/gerar_mocks.py
"""

from __future__ import annotations

import json
import os
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.contrato import (  # noqa: E402
    AVISO_LEGAL,
    Alerta,
    AlertasResposta,
    AliquotasNominais,
    BuscaNcmResposta,
    CandidatoNcm,
    CarrinhoResposta,
    ChatResposta,
    ClassificacaoCandidata,
    ClienteB2B,
    Emitente,
    ErroDescricao,
    ExplicarResposta,
    Fundamentacao,
    ImpostoSeletivoEntrada,
    ItemCalculado,
    ItemEntrada,
    ItemNotaCasado,
    Motor,
    NfeImportarResposta,
    NotaResumo,
    OrigemAlerta,
    PrecoAlvoResposta,
    Premissa,
    PremissasDas,
    Regime,
    RegimeCompararRequisicao,
    RegimeCompararResposta,
    Totais,
    Tributos,
)
from app.dados_demo import PASTA_DEMO, ItemCatalogo, carregar_cliente_b2b, carregar_distribuidora  # noqa: E402
from app.motores.conversao import LeituraItem, ler_resposta, versoes  # noqa: E402
from app.motores.requisicoes import AliquotasPremissa, DasPremissa, Linha, operacao_rr, operacao_sn  # noqa: E402
from app.precificacao.lote import LOTE  # noqa: E402

MOTOR_RR_URL = os.environ.get("MOTOR_RR_URL", "http://127.0.0.1:8080/api")
MOTOR_SN_URL = os.environ.get("MOTOR_SN_URL", "http://127.0.0.1:8082/api")
# CONTAAI_SAIDA_MOCKS permite regravar em outra pasta (o teste de reprodutibilidade usa isso).
PASTA_MOCKS = Path(os.environ.get("CONTAAI_SAIDA_MOCKS") or Path(__file__).resolve().parents[1] / "app" / "mocks")
NS = {"n": "http://www.portalfiscal.inf.br/nfe"}

C2, C4 = Decimal("0.01"), Decimal("0.0001")
NCM_NEUTRA = "84381000"  # máquina industrial: referência sem redução específica de produto (ADR 0003)

DEMO = carregar_distribuidora()
CLIENTE = carregar_cliente_b2b()
CEN, EMP = DEMO.cenario, DEMO.empresa
ALIQ = AliquotasPremissa(
    cbs=CEN.aliquotasNominais.cbs,
    ibsEstadual=CEN.aliquotasNominais.ibsEstadual,
    ibsMunicipal=CEN.aliquotasNominais.ibsMunicipal,
    impostoSeletivoAdValorem=CEN.impostoSeletivoAdValorem.valor,
)
DAS = DasPremissa(
    anexo=CEN.premissasDas.anexo,
    cAtivSN=EMP.simples.cAtivSN,
    pCBSSN=CEN.premissasDas.pCBSSN,
    pIBSSN=CEN.premissasDas.pIBSSN,
)


def br(valor: Decimal) -> str:
    return f"{valor.normalize():f}".replace(".", ",")


def pct(parte: Decimal, todo: Decimal) -> Decimal:
    return (parte / todo * 100).quantize(C2, ROUND_HALF_UP)


# ---------------------------------------------------------------------------
# Motores


class Motores:
    def __init__(self, cli: httpx.Client) -> None:
        self.cli = cli
        self.headers_rr: dict[str, str] = {}
        self.headers_sn: dict[str, str] = {}

    def rr(self, linhas: list[Linha], data_fato: date) -> list[LeituraItem]:
        r = self.cli.post(
            f"{MOTOR_RR_URL}/calculadora/observabilidade/regime-geral",
            json=operacao_rr(linhas, data_fato, EMP.uf, EMP.municipio, ALIQ),
        ).raise_for_status()
        self.headers_rr = dict(r.headers)
        return ler_resposta(r.json(), Motor.REGIME_REGULAR)

    def sn(self, linhas: list[Linha], data_fato: date) -> list[LeituraItem]:
        r = self.cli.post(
            f"{MOTOR_SN_URL}/calculadora/observabilidade/simples-nacional/nao-assistido",
            json=operacao_sn(linhas, data_fato, DAS),
        ).raise_for_status()
        self.headers_sn = dict(r.headers)
        return ler_resposta(r.json(), Motor.SIMPLES_NACIONAL)

    def calcular(self, regime: Regime, linhas: list[Linha], data_fato: date) -> list[LeituraItem]:
        return self.sn(linhas, data_fato) if regime == Regime.SIMPLES_TRADICIONAL else self.rr(linhas, data_fato)

    def get(self, base: str, rota: str, **params: Any) -> Any:
        texto = {k: v.isoformat() if isinstance(v, date) else v for k, v in params.items()}
        return self.cli.get(base + rota, params=texto).raise_for_status().json()


# ---------------------------------------------------------------------------
# Notas de compra e custos


@dataclass(frozen=True)
class ItemNota:
    cProd: str
    xProd: str
    ncm: str
    qCom: Decimal
    vUnCom: Decimal
    vProd: Decimal
    cbsIbs: Decimal | None  # vCBS + vIBS do grupo IBSCBS, quando a nota traz


@dataclass(frozen=True)
class Nota:
    numero: str
    dhEmi: datetime
    emitente: Emitente
    itens: list[ItemNota]

    @property
    def tem_grupo(self) -> bool:
        return any(i.cbsIbs is not None for i in self.itens)


@dataclass(frozen=True)
class Custo:
    custoUnitario: Decimal
    creditoUnitario: Decimal | None
    fonte: str | None  # "nfe" ou "motor"
    nota: Nota


def ler_notas() -> list[Nota]:
    notas = []
    for caminho in sorted((PASTA_DEMO / "notas").glob("nfe-compra-*.xml")):
        # Notas fictícias do próprio repositório (data/demo), não arquivo de terceiro. O backend lê nota
        # recebida pelo leitor estrito de app/nfe/leitor.py (sem DTD nem entidades).
        inf = ET.parse(caminho).getroot().find("n:infNFe", NS)  # noqa: S314
        itens = []
        for det in inf.findall("n:det", NS):
            p = det.find("n:prod", NS)
            g = det.find("n:imposto/n:IBSCBS/n:gIBSCBS", NS)
            itens.append(
                ItemNota(
                    cProd=p.findtext("n:cProd", namespaces=NS),
                    xProd=p.findtext("n:xProd", namespaces=NS),
                    ncm=p.findtext("n:NCM", namespaces=NS),
                    qCom=Decimal(p.findtext("n:qCom", namespaces=NS)),
                    vUnCom=Decimal(p.findtext("n:vUnCom", namespaces=NS)),
                    vProd=Decimal(p.findtext("n:vProd", namespaces=NS)),
                    cbsIbs=None
                    if g is None
                    else Decimal(g.findtext("n:gCBS/n:vCBS", namespaces=NS))
                    + Decimal(g.findtext("n:vIBS", namespaces=NS)),
                )
            )
        notas.append(
            Nota(
                numero=inf.findtext("n:ide/n:nNF", namespaces=NS),
                dhEmi=datetime.fromisoformat(inf.findtext("n:ide/n:dhEmi", namespaces=NS)),
                emitente=Emitente(
                    cnpj=inf.findtext("n:emit/n:CNPJ", namespaces=NS),
                    nome=inf.findtext("n:emit/n:xNome", namespaces=NS),
                ),
                itens=itens,
            )
        )
    return sorted(notas, key=lambda n: n.dhEmi)


def casar(item_nota: ItemNota) -> ItemCatalogo | None:
    """Casa pelo NCM + código do fornecedor (plano 11.3)."""
    return next(
        (c for c in DEMO.catalogo if c.ncm == item_nota.ncm and c.codigoFornecedor == item_nota.cProd),
        None,
    )


def custos_da_nota(motores: Motores, nota: Nota) -> dict[str, Custo]:
    """Custo e crédito por unidade de cada item da nota. Sem grupo IBSCBS, o crédito vem do motor RR."""
    casados = [(i, casar(i)) for i in nota.itens]
    casados = [(i, c) for i, c in casados if c is not None]
    if nota.tem_grupo:
        creditos = {c.id: (i.cbsIbs / i.qCom).quantize(C4, ROUND_HALF_UP) for i, c in casados}
        fonte = "nfe"
    else:
        leituras = motores.rr([Linha(c, i.qCom, i.vProd) for i, c in casados], nota.dhEmi.date())
        creditos = {
            c.id: (lei.tributo_cbs_ibs() / i.qCom).quantize(C4, ROUND_HALF_UP) if lei.calculado else None
            for (i, c), lei in zip(casados, leituras, strict=True)
        }
        fonte = "motor"
    return {
        c.id: Custo(i.vUnCom, creditos[c.id], fonte if creditos[c.id] is not None else None, nota) for i, c in casados
    }


def custo_efetivo(regime: Regime, custo: Custo) -> Decimal | None:
    """Tradicional: o crédito da compra não é aproveitado e entra no custo. Híbrido: vira crédito."""
    if regime == Regime.SIMPLES_HIBRIDO:
        return custo.custoUnitario
    return None if custo.creditoUnitario is None else custo.custoUnitario + custo.creditoUnitario


# ---------------------------------------------------------------------------
# Premissas


def premissas(regime: Regime, com_is: bool = True) -> list[Premissa]:
    al = CEN.aliquotasNominais
    lista = [
        Premissa(
            nome="Alíquotas nominais de 2027",
            valor=f"CBS {br(al.cbs)}% · IBS estadual {br(al.ibsEstadual)}% · IBS municipal {br(al.ibsMunicipal)}%",
            fonte=al.fonte,
        )
    ]
    if com_is:
        lista.append(
            Premissa(
                nome="Imposto Seletivo da cerveja",
                valor=f"não incide na revenda (cClassTrib do IS 200007); alíquota exigida pelo motor: {br(CEN.impostoSeletivoAdValorem.valor)}%",
                fonte=CEN.impostoSeletivoAdValorem.fonte,
            )
        )
    if regime == Regime.SIMPLES_TRADICIONAL:
        das = CEN.premissasDas
        lista += [
            Premissa(
                nome=f"Alíquotas efetivas do Simples (anexo {das.anexo})",
                valor=f"CBS {br(das.pCBSSN)}% · IBS {br(das.pIBSSN)}%",
                fonte=das.fonte,
            ),
            Premissa(
                nome="Crédito das compras no Simples tradicional",
                valor="não aproveitado: entra no custo",
                fonte="LC 214/2025, art. 47, §9º, I: o optante do Simples não se credita de IBS e CBS.",
            ),
            Premissa(
                nome="Cesta básica dentro do DAS",
                valor="sem redução: o arroz paga as alíquotas efetivas do anexo",
                fonte="Premissa da equipe. A LC 214 zera a cesta básica (art. 125), mas não diz se vale dentro do DAS, "
                "e o motor do Simples só aplica as alíquotas informadas. Validar com o contador (ADR 0003).",
            ),
        ]
    lista += [
        Premissa(
            nome="Crédito das compras sem grupo IBSCBS na nota",
            valor="calculado no motor RR sobre o custo",
            fonte="Hipótese de fornecedor no regime regular (plano, E3).",
        ),
        Premissa(
            nome="ICMS",
            valor="fora das contas",
            fonte="Simplificação da demonstração. Em 2027 o ICMS ainda existe e é deduzido da base do IBS/CBS "
            "(docs/exemplos.md da calculadora RR).",
        ),
    ]
    return lista


def aviso_simulacao(regime: Regime) -> str:
    if regime == Regime.SIMPLES_TRADICIONAL:
        das = CEN.premissasDas
        return f"Simulação de 2027 com alíquotas efetivas do Simples assumidas (CBS {br(das.pCBSSN)}%, IBS {br(das.pIBSSN)}%)"
    return f"Simulação de 2027 com CBS {br(CEN.aliquotasNominais.cbs)}% assumida"


# ---------------------------------------------------------------------------
# POST /carrinho/calcular


def carrinho(
    motores: Motores, regime: Regime, custos: dict[str, Custo]
) -> tuple[CarrinhoResposta, dict[str, LeituraItem]]:
    linhas = [Linha(c, LOTE, (LOTE * c.precoVenda).quantize(C2)) for c in DEMO.catalogo]
    leituras = motores.calcular(regime, linhas, CEN.data)
    itens, por_id = [], {}
    for cat, linha, lei in zip(DEMO.catalogo, linhas, leituras, strict=True):
        por_id[cat.id] = lei
        preco = custo_ef = margem = None
        if lei.calculado:
            tributo = lei.tributo_cbs_ibs()
            imposto_seletivo = lei.tributos.impostoSeletivo or Decimal(0)
            custo = custos.get(cat.id)
            unit = custo_efetivo(regime, custo) if custo else None
            custo_ef = None if unit is None else (unit * LOTE).quantize(C2, ROUND_HALF_UP)
            if regime == Regime.SIMPLES_TRADICIONAL:
                preco = linha.base
                if custo_ef is not None:
                    margem = pct(linha.base - tributo - custo_ef, preco)
            else:
                preco = linha.base + tributo + imposto_seletivo
                if custo_ef is not None:
                    margem = pct(linha.base - custo_ef, preco)
        itens.append(
            ItemCalculado(
                id=cat.id,
                descricao=cat.descricao,
                motor=lei.motor,
                estado=lei.estado,
                motivoEstado=lei.motivoEstado,
                quantidade=LOTE,
                valorUnitario=cat.precoVenda,
                valorProdutos=linha.base,
                tributos=lei.tributos,
                reducaoPct=lei.reducaoPct,
                aliquotaEfetiva=lei.aliquotaEfetiva,
                precoCliente=preco,
                custoEfetivo=custo_ef,
                margemPct=margem,
                memoria=lei.memoria,
                erros=lei.erros,
            )
        )
    calc = [i for i in itens if i.precoCliente is not None]

    def soma(valores: list[Decimal | None]) -> Decimal:
        return sum((v for v in valores if v is not None), Decimal("0.00"))

    resposta = CarrinhoResposta(
        regime=regime,
        data=CEN.data,
        simulado=True,
        avisoSimulacao=aviso_simulacao(regime),
        premissas=premissas(regime)
        + [
            Premissa(
                nome="Lote de referência", valor="100 unidades por item", fonte="Valores por unidade = linha ÷ 100."
            )
        ],
        itens=itens,
        totais=Totais(
            valorProdutos=soma([i.valorProdutos for i in calc]),
            tributos=Tributos(
                cbs=soma([i.tributos.cbs for i in calc]),
                ibs=soma([i.tributos.ibs for i in calc]),
                impostoSeletivo=soma([i.tributos.impostoSeletivo for i in calc]),
            ),
            precoCliente=soma([i.precoCliente for i in calc]),
            itensCalculados=len(calc),
            itensComErro=len(itens) - len(calc),
        ),
        versoes=versoes(motores.headers_rr, motores.headers_sn),
    )
    return resposta, por_id


# ---------------------------------------------------------------------------
# POST /item/preco-alvo (ajuste afim do plano 11.1; no tradicional, o tributo incide sobre o preço)


def preco_alvo(
    motores: Motores, regime: Regime, cat: ItemCatalogo, custo: Custo, margem_alvo: Decimal
) -> PrecoAlvoResposta:
    c_ef = custo_efetivo(regime, custo)
    m = margem_alvo / 100

    def tributo_unitario(valor_unitario: Decimal) -> tuple[Decimal, LeituraItem]:
        lei = motores.calcular(regime, [Linha(cat, LOTE, (LOTE * valor_unitario).quantize(C2))], CEN.data)[0]
        total = lei.tributo_cbs_ibs()
        if regime == Regime.SIMPLES_HIBRIDO:
            total += lei.tributos.impostoSeletivo or Decimal(0)
        return total / LOTE, lei

    x1, x2 = c_ef, 2 * c_ef
    t1, _ = tributo_unitario(x1)  # chamada 1
    t2, _ = tributo_unitario(x2)  # chamada 2
    beta = (t2 - t1) / (x2 - x1)
    alfa = t1 - beta * x1
    if regime == Regime.SIMPLES_TRADICIONAL:
        den, num = 1 - beta - m, c_ef + alfa  # m = (p − T(p) − c) ÷ p
    else:
        den, num = 1 - m * (1 + beta), c_ef + m * alfa  # m = (b − c) ÷ (b + T(b)), plano 11.1
    if den <= 0:
        raise ValueError(f"Margem impossível para {cat.id}")
    valor = (num / den).quantize(C2, ROUND_CEILING)
    t, lei = tributo_unitario(valor)  # chamada 3, confirmação
    preco = valor if regime == Regime.SIMPLES_TRADICIONAL else valor + t
    obtida = (valor - t - c_ef) / valor if regime == Regime.SIMPLES_TRADICIONAL else (valor - c_ef) / (valor + t)
    if obtida < m:
        raise ValueError(f"Confirmação abaixo da margem-alvo para {cat.id}: {obtida}")
    return PrecoAlvoResposta(
        regime=regime,
        itemId=cat.id,
        valorUnitario=valor,
        precoCliente=preco,
        tributosUnitarios=Tributos(
            cbs=((lei.tributos.cbs or Decimal(0)) / LOTE).quantize(C4),
            ibs=((lei.tributos.ibs or Decimal(0)) / LOTE).quantize(C4),
            impostoSeletivo=((lei.tributos.impostoSeletivo or Decimal(0)) / LOTE).quantize(C4),
        ),
        custoEfetivoUnitario=c_ef,
        margemAlvoPct=margem_alvo,
        margemObtidaPct=(obtida * 100).quantize(C2, ROUND_HALF_UP),
        loteReferencia=int(LOTE),
        chamadas=3,
        metodo="afim",
        memoria=lei.memoria,
        simulado=True,
        avisoSimulacao=aviso_simulacao(regime),
        premissas=premissas(regime),
    )


# ---------------------------------------------------------------------------
# POST /regime/comparar: código de produção (app/regime/comparar.py, E3) com a venda mensal ao cliente B2B


def operacao_demo() -> dict[str, Any]:
    """Data, local e premissas do cenário de demonstração, rotuladas como no GET /explicar da demo."""
    return {
        "data": CEN.data,
        "uf": EMP.uf,
        "municipio": EMP.municipio,
        "aliquotasNominais": AliquotasNominais(
            cbs=CEN.aliquotasNominais.cbs,
            ibsEstadual=CEN.aliquotasNominais.ibsEstadual,
            ibsMunicipal=CEN.aliquotasNominais.ibsMunicipal,
            impostoSeletivoAdValorem=CEN.impostoSeletivoAdValorem.valor,
            fonte="Cenário de demonstração (data/demo): entradas do exemplo oficial da calculadora RR",
        ),
        "premissasDas": PremissasDas(
            anexo=CEN.premissasDas.anexo,
            cAtivSN=EMP.simples.cAtivSN,
            pCBSSN=CEN.premissasDas.pCBSSN,
            pIBSSN=CEN.premissasDas.pIBSSN,
            fonte="Cenário de demonstração (data/demo): valores de exemplo do esquema do motor SN",
        ),
    }


def item_demo(cat: ItemCatalogo, quantidade: Decimal, custo: Custo | None) -> ItemEntrada:
    """Item do catálogo com o custo da nota. O crédito por unidade só vai quando a nota trouxe o grupo
    IBSCBS (fonte "nfe"); sem o grupo, a produção calcula no motor RR sobre o custo, como faria sem a nota."""
    return ItemEntrada(
        id=cat.id,
        descricao=cat.descricao,
        ncm=cat.ncm,
        cst=cat.cst,
        cClassTrib=cat.cClassTrib,
        impostoSeletivo=ImpostoSeletivoEntrada(
            cst=cat.impostoSeletivo.cst,
            cClassTrib=cat.impostoSeletivo.cClassTrib,
            litrosPorUnidade=cat.impostoSeletivo.litrosPorUnidade,
        )
        if cat.impostoSeletivo
        else None,
        unidade=cat.unidade,
        quantidade=quantidade,
        valorUnitario=cat.precoVenda,
        custoUnitario=custo.custoUnitario if custo else None,
        creditoCompraUnitario=custo.creditoUnitario if custo and custo.fonte == "nfe" else None,
    )


def requisicao_comparar_demo(custos: dict[str, Custo]) -> RegimeCompararRequisicao:
    """A compra mensal do cliente B2B (data/demo) aos preços do catálogo e com o custo da última nota."""
    return RegimeCompararRequisicao(
        **operacao_demo(),
        cliente=ClienteB2B(nome=CLIENTE.cliente.razaoSocial, regime="regime_regular"),
        itens=[item_demo(DEMO.item(c.itemId), c.quantidade, custos[c.itemId]) for c in CLIENTE.compraMensal.itens],
    )


def regime_comparar(custos: dict[str, Custo]) -> RegimeCompararResposta:
    import asyncio

    from app.motores.cliente import ClienteMotores
    from app.regime.comparar import comparar_regimes

    async def rodar() -> RegimeCompararResposta:
        async with httpx.AsyncClient(timeout=60, trust_env=False) as http:
            motores = ClienteMotores(http, MOTOR_RR_URL, MOTOR_SN_URL)
            return await comparar_regimes(requisicao_comparar_demo(custos), motores)

    return asyncio.run(rodar())


# Carrinho, preço-alvo e explicação: código de produção (E1 e E2), conferido contra a referência acima


CAMPOS_CARRINHO = {"id", "estado", "tributos", "reducaoPct", "aliquotaEfetiva", "valorProdutos", "precoCliente"}
CAMPOS_CARRINHO |= {"custoEfetivo", "margemPct", "memoria", "erros"}
CAMPOS_PRECO_ALVO = {"valorUnitario", "precoCliente", "tributosUnitarios", "custoEfetivoUnitario", "margemObtidaPct"}
CAMPOS_PRECO_ALVO |= {"chamadas", "metodo", "loteReferencia", "memoria"}


class Divergencia(Exception):
    """A produção não bate com a implementação de referência: nenhum mock é gravado."""


def producao(
    custos: dict[str, Custo],
    referencia_carrinho: dict[Regime, CarrinhoResposta],
    referencia_preco: dict[Regime, PrecoAlvoResposta],
) -> tuple[dict[str, CarrinhoResposta], dict[str, PrecoAlvoResposta], dict[str, dict[str, ExplicarResposta]]]:
    import asyncio

    from app.contrato import CarrinhoRequisicao, ItemBase, PrecoAlvoRequisicao
    from app.empresa import requisicao_explicar
    from app.explicacao import explicar_item
    from app.motores.cliente import ClienteMotores
    from app.motores.dados_abertos import DadosAbertos
    from app.precificacao.carrinho import calcular_carrinho
    from app.precificacao.preco_alvo import calcular_preco_alvo

    cerveja = DEMO.item("cerveja-lata")

    async def rodar() -> tuple[dict, dict, dict]:
        async with httpx.AsyncClient(timeout=60, trust_env=False) as http:
            motores = ClienteMotores(http, MOTOR_RR_URL, MOTOR_SN_URL)
            da = DadosAbertos(http, MOTOR_RR_URL, MOTOR_SN_URL)
            car, preco, expl = {}, {}, {}
            for regime in Regime:
                req = CarrinhoRequisicao(
                    **operacao_demo(),
                    regime=regime,
                    itens=[item_demo(c, LOTE, custos.get(c.id)) for c in DEMO.catalogo],
                )
                car[regime] = await calcular_carrinho(req, motores)
                item = item_demo(cerveja, LOTE, custos[cerveja.id])
                preco[regime] = await calcular_preco_alvo(
                    PrecoAlvoRequisicao(
                        **operacao_demo(),
                        regime=regime,
                        item=ItemBase.model_validate(item.model_dump(include=set(ItemBase.model_fields))),
                        custoUnitario=item.custoUnitario,
                        creditoCompraUnitario=item.creditoCompraUnitario,
                        margemAlvoPct=cerveja.margemAlvoPct,
                    ),
                    motores,
                )
            for cat in DEMO.catalogo:
                # O mesmo pedido do GET /explicar/{id} no estado das sementes (preço de venda da semente).
                expl[cat.id] = {
                    r.value: await explicar_item(requisicao_explicar(EMP, CEN, cat, cat.precoVenda, r), motores, da)
                    for r in Regime
                }
            return car, preco, expl

    car, preco, expl = asyncio.run(rodar())
    for regime in Regime:
        for real, ref in zip(car[regime].itens, referencia_carrinho[regime].itens, strict=True):
            if real.model_dump(include=CAMPOS_CARRINHO) != ref.model_dump(include=CAMPOS_CARRINHO):
                raise Divergencia(f"carrinho {regime.value}, item {real.id}")
        if car[regime].totais != referencia_carrinho[regime].totais:
            raise Divergencia(f"totais do carrinho {regime.value}")
        real_p = preco[regime].model_dump(include=CAMPOS_PRECO_ALVO)
        if real_p != referencia_preco[regime].model_dump(include=CAMPOS_PRECO_ALVO):
            raise Divergencia(f"preço-alvo {regime.value}")
    return {r.value: c for r, c in car.items()}, {r.value: p for r, p in preco.items()}, expl


# ---------------------------------------------------------------------------
# POST /nfe/importar e GET /alertas


def importar(
    motores: Motores,
    nota: Nota,
    antes: dict[str, Custo],
    depois: dict[str, Custo],
    leituras_trad: dict[str, LeituraItem],
) -> NfeImportarResposta:
    casados, alertas = [], []
    regime = Regime.SIMPLES_TRADICIONAL  # regime atual da distribuidora
    for item_nota in nota.itens:
        cat = casar(item_nota)
        if cat is None:
            continue
        anterior, novo = antes.get(cat.id), depois[cat.id]
        casados.append(
            ItemNotaCasado(
                itemId=cat.id,
                codigoFornecedor=item_nota.cProd,
                ncm=item_nota.ncm,
                descricaoNota=item_nota.xProd,
                quantidade=item_nota.qCom,
                custoAnterior=anterior.custoUnitario if anterior else None,
                custoNovo=novo.custoUnitario,
                variacaoPct=pct(novo.custoUnitario - anterior.custoUnitario, anterior.custoUnitario)
                if anterior
                else None,
                creditoCompraUnitario=novo.creditoUnitario,
                fonteCredito=novo.fonte,
            )
        )
        lei = leituras_trad[cat.id]
        if anterior is None or not lei.calculado:
            continue
        tributo_unit = lei.tributo_cbs_ibs() / LOTE
        p = cat.precoVenda
        m_antes = pct(p - tributo_unit - custo_efetivo(regime, anterior), p)
        m_depois = pct(p - tributo_unit - custo_efetivo(regime, novo), p)
        if m_depois < cat.margemAlvoPct:
            sugerido = preco_alvo(motores, regime, cat, novo, cat.margemAlvoPct)
            alertas.append(
                Alerta(
                    id=f"alerta-{cat.id}-nfe-{nota.numero}",
                    itemId=cat.id,
                    descricaoItem=cat.descricao,
                    regime=regime,
                    margemAntesPct=m_antes,
                    margemDepoisPct=m_depois,
                    margemAlvoPct=cat.margemAlvoPct,
                    precoAtual=p,
                    precoSugerido=sugerido.valorUnitario,
                    origem=OrigemAlerta(
                        tipo="nfe", numero=nota.numero, dataEmissao=nota.dhEmi, emitente=nota.emitente.nome
                    ),
                    criadoEm=nota.dhEmi,
                    simulado=True,
                    premissas=premissas(regime),
                )
            )
    return NfeImportarResposta(
        nota=NotaResumo(
            numero=nota.numero, dataEmissao=nota.dhEmi, emitente=nota.emitente, temGrupoIbsCbs=nota.tem_grupo
        ),
        itensCasados=casados,
        itensSemPar=[],
        alertas=alertas,
        simulado=True,
        premissas=[],
    )


# Produção da E4 (ADR 0008): banco temporário com as sementes, importação da nota 2 pela rota real.
# O relógio é fixo (hora da nota 2, em UTC como todo instante do sistema) para que os mocks sejam reproduzíveis.

RELOGIO_MOCKS = datetime.fromisoformat("2027-03-16T12:00:00+00:00")  # hora da nota 2 (09:00 -03:00), em UTC
CAMPOS_ALERTA = {"itemId", "regime", "margemAntesPct", "margemDepoisPct", "margemAlvoPct", "precoAtual"}
CAMPOS_ALERTA |= {"precoSugerido"}
CAMPOS_CASADO = {"itemId", "codigoFornecedor", "ncm", "quantidade", "custoAnterior", "custoNovo", "variacaoPct"}
CAMPOS_CASADO |= {"creditoCompraUnitario", "fonteCredito"}


def producao_nfe(
    referencia: NfeImportarResposta,
) -> tuple[NfeImportarResposta, AlertasResposta, Any, Any, Any]:
    import asyncio
    import tempfile

    from app.motores.cliente import ClienteMotores
    from app.nfe import consultas
    from app.nfe.importacao import importar_nota
    from app.persistencia.banco import Banco
    from app.persistencia.repositorio import Repositorio
    from app.persistencia.sementes import restaurar

    def relogio() -> datetime:
        return RELOGIO_MOCKS

    async def rodar() -> tuple[NfeImportarResposta, AlertasResposta, Any, Any, Any]:
        with tempfile.TemporaryDirectory() as pasta:
            banco = Banco(Path(pasta) / "mocks.db")
            banco.migrar()
            repo = Repositorio(banco)
            async with httpx.AsyncClient(timeout=60, trust_env=False) as http:
                motores = ClienteMotores(http, MOTOR_RR_URL, MOTOR_SN_URL)
                await restaurar(repo, motores, relogio=relogio)
                nota2 = (PASTA_DEMO / "notas" / "nfe-compra-2.xml").read_bytes()
                importacao = await importar_nota(nota2, repo, motores, relogio)
            return (
                importacao,
                AlertasResposta(alertas=consultas.alertas(repo, None, None)),
                consultas.catalogo(repo, EMP.cnpj),
                consultas.painel(repo),
                consultas.notas(repo, EMP.cnpj, 50),
            )

    importacao, alertas, catalogo, painel, notas = asyncio.run(rodar())
    if [a.model_dump(include=CAMPOS_ALERTA) for a in importacao.alertas] != [
        a.model_dump(include=CAMPOS_ALERTA) for a in referencia.alertas
    ]:
        raise Divergencia("alertas da nota 2")
    if [c.model_dump(include=CAMPOS_CASADO) for c in importacao.itensCasados] != [
        c.model_dump(include=CAMPOS_CASADO) for c in referencia.itensCasados
    ]:
        raise Divergencia("itens casados da nota 2")
    return importacao, alertas, catalogo, painel, notas


# ---------------------------------------------------------------------------
# GET /busca/ncm, GET /explicar/{itemId}, GET /erros/{codigo}, POST /chat


def busca_ncm(motores: Motores) -> dict[str, BuscaNcmResposta]:
    rr = MOTOR_RR_URL + "/calculadora/dados-abertos"
    catalogo_ct = {c["codigo"]: c for c in motores.get(rr, "/classificacoes-tributarias/cbs-ibs", data=CEN.data)}
    fund = {f["codigoClassificacaoTributaria"]: f for f in motores.get(rr, "/fundamentacoes-legais", data=CEN.data)}
    candidatas = [k for k, c in catalogo_ct.items() if c.get("nomenclatura") in ("NCM", "NBS ou NCM")]

    def validas(ncm: str) -> set[str]:
        return {
            c
            for c in candidatas
            if motores.get(
                rr,
                "/classificacoes-tributarias/ncm-aplicavel",
                cClassTrib=c,
                ncm=ncm,
                dataOcorrenciaFatoGerador=CEN.data,
            ).get("valido")
        }

    neutras = validas(NCM_NEUTRA)
    consultas = {
        "arroz": "arroz-5kg",
        "cerveja": "cerveja-lata",
        "chocolate": "chocolate-barra",
        "carne": "carne-bovina-kg",
    }
    saida = {}
    for consulta, item_id in consultas.items():
        cat = DEMO.item(item_id)
        info = motores.get(rr, "/ncm", ncm=cat.ncm, data=CEN.data)
        hierarquia = " - ".join(
            info[k].rstrip(".") for k in ("posicao", "subposicao", "item", "subitem") if info.get(k)
        )
        v = validas(cat.ncm)
        codigos = sorted(v - neutras) + sorted({"000001"} & v)  # mesma ordem de app/classificacao (ADR 0006)
        saida[consulta] = BuscaNcmResposta(
            consulta=consulta,
            candidatos=[
                CandidatoNcm(
                    ncm=cat.ncm,
                    descricao=hierarquia,
                    tributadoPeloImpostoSeletivo=bool(info.get("tributadoPeloImpostoSeletivo")),
                    classificacoes=[
                        ClassificacaoCandidata(
                            cClassTrib=c,
                            cst=fund[c]["codigoSituacaoTributaria"],
                            descricao=catalogo_ct[c]["descricao"],
                            reducaoPct=Decimal(str(catalogo_ct[c].get("percentualReducaoCbs") or 0)).quantize(C2),
                            especificaDoProduto=c not in neutras,
                            fundamentacao=fund[c].get("textoCurto"),
                        )
                        for c in codigos
                    ],
                )
            ],
            aviso="Candidatos para o usuário confirmar. A classificação fiscal é decisão do usuário ou do contador (P3).",
        )
    return saida


def explicar(
    motores: Motores, leituras: dict[Regime, dict[str, LeituraItem]]
) -> dict[str, dict[str, ExplicarResposta]]:
    fund = motores.get(MOTOR_RR_URL + "/calculadora/dados-abertos", "/fundamentacoes-legais", data=CEN.data)
    saida: dict[str, dict[str, ExplicarResposta]] = {}
    for cat in DEMO.catalogo:
        saida[cat.id] = {}
        for regime, por_id in leituras.items():
            lei = por_id[cat.id]
            saida[cat.id][regime.value] = ExplicarResposta(
                itemId=cat.id,
                regime=regime,
                motor=lei.motor,
                estado=lei.estado,
                reducaoPct=lei.reducaoPct,
                memoria=lei.memoria,
                erros=lei.erros,
                fundamentacoes=[
                    Fundamentacao(
                        cClassTrib=f["codigoClassificacaoTributaria"],
                        textoCurto=f.get("textoCurto") or "",
                        texto=f.get("texto") or "",
                        referenciaNormativa=f.get("referenciaNormativa") or "",
                    )
                    for f in fund
                    if f["codigoClassificacaoTributaria"] == cat.cClassTrib
                ],
                premissas=premissas(regime, com_is=cat.impostoSeletivo is not None),
                aviso=AVISO_LEGAL,
            )
    return saida


def erros(motores: Motores) -> dict[str, ErroDescricao]:
    saida = {}
    for codigo in ("REG-011", "REG-013", "REG-035"):
        e = motores.get(MOTOR_RR_URL, "/calculadora/observabilidade/erros", codigo=codigo)
        saida[codigo] = ErroDescricao(
            codigo=e["codigo"], titulo=e["titulo"], descricao=e["descricao"], motor=Motor.REGIME_REGULAR
        )
    for codigo in ("VSN-039", "VSN-047"):
        e = motores.get(MOTOR_SN_URL, "/calculadora/observabilidade/simples-nacional/erros", codigo=codigo)
        saida[codigo] = ErroDescricao(
            codigo=e["codigo"], titulo=e["titulo"], descricao=e["descricao"], motor=Motor.SIMPLES_NACIONAL
        )
    return saida


FRASE_CHAT = "Cadastra arroz polido não parboilizado, cerveja de malte e chocolate não recheado"


def chat() -> ChatResposta:
    """Saída real do agente (provedor roteiro, sem IA) para a frase da demo, contra os motores em execução."""
    import asyncio

    from app.agente.ferramentas import Ambiente
    from app.agente.loop import responder_chat
    from app.agente.provedores.roteiro import Roteiro
    from app.config import Configuracao
    from app.contrato import ChatRequisicao, MensagemChat
    from app.motores.cliente import ClienteMotores
    from app.motores.dados_abertos import DadosAbertos

    async def rodar() -> ChatResposta:
        async with httpx.AsyncClient(timeout=60, trust_env=False) as http:
            # Sem contexto: a tela ainda não confirmou nada. As classificações valem na data do cenário.
            amb = Ambiente(
                ClienteMotores(http, MOTOR_RR_URL, MOTOR_SN_URL),
                DadosAbertos(http, MOTOR_RR_URL, MOTOR_SN_URL),
                contexto=None,
                data_sem_contexto=CEN.data,
            )
            req = ChatRequisicao(mensagens=[MensagemChat(papel="usuario", texto=FRASE_CHAT)])
            return await responder_chat(req, Roteiro(), Configuracao(modo="real"), amb)

    return asyncio.run(rodar())


# ---------------------------------------------------------------------------


def gravar(nome: str, conteudo: Any) -> None:
    def serializar(v: Any) -> Any:
        if hasattr(v, "model_dump"):
            return v.model_dump(mode="json", by_alias=True)
        if isinstance(v, dict):
            return {k: serializar(x) for k, x in v.items()}
        return v

    (PASTA_MOCKS / nome).write_text(
        json.dumps(serializar(conteudo), ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(f"  {nome}")


def main() -> None:
    PASTA_MOCKS.mkdir(exist_ok=True)
    with httpx.Client(timeout=30) as cli:
        motores = Motores(cli)
        notas = ler_notas()
        custos_por_nota = [custos_da_nota(motores, n) for n in notas]
        atuais: dict[str, Custo] = {}
        for custos in custos_por_nota:
            atuais.update(custos)
        antes_ultima: dict[str, Custo] = {}
        for custos in custos_por_nota[:-1]:
            antes_ultima.update(custos)

        car_trad, leit_trad = carrinho(motores, Regime.SIMPLES_TRADICIONAL, atuais)
        car_hib, _ = carrinho(motores, Regime.SIMPLES_HIBRIDO, atuais)
        importacao = importar(motores, notas[-1], antes_ultima, custos_por_nota[-1], leit_trad)
        busca = busca_ncm(motores)

        cerveja = DEMO.item("cerveja-lata")
        ref_preco = {r: preco_alvo(motores, r, cerveja, atuais[cerveja.id], cerveja.margemAlvoPct) for r in Regime}
        car, preco, expl = producao(
            atuais, {Regime.SIMPLES_TRADICIONAL: car_trad, Regime.SIMPLES_HIBRIDO: car_hib}, ref_preco
        )
        nfe, alertas, catalogo, painel, notas = producao_nfe(importacao)

        print("Mocks gravados em backend/app/mocks/:")
        gravar("carrinho.json", car)
        gravar("preco-alvo.json", preco)
        gravar("regime-comparar.json", regime_comparar(atuais))
        gravar("nfe-importar.json", nfe)
        gravar("alertas.json", alertas)
        gravar("catalogo.json", catalogo)
        gravar("contador-painel.json", painel)
        gravar("notas.json", notas)
        gravar("busca-ncm.json", busca)
        gravar("explicar.json", expl)
        gravar("erros.json", erros(motores))
        gravar("chat.json", chat())


if __name__ == "__main__":
    main()
