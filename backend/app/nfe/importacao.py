"""POST /nfe/importar (E4-01 e E4-02, plano 11.3, ADR 0008).

Fluxo:
1. Lê o XML com o leitor seguro (`leitor.py`). O destinatário precisa ser uma empresa cadastrada:
   uma nota de outra empresa é recusada antes de qualquer gravação, e nada dela vai para o log.
2. A mesma nota (destinatário, emitente, série e número) com o mesmo arquivo devolve o recibo da
   primeira importação (`jaImportada`); com outro arquivo, é recusada (409).
3. Casa cada item pelo CNPJ do emitente + código do produto (cProd), conferindo NCM e unidade do
   cadastro. O que não casa vira pergunta ao usuário (`itensSemPar`, com o motivo).
4. Crédito da compra por unidade: do grupo IBSCBS do item (vCBS + vIBS ÷ qCom, ADR 0003); sem o
   grupo, do motor RR sobre o custo, na data da nota (hipótese de fornecedor no regime regular).
5. Margem antes e depois, no regime atual da empresa, ao preço atual e na data do cenário dela,
   pelo carrinho real (E1). Se a margem caiu e ficou abaixo do alvo, o alerta traz o preço-alvo
   (E1-03) com o custo novo.
6. Grava nota, lançamentos de custo, alertas e o recibo numa transação só.

As chamadas aos motores acontecem fora da transação de escrita, para não segurar o banco. Por isso a
gravação confere, já dentro da transação, se o custo e o preço de cada item ainda são os lidos no
passo 3 (checagem otimista). Se outra nota ou um preço aplicado entrou no meio, a importação é refeita
uma vez do começo; se mudar de novo, a resposta é 409 e nada é gravado.

O acesso ao SQLite é síncrono e roda numa thread (`asyncio.to_thread`), para não travar o servidor
enquanto a consulta acontece.
"""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal

from app.contrato import (
    Alerta,
    CarrinhoRequisicao,
    CausaSemPar,
    Emitente,
    ItemNotaCasado,
    ItemNotaSemPar,
    NfeImportarResposta,
    NotaResumo,
    Operacao,
    OrigemAlerta,
    PrecoAlvoRequisicao,
    Premissa,
    Regime,
)
from app.dados_demo import ItemCatalogo
from app.empresa import item_base, item_entrada, operacao_da_empresa, regime_atual
from app.motores.cliente import ClienteMotores
from app.motores.requisicoes import Linha
from app.nfe.leitor import ItemLido, NotaLida, ler_nfe
from app.persistencia.repositorio import EmpresaRegistro, FonteCredito, LancamentoCusto, Repositorio, Sessao
from app.precificacao.carrinho import aliquotas_premissa, calcular_carrinho, pct
from app.precificacao.lote import LOTE
from app.precificacao.preco_alvo import CalculoRecusado, calcular_preco_alvo

C4 = Decimal("0.0001")
Relogio = Callable[[], datetime]
TENTATIVAS = 2  # a primeira e uma nova, se o estado mudar no meio

PREMISSA_CREDITO_MOTOR = "Crédito da compra sem grupo IBSCBS na nota"
PREMISSA_MARGEM = Premissa(
    nome="Margem do alerta",
    valor="regime atual da empresa, preço de venda atual e data do cenário; lote de 100 unidades por item",
    fonte="Plano, seção 11.3, e ADR 0008. Os tributos vêm do motor; o alerta sai quando a margem cai e fica "
    "abaixo do alvo do item.",
)


def agora_utc() -> datetime:
    return datetime.now(UTC)


class NotaRecusada(Exception):
    """A nota é uma NF-e legível, mas não pode ser importada (destinatário, conflito). Vira 4xx."""

    def __init__(self, mensagem: str, status: int = 422) -> None:
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.status = status


class _EstadoMudou(Exception):
    """Outro lançamento de custo ou de preço de um item da nota entrou entre a leitura e a gravação."""


@dataclass
class _Casado:
    lido: ItemLido
    cat: ItemCatalogo
    anterior: LancamentoCusto | None
    atualiza: bool  # falso se a nota é mais antiga que o custo atual
    credito: Decimal | None = None
    fonte: FonteCredito | None = None


@dataclass
class _Leitura:
    """O que a importação precisa do banco, lido numa transação curta antes dos motores."""

    reg: EmpresaRegistro
    casados: list[_Casado]
    sem_par: list[ItemNotaSemPar]
    precos: dict[str, Decimal]


