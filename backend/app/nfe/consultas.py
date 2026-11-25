"""Leituras e a ação de aplicar preço sobre o estado (E4-02 e E4-04, ADR 0008). Nenhuma chama os motores."""

from __future__ import annotations

from datetime import datetime

from app.contrato import (
    Alerta,
    AplicarAlertaResposta,
    CatalogoResposta,
    EmpresaNoPainel,
    EmpresaResumo,
    ItemCatalogoEstado,
    LancamentoCustoSaida,
    PainelContadorResposta,
    Regime,
)
from app.empresa import item_base
from app.persistencia.repositorio import AlertaRegistro, EmpresaRegistro, LancamentoCusto, Repositorio, Sessao

AVISO_DEMO = "Dados fictícios de demonstração (P10): empresas, CNPJs, preços e custos não são reais."
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


def catalogo(repo: Repositorio, cnpj: str) -> CatalogoResposta:
    with repo.leitura() as s:
        reg = _empresa(s, cnpj)
        itens = []
        for cat in s.itens(cnpj):
            historico = [_lancamento(s, cnpj, h) for h in s.historico_custo(cnpj, cat.id, HISTORICO_MAX)]
            itens.append(
                ItemCatalogoEstado(
                    **item_base(cat).model_dump(),
                    ncmDescricaoOficial=cat.ncmDescricaoOficial,
                    classificacaoFonte=cat.classificacaoFonte,
                    margemAlvoPct=cat.margemAlvoPct,
                    precoVenda=s.preco_atual(cnpj, cat.id) or cat.precoVenda,
                    custoAtual=historico[0] if historico else None,
                    historicoCusto=historico,
                )
            )
    return CatalogoResposta(empresa=resumo_empresa(reg), itens=itens, aviso=AVISO_DEMO)


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


def aplicar(repo: Repositorio, alerta_id: str, agora: datetime) -> AplicarAlertaResposta:
    """Lança o preço sugerido como preço de venda e marca o alerta como aplicado (P3: só com o clique)."""
    with repo.escrita() as s:
        achado = s.alerta(alerta_id)
        if achado is None:
            raise NaoEncontrado("Alerta não encontrado.")
        cnpj, reg = achado
        if reg.aplicado_em is not None:
            raise Conflito("O preço deste alerta já foi aplicado.")
        sugerido = reg.alerta.precoSugerido
        if sugerido is None:
            raise Conflito("Este alerta não tem preço sugerido (margem-alvo impossível).")
        anterior = s.preco_atual(cnpj, reg.alerta.itemId) or reg.alerta.precoAtual
        s.lancar_preco(cnpj, reg.alerta.itemId, sugerido, agora, "alerta", alerta_id)
        s.marcar_aplicado(alerta_id, agora)
        atualizado = AlertaRegistro(reg.alerta, reg.nota_id, agora)
    return AplicarAlertaResposta(alerta=_saida(atualizado), precoAnterior=anterior, precoNovo=sugerido)


def painel(repo: Repositorio) -> PainelContadorResposta:
    with repo.leitura() as s:
        linhas = []
        for reg in s.empresas():
            cnpj = reg.empresa.cnpj
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
    return PainelContadorResposta(empresas=linhas, aviso=AVISO_DEMO)
