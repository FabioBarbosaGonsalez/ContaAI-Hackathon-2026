"""Gera os mocks da API (backend/app/mocks/*.json) a partir dos motores em execução (E0-05).

"Mocks servidos a partir das respostas gravadas" (plano, E0): todo valor de tributo vem dos motores,
chamados aqui com os dados de demonstração (data/demo). Margens, preço-alvo e comparação de regimes
usam as fórmulas do ADR 0003 sobre esses valores, só com soma, subtração e divisão (P1).

É a implementação de referência que as etapas E1 a E4 substituem pelo código de produção, com testes.

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
    ItemCalculado,
    ItemNotaCasado,
    LadoHibrido,
    LadoTradicional,
    Motor,
    NfeImportarResposta,
    NotaResumo,
    OrigemAlerta,
    PrecoAlvoResposta,
    Premissa,
    Regime,
    RegimeCompararResposta,
    Totais,
    Tributos,
)
from app.dados_demo import PASTA_DEMO, ItemCatalogo, carregar_cliente_b2b, carregar_distribuidora  # noqa: E402
from app.motores.conversao import LeituraItem, ler_resposta, versoes  # noqa: E402
from app.motores.requisicoes import AliquotasPremissa, DasPremissa, Linha, operacao_rr, operacao_sn  # noqa: E402

MOTOR_RR_URL = os.environ.get("MOTOR_RR_URL", "http://127.0.0.1:8080/api")
MOTOR_SN_URL = os.environ.get("MOTOR_SN_URL", "http://127.0.0.1:8082/api")
# CONTAAI_SAIDA_MOCKS permite regravar em outra pasta (o teste de reprodutibilidade usa isso).
PASTA_MOCKS = Path(os.environ.get("CONTAAI_SAIDA_MOCKS") or Path(__file__).resolve().parents[1] / "app" / "mocks")
NS = {"n": "http://www.portalfiscal.inf.br/nfe"}

LOTE = Decimal(100)  # quantidade por chamada: reduz o efeito do arredondamento ao centavo dos motores
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
    for caminho in sorted((PASTA_DEMO / "notas").glob("*.xml")):
        inf = ET.parse(caminho).getroot().find("n:infNFe", NS)
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
# POST /regime/comparar (mesmo preço total ao cliente nos dois regimes)


def regime_comparar(motores: Motores, custos: dict[str, Custo]) -> RegimeCompararResposta:
    venda = [(DEMO.item(i.itemId), i.quantidade) for i in CLIENTE.compraMensal.itens]
    valores = [(qtd * cat.precoVenda).quantize(C2) for cat, qtd in venda]
    total = sum(valores, Decimal("0.00"))

    trad = motores.sn([Linha(cat, qtd, v) for (cat, qtd), v in zip(venda, valores, strict=True)], CEN.data)
    tributo_trad = sum((lei.tributo_cbs_ibs() for lei in trad), Decimal("0.00"))

    def debitos(bases: list[Decimal]) -> list[Decimal]:
        leis = motores.rr([Linha(cat, qtd, b) for (cat, qtd), b in zip(venda, bases, strict=True)], CEN.data)
        return [lei.tributo_cbs_ibs() + (lei.tributos.impostoSeletivo or Decimal(0)) for lei in leis]

    d1, d2 = debitos(valores), debitos([2 * v for v in valores])
    bases = []
    for v, t1, t2 in zip(valores, d1, d2, strict=True):
        beta = (t2 - t1) / v
        alfa = t1 - beta * v
        bases.append(((v - alfa) / (1 + beta)).quantize(C2, ROUND_HALF_UP))  # b + T(b) = preço total
    d_final = debitos(bases)
    debito = sum(d_final, Decimal("0.00"))
    preco_hib = sum(bases, Decimal("0.00")) + debito
    credito_compras = sum(
        ((qtd * custos[cat.id].creditoUnitario).quantize(C2, ROUND_HALF_UP) for cat, qtd in venda), Decimal("0.00")
    )
    tributo_liquido = debito - credito_compras
    return RegimeCompararResposta(
        criterio="mesmo_preco_total_ao_cliente",
        cliente=ClienteB2B(nome=CLIENTE.cliente.razaoSocial, regime="regime_regular"),
        valorVenda=total,
        tradicional=LadoTradicional(
            precoCliente=total,
            tributo=tributo_trad,
            creditoCliente=tributo_trad,
            custoLiquidoCliente=total - tributo_trad,
        ),
        hibrido=LadoHibrido(
            precoCliente=preco_hib,
            valorProdutos=sum(bases, Decimal("0.00")),
            debito=debito,
            creditoCompras=credito_compras,
            tributoLiquido=tributo_liquido,
            creditoCliente=debito,
            custoLiquidoCliente=preco_hib - debito,
        ),
        diferencaCaixa=tributo_trad - tributo_liquido,
        fonteTradicional="motor",
        simplificacoes=[
            "O restante do DAS (IRPJ, CSLL, CPP etc.) é tratado como igual nos dois regimes; só a parcela de CBS/IBS muda (plano, 11.2).",
            "Mesmo preço total ao cliente nos dois regimes: no híbrido, a base é o valor que somado à CBS/IBS dá esse "
            "preço (pode diferir em centavos pelo arredondamento ao centavo de cada linha).",
            "Crédito das compras proporcional às quantidades vendidas, pelo crédito por unidade da última nota de cada item.",
            "No Simples tradicional o crédito das compras não é aproveitado (LC 214/2025, art. 47, §9º, I).",
            "No Simples tradicional o arroz paga as alíquotas efetivas do anexo, sem a redução da cesta básica "
            "(premissa da equipe; validar com o contador). O resultado da comparação depende dela.",
            "ICMS fora das contas.",
        ],
        simulado=True,
        avisoSimulacao=f"{aviso_simulacao(Regime.SIMPLES_HIBRIDO)} e alíquotas efetivas do Simples assumidas",
        premissas=premissas(Regime.SIMPLES_TRADICIONAL),
        versoes=versoes(motores.headers_rr, motores.headers_sn),
    )


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
                )
            )
    return NfeImportarResposta(
        nota=NotaResumo(
            numero=nota.numero, dataEmissao=nota.dhEmi, emitente=nota.emitente, temGrupoIbsCbs=nota.tem_grupo
        ),
        itensCasados=casados,
        itensSemPar=[],
        alertas=alertas,
    )


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
        car_hib, leit_hib = carrinho(motores, Regime.SIMPLES_HIBRIDO, atuais)
        cerveja = DEMO.item("cerveja-lata")
        importacao = importar(motores, notas[-1], antes_ultima, custos_por_nota[-1], leit_trad)
        busca = busca_ncm(motores)

        print("Mocks gravados em backend/app/mocks/:")
        gravar(
            "carrinho.json",
            {r.value: c for r, c in ((Regime.SIMPLES_TRADICIONAL, car_trad), (Regime.SIMPLES_HIBRIDO, car_hib))},
        )
        gravar(
            "preco-alvo.json",
            {r.value: preco_alvo(motores, r, cerveja, atuais[cerveja.id], cerveja.margemAlvoPct) for r in Regime},
        )
        gravar("regime-comparar.json", regime_comparar(motores, atuais))
        gravar("nfe-importar.json", importacao)
        gravar("alertas.json", AlertasResposta(alertas=importacao.alertas))
        gravar("busca-ncm.json", busca)
        gravar(
            "explicar.json",
            explicar(motores, {Regime.SIMPLES_TRADICIONAL: leit_trad, Regime.SIMPLES_HIBRIDO: leit_hib}),
        )
        gravar("erros.json", erros(motores))
        gravar("chat.json", chat())


if __name__ == "__main__":
    main()
