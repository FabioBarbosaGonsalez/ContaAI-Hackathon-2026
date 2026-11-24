"""Contrato da API do backend do ContaAI (E0-05).

Fonte da verdade para frontend e agente: seção 9 do plano v2.0, com as mudanças do ADR 0003.

Convenções:
- Dinheiro e percentuais são Decimal e saem como texto no JSON ("27.90"). Percentuais em pontos
  percentuais (15 = 15%).
- valorUnitario é o valor do produto por unidade, como o vUnCom da NF-e. No Simples tradicional é o
  preço cobrado do cliente (CBS/IBS dentro do DAS); no híbrido, a CBS/IBS é cobrada por fora.
- Nenhum valor de tributo é calculado pelo backend: todos vêm dos motores (P1). O backend só soma,
  subtrai e calcula margens e preços com as fórmulas do ADR 0003.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Literal

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


class PremissasDas(_Modelo):
    """Linha de alíquotas efetivas do Simples do contribuinte (premissa rotulada, P8 e ADR 0001)."""

    anexo: Anexo
    cAtivSN: str = Field(pattern=r"^\d{2}$", description="Código de atividade do Simples (ex.: 01, revenda).")
    pCBSSN: Porcentagem = Field(ge=0, lt=100)
    pIBSSN: Porcentagem = Field(ge=0, lt=100)


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
        default=None, ge=0, description="Valor pago ao fornecedor por unidade, sem CBS/IBS por fora (vUnCom da compra)."
    )
    creditoCompraUnitario: Decimal | None = Field(
        default=None,
        ge=0,
        description="CBS + IBS da compra por unidade, lida do grupo IBSCBS da NF-e. Ausente: o backend calcula no "
        "motor RR sobre o custo, com a hipótese exibida de fornecedor no regime regular.",
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

    @model_validator(mode="after")
    def validar_das_no_tradicional(self) -> CarrinhoRequisicao:
        if self.regime == Regime.SIMPLES_TRADICIONAL and self.premissasDas is None:
            raise ValueError("No Simples tradicional informe premissasDas (alíquotas efetivas do anexo).")
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
    versoes: Versoes


# ---------------------------------------------------------------------------
# POST /item/preco-alvo


class PrecoAlvoRequisicao(_Operacao):
    regime: Regime
    item: ItemBase
    custoUnitario: Decimal = Field(ge=0)
    creditoCompraUnitario: Decimal | None = Field(default=None, ge=0)
    margemAlvoPct: Porcentagem = Field(gt=0, lt=100)


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
    chamadas: int
    metodo: Literal["afim", "bissecao"]
    memoria: dict[str, str] | None = None


# ---------------------------------------------------------------------------
# POST /regime/comparar


class ClienteB2B(_Modelo):
    nome: str
    regime: Literal["regime_regular"]


class RegimeCompararRequisicao(_Operacao):
    cliente: ClienteB2B
    itens: list[ItemEntrada] = Field(
        min_length=1,
        max_length=200,
        description="A venda. valorUnitario é o preço total cobrado do cliente (igual nos dois regimes).",
    )

    @model_validator(mode="after")
    def validar_das_obrigatorio(self) -> RegimeCompararRequisicao:
        if self.premissasDas is None:
            raise ValueError("Informe premissasDas: sem elas não há lado tradicional para comparar.")
        return self


class LadoTradicional(_Modelo):
    precoCliente: Decimal
    tributo: Decimal = Field(description="CBS + IBS dentro do DAS sobre a venda (motor SN).")
    creditoCliente: Decimal = Field(description="Igual ao tributo pago no Simples (LC 214/2025, art. 47, §9, II).")
    custoLiquidoCliente: Decimal


class LadoHibrido(_Modelo):
    precoCliente: Decimal
    valorProdutos: Decimal = Field(description="Base tal que valorProdutos + débito = preço total ao cliente.")
    debito: Decimal = Field(description="CBS + IBS por fora sobre a venda (motor RR).")
    creditoCompras: Decimal = Field(description="CBS + IBS das compras dos itens vendidos (NF-e ou motor RR).")
    tributoLiquido: Decimal = Field(description="debito − creditoCompras.")
    creditoCliente: Decimal = Field(description="Igual ao débito (crédito integral).")
    custoLiquidoCliente: Decimal


class RegimeCompararResposta(_Simulacao):
    criterio: Literal["mesmo_preco_total_ao_cliente"]
    cliente: ClienteB2B
    valorVenda: Decimal
    tradicional: LadoTradicional
    hibrido: LadoHibrido
    diferencaCaixa: Decimal = Field(
        description="Caixa no híbrido − caixa no tradicional = tributo tradicional − tributo líquido híbrido. "
        "Positivo: o híbrido deixa mais dinheiro com a empresa."
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
    numero: str
    dataEmissao: datetime
    emitente: Emitente
    temGrupoIbsCbs: bool


class ItemNotaCasado(_Modelo):
    itemId: str
    codigoFornecedor: str
    ncm: str
    descricaoNota: str
    quantidade: Decimal
    custoAnterior: Decimal | None
    custoNovo: Decimal
    variacaoPct: Porcentagem | None
    creditoCompraUnitario: Decimal | None
    fonteCredito: Literal["nfe", "motor"] | None


class ItemNotaSemPar(_Modelo):
    """Item que não casou com o catálogo: vira pergunta ao usuário (plano 11.3)."""

    codigoFornecedor: str
    ncm: str
    descricaoNota: str


class OrigemAlerta(_Modelo):
    tipo: Literal["nfe"]
    numero: str
    dataEmissao: datetime
    emitente: str


class Alerta(_Modelo):
    id: str
    itemId: str
    descricaoItem: str
    regime: Regime
    margemAntesPct: Porcentagem
    margemDepoisPct: Porcentagem
    margemAlvoPct: Porcentagem
    precoAtual: Decimal
    precoSugerido: Decimal
    origem: OrigemAlerta
    criadoEm: datetime


class NfeImportarResposta(_Modelo):
    nota: NotaResumo
    itensCasados: list[ItemNotaCasado]
    itensSemPar: list[ItemNotaSemPar]
    alertas: list[Alerta]


class AlertasResposta(_Modelo):
    alertas: list[Alerta]


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


class Fundamentacao(_Modelo):
    cClassTrib: str
    textoCurto: str
    texto: str
    referenciaNormativa: str


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


class ChatRequisicao(_Modelo):
    mensagens: list[MensagemChat] = Field(min_length=1, max_length=50)
    regime: Regime | None = None


class AcaoConfirmarClassificacao(_Modelo):
    """O cálculo só acontece depois que o usuário confirma (P3)."""

    tipo: Literal["confirmar_classificacao"]
    itemDescricao: str
    candidatos: list[CandidatoNcm]


class ChatResposta(_Modelo):
    resposta: str
    acoesPropostas: list[AcaoConfirmarClassificacao]
    ferramentasChamadas: list[str]
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