def _resumo(nota: NotaLida) -> NotaResumo:
    return NotaResumo(
        serie=nota.serie,
        numero=nota.numero,
        dataEmissao=nota.dataEmissao,
        emitente=Emitente(cnpj=nota.emitente.cnpj, nome=nota.emitente.nome),
        destinatario=Emitente(cnpj=nota.destinatario.cnpj, nome=nota.destinatario.nome),
        homologacao=nota.homologacao,
        temGrupoIbsCbs=nota.temGrupoIbsCbs,
    )


def _casar(s: Sessao, nota: NotaLida) -> tuple[list[_Casado], list[ItemNotaSemPar]]:
    cnpj = nota.destinatario.cnpj
    casados: list[_Casado] = []
    sem_par: list[ItemNotaSemPar] = []
    vistos: set[str] = set()
    for item in nota.itens:
        cat = s.item_por_codigo(cnpj, nota.emitente.cnpj, item.cProd)
        monofasico = item.ibscbs is not None and item.ibscbs.monofasico
        causa: CausaSemPar | None = None
        motivo = None
        if cat is None and monofasico:
            causa, motivo = "monofasico", MOTIVO_MONOFASICO
        elif cat is None:
            causa, motivo = "semCadastro", "Código do produto deste fornecedor sem cadastro no catálogo."
        elif cat.id in vistos:
            causa, motivo = "repetido", "O mesmo produto aparece mais de uma vez na nota: confira com o fornecedor."
        elif cat.ncm != item.ncm:
            causa, motivo = "ncm", f"NCM da nota diferente da do cadastro ({cat.ncm}): confira a classificação."
        elif cat.unidade != item.uCom.upper():
            causa = "unidade"
            motivo = f"Unidade da nota diferente da do cadastro ({cat.unidade}): sem conversão automática."
        elif monofasico:
            causa, motivo = "monofasico", MOTIVO_MONOFASICO
        if causa is not None or cat is None:
            sem_par.append(_sem_par(item, causa, motivo))
            continue
        vistos.add(cat.id)
        anterior = s.custo_atual(cnpj, cat.id)
        casados.append(_Casado(item, cat, anterior, anterior is None or anterior.data <= nota.dataEmissao))
    return casados, sem_par


MOTIVO_MONOFASICO = "Tributação monofásica (gIBSCBSMono): ainda não suportada."


def _sem_par(item: ItemLido, causa: CausaSemPar | None, motivo: str | None) -> ItemNotaSemPar:
    """A linha sem par com o que o cadastro a partir da nota precisa (C3b): o custo e o crédito da própria nota."""
    credito = None
    if item.ibscbs is not None and not item.ibscbs.monofasico:
        credito = (item.ibscbs.credito / item.qCom).quantize(C4, ROUND_HALF_UP)
    return ItemNotaSemPar(
        nItem=item.nItem,
        codigoFornecedor=item.cProd,
        ncm=item.ncm,
        descricaoNota=item.xProd,
        motivo=motivo,
        causa=causa,
        unidade=item.uCom.upper(),
        quantidade=item.qCom,
        custoUnitario=item.vUnCom,
        valorTotal=item.vProd,
        creditoCompraUnitario=credito,
    )


async def _creditos(
    motores: ClienteMotores, reg: EmpresaRegistro, nota: NotaLida, casados: list[_Casado]
) -> list[ItemCatalogo]:
    """Preenche o crédito por unidade. Devolve os itens cujo crédito veio do motor RR (premissa)."""
    pelo_motor = []
    for c in casados:
        if c.lido.ibscbs is not None:
            c.credito, c.fonte = (c.lido.ibscbs.credito / c.lido.qCom).quantize(C4, ROUND_HALF_UP), "nfe"
        else:
            pelo_motor.append(c)
    if not pelo_motor:
        return []
    creditos = await creditos_pelo_motor(
        motores, reg, nota.dataEmissao.date(), [(c.cat, c.lido.qCom, c.lido.vProd) for c in pelo_motor]
    )
    for c, credito in zip(pelo_motor, creditos, strict=True):
        if credito is not None:
            c.credito, c.fonte = credito, "motor"
    return [c.cat for c in pelo_motor]


