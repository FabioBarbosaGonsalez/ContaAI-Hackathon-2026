"""Contrato da API do backend do ContaAI (E0-05).

Fonte da verdade para frontend e agente: seção 9 do plano v2.0, com as mudanças do ADR 0003.

Convenções:
- Dinheiro e percentuais são Decimal e saem como texto no JSON ("27.90"). Percentuais em pontos
  percentuais (15 = 15%).
- valorUnitario é o valor do produto por unidade, como o vUnCom da NF-e. No Simples tradicional é o
  preço cobrado do cliente (CBS/IBS dentro do DAS); no híbrido, a CBS/IBS é cobrada por fora.
- Nenhum valor de tributo é calculado pelo backend: todos vêm dos motores (P1). O backend só soma,
  subtrai e calcula margens e preços com as fórmulas do ADR 0003.
- Datas e horas em ISO 8601, sempre com fuso (ADR 0003, revisado na E4). Instantes do sistema
  (criadoEm, aplicadoEm) saem em UTC. Datas copiadas de um documento (dataEmissao da NF-e, a data dos
  lançamentos de custo) saem como vieram, com o fuso da nota. A ordem é sempre a do instante.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

AVISO_LEGAL = "Estimativa baseada nas calculadoras oficiais. Não é parecer fiscal e não substitui o contador."

Anexo = Literal["I", "II", "III", "IV", "V"]
Porcentagem = Decimal


class _Modelo(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Regime(StrEnum):
    SIMPLES_TRADICIONAL = "simples_tradicional"
    SIMPLES_HIBRIDO = "simples_hibrido"


class Motor(StrEnum):
    REGIME_REGULAR = "regime_regular"
    SIMPLES_NACIONAL = "simples_nacional"


class EstadoItem(StrEnum):
    """União dos estados dos dois motores (RR tem CALCULO_SIMULADO; SN tem NAO_CALCULADO)."""

    CALCULADO = "CALCULADO"
    CALCULO_SIMULADO = "CALCULO_SIMULADO"
    NAO_CALCULADO = "NAO_CALCULADO"
    INCONSISTENCIA_ENTRADA = "INCONSISTENCIA_ENTRADA"
    NAO_IMPLEMENTADO = "NAO_IMPLEMENTADO"
    FALHA_TECNICA = "FALHA_TECNICA"


# ---------------------------------------------------------------------------
# Entradas comuns


class AliquotasNominais(_Modelo):
    """Premissas de alíquota do usuário. Obrigatórias a partir de 2027 e proibidas antes (P6)."""

    cbs: Porcentagem = Field(ge=0, lt=100)
    ibsEstadual: Porcentagem = Field(ge=0, lt=100)
    ibsMunicipal: Porcentagem = Field(ge=0, lt=100)
    impostoSeletivoAdValorem: Porcentagem | None = Field(
        default=None, ge=0, description="Exigida pelo motor para NCM sujeita ao IS, mesmo na revenda (REG-035)."
    )
    fonte: str | None = Field(
        default=None,
        max_length=200,
        description="De onde veio a premissa (ex.: o rótulo do preset escolhido). Sai impressa nas premissas.",
    )


class PremissasDas(_Modelo):
    """Linha de alíquotas efetivas do Simples do contribuinte (premissa rotulada, P8 e ADR 0001)."""

    anexo: Anexo
    cAtivSN: str = Field(pattern=r"^\d{2}$", description="Código de atividade do Simples (ex.: 01, revenda).")
    pCBSSN: Porcentagem = Field(ge=0, lt=100)
    pIBSSN: Porcentagem = Field(ge=0, lt=100)
    fonte: str | None = Field(
        default=None,
        max_length=200,
        description="De onde veio a premissa (ex.: o rótulo do preset escolhido). Sai impressa nas premissas.",
    )


class ImpostoSeletivoEntrada(_Modelo):
    cst: str = Field(pattern=r"^\d{3}$")
    cClassTrib: str = Field(pattern=r"^\d{6}$")
    litrosPorUnidade: Decimal | None = Field(default=None, gt=0)


class ItemBase(_Modelo):
    """Produto já classificado e confirmado pelo usuário (P3)."""

    id: str = Field(min_length=1, max_length=64)
    descricao: str = Field(min_length=1, max_length=200)
    ncm: str | None = Field(default=None, pattern=r"^\d{8}$")
    nbs: str | None = Field(default=None, pattern=r"^\d{9}$")
    cst: str = Field(pattern=r"^\d{3}$")
    cClassTrib: str = Field(pattern=r"^\d{6}$")
    impostoSeletivo: ImpostoSeletivoEntrada | None = None
    unidade: str = Field(min_length=1, max_length=6)

    @model_validator(mode="after")
    def validar_ncm_ou_nbs(self) -> ItemBase:
        if (self.ncm is None) == (self.nbs is None):
            raise ValueError("Informe NCM ou NBS, nunca os dois.")
        return self


class ItemEntrada(ItemBase):
    quantidade: Decimal = Field(gt=0)
    valorUnitario: Decimal = Field(gt=0, description="Valor do produto por unidade (vUnCom).")
    custoUnitario: Decimal | None = Field(
        default=None,
        ge=0,
        description="Valor pago ao fornecedor por unidade, sem CBS/IBS por fora (vUnCom da compra). Ausente: sem margem.",
    )
    creditoCompraUnitario: Decimal | None = Field(
        default=None,
        ge=0,
        description="CBS + IBS da compra por unidade, lida do grupo IBSCBS da NF-e. No carrinho e no preço-alvo só é "
        "usada no Simples tradicional, onde entra no custo; na comparação de regimes é o crédito das compras do "
        "híbrido. Ausente: o backend calcula no motor RR sobre o custo, na data e com as alíquotas da operação, com "
        "a hipótese exibida de fornecedor no regime regular.",
    )


RECUSA_TRADICIONAL_2026 = (
    "O Simples tradicional só é calculado a partir de 2027: em 2026 o motor do Simples não calcula a NF-e "
    "(erro VSN-015, conferido no motor SN 1.0.2). Use uma data de 2027 ou o Simples híbrido."
)


def validar_data_do_tradicional(data: date) -> None:
    """Recusa clara antes de chamar o motor, em vez do erro cru do VSN-015 (ADR 0004 e ADR 0007)."""
    if data.year < 2027:
        raise ValueError(RECUSA_TRADICIONAL_2026)


def validar_itens_do_tradicional(itens: list[ItemEntrada] | list[ItemBase]) -> None:
    """Casos que o lado tradicional ainda não trata (ADR 0004): recusa clara em vez de número errado."""
    for item in itens:
        if item.nbs is not None:
            raise ValueError(
                f"Item {item.id}: serviço (NBS) no Simples tradicional ainda não é suportado. O ContaAI envia ao "
                "motor do Simples uma NF-e de mercadorias (tpDoc 55)."
            )
        if item.impostoSeletivo is not None and item.impostoSeletivo.cst != "200":
            raise ValueError(
                f"Item {item.id}: Imposto Seletivo com incidência (CST do IS {item.impostoSeletivo.cst}) no Simples "
                "tradicional ainda não é suportado. Só o IS sem nova incidência (CST 200, ex.: revenda 200007)."
            )


class _Operacao(_Modelo):
    data: date = Field(description="Data do fato gerador. Rege as vigências nos dois motores.")
    uf: str = Field(pattern=r"^[A-Z]{2}$")
    municipio: int = Field(description="Código IBGE do município.")
    aliquotasNominais: AliquotasNominais | None = None
    premissasDas: PremissasDas | None = None

    @model_validator(mode="after")
    def validar_premissas_por_ano(self) -> _Operacao:
        if self.data.year >= 2027 and self.aliquotasNominais is None:
            raise ValueError("A partir de 2027 as alíquotas são premissas do usuário: informe aliquotasNominais (P6).")
        if self.data.year < 2027 and self.aliquotasNominais is not None:
            raise ValueError("Antes de 2027 o motor usa as alíquotas de referência: não informe aliquotasNominais.")
        return self


# ---------------------------------------------------------------------------
# Saídas comuns


class Premissa(_Modelo):
    """Toda premissa aparece impressa junto do resultado (P6, P7, P8)."""

    nome: str
    valor: str
    fonte: str


class ErroMotor(_Modelo):
    codigo: str = Field(description="Ex.: REG-011, VSN-047.")
    titulo: str
    campo: str | None = Field(default=None, description="JSON Pointer do campo com problema.")
    detalhe: str | None = None


class Tributos(_Modelo):
    cbs: Decimal | None = None
    ibs: Decimal | None = None
    impostoSeletivo: Decimal | None = None


class AliquotaEfetiva(_Modelo):
    """Como o motor devolve: RR separa IBS estadual e municipal; SN traz o IBS inteiro."""

    cbs: Porcentagem | None = None
    ibsUF: Porcentagem | None = None
    ibsMun: Porcentagem | None = None
    ibs: Porcentagem | None = None


class Versoes(_Modelo):
    motorRegimeRegular: str | None = None
    motorSimplesNacional: str | None = None
    banco: str | None = None


class _Simulacao(_Modelo):
    simulado: bool = Field(description="Verdadeiro quando há alíquota premissa (2027 em diante ou DAS informado).")
    avisoSimulacao: str | None = Field(default=None, description="Frase de estado para o título da tela.")
    premissas: list[Premissa]


# ---------------------------------------------------------------------------
# POST /carrinho/calcular


class CarrinhoRequisicao(_Operacao):
    regime: Regime
    itens: list[ItemEntrada] = Field(min_length=1, max_length=200)
    cargaAtualPct: Porcentagem | None = Field(
        default=None,
        ge=0,
        lt=100,
        description="Carga de tributos que o usuário diz pagar hoje, em % do preço. Só para comparação: volta "
        "impressa, sem entrar em nenhuma conta.",
    )

    @model_validator(mode="after")
    def validar_das_no_tradicional(self) -> CarrinhoRequisicao:
        ids = [i.id for i in self.itens]
        if len(set(ids)) != len(ids):
            raise ValueError("Os itens do carrinho precisam ter id único.")
        if self.regime == Regime.SIMPLES_TRADICIONAL:
            if self.premissasDas is None:
                raise ValueError("No Simples tradicional informe premissasDas (alíquotas efetivas do anexo).")
            validar_data_do_tradicional(self.data)
            validar_itens_do_tradicional(self.itens)
        return self


class ItemCalculado(_Modelo):
    id: str
    descricao: str
    motor: Motor
    estado: EstadoItem
    motivoEstado: str | None = None
    quantidade: Decimal
    valorUnitario: Decimal
    valorProdutos: Decimal = Field(description="quantidade × valorUnitario.")
    tributos: Tributos
    reducaoPct: Porcentagem | None = None
    aliquotaEfetiva: AliquotaEfetiva | None = None
    precoCliente: Decimal | None = Field(
        default=None,
        description="Total pago pelo cliente na linha: valorProdutos no tradicional; mais CBS/IBS no híbrido.",
    )
    custoEfetivo: Decimal | None = Field(
        default=None, description="Custo da linha: com o crédito da compra no tradicional; sem ele no híbrido."
    )
    margemPct: Porcentagem | None = None
    memoria: dict[str, str] | None = None
    erros: list[ErroMotor] = []


class Totais(_Modelo):
    """Somam só os itens calculados, como os motores."""

    valorProdutos: Decimal
    tributos: Tributos
    precoCliente: Decimal
    itensCalculados: int
    itensComErro: int


class CarrinhoResposta(_Simulacao):
    regime: Regime
    data: date
    itens: list[ItemCalculado]
    totais: Totais
    cargaAtualPct: Porcentagem | None = Field(
        default=None, description="A carga atual informada pelo usuário, devolvida para comparação."
    )
    versoes: Versoes


# ---------------------------------------------------------------------------
# POST /item/preco-alvo


class PrecoAlvoRequisicao(_Operacao):
    regime: Regime
    item: ItemBase
    custoUnitario: Decimal = Field(ge=0)
    creditoCompraUnitario: Decimal | None = Field(
        default=None,
        ge=0,
        description="CBS + IBS da compra por unidade (grupo IBSCBS da NF-e). Só usada no Simples tradicional; "
        "ausente, vem do motor RR sobre o custo, com a hipótese exibida.",
    )
    margemAlvoPct: Porcentagem = Field(gt=0, lt=100)

    @model_validator(mode="after")
    def validar_das_no_tradicional(self) -> PrecoAlvoRequisicao:
        if self.regime == Regime.SIMPLES_TRADICIONAL:
            if self.premissasDas is None:
                raise ValueError("No Simples tradicional informe premissasDas (alíquotas efetivas do anexo).")
            validar_data_do_tradicional(self.data)
            validar_itens_do_tradicional([self.item])
        return self


class PrecoAlvoResposta(_Simulacao):
    regime: Regime
    itemId: str
    valorUnitario: Decimal = Field(
        description="Valor do produto por unidade a cobrar (vUnCom), arredondado ao centavo acima."
    )
    precoCliente: Decimal = Field(
        description="Total pago pelo cliente por unidade (igual ao valorUnitario no tradicional)."
    )
    tributosUnitarios: Tributos
    custoEfetivoUnitario: Decimal
    margemAlvoPct: Porcentagem
    margemObtidaPct: Porcentagem
    loteReferencia: int = Field(
        description="Quantidade usada nas chamadas ao motor, para reduzir o efeito do arredondamento."
    )
    chamadas: int = Field(
        description="Avaliações do motor usadas pelo método (as respondidas pelo cache contam): 3 no ajuste afim."
    )
    metodo: Literal["afim", "bissecao"]
    memoria: dict[str, str] | None = None


# ---------------------------------------------------------------------------
# POST /regime/comparar


class ClienteB2B(_Modelo):
    nome: str
    regime: Literal["regime_regular"]


class RegimeCompararRequisicao(_Operacao):
    """Venda a um cliente do regime regular, comparada nos dois lados do Simples (plano 11.2, ADR 0007).

    O crédito das compras vem de creditoCompraUnitario (grupo IBSCBS da NF-e; desde a E4, o GET /catalogo
    traz o da última nota de cada item) ou, ausente, do motor RR sobre o custo. Por isso todo item precisa do custo.
    """

    cliente: ClienteB2B
    itens: list[ItemEntrada] = Field(
        min_length=1,
        max_length=200,
        description="A venda. valorUnitario é o preço total cobrado do cliente (igual nos dois regimes). "
        "custoUnitario é obrigatório: sem ele não há crédito das compras.",
    )

    @model_validator(mode="after")
    def validar_comparacao(self) -> RegimeCompararRequisicao:
        if self.data.year < 2027:
            raise ValueError(
                "A comparação de regimes começa em 2027: em 2026 o motor do Simples não calcula a NF-e (VSN-015), "
                "então não há lado tradicional."
            )
        if self.premissasDas is None:
            raise ValueError("Informe premissasDas: sem elas não há lado tradicional para comparar.")
        ids = [i.id for i in self.itens]
        if len(set(ids)) != len(ids):
            raise ValueError("Os itens da venda precisam ter id único.")
        sem_custo = [i.id for i in self.itens if i.custoUnitario is None]
        if sem_custo:
            raise ValueError(
                f"Informe custoUnitario dos itens {', '.join(sem_custo)}: sem o custo não há crédito das compras e o "
                "lado híbrido sairia pior do que é."
            )
        validar_itens_do_tradicional(self.itens)
        return self


class LadoTradicional(_Modelo):
    precoCliente: Decimal
    tributo: Decimal = Field(description="CBS + IBS dentro do DAS sobre a venda (motor SN).")
    creditoCliente: Decimal = Field(description="Igual ao tributo pago no Simples (LC 214/2025, art. 47, §9º, II).")
    custoLiquidoCliente: Decimal = Field(description="precoCliente − creditoCliente.")


class LadoHibrido(_Modelo):
    precoCliente: Decimal = Field(description="valorProdutos + débito + impostoSeletivo.")
    valorProdutos: Decimal = Field(
        description="Base de cada linha achada para que base + CBS/IBS + IS dê o preço da venda (ajuste afim)."
    )
    debito: Decimal = Field(description="CBS + IBS por fora sobre a venda (motor RR).")
    impostoSeletivo: Decimal = Field(
        description="IS devolvido pelo motor RR. Entra no preço, mas não no débito nem no crédito do cliente (ADR 0007)."
    )
    creditoCompras: Decimal = Field(description="CBS + IBS das compras dos itens vendidos (NF-e ou motor RR).")
    tributoLiquido: Decimal = Field(description="debito − creditoCompras.")
    creditoCliente: Decimal = Field(description="Igual ao débito: CBS + IBS destacados (crédito integral).")
    custoLiquidoCliente: Decimal = Field(description="precoCliente − creditoCliente.")


class ItemComparado(_Modelo):
    """Uma linha da venda nos dois regimes. Os totais dos lados são a soma destas linhas."""

    id: str
    descricao: str
    quantidade: Decimal
    valorVenda: Decimal = Field(description="quantidade × valorUnitario: o preço total da linha ao cliente.")
    tributoTradicional: Decimal = Field(description="CBS + IBS dentro do DAS da linha (motor SN).")
    valorProdutosHibrido: Decimal
    debitoHibrido: Decimal = Field(description="CBS + IBS por fora da linha (motor RR).")
    impostoSeletivoHibrido: Decimal
    precoClienteHibrido: Decimal
    creditoCompras: Decimal = Field(description="CBS + IBS da compra das unidades vendidas.")
    fonteCredito: Literal["nfe", "motor", "custo_zero"] = Field(
        description="nfe: creditoCompraUnitario informado (grupo IBSCBS da nota); motor: motor RR sobre o custo, "
        "com a hipótese de fornecedor no regime regular; custo_zero: custo informado como zero."
    )


class EmpateTradicional(_Modelo):
    """Preço no Simples tradicional que dá ao cliente o mesmo custo líquido de um concorrente do regime
    regular que cobra o mesmo preço total (plano 11.2, "argumento de venda"; ADR 0007)."""

    hipotese: str
    precoCliente: Decimal = Field(description="Preço total no tradicional que empata o custo líquido do cliente.")
    descontoNecessario: Decimal = Field(
        description="valorVenda − precoCliente. Positivo: quanto o tradicional precisa baixar o preço."
    )
    tributo: Decimal = Field(description="CBS + IBS dentro do DAS sobre o preço de empate (motor SN).")
    creditoCliente: Decimal
    custoLiquidoCliente: Decimal = Field(description="precoCliente − creditoCliente.")
    custoLiquidoAlvo: Decimal = Field(description="O custo líquido do cliente no concorrente (= hibrido).")


class RegimeCompararResposta(_Simulacao):
    criterio: Literal["mesmo_preco_total_ao_cliente"]
    cliente: ClienteB2B
    data: date
    valorVenda: Decimal
    tradicional: LadoTradicional
    hibrido: LadoHibrido
    diferencaCaixa: Decimal = Field(
        description="Caixa no híbrido − caixa no tradicional, a preço igual = tributo tradicional − tributo líquido "
        "híbrido. Positivo: o híbrido deixa mais dinheiro com a empresa."
    )
    diferencaPrecoCliente: Decimal = Field(
        description="hibrido.precoCliente − valorVenda: centavos que sobram do arredondamento da base de cada linha."
    )
    itens: list[ItemComparado]
    empateTradicional: EmpateTradicional | None = Field(
        default=None,
        description="Ausente quando o preço de empate não fecha no motor SN dentro da tolerância por linha.",
    )
    fonteTradicional: Literal["motor"] = Field(
        description="Sempre o motor SN (ADR 0001); a premissa fica em premissas."
    )
    simplificacoes: list[str]
    versoes: Versoes


# ---------------------------------------------------------------------------
# POST /nfe/importar e GET /alertas


class Emitente(_Modelo):
    cnpj: str
    nome: str


class NotaResumo(_Modelo):
    serie: str | None = None
    numero: str
    dataEmissao: datetime
    emitente: Emitente
    destinatario: Emitente | None = Field(default=None, description="A empresa cadastrada que recebeu a nota.")
    homologacao: bool = Field(default=False, description="Nota de ambiente de homologação (tpAmb 2), como as da demo.")
    temGrupoIbsCbs: bool


class ItemNotaCasado(_Modelo):
    nItem: int | None = None
    itemId: str
    codigoFornecedor: str
    ncm: str
    descricaoNota: str = Field(description="xProd da nota: texto do fornecedor, tratado como dado não confiável.")
    quantidade: Decimal
    custoAnterior: Decimal | None
    custoNovo: Decimal
    variacaoPct: Porcentagem | None
    atualizaCusto: bool = Field(
        default=True,
        description="Falso quando a nota é mais antiga que o custo atual: entra no histórico sem mudar o custo.",
    )
    creditoCompraUnitario: Decimal | None
    fonteCredito: Literal["nfe", "motor"] | None


class ItemNotaSemPar(_Modelo):
    """Item que não casou com o catálogo: vira pergunta ao usuário (plano 11.3)."""

    nItem: int | None = None
    codigoFornecedor: str
    ncm: str
    descricaoNota: str = Field(description="xProd da nota: texto do fornecedor, tratado como dado não confiável.")
    motivo: str | None = Field(default=None, description="Por que não casou (código sem cadastro, NCM ou unidade).")


class OrigemAlerta(_Modelo):
    tipo: Literal["nfe"]
    numero: str
    dataEmissao: datetime
    emitente: str


class Alerta(_Simulacao):
    id: str
    cnpj: str | None = Field(default=None, description="Empresa do alerta (painel do contador, D1).")
    itemId: str
    descricaoItem: str
    regime: Regime
    margemAntesPct: Porcentagem
    margemDepoisPct: Porcentagem
    margemAlvoPct: Porcentagem
    custoAnterior: Decimal | None = None
    custoNovo: Decimal | None = None
    precoAtual: Decimal
    precoSugerido: Decimal | None = Field(
        description="Preço-alvo (POST /item/preco-alvo) com o custo novo. Vazio quando a margem-alvo é impossível."
    )
    motivoSemPreco: str | None = None
    origem: OrigemAlerta
    criadoEm: datetime
    aplicadoEm: datetime | None = Field(default=None, description="Quando o preço sugerido foi aplicado.")


class NfeImportarResposta(_Simulacao):
    jaImportada: bool = Field(
        default=False, description="A mesma nota (mesmo arquivo) já tinha sido importada: nada foi gravado de novo."
    )
    nota: NotaResumo
    itensCasados: list[ItemNotaCasado]
    itensSemPar: list[ItemNotaSemPar]
    alertas: list[Alerta]


class AlertasResposta(_Modelo):
    alertas: list[Alerta]


class AplicarAlertaResposta(_Modelo):
    """O preço sugerido virou o preço de venda do item (lançamento de preço com origem no alerta)."""

    alerta: Alerta
    precoAnterior: Decimal
    precoNovo: Decimal


# ---------------------------------------------------------------------------
# GET /catalogo, GET /contador/painel e POST /demo/restaurar (E4, ADR 0008)


class LancamentoCustoSaida(_Modelo):
    data: datetime = Field(description="Emissão da nota de compra.")
    notaNumero: str | None = None
    custoUnitario: Decimal
    creditoCompraUnitario: Decimal | None
    fonteCredito: Literal["nfe", "motor"] | None


class ItemCatalogoEstado(ItemBase):
    """O item com o estado atual: preço de venda e custo vêm do último lançamento de cada um."""

    ncmDescricaoOficial: str
    classificacaoFonte: str
    margemAlvoPct: Porcentagem
    precoVenda: Decimal = Field(description="Preço de venda atual por unidade (vUnCom).")
    custoAtual: LancamentoCustoSaida | None = Field(description="Último custo pela data da nota; vazio sem compra.")
    historicoCusto: list[LancamentoCustoSaida] = Field(description="Do mais recente para o mais antigo (até 10).")


class EmpresaResumo(_Modelo):
    cnpj: str
    razaoSocial: str
    regimeAtual: Regime
    uf: str
    municipio: int
    municipioNome: str
    dataCenario: date


class CatalogoResposta(_Modelo):
    empresa: EmpresaResumo
    itens: list[ItemCatalogoEstado]
    aviso: str = Field(description="Dados fictícios de demonstração (P10).")


class EmpresaNoPainel(_Modelo):
    empresa: EmpresaResumo
    alertasAbertos: int
    alertasAplicados: int
    ultimaNota: datetime | None
    alertaMaisRecente: Alerta | None


class PainelContadorResposta(_Modelo):
    """Painel do contador (D1): as empresas da carteira, a que tem mais alertas abertos primeiro."""

    empresas: list[EmpresaNoPainel]
    aviso: str


class RestaurarResposta(_Modelo):
    empresas: int
    notasImportadas: list[str] = Field(description="Número de cada nota inicial importada.")
    alertas: int


# ---------------------------------------------------------------------------
# GET /busca/ncm, GET /explicar/{itemId}, GET /erros/{codigo}


class ClassificacaoCandidata(_Modelo):
    cClassTrib: str
    cst: str
    descricao: str
    reducaoPct: Porcentagem
    especificaDoProduto: bool = Field(
        description="Válida para esta NCM e inválida para uma NCM sem benefício (método do ADR 0003)."
    )
    fundamentacao: str | None = None


class CandidatoNcm(_Modelo):
    ncm: str | None = None
    nbs: str | None = None
    descricao: str = Field(description="Hierarquia oficial dos dados abertos.")
    tributadoPeloImpostoSeletivo: bool
    classificacoes: list[ClassificacaoCandidata]


class BuscaNcmResposta(_Modelo):
    consulta: str
    candidatos: list[CandidatoNcm]
    aviso: str = Field(description="A IA propõe; o usuário confirma (P3).")
    fonte: str | None = Field(
        default=None, description="De onde vieram os candidatos (índice local dos dados abertos e versão do motor)."
    )


class Fundamentacao(_Modelo):
    cClassTrib: str
    textoCurto: str
    texto: str
    referenciaNormativa: str


class ExplicarRequisicao(_Operacao):
    """Explicação de um item qualquer (o GET /explicar/{itemId} conhece só o catálogo de demonstração)."""

    regime: Regime
    item: ItemEntrada

    @model_validator(mode="after")
    def validar_das_no_tradicional(self) -> ExplicarRequisicao:
        if self.regime == Regime.SIMPLES_TRADICIONAL:
            if self.premissasDas is None:
                raise ValueError("No Simples tradicional informe premissasDas (alíquotas efetivas do anexo).")
            validar_data_do_tradicional(self.data)
            validar_itens_do_tradicional([self.item])
        return self


class ExplicarResposta(_Modelo):
    itemId: str
    regime: Regime
    motor: Motor
    estado: EstadoItem
    reducaoPct: Porcentagem | None = None
    memoria: dict[str, str] | None = None
    erros: list[ErroMotor] = []
    fundamentacoes: list[Fundamentacao]
    premissas: list[Premissa]
    aviso: str


class ErroDescricao(_Modelo):
    codigo: str
    titulo: str
    descricao: str
    motor: Motor


# ---------------------------------------------------------------------------
# POST /chat


class MensagemChat(_Modelo):
    papel: Literal["usuario", "assistente"]
    texto: str = Field(min_length=1, max_length=4000)


class ContextoChat(_Operacao):
    """O que a tela já sabe: a operação, o regime e os itens que o usuário já confirmou (P3).

    O backend não guarda estado: a cada mensagem a tela manda o contexto. O agente só calcula os
    itens daqui, pelo id; um item que só aparece no texto da conversa precisa ser confirmado antes.
    """

    regime: Regime
    itens: list[ItemEntrada] = Field(default=[], max_length=200)
    cnpj: str | None = Field(
        default=None, pattern=r"^\d{14}$", description="Empresa da tela: os alertas do chat são os dela (E4)."
    )

    @model_validator(mode="after")
    def validar_contexto(self) -> ContextoChat:
        ids = [i.id for i in self.itens]
        if len(set(ids)) != len(ids):
            raise ValueError("Os itens do contexto precisam ter id único.")
        if self.regime == Regime.SIMPLES_TRADICIONAL:
            if self.premissasDas is None:
                raise ValueError("No Simples tradicional informe premissasDas (alíquotas efetivas do anexo).")
            validar_itens_do_tradicional(self.itens)
        return self


class ChatRequisicao(_Modelo):
    mensagens: list[MensagemChat] = Field(min_length=1, max_length=50)
    contexto: ContextoChat | None = Field(
        default=None, description="Sem contexto, o agente só busca classificações e explica erros (não calcula)."
    )

    @model_validator(mode="after")
    def validar_ultima(self) -> ChatRequisicao:
        if self.mensagens[-1].papel != "usuario":
            raise ValueError("A última mensagem precisa ser do usuário.")
        return self


class AcaoConfirmarClassificacao(_Modelo):
    """O cálculo só acontece depois que o usuário confirma (P3)."""

    tipo: Literal["confirmar_classificacao"]
    itemDescricao: str
    candidatos: list[CandidatoNcm]


class AcaoCorrigirClassificacao(_Modelo):
    """Item que voltou com erro de classificação (REG-011, VSN-047): o usuário escolhe a nova (P3, plano 11.4)."""

    tipo: Literal["corrigir_classificacao"]
    itemId: str
    erro: ErroMotor
    ncm: str
    candidatas: list[ClassificacaoCandidata] = Field(max_length=3)


class AcaoAplicarPreco(_Modelo):
    """Preço-alvo calculado: a tela aplica no item se o usuário confirmar."""

    tipo: Literal["aplicar_preco"]
    itemId: str
    valorUnitarioAtual: Decimal | None
    valorUnitarioSugerido: Decimal
    precoCliente: Decimal
    margemAlvoPct: Porcentagem
    margemObtidaPct: Porcentagem


AcaoProposta = Annotated[
    AcaoConfirmarClassificacao | AcaoCorrigirClassificacao | AcaoAplicarPreco, Field(discriminator="tipo")
]


class ChatResposta(_Modelo):
    resposta: str
    acoesPropostas: list[AcaoProposta] = Field(
        description="Montadas pelo backend a partir dos resultados das ferramentas, nunca do texto da IA. "
        "Nada é aplicado sem o clique do usuário."
    )
    ferramentasChamadas: list[str]
    provedor: str = Field(description="Quem escreveu a resposta: 'roteiro' (sem IA) ou o provedor de IA configurado.")
    verificacao: Literal["aprovada", "resposta_segura"] = Field(
        description="aprovada: todo R$ e % da resposta existe nos resultados das ferramentas ou na mensagem do "
        "usuário (P2). resposta_segura: a IA citou número sem fonte duas vezes e a resposta foi trocada."
    )
    simulado: bool = Field(description="Algum resultado usado na resposta é simulação (P6).")
    avisoSimulacao: str | None = None
    premissas: list[Premissa] = Field(default=[], description="Premissas dos resultados usados, sem repetição.")
    aviso: str


# ---------------------------------------------------------------------------
# Falhas dos motores (modo real)


class FalhaMotorResposta(_Modelo):
    """Corpo das respostas 422 (o motor recusou a operação), 502 e 503 vindas dos motores.

    Os erros de validação do próprio ContaAI também usam 422, no formato padrão do FastAPI
    (detail como lista). Nunca traz URL, host ou corpo do motor.
    """

    detail: str
    motor: Motor
    erros: list[ErroMotor] = []


class RecusaCalculo(_Modelo):
    """422 quando o cálculo pedido não tem resposta: margem impossível, item que o motor não calcula ou
    preço-alvo que não converge. Traz os erros do motor quando eles explicam a recusa."""

    detail: str
    erros: list[ErroMotor] = []


# ---------------------------------------------------------------------------
# GET /cenarios/presets


class PresetAliquotas(_Modelo):
    """Valores prontos para os campos de alíquota de 2027, cada um com a sua fonte (plano 11.5, P6).

    Os campos de alíquota da tela começam vazios; o preset só preenche o que tem fonte. O que vier
    vazio (null) o usuário informa.
    """

    id: str
    rotulo: str = Field(description="Texto curto para a tela; vai em aliquotasNominais.fonte quando escolhido.")
    cbs: Porcentagem
    ibsEstadual: Porcentagem | None = None
    ibsMunicipal: Porcentagem | None = None
    impostoSeletivoAdValorem: Porcentagem | None = None
    fonte: str
    ressalva: str


class PresetsResposta(_Modelo):
    presets: list[PresetAliquotas]
    aviso: str


# ---------------------------------------------------------------------------
# GET /saude


class SaudeMotor(_Modelo):
    motor: Motor
    ok: bool
    versaoFixada: str
    versaoEmExecucao: str | None = None
    banco: str | None = None
    coerente: bool = Field(description="Versão em execução igual à fixada nos Dockerfiles (P5).")
    detalhe: str | None = None


class SaudeResposta(_Modelo):
    status: Literal["ok", "degradado"]
    modo: Literal["mock", "real"]
    motores: list[SaudeMotor]
