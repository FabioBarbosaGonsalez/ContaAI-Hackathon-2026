"""Empresa própria (C3-B, ADR 0017): referências oficiais, cadastro, configurações, catálogo e clientes B2B
editáveis.

Tudo o que é dado oficial vem dos motores, na versão fixada (P5), e nunca da tela:
- UF e município (código do IBGE e nome): dados abertos do motor RR;
- atividade do Simples e o anexo dela: motor SN, com a admissibilidade na NF-e (modelo 55);
- NCM (descrição oficial e Imposto Seletivo) e as classificações válidas: dados abertos do motor RR (P3).

O cenário da empresa própria é o mesmo da demonstração (data/demo), rotulado como simulação (decisão 2 da C3). As
alíquotas efetivas do Simples da própria empresa entram nas configurações (P8).
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from app.classificacao.candidatos import classificacoes_da_ncm
from app.cnpj import cnpj_valido
from app.contas.servico import Contas
from app.contrato import (
    AtividadeDaEmpresa,
    AtividadeSimples,
    AtividadesResposta,
    ClienteAlteracaoRequisicao,
    ClienteExcluidoResposta,
    ClienteNovoRequisicao,
    ClienteQueCompra,
    ClienteResposta,
    EmpresaCadastroRequisicao,
    EmpresaConfiguracaoRequisicao,
    EmpresaResposta,
    ItemAlteracaoRequisicao,
    ItemArquivadoResposta,
    ItemDaCompraMensal,
    ItemNovoRequisicao,
    ItemResposta,
    MunicipioReferencia,
    MunicipiosResposta,
    UfReferencia,
    UfsResposta,
)
from app.dados_demo import AtividadeSimples as AtividadeDoCadastro
from app.dados_demo import Cenario, Cliente, ClienteB2B, CompraMensal, Empresa, ItemCatalogo, carregar_distribuidora
from app.dados_demo import ItemCompraMensal as ItemDaCompraGravado
from app.motores.dados_abertos import DA, ROTA_ATIVIDADES_SN, DadosAbertos
from app.nfe.consultas import (
    Conflito,
    NaoEncontrado,
    _empresa,
    _item_estado,
    cenario_empresa,
    cliente_estado,
    resumo_empresa,
)
from app.persistencia.repositorio import EmpresaRegistro, Repositorio, Sessao

# Tetos de produto, não regra fiscal: só evitam que uma conta cresça sem limite no disco do servidor.
EMPRESAS_POR_ORGANIZACAO = 10
ITENS_POR_EMPRESA = 500
CLIENTES_POR_EMPRESA = 50
TP_DOC_NFE = "55"
ANEXOS = ("I", "II", "III", "IV", "V")
MENSAGEM_CNPJ = "CNPJ inválido: confira os dígitos verificadores."
# Os dados abertos do motor RR trazem "EX" (EXTERIOR, município 9999999), o código das operações com o exterior. Não
# é uma UF onde a empresa fica: sai da lista do cadastro.
UF_EXTERIOR = "EX"


class Recusado(Exception):
    """A entrada segue o contrato, mas não passa numa regra que depende dos dados (422)."""

    def __init__(self, mensagem: str) -> None:
        super().__init__(mensagem)
        self.mensagem = mensagem


class ItemEmUso(Conflito):
    """O item está na compra mensal de clientes B2B (409 /problemas/item-em-uso). Sem esta trava, a venda desses
    clientes apontaria para um item fora do catálogo e a comparação de regimes deles ficaria sem venda."""

    def __init__(self, clientes: list[ClienteQueCompra]) -> None:
        super().__init__(
            "O item está na compra mensal de clientes desta empresa. Tire-o da compra deles antes de arquivar."
        )
        self.clientes = clientes


@dataclass(frozen=True)
class Versoes:
    rr: str
    sn: str


# -- referências ------------------------------------------------------------------------------------------


def cenario_padrao(pasta_demo: Path) -> Cenario:
    """O cenário de data/demo (data, alíquotas e premissas rotuladas), como simulação da empresa própria."""
    return carregar_distribuidora(pasta_demo).cenario.model_copy(
        update={"origem": "empresa_propria", "cargaAtualPct": None}
    )


def _fonte_rr(versao: str, rota: str) -> str:
    return f"Dados abertos do motor RR {versao} (GET {DA}{rota})."


def _fonte_atividades(data: date, versao: str) -> str:
    return f"GET {ROTA_ATIVIDADES_SN}?data={data.isoformat()}&tpDoc={TP_DOC_NFE} (motor SN {versao})"


async def ufs(da: DadosAbertos, versoes: Versoes) -> UfsResposta:
    lista = sorted((u for u in await da.ufs() if u.sigla != UF_EXTERIOR), key=lambda u: u.sigla)
    return UfsResposta(
        ufs=[UfReferencia(sigla=u.sigla, nome=u.nome, codigo=u.codigo) for u in lista],
        fonte=_fonte_rr(versoes.rr, "/ufs"),
    )


async def municipios(da: DadosAbertos, uf: str, versoes: Versoes) -> MunicipiosResposta:
    if uf == UF_EXTERIOR or uf not in {u.sigla for u in await da.ufs()}:
        raise NaoEncontrado("UF não encontrada nos dados abertos do motor RR.")
    lista = await da.municipios(uf)
    return MunicipiosResposta(
        uf=uf,
        municipios=[MunicipioReferencia(codigo=m.codigo, nome=m.nome) for m in lista],
        fonte=_fonte_rr(versoes.rr, f"/ufs/municipios?siglaUf={uf}"),
    )


async def atividades(da: DadosAbertos, data: date, versoes: Versoes) -> AtividadesResposta:
    """As atividades que o ContaAI calcula: admissíveis na NF-e e disponíveis na data, com anexo e sem fator R
    (o fator R depende da folha de salários, que o ContaAI não recebe)."""
    validas = [
        AtividadeSimples(cAtivSN=a.codigo, descricao=a.descricao, anexo=a.anexoSemFatorR)
        for a in await da.atividades_simples(data, TP_DOC_NFE)
        if a.disponivel and a.admissivelNoDocumento and not a.sujeitaFatorR and a.anexoSemFatorR in ANEXOS
    ]
    return AtividadesResposta(data=data, atividades=validas, fonte=_fonte_atividades(data, versoes.sn))


# -- empresa ----------------------------------------------------------------------------------------------


async def _local(da: DadosAbertos, uf: str, municipio: int) -> str:
    """O nome oficial do município, conferido na UF."""
    if uf == UF_EXTERIOR or uf not in {u.sigla for u in await da.ufs()}:
        raise Recusado("UF não encontrada nos dados abertos do motor RR.")
    achado = next((m for m in await da.municipios(uf) if m.codigo == municipio), None)
    if achado is None:
        raise Recusado("Município não encontrado nesta UF nos dados abertos do motor RR.")
    return achado.nome


async def _atividade(da: DadosAbertos, data: date, codigo: str, versoes: Versoes) -> AtividadeDoCadastro:
    lista = await atividades(da, data, versoes)
    achada = next((a for a in lista.atividades if a.cAtivSN == codigo), None)
    if achada is None:
        raise Recusado(
            "Atividade do Simples que o ContaAI não calcula: use uma das admissíveis na NF-e (GET "
            "/referencias/atividades)."
        )
    return AtividadeDoCadastro(
        anexo=achada.anexo, cAtivSN=achada.cAtivSN, descricaoAtividade=achada.descricao, fonte=lista.fonte
    )


async def montar_empresa(
    da: DadosAbertos, req: EmpresaCadastroRequisicao, base: Cenario, versoes: Versoes
) -> tuple[Empresa, Cenario]:
    if not cnpj_valido(req.cnpj):
        raise Recusado(MENSAGEM_CNPJ)
    nome = await _local(da, req.uf, req.municipio)
    atividade = await _atividade(da, base.data, req.cAtivSN, versoes)
    empresa = Empresa(
        razaoSocial=req.razaoSocial,
        cnpj=req.cnpj,
        regimeAtual=req.regimeAtual,
        uf=req.uf,
        municipio=req.municipio,
        municipioNome=nome,
        simples=atividade,
    )
    cenario = base.model_copy(update={"premissasDas": base.premissasDas.model_copy(update={"anexo": atividade.anexo})})
    return empresa, cenario


def resposta_da_empresa(reg: EmpresaRegistro, aviso: str) -> EmpresaResposta:
    s = reg.empresa.simples
    return EmpresaResposta(
        empresa=resumo_empresa(reg),
        atividade=AtividadeDaEmpresa(cAtivSN=s.cAtivSN, descricao=s.descricaoAtividade, anexo=s.anexo, fonte=s.fonte),
        cenario=cenario_empresa(reg),
        premissasDasOrigem=reg.cenario.premissasDas.origem,
        aviso=aviso,
    )


def cadastrar_empresa(
    repo: Repositorio,
    contas: Contas,
    organizacao_id: str,
    empresa: Empresa,
    cenario: Cenario,
    agora: datetime,
    aviso: str,
) -> EmpresaResposta:
    """Grava no banco da organização e depois dá o acesso no banco das contas. Se o acesso falhar, a empresa sai
    do banco da organização: os dois bancos não têm transação em comum."""
    with repo.escrita() as s:
        if s.empresa(empresa.cnpj) is not None:
            raise Conflito("Esta empresa já está cadastrada na sua conta.")
        if len(s.empresas()) >= EMPRESAS_POR_ORGANIZACAO:
            raise Conflito(f"A conta já tem {EMPRESAS_POR_ORGANIZACAO} empresas, o limite por conta.")
        s.inserir_empresa(empresa, cenario)
    try:
        contas.vincular_empresa(organizacao_id, empresa.cnpj, agora)
    except BaseException:
        with repo.escrita() as s:
            s.apagar_empresa(empresa.cnpj)
        raise
    return resposta_da_empresa(EmpresaRegistro(empresa, cenario), aviso)


def excluir_empresa(repo: Repositorio, contas: Contas, organizacao_id: str, cnpj: str) -> None:
    """De vez, sem excluir a conta (C3-B, etapa 7). Primeiro a empresa sai do banco da organização, e tudo dela vai
    junto em cascata (itens, códigos de fornecedor, notas, custos, preços, alertas, classificações e clientes); depois
    sai o acesso no banco das contas, e o contador deixa de alcançá-la. Os dois bancos não têm transação em comum: uma
    falha no meio deixa só o acesso, sem dado nenhum, e o recadastro aceita esse caso (Contas.vincular_empresa). Um
    acesso que já tinha sobrado assim também sai por aqui."""
    with repo.escrita() as s:
        s.apagar_empresa(cnpj)
    contas.desvincular_empresa(organizacao_id, cnpj)


def ler_empresa(repo: Repositorio, cnpj: str, aviso: str) -> EmpresaResposta:
    with repo.leitura() as s:
        return resposta_da_empresa(_empresa(s, cnpj), aviso)


async def configurar_empresa(
    da: DadosAbertos,
    repo: Repositorio,
    cnpj: str,
    req: EmpresaConfiguracaoRequisicao,
    base: Cenario,
    versoes: Versoes,
    aviso: str,
) -> EmpresaResposta:
    """Só o que veio muda. As consultas aos motores ficam fora da transação; a gravação confere que a empresa
    ainda é a mesma que foi lida (checagem otimista, como na correção da classificação)."""
    with repo.leitura() as s:
        lido = _empresa(s, cnpj)
    empresa, cenario = lido.empresa, lido.cenario
    enviados = req.model_fields_set
    mudancas: dict[str, object] = {}
    if "razaoSocial" in enviados:
        mudancas["razaoSocial"] = req.razaoSocial
    if "regimeAtual" in enviados:
        mudancas["regimeAtual"] = req.regimeAtual
    if "uf" in enviados and req.uf is not None and req.municipio is not None:
        mudancas |= {"uf": req.uf, "municipio": req.municipio, "municipioNome": await _local(da, req.uf, req.municipio)}
    premissas = cenario.premissasDas
    if "cAtivSN" in enviados and req.cAtivSN is not None:
        atividade = await _atividade(da, cenario.data, req.cAtivSN, versoes)
        mudancas["simples"] = atividade
        premissas = premissas.model_copy(update={"anexo": atividade.anexo})
    if "premissasDas" in enviados:
        if req.premissasDas is None:  # volta aos valores da simulação, no anexo da atividade
            premissas = base.premissasDas.model_copy(update={"anexo": premissas.anexo})
        else:
            premissas = premissas.model_copy(
                update={
                    "pCBSSN": req.premissasDas.pCBSSN,
                    "pIBSSN": req.premissasDas.pIBSSN,
                    "fonte": "Configurações da empresa (P8).",
                    "origem": "usuario",
                }
            )
    atualizacao_cenario: dict[str, object] = {"premissasDas": premissas}
    if "cargaAtualPct" in enviados:
        atualizacao_cenario["cargaAtualPct"] = req.cargaAtualPct
    nova_empresa = empresa.model_copy(update=mudancas)
    novo_cenario = cenario.model_copy(update=atualizacao_cenario)
    # Revalida (model_copy não valida): o que entrou passou pelo contrato, mas o modelo gravado é outro.
    nova_empresa = Empresa.model_validate(nova_empresa.model_dump())
    novo_cenario = Cenario.model_validate(novo_cenario.model_dump())
    with repo.escrita() as s:
        atual = _empresa(s, cnpj)
        if (atual.empresa, atual.cenario) != (empresa, cenario):
            raise Conflito("A empresa mudou enquanto as configurações eram conferidas. Tente de novo.")
        s.atualizar_empresa(nova_empresa, novo_cenario)
    return resposta_da_empresa(EmpresaRegistro(nova_empresa, novo_cenario), aviso)


# -- catálogo ---------------------------------------------------------------------------------------------


async def criar_item(
    da: DadosAbertos, repo: Repositorio, req: ItemNovoRequisicao, exigir_digito: bool, agora: datetime
) -> ItemResposta:
    """O item com a classificação que o usuário escolheu entre as válidas para a NCM (P3). Itens sujeitos ao
    Imposto Seletivo ficam para depois: a classificação do IS e os litros por unidade não têm, por enquanto, uma
    fonte oficial que o ContaAI consulte, e o ContaAI não inventa (ADR 0017)."""
    if exigir_digito and not cnpj_valido(req.cnpjFornecedor):
        raise Recusado("CNPJ do fornecedor inválido: confira os dígitos verificadores.")
    with repo.leitura() as s:
        reg = _empresa(s, req.cnpj)
    data = reg.cenario.data
    info = await da.ncm(req.ncm, data)
    if info is None:
        raise Recusado("NCM não encontrada nos dados abertos do motor RR na data do cenário.")
    if info.tributadoPeloImpostoSeletivo:
        raise Recusado(
            "Esta NCM é tributada pelo Imposto Seletivo. O cadastro de itens com Imposto Seletivo ainda não está "
            "disponível na empresa própria."
        )
    escolhida = next(
        (c for c in await classificacoes_da_ncm(da, req.ncm, data) if c.cClassTrib == req.cClassTrib), None
    )
    if escolhida is None:
        raise Recusado(
            "Classificação não válida para a NCM nos dados abertos do motor RR. Use uma das candidatas da busca "
            "(GET /busca/ncm)."
        )
    fonte = (
        f"Escolhida no cadastro do item em {agora.date().isoformat()} (UTC), com a confirmação do usuário (P3): "
        f"{escolhida.cClassTrib} ({escolhida.descricao}), válida para a NCM nos dados abertos do motor RR em "
        f"{data.isoformat()}."
    )
    with repo.escrita() as s:
        _empresa(s, req.cnpj)
        if s.contar_itens(req.cnpj) >= ITENS_POR_EMPRESA:
            raise Conflito(f"O catálogo já tem {ITENS_POR_EMPRESA} itens, o limite por empresa.")
        if s.item_por_codigo(req.cnpj, req.cnpjFornecedor, req.codigoFornecedor) is not None:
            raise Conflito("Este código do fornecedor já está em outro item do catálogo.")
        item_id = f"item-{secrets.token_hex(6)}"
        while s.existe_item(req.cnpj, item_id):
            item_id = f"item-{secrets.token_hex(6)}"
        item = ItemCatalogo(
            id=item_id,
            descricao=req.descricao,
            ncm=req.ncm,
            ncmDescricaoOficial=info.hierarquia() or req.ncm,
            cst=escolhida.cst,
            cClassTrib=escolhida.cClassTrib,
            classificacaoFonte=fonte,
            impostoSeletivo=None,
            unidade=req.unidade,
            cnpjFornecedor=req.cnpjFornecedor,
            codigoFornecedor=req.codigoFornecedor,
            precoVenda=req.precoVenda,
            margemAlvoPct=req.margemAlvoPct,
        )
        s.inserir_item(req.cnpj, item)
        s.lancar_preco(req.cnpj, item.id, req.precoVenda, agora, "tela")
        estado = _item_estado(s, req.cnpj, item)
    return ItemResposta(item=estado)


def alterar_item(repo: Repositorio, item_id: str, req: ItemAlteracaoRequisicao, exigir_digito: bool) -> ItemResposta:
    enviados = req.model_fields_set - {"cnpj"}
    if exigir_digito and req.cnpjFornecedor is not None and not cnpj_valido(req.cnpjFornecedor):
        raise Recusado("CNPJ do fornecedor inválido: confira os dígitos verificadores.")
    with repo.escrita() as s:
        _empresa(s, req.cnpj)
        cat = s.item(req.cnpj, item_id)
        if cat is None:
            raise NaoEncontrado("Item não encontrado no catálogo desta empresa.")
        mudancas = {campo: getattr(req, campo) for campo in enviados}
        if "codigoFornecedor" in mudancas:
            outro = s.item_por_codigo(req.cnpj, req.cnpjFornecedor or "", req.codigoFornecedor or "")
            if outro is not None and outro.id != item_id:
                raise Conflito("Este código do fornecedor já está em outro item do catálogo.")
        novo = ItemCatalogo.model_validate(cat.model_copy(update=mudancas).model_dump(by_alias=True))
        if novo == cat:
            raise Conflito("Nada mudou: o item já tem estes valores.")
        # O JSON guarda a classificação do cadastro; a atual (do último lançamento) não vai para ele.
        cadastro = s.item_do_cadastro(req.cnpj, item_id)
        if cadastro is None:
            raise NaoEncontrado("Item não encontrado no catálogo desta empresa.")
        s.atualizar_item(req.cnpj, ItemCatalogo.model_validate(cadastro.model_copy(update=mudancas).model_dump()))
        atualizado = s.item(req.cnpj, item_id)
        if atualizado is None:
            raise NaoEncontrado("Item não encontrado no catálogo desta empresa.")
        estado = _item_estado(s, req.cnpj, atualizado)
    return ItemResposta(item=estado)


def arquivar_item(repo: Repositorio, cnpj: str, item_id: str, agora: datetime) -> ItemArquivadoResposta:
    """Confere os clientes na mesma transação de escrita (BEGIN IMMEDIATE) que arquiva: um cliente gravado ao mesmo
    tempo não escapa da trava."""
    with repo.escrita() as s:
        _empresa(s, cnpj)
        if s.item(cnpj, item_id) is None:
            raise NaoEncontrado("Item não encontrado no catálogo desta empresa.")
        compram = s.clientes_que_compram(cnpj, item_id)
        if compram:
            raise ItemEmUso([ClienteQueCompra(cnpj=c.cliente.cnpj, nome=c.cliente.razaoSocial) for c in compram])
        s.arquivar_item(cnpj, item_id, agora)
    return ItemArquivadoResposta(itemId=item_id, arquivadoEm=agora)


# -- clientes B2B -----------------------------------------------------------------------------------------

# Texto fixo, montado pelo backend: a descrição da compra das sementes (data/demo) deixa de valer quando a pessoa
# muda a compra.
DESCRICAO_DA_COMPRA = "Compra mensal informada no cadastro do cliente."
AVISO_CLIENTE_DEMO = "Dados fictícios de demonstração (P10): empresa, CNPJ e quantidades não são reais."
AVISO_CLIENTE_DA_CONTA = "Cliente cadastrado pela empresa da conta."
MENSAGEM_CLIENTE_DO_SIMPLES = (
    "O ContaAI compara os regimes na venda a um cliente do regime regular. Clientes do Simples Nacional ainda não "
    "entram."
)


def _conferir_compra(s: Sessao, cnpj: str, compra: list[ItemDaCompraMensal]) -> CompraMensal:
    """Cada item precisa estar no catálogo da empresa (sem os arquivados)."""
    if any(s.item(cnpj, i.itemId) is None for i in compra):
        raise Recusado("A compra mensal tem um item que não está no catálogo desta empresa.")
    return CompraMensal(
        descricao=DESCRICAO_DA_COMPRA,
        itens=[ItemDaCompraGravado(itemId=i.itemId, quantidade=i.quantidade) for i in compra],
    )


async def criar_cliente(
    da: DadosAbertos, repo: Repositorio, req: ClienteNovoRequisicao, na_empresa_propria: bool
) -> ClienteResposta:
    """O dígito do CNPJ do cliente é exigido só na empresa da conta, como o do fornecedor (ADR 0017). A consulta do
    município ao motor fica fora da transação."""
    if req.regime != "regime_regular":
        raise Recusado(MENSAGEM_CLIENTE_DO_SIMPLES)
    if na_empresa_propria and not cnpj_valido(req.cnpjCliente):
        raise Recusado("CNPJ do cliente inválido: confira os dígitos verificadores.")
    if req.cnpjCliente == req.cnpj:
        raise Recusado("O cliente não pode ser a própria empresa.")
    await _local(da, req.uf, req.municipio)
    with repo.escrita() as s:
        _empresa(s, req.cnpj)
        if s.cliente_b2b(req.cnpj, req.cnpjCliente) is not None:
            raise Conflito("Este cliente já está cadastrado nesta empresa.")
        if s.contar_clientes_b2b(req.cnpj) >= CLIENTES_POR_EMPRESA:
            raise Conflito(f"A empresa já tem {CLIENTES_POR_EMPRESA} clientes, o limite por empresa.")
        cliente = ClienteB2B(
            aviso=AVISO_CLIENTE_DA_CONTA if na_empresa_propria else AVISO_CLIENTE_DEMO,
            cliente=Cliente(
                razaoSocial=req.razaoSocial,
                cnpj=req.cnpjCliente,
                regime="regime_regular",
                uf=req.uf,
                municipio=req.municipio,
            ),
            compraMensal=_conferir_compra(s, req.cnpj, req.compraMensal),
        )
        s.inserir_cliente_b2b(req.cnpj, cliente)
    return ClienteResposta(cliente=cliente_estado(cliente))


async def alterar_cliente(
    da: DadosAbertos, repo: Repositorio, cnpj_cliente: str, req: ClienteAlteracaoRequisicao
) -> ClienteResposta:
    """Só o que veio muda. A mesma compra mensal reenviada guarda a descrição que já tinha."""
    enviados = req.model_fields_set - {"cnpj"}
    if req.uf is not None and req.municipio is not None:
        await _local(da, req.uf, req.municipio)
    with repo.escrita() as s:
        _empresa(s, req.cnpj)
        atual = s.cliente_b2b(req.cnpj, cnpj_cliente)
        if atual is None:
            raise NaoEncontrado("Cliente não encontrado nesta empresa.")
        dados = atual.cliente.model_copy(
            update={campo: getattr(req, campo) for campo in enviados & {"razaoSocial", "uf", "municipio"}}
        )
        compra = atual.compraMensal
        if req.compraMensal is not None:
            nova = _conferir_compra(s, req.cnpj, req.compraMensal)
            if nova.itens != atual.compraMensal.itens:
                compra = nova
        novo = ClienteB2B.model_validate(
            atual.model_copy(update={"cliente": dados, "compraMensal": compra}).model_dump(by_alias=True)
        )
        if novo == atual:
            raise Conflito("Nada mudou: o cliente já tem estes valores.")
        s.atualizar_cliente_b2b(req.cnpj, novo)
    return ClienteResposta(cliente=cliente_estado(novo))


def excluir_cliente(repo: Repositorio, cnpj: str, cnpj_cliente: str, agora: datetime) -> ClienteExcluidoResposta:
    """De vez, sem histórico (decisão da etapa 6)."""
    with repo.escrita() as s:
        _empresa(s, cnpj)
        if not s.apagar_cliente_b2b(cnpj, cnpj_cliente):
            raise NaoEncontrado("Cliente não encontrado nesta empresa.")
    return ClienteExcluidoResposta(cnpjCliente=cnpj_cliente, excluidoEm=agora)