async def creditos_pelo_motor(
    motores: ClienteMotores, reg: EmpresaRegistro, data: date, linhas: list[tuple[ItemCatalogo, Decimal, Decimal]]
) -> list[Decimal | None]:
    """Crédito por unidade de cada linha (item, qCom, vProd) sem o grupo IBSCBS na nota: o motor RR sobre o custo,
    na data da nota, com as alíquotas do cenário da empresa (hipótese de fornecedor no regime regular). Vazio quando
    o motor não calcula a linha. Também serve ao item cadastrado a partir da nota (C3b)."""
    op = Operacao(**operacao_da_empresa(reg.empresa, reg.cenario, data))
    calculo = await motores.regime_regular(
        [Linha(item_base(cat), qcom, vprod) for cat, qcom, vprod in linhas],
        data,
        reg.empresa.uf,
        reg.empresa.municipio,
        aliquotas_premissa(op),
    )
    return [
        (lei.tributo_cbs_ibs() / qcom).quantize(C4, ROUND_HALF_UP) if lei.calculado else None
        for (_, qcom, _), lei in zip(linhas, calculo.itens, strict=True)
    ]


async def margens(
    motores: ClienteMotores,
    reg: EmpresaRegistro,
    linhas: list[tuple[ItemCatalogo, Decimal, Decimal, Decimal | None]],
) -> dict[str, Decimal | None]:
    """Margem (%) de cada item (catálogo, preço, custo, crédito por unidade) pelo carrinho real.

    Um lote de 100 unidades por item, como no preço-alvo (LOTE), para reduzir o arredondamento.
    No híbrido o crédito não entra no custo (ADR 0004); sem crédito, o carrinho calcula no motor RR.
    """
    if not linhas:
        return {}
    regime = regime_atual(reg.empresa)
    req = CarrinhoRequisicao(
        **operacao_da_empresa(reg.empresa, reg.cenario),
        regime=regime,
        itens=[
            item_entrada(cat, LOTE, preco, custo, credito if regime == Regime.SIMPLES_TRADICIONAL else None)
            for cat, preco, custo, credito in linhas
        ],
    )
    resposta = await calcular_carrinho(req, motores)
    return {i.id: i.margemPct for i in resposta.itens}


def id_alerta(cnpj: str, nota: NotaLida, item_id: str) -> str:
    chave = f"{cnpj}|{nota.emitente.cnpj}|{nota.serie}|{nota.numero}|{item_id}"
    return "alerta-" + hashlib.sha256(chave.encode()).hexdigest()[:16]


async def _alerta(
    motores: ClienteMotores,
    reg: EmpresaRegistro,
    nota: NotaLida,
    c: _Casado,
    preco: Decimal,
    antes: Decimal,
    depois: Decimal,
    agora: datetime,
) -> Alerta:
    regime = regime_atual(reg.empresa)
    req = PrecoAlvoRequisicao(
        **operacao_da_empresa(reg.empresa, reg.cenario),
        regime=regime,
        item=item_base(c.cat),
        custoUnitario=c.lido.vUnCom,
        creditoCompraUnitario=c.credito if regime == Regime.SIMPLES_TRADICIONAL else None,
        margemAlvoPct=c.cat.margemAlvoPct,
    )
    sugerido, motivo, lista, eh_simulado, aviso = None, None, [], True, None
    try:
        alvo = await calcular_preco_alvo(req, motores)
        sugerido, lista, eh_simulado, aviso = alvo.valorUnitario, alvo.premissas, alvo.simulado, alvo.avisoSimulacao
    except CalculoRecusado as e:
        motivo = e.detalhe
    if c.fonte == "motor":
        lista = [*lista, _premissa_credito_motor([c.cat])]
    return Alerta(
        id=id_alerta(reg.empresa.cnpj, nota, c.cat.id),
        cnpj=reg.empresa.cnpj,
        itemId=c.cat.id,
        descricaoItem=c.cat.descricao,
        regime=regime,
        margemAntesPct=antes,
        margemDepoisPct=depois,
        margemAlvoPct=c.cat.margemAlvoPct,
        custoAnterior=c.anterior.custo_unitario if c.anterior else None,
        custoNovo=c.lido.vUnCom,
        precoAtual=preco,
        precoSugerido=sugerido,
        motivoSemPreco=motivo,
        origem=OrigemAlerta(tipo="nfe", numero=nota.numero, dataEmissao=nota.dataEmissao, emitente=nota.emitente.nome),
        criadoEm=agora,
        simulado=eh_simulado,
        avisoSimulacao=aviso,
        premissas=[*lista, PREMISSA_MARGEM],
    )


