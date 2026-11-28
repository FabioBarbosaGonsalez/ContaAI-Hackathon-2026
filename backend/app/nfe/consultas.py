"""Leituras e ações sobre o estado (E4-02 e E4-04, ADR 0008; preço e classificação pela tela, ADR 0011).

Nenhuma chama os motores: a classificação chega aqui já conferida nos dados abertos pela rota.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from app.contrato import (
    Alerta,
    AplicarAlertaResposta,
    AplicarPrecoResposta,
    CatalogoResposta,
    CenarioEmpresa,
    ClassificacaoCandidata,
    ClienteB2BEstado,
    CorrigirClassificacaoResposta,
    EmpresaNoPainel,
    EmpresaResumo,
    FornecedorDoItem,
    ItemCatalogoEstado,
    ItemCompraMensal,
    LancamentoCustoSaida,
    NfeImportarResposta,
    NotaImportada,
    NotasResposta,
    Operacao,
    PainelContadorResposta,
    ReciboDaNotaResposta,
    Regime,
)
from app.dados_demo import ClienteB2B, ItemCatalogo
from app.empresa import item_base, operacao_da_empresa
from app.persistencia.repositorio import AlertaRegistro, EmpresaRegistro, LancamentoCusto, Repositorio, Sessao
from app.precificacao.lote import LOTE

AVISO_DEMO = "Dados fictícios de demonstração (P10): empresas, CNPJs, preços e custos não são reais."
# Empresa da conta (C3-B, ADR 0017): o P10 vale só para a demonstração; aqui os dados são os que a empresa cadastrou.
AVISO_EMPRESA_PROPRIA = (
    "Dados cadastrados pela sua empresa. Os resultados são simulações com as calculadoras oficiais: não são "
    "apuração fiscal e não substituem o contador."
)
HISTORICO_MAX = 10


class NaoEncontrado(Exception):
    def __init__(self, mensagem: str) -> None:
        super().__init__(mensagem)
        self.mensagem = mensagem


class Conflito(Exception):
    def __init__(self, mensagem: str) -> None:
        super().__init__(mensagem)
        self.mensagem = mensagem


def resumo_empresa(reg: EmpresaRegistro) -> EmpresaResumo:
    e = reg.empresa
    return EmpresaResumo(
        cnpj=e.cnpj,
        razaoSocial=e.razaoSocial,
        regimeAtual=Regime(e.regimeAtual),
        uf=e.uf,
        municipio=e.municipio,
        municipioNome=e.municipioNome,
        dataCenario=reg.cenario.data,
    )


def _lancamento(s: Sessao, cnpj: str, lanc: LancamentoCusto) -> LancamentoCustoSaida:
    return LancamentoCustoSaida(
        data=lanc.data,
        notaNumero=s.numero_da_nota(cnpj, lanc.nota_id),
        custoUnitario=lanc.custo_unitario,
        creditoCompraUnitario=lanc.credito_unitario,
        fonteCredito=lanc.fonte_credito,
    )


def _empresa(s: Sessao, cnpj: str) -> EmpresaRegistro:
    reg = s.empresa(cnpj)
    if reg is None:
        raise NaoEncontrado("Empresa não cadastrada.")
    return reg


def cenario_empresa(reg: EmpresaRegistro) -> CenarioEmpresa:
    """O mesmo cenário que as margens dos alertas usam (app.empresa.operacao_da_empresa)."""
    return CenarioEmpresa(
        descricao=reg.cenario.descricao,
        operacao=Operacao(**operacao_da_empresa(reg.empresa, reg.cenario)),
        cargaAtualPct=reg.cenario.cargaAtualPct,
    )


def cliente_estado(c: ClienteB2B) -> ClienteB2BEstado:
    return ClienteB2BEstado(
        cnpj=c.cliente.cnpj,
        nome=c.cliente.razaoSocial,
        regime=c.cliente.regime,
        uf=c.cliente.uf,
        municipio=c.cliente.municipio,
        compraMensalDescricao=c.compraMensal.descricao,
        compraMensal=[ItemCompraMensal(itemId=i.itemId, quantidade=i.quantidade) for i in c.compraMensal.itens],
    )


def _item_estado(s: Sessao, cnpj: str, cat: ItemCatalogo) -> ItemCatalogoEstado:
    historico = [_lancamento(s, cnpj, h) for h in s.historico_custo(cnpj, cat.id, HISTORICO_MAX)]
    return ItemCatalogoEstado(
        **item_base(cat).model_dump(),
        fornecedor=FornecedorDoItem(cnpj=cat.cnpjFornecedor, codigo=cat.codigoFornecedor),
        ncmDescricaoOficial=cat.ncmDescricaoOficial,
        classificacaoFonte=cat.classificacaoFonte,
        margemAlvoPct=cat.margemAlvoPct,
        precoVenda=s.preco_atual(cnpj, cat.id) or cat.precoVenda,
        custoAtual=historico[0] if historico else None,
        historicoCusto=historico,
    )


def catalogo(repo: Repositorio, cnpj: str, aviso: str = AVISO_DEMO) -> CatalogoResposta:
    with repo.leitura() as s:
        reg = _empresa(s, cnpj)
        itens = [_item_estado(s, cnpj, cat) for cat in s.itens(cnpj)]
        clientes = [cliente_estado(c) for c in s.clientes_b2b(cnpj)]
    return CatalogoResposta(
        empresa=resumo_empresa(reg),
        cenario=cenario_empresa(reg),
        clientesB2B=clientes,
        loteReferencia=int(LOTE),
        itens=itens,
        aviso=aviso,
    )


def notas(repo: Repositorio, cnpj: str, limite: int, aviso: str = AVISO_DEMO) -> NotasResposta:
    """As notas de compra da empresa, lidas do recibo de cada importação (o mesmo do POST /nfe/importar)."""
    with repo.leitura() as s:
        reg = _empresa(s, cnpj)
        listadas = s.notas(cnpj, limite)
    saida = []
    for n in listadas:
        recibo = NfeImportarResposta.model_validate_json(n.recibo_json)
        saida.append(
            NotaImportada(
                nota=recibo.nota,
                importadaEm=n.importada_em,
                itensCasados=len(recibo.itensCasados),
                itensSemPar=sum(1 for i in recibo.itensSemPar if i.itemCadastrado is None),
                alertasGerados=n.alertas_gerados,
                alertasAbertos=n.alertas_abertos,
            )
        )
    return NotasResposta(empresa=resumo_empresa(reg), notas=saida, aviso=aviso)


def recibo_da_nota(repo: Repositorio, cnpj: str, cnpj_emitente: str, serie: str, numero: str) -> ReciboDaNotaResposta:
    """O recibo gravado de uma nota da empresa (o de POST /nfe/importar), para cadastrar depois os itens sem par
    (C3b). Os alertas vêm com o estado atual: um preço aplicado depois da importação aparece aplicado."""
    with repo.leitura() as s:
        _empresa(s, cnpj)
        gravada = s.nota_gravada(cnpj, cnpj_emitente, serie, numero)
        if gravada is None:
            raise NaoEncontrado("Nota não encontrada para este fornecedor, com esta série e este número.")
        recibo = NfeImportarResposta.model_validate_json(gravada.recibo_json)
        atuais = [s.alerta(a.id) for a in recibo.alertas]
    alertas = [
        a.model_copy(update={"aplicadoEm": atual[1].aplicado_em}) if atual is not None else a
        for a, atual in zip(recibo.alertas, atuais, strict=True)
    ]
    return ReciboDaNotaResposta(importadaEm=gravada.importada_em, recibo=recibo.model_copy(update={"alertas": alertas}))


@dataclass(frozen=True)
class ItemDaEmpresa:
    """O item com o cenário da empresa e o preço atual, para quem precisa calcular (explicação, correção)."""

    empresa: EmpresaRegistro
    item: ItemCatalogo
    preco_atual: Decimal


def item_da_empresa(repo: Repositorio, cnpj: str, item_id: str) -> ItemDaEmpresa:
    with repo.leitura() as s:
        reg = _empresa(s, cnpj)
        cat = s.item(cnpj, item_id)
        if cat is None:
            raise NaoEncontrado("Item não encontrado no catálogo desta empresa.")
        return ItemDaEmpresa(reg, cat, s.preco_atual(cnpj, item_id) or cat.precoVenda)


def aplicar_preco(repo: Repositorio, cnpj: str, item_id: str, valor: Decimal, agora: datetime) -> AplicarPrecoResposta:
    """Lança o preço escolhido pelo usuário na tela (P3: só com o clique). Não fecha alertas."""
    with repo.escrita() as s:
        _empresa(s, cnpj)
        cat = s.item(cnpj, item_id)
        if cat is None:
            raise NaoEncontrado("Item não encontrado no catálogo desta empresa.")
        anterior = s.preco_atual(cnpj, item_id) or cat.precoVenda
        if anterior == valor:
            raise Conflito("Este já é o preço de venda atual do item.")
        s.lancar_preco(cnpj, item_id, valor, agora, "tela")
    return AplicarPrecoResposta(itemId=item_id, precoAnterior=anterior, precoNovo=valor, vigenteDesde=agora)


def fonte_da_correcao(escolhida: ClassificacaoCandidata, data_cenario: date, agora: datetime) -> str:
    """Texto montado só com dados oficiais (dados abertos do motor RR) e datas: nada digitado pelo usuário."""
    return (
        f"Corrigida na tela em {agora.date().isoformat()} (UTC), com a confirmação do usuário (P3): "
        f"{escolhida.cClassTrib} ({escolhida.descricao}), válida para a NCM nos dados abertos do motor RR em "
        f"{data_cenario.isoformat()}."
    )


def corrigir_classificacao(
    repo: Repositorio,
    cnpj: str,
    lido: ItemCatalogo,
    escolhida: ClassificacaoCandidata,
    agora: datetime,
) -> CorrigirClassificacaoResposta:
    """Grava a classificação escolhida, se o item ainda estiver como a rota o leu (checagem otimista)."""
    with repo.escrita() as s:
        reg = _empresa(s, cnpj)
        cat = s.item(cnpj, lido.id)
        if cat is None:
            raise NaoEncontrado("Item não encontrado no catálogo desta empresa.")
        if (cat.cst, cat.cClassTrib) != (lido.cst, lido.cClassTrib):
            raise Conflito("A classificação do item mudou enquanto a correção era conferida. Tente de novo.")
        if (cat.cst, cat.cClassTrib) == (escolhida.cst, escolhida.cClassTrib):
            raise Conflito("O item já tem esta classificação.")
        s.lancar_classificacao(
            cnpj,
            cat.id,
            escolhida.cst,
            escolhida.cClassTrib,
            fonte_da_correcao(escolhida, reg.cenario.data, agora),
            agora,
        )
        novo = s.item(cnpj, cat.id)
        if novo is None:
            raise NaoEncontrado("Item não encontrado no catálogo desta empresa.")
        estado = _item_estado(s, cnpj, novo)
    return CorrigirClassificacaoResposta(
        cstAnterior=cat.cst,
        cClassTribAnterior=cat.cClassTrib,
        classificacao=escolhida,
        item=estado,
        vigenteDesde=agora,
    )


def _saida(reg: AlertaRegistro) -> Alerta:
    return reg.alerta.model_copy(update={"aplicadoEm": reg.aplicado_em})


def alertas(repo: Repositorio, cnpj: str | None, abertos: bool | None) -> list[Alerta]:
    with repo.leitura() as s:
        if cnpj is not None:
            _empresa(s, cnpj)
        registros = s.alertas(cnpj)
    if abertos is not None:
        registros = [r for r in registros if (r.aplicado_em is None) == abertos]
    return [_saida(r) for r in registros]


def aplicar(
    repo: Repositorio, alerta_id: str, agora: datetime, cnpjs: frozenset[str] | None = None
) -> AplicarAlertaResposta:
    """Lança o preço sugerido como preço de venda e marca o alerta como aplicado (P3: só com o clique). Com
    `cnpjs`, um alerta de outra empresa responde como inexistente (ADR 0015)."""
    with repo.escrita() as s:
        achado = s.alerta(alerta_id)
        if achado is None or (cnpjs is not None and achado[0] not in cnpjs):
            raise NaoEncontrado("Alerta não encontrado.")
        cnpj, reg = achado
        if reg.aplicado_em is not None:
            raise Conflito("O preço deste alerta já foi aplicado.")
        if s.item(cnpj, reg.alerta.itemId) is None:
            raise Conflito("O item deste alerta foi arquivado e saiu do catálogo.")
        sugerido = reg.alerta.precoSugerido
        if sugerido is None:
            raise Conflito("Este alerta não tem preço sugerido (margem-alvo impossível).")
        anterior = s.preco_atual(cnpj, reg.alerta.itemId) or reg.alerta.precoAtual
        s.lancar_preco(cnpj, reg.alerta.itemId, sugerido, agora, "alerta", alerta_id)
        s.marcar_aplicado(alerta_id, agora)
        atualizado = AlertaRegistro(reg.alerta, reg.nota_id, agora)
    return AplicarAlertaResposta(alerta=_saida(atualizado), precoAnterior=anterior, precoNovo=sugerido)


def painel(repo: Repositorio, cnpjs: frozenset[str] | None = None, aviso: str = AVISO_DEMO) -> PainelContadorResposta:
    """Com `cnpjs`, só as empresas desse conjunto (ADR 0015)."""
    with repo.leitura() as s:
        linhas = []
        for reg in s.empresas():
            cnpj = reg.empresa.cnpj
            if cnpjs is not None and cnpj not in cnpjs:
                continue
            todos = s.alertas(cnpj)
            abertos = [a for a in todos if a.aplicado_em is None]
            linhas.append(
                EmpresaNoPainel(
                    empresa=resumo_empresa(reg),
                    alertasAbertos=len(abertos),
                    alertasAplicados=len(todos) - len(abertos),
                    ultimaNota=s.ultima_nota(cnpj),
                    alertaMaisRecente=_saida(abertos[0]) if abertos else None,
                )
            )
    linhas.sort(key=lambda e: (-e.alertasAbertos, e.empresa.razaoSocial))
    return PainelContadorResposta(empresas=linhas, aviso=aviso)