def _premissa_credito_motor(itens: list[ItemCatalogo]) -> Premissa:
    return Premissa(
        nome=PREMISSA_CREDITO_MOTOR,
        valor="calculado no motor RR sobre o custo, na data da nota: " + ", ".join(i.descricao for i in itens),
        fonte="Hipótese de fornecedor no regime regular (plano, E3), com as alíquotas do cenário da empresa.",
    )


def _premissas_da_importacao(reg: EmpresaRegistro, nota: NotaLida, pelo_motor: list[ItemCatalogo]) -> list[Premissa]:
    lista = []
    if pelo_motor:
        op = Operacao(**operacao_da_empresa(reg.empresa, reg.cenario, nota.dataEmissao.date()))
        if op.aliquotasNominais is not None:
            al = op.aliquotasNominais
            lista.append(
                Premissa(
                    nome=f"Alíquotas nominais de {op.data.year} (crédito das compras)",
                    valor=f"CBS {al.cbs}% · IBS estadual {al.ibsEstadual}% · IBS municipal {al.ibsMunicipal}%",
                    fonte=f"{al.fonte}. Não são alíquotas oficiais (P6).",
                )
            )
        lista.append(_premissa_credito_motor(pelo_motor))
    if nota.homologacao:
        lista.append(
            Premissa(
                nome="Nota de homologação",
                valor="tpAmb 2: sem valor fiscal",
                fonte="Campo ide/tpAmb da própria nota. As notas da demonstração são fictícias (data/demo).",
            )
        )
    return lista


DESTINATARIO_DESCONHECIDO = "O destinatário da nota não é uma empresa cadastrada no ContaAI. Nada foi gravado."


def _ler(repo: Repositorio, nota: NotaLida, sha: str) -> _Leitura | NfeImportarResposta:
    with repo.leitura() as s:
        reg = s.empresa(nota.destinatario.cnpj)
        if reg is None:
            raise NotaRecusada(DESTINATARIO_DESCONHECIDO, status=422)
        existente = s.nota(nota.destinatario.cnpj, nota.emitente.cnpj, nota.serie, nota.numero)
        if existente is not None:
            return _recibo_existente(existente.sha256, existente.recibo_json, sha)
        casados, sem_par = _casar(s, nota)
        precos = {c.cat.id: s.preco_atual(reg.empresa.cnpj, c.cat.id) or c.cat.precoVenda for c in casados}
    return _Leitura(reg, casados, sem_par, precos)


def _recibo_existente(sha_gravado: str, recibo_json: str, sha: str) -> NfeImportarResposta:
    if sha_gravado != sha:
        raise NotaRecusada(
            "Esta nota (mesmo emitente, série e número) já foi importada com outro conteúdo. Nada foi gravado.",
            status=409,
        )
    return NfeImportarResposta.model_validate_json(recibo_json).model_copy(update={"jaImportada": True})


async def importar_nota(
    conteudo: bytes,
    repo: Repositorio,
    motores: ClienteMotores,
    relogio: Relogio = agora_utc,
    cnpjs: frozenset[str] | None = None,
) -> NfeImportarResposta:
    """Com `cnpjs`, só entra a nota de uma empresa desse conjunto; as outras recebem a mesma recusa de um
    destinatário que não existe (ADR 0015)."""
    nota = ler_nfe(conteudo)
    if cnpjs is not None and nota.destinatario.cnpj not in cnpjs:
        raise NotaRecusada(DESTINATARIO_DESCONHECIDO, status=422)
    sha = hashlib.sha256(conteudo).hexdigest()
    for _ in range(TENTATIVAS):
        try:
            return await _importar(nota, sha, repo, motores, relogio)
        except _EstadoMudou:
            continue
    raise NotaRecusada(
        "O custo ou o preço de um item desta nota mudou durante a importação (outra nota ou um preço aplicado ao "
        "mesmo tempo). Nada foi gravado: envie a nota de novo.",
        status=409,
    )


async def _importar(
    nota: NotaLida, sha: str, repo: Repositorio, motores: ClienteMotores, relogio: Relogio
) -> NfeImportarResposta:
    leitura = await asyncio.to_thread(_ler, repo, nota, sha)
    if isinstance(leitura, NfeImportarResposta):
        return leitura
    reg, casados = leitura.reg, leitura.casados
    agora = relogio()

    pelo_motor = await _creditos(motores, reg, nota, casados)

    # Margens só dos itens que mudam de custo e já tinham custo (sem histórico não há "antes").
    comparaveis = [c for c in casados if c.atualiza and c.anterior is not None]
    antes = await margens(
        motores,
        reg,
        [
            (c.cat, leitura.precos[c.cat.id], anterior.custo_unitario, anterior.credito_unitario)
            for c in comparaveis
            if (anterior := c.anterior) is not None
        ],
    )
    depois = await margens(
        motores, reg, [(c.cat, leitura.precos[c.cat.id], c.lido.vUnCom, c.credito) for c in comparaveis]
    )
    alertas = []
    for c in comparaveis:
        m_antes, m_depois = antes.get(c.cat.id), depois.get(c.cat.id)
        if m_antes is None or m_depois is None:
            continue
        if m_depois < c.cat.margemAlvoPct and m_depois < m_antes:
            alertas.append(await _alerta(motores, reg, nota, c, leitura.precos[c.cat.id], m_antes, m_depois, agora))

    resposta = NfeImportarResposta(
        nota=_resumo(nota),
        itensCasados=[
            ItemNotaCasado(
                nItem=c.lido.nItem,
                itemId=c.cat.id,
                codigoFornecedor=c.lido.cProd,
                ncm=c.lido.ncm,
                descricaoNota=c.lido.xProd,
                quantidade=c.lido.qCom,
                custoAnterior=c.anterior.custo_unitario if c.anterior else None,
                custoNovo=c.lido.vUnCom,
                variacaoPct=pct(c.lido.vUnCom - c.anterior.custo_unitario, c.anterior.custo_unitario)
                if c.anterior and c.anterior.custo_unitario > 0
                else None,
                atualizaCusto=c.atualiza,
                creditoCompraUnitario=c.credito,
                fonteCredito=c.fonte,
            )
            for c in casados
        ],
        itensSemPar=leitura.sem_par,
        alertas=alertas,
        simulado=bool(pelo_motor) or bool(alertas),
        avisoSimulacao=next((a.avisoSimulacao for a in alertas if a.avisoSimulacao), None)
        or (
            f"Simulação de {nota.dataEmissao.year}: crédito das compras com alíquotas assumidas" if pelo_motor else None
        ),
        premissas=_premissas_da_importacao(reg, nota, pelo_motor),
    )
    return await asyncio.to_thread(_gravar, repo, leitura, nota, sha, agora, resposta)


def _conferir_estado(s: Sessao, cnpj: str, leitura: _Leitura) -> None:
    """Checagem otimista: o custo atual e o preço atual de cada item ainda são os da leitura."""
    for c in leitura.casados:
        atual = s.custo_atual(cnpj, c.cat.id)
        if (atual.id if atual else None) != (c.anterior.id if c.anterior else None):
            raise _EstadoMudou
        if (s.preco_atual(cnpj, c.cat.id) or c.cat.precoVenda) != leitura.precos[c.cat.id]:
            raise _EstadoMudou


def _gravar(
    repo: Repositorio,
    leitura: _Leitura,
    nota: NotaLida,
    sha: str,
    agora: datetime,
    resposta: NfeImportarResposta,
) -> NfeImportarResposta:
    """Uma transação de escrita (BEGIN IMMEDIATE): as conferências e as gravações não se cruzam com outra."""
    cnpj = leitura.reg.empresa.cnpj
    with repo.escrita() as s:
        # A mesma nota pode ter sido gravada por outra importação enquanto esta chamava os motores.
        existente = s.nota(cnpj, nota.emitente.cnpj, nota.serie, nota.numero)
        if existente is not None:
            return _recibo_existente(existente.sha256, existente.recibo_json, sha)
        _conferir_estado(s, cnpj, leitura)
        nota_id = s.inserir_nota(cnpj, nota.emitente.cnpj, nota.serie, nota.numero, nota.dataEmissao, sha, agora)
        for c in leitura.casados:
            s.lancar_custo(
                cnpj,
                LancamentoCusto(
                    item_id=c.cat.id,
                    nota_id=nota_id,
                    data=nota.dataEmissao,
                    quantidade=c.lido.qCom,
                    custo_unitario=c.lido.vUnCom,
                    credito_unitario=c.credito,
                    fonte_credito=c.fonte,
                ),
            )
        for alerta in resposta.alertas:
            s.inserir_alerta(cnpj, alerta, nota_id)
        s.gravar_recibo(nota_id, resposta.model_dump_json())
    return resposta
