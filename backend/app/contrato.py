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

import re
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

from app.cnpj import PADRAO_CNPJ
from app.contas.termos import VERSAO_TERMOS, conferir_versao

AVISO_LEGAL = "Estimativa baseada nas calculadoras oficiais. Não é parecer fiscal e não substitui o contador."

Anexo = Literal["I", "II", "III", "IV", "V"]
Porcentagem = Decimal

# Limites de sanidade das entradas (ADR 0011). Sem eles, "1e999999" no valor derrubava o cálculo com erro 500
# (o arredondamento ao centavo estoura), e "1e-999999" ia ao motor. As casas decimais seguem o leitor da NF-e
# (app/nfe/leitor.py: até 10 casas); o teto (R$ 1 bilhão por unidade, 1 bilhão de unidades, 1.000 pontos
# percentuais no IS) é escolha de projeto, não regra fiscal: só recusa número que nenhuma venda real tem.
TETO_ENTRADA = Decimal("1000000000")
ValorEntrada = Annotated[Decimal, Field(le=TETO_ENTRADA, decimal_places=10)]
QuantidadeEntrada = Annotated[Decimal, Field(le=TETO_ENTRADA, decimal_places=4)]
PorcentagemEntrada = Annotated[Decimal, Field(decimal_places=4)]


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

    cbs: PorcentagemEntrada = Field(ge=0, lt=100)
    ibsEstadual: PorcentagemEntrada = Field(ge=0, lt=100)
    ibsMunicipal: PorcentagemEntrada = Field(ge=0, lt=100)
    impostoSeletivoAdValorem: PorcentagemEntrada | None = Field(
        default=None,
        ge=0,
        le=1000,
        description="Exigida pelo motor para NCM sujeita ao IS, mesmo na revenda (REG-035).",
    )
    fonte: str | None = Field(
        default=None,
        max_length=200,
        description="De onde veio a premissa (ex.: o rótulo do preset escolhido). Sai impressa nas premissas.",
    )


class PremissasDas(_Modelo):
    """Linha de alíquotas efetivas do Simples do contribuinte (premissa rotulada, P8 e ADR 0001)."""

    anexo: Anexo
    cAtivSN: str = Field(pattern=r"^[0-9]{2}$", description="Código de atividade do Simples (ex.: 01, revenda).")
    pCBSSN: PorcentagemEntrada = Field(ge=0, lt=100)
    pIBSSN: PorcentagemEntrada = Field(ge=0, lt=100)
    fonte: str | None = Field(
        default=None,
        max_length=200,
        description="De onde veio a premissa (ex.: o rótulo do preset escolhido). Sai impressa nas premissas.",
    )


class ImpostoSeletivoEntrada(_Modelo):
    cst: str = Field(pattern=r"^[0-9]{3}$")
    cClassTrib: str = Field(pattern=r"^[0-9]{6}$")
    litrosPorUnidade: QuantidadeEntrada | None = Field(default=None, gt=0)


class ItemBase(_Modelo):
    """Produto já classificado e confirmado pelo usuário (P3)."""

    id: str = Field(min_length=1, max_length=64)
    descricao: str = Field(min_length=1, max_length=200)
    ncm: str | None = Field(default=None, pattern=r"^[0-9]{8}$")
    nbs: str | None = Field(default=None, pattern=r"^[0-9]{9}$")
    cst: str = Field(pattern=r"^[0-9]{3}$")
    cClassTrib: str = Field(pattern=r"^[0-9]{6}$")
    impostoSeletivo: ImpostoSeletivoEntrada | None = None
    unidade: str = Field(min_length=1, max_length=6)

    @model_validator(mode="after")
    def validar_ncm_ou_nbs(self) -> ItemBase:
        if (self.ncm is None) == (self.nbs is None):
            raise ValueError("Informe NCM ou NBS, nunca os dois.")
        return self


class ItemEntrada(ItemBase):
    quantidade: QuantidadeEntrada = Field(gt=0)
    valorUnitario: ValorEntrada = Field(gt=0, description="Valor do produto por unidade (vUnCom).")
    custoUnitario: ValorEntrada | None = Field(
        default=None,
        ge=0,
        description="Valor pago ao fornecedor por unidade, sem CBS/IBS por fora (vUnCom da compra). Ausente: sem margem.",
    )
    creditoCompraUnitario: ValorEntrada | None = Field(
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


class Operacao(_Modelo):
    data: date = Field(description="Data do fato gerador. Rege as vigências nos dois motores.")
    uf: str = Field(pattern=r"^[A-Z]{2}$")
    municipio: int = Field(description="Código IBGE do município.")
    aliquotasNominais: AliquotasNominais | None = None
    premissasDas: PremissasDas | None = None

    @model_validator(mode="after")
    def validar_premissas_por_ano(self) -> Operacao:
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


class CarrinhoRequisicao(Operacao):
    regime: Regime
    itens: list[ItemEntrada] = Field(min_length=1, max_length=200)
    cargaAtualPct: PorcentagemEntrada | None = Field(
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


class PrecoAlvoRequisicao(Operacao):
    regime: Regime
    item: ItemBase
    custoUnitario: ValorEntrada = Field(ge=0)
    creditoCompraUnitario: ValorEntrada | None = Field(
        default=None,
        ge=0,
        description="CBS + IBS da compra por unidade (grupo IBSCBS da NF-e). Só usada no Simples tradicional; "
        "ausente, vem do motor RR sobre o custo, com a hipótese exibida.",
    )
    margemAlvoPct: PorcentagemEntrada = Field(gt=0, lt=100)

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


class RegimeCompararRequisicao(Operacao):
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


CausaSemPar = Literal["semCadastro", "repetido", "ncm", "unidade", "monofasico"]


class ItemNotaSemPar(_Modelo):
    """Item que não casou com o catálogo: vira pergunta ao usuário (plano 11.3). Desde a C3b, o recibo guarda também
    a unidade, a quantidade, o custo e o crédito da linha, para o item ser cadastrado a partir da nota com o custo
    dela (POST /catalogo/itens com `daNota`). Nos recibos anteriores, esses campos ficam vazios."""

    nItem: int | None = None
    codigoFornecedor: str
    ncm: str
    descricaoNota: str = Field(description="xProd da nota: texto do fornecedor, tratado como dado não confiável.")
    motivo: str | None = Field(default=None, description="Por que não casou (código sem cadastro, NCM ou unidade).")
    causa: CausaSemPar | None = Field(
        default=None,
        description="semCadastro: o código deste fornecedor não está no catálogo (o único caso que se cadastra a "
        "partir da nota); repetido, ncm, unidade e monofasico: o item existe, ou a tributação não é suportada. Vazio "
        "nos recibos anteriores à C3b.",
    )
    unidade: str | None = Field(default=None, description="uCom da nota, em maiúsculas.")
    quantidade: Decimal | None = Field(default=None, description="qCom da nota.")
    custoUnitario: Decimal | None = Field(default=None, description="vUnCom da nota.")
    valorTotal: Decimal | None = Field(default=None, description="vProd da nota.")
    creditoCompraUnitario: Decimal | None = Field(
        default=None, description="Do grupo IBSCBS da linha (vCBS + vIBS ÷ qCom); vazio sem o grupo."
    )
    itemCadastrado: str | None = Field(
        default=None, description="Id do item cadastrado a partir desta linha (o custo dela entrou no histórico)."
    )


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


class CenarioEmpresa(_Modelo):
    """O cenário que a empresa usa em todo cálculo: o mesmo dos alertas (ADR 0011). A tela monta o carrinho,
    o preço-alvo, a comparação de regimes, a explicação e o contexto do chat com `operacao`, sem repetir
    nenhuma alíquota no próprio código (P6: são premissas, impressas nas respostas)."""

    descricao: str = Field(description='Ex.: "Simulação de março de 2027".')
    operacao: Operacao
    cargaAtualPct: Porcentagem | None = Field(
        default=None, description="Carga atual informada pelo usuário, só como número de comparação."
    )


class ItemCompraMensal(_Modelo):
    itemId: str
    quantidade: Decimal = Field(gt=0)


class ClienteB2BEstado(_Modelo):
    """Um cliente empresa e a compra mensal dele: a venda que a decisão de regime compara (E3, ADR 0011)."""

    cnpj: str
    nome: str
    regime: Literal["regime_regular"]
    uf: str
    municipio: int
    compraMensalDescricao: str
    compraMensal: list[ItemCompraMensal]


class CatalogoResposta(_Modelo):
    empresa: EmpresaResumo
    cenario: CenarioEmpresa
    clientesB2B: list[ClienteB2BEstado] = Field(
        description="Clientes empresa desta empresa (fictícios na demonstração)."
    )
    loteReferencia: int = Field(
        description="Unidades por cálculo de item no catálogo, na explicação e no preço-alvo (CBS/IBS a cada "
        "N unidades). A tela usa este número, nunca uma cópia própria."
    )
    itens: list[ItemCatalogoEstado]
    aviso: str = Field(
        description="Na demonstração e nos espaços, dados fictícios (P10); na empresa da conta, o aviso de simulação."
    )


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


# ---------------------------------------------------------------------------
# GET /notas (E5, PR 3b)


class NotaImportada(_Modelo):
    """Uma NF-e de compra já importada. O resumo e as contagens de itens vêm do recibo gravado na importação;
    as de alertas, do estado atual (um alerta aplicado depois deixa de contar como aberto)."""

    nota: NotaResumo
    importadaEm: datetime = Field(description="Quando a nota entrou no sistema (UTC).")
    itensCasados: int = Field(ge=0)
    itensSemPar: int = Field(ge=0, description="Itens sem par que ainda não foram cadastrados a partir da nota.")
    alertasGerados: int = Field(ge=0)
    alertasAbertos: int = Field(ge=0, description="Alertas desta nota ainda sem o preço sugerido aplicado.")


class NotasResposta(_Modelo):
    """Notas de compra da empresa, da emissão mais recente para a mais antiga."""

    empresa: EmpresaResumo
    notas: list[NotaImportada]
    aviso: str = Field(
        description="Na demonstração e nos espaços, dados fictícios (P10); na empresa da conta, o aviso de simulação."
    )


class EspacoResposta(_Modelo):
    """Espaço de avaliação (ADR 0010): cópia própria dos dados fictícios da demonstração. Envie `id` no header
    X-ContaAI-Espaco nas rotas de notas, alertas, catálogo, painel, restauração e chat. O id é a chave do espaço:
    guarde-o só no navegador de quem avalia."""

    id: str = Field(pattern=r"^[0-9a-f]{32}$")
    criadoEm: datetime
    expiraEm: datetime
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


class ExplicarRequisicao(Operacao):
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


class ContextoChat(Operacao):
    """O que a tela já sabe: a operação, o regime e os itens que o usuário já confirmou (P3).

    O backend não guarda estado: a cada mensagem a tela manda o contexto. O agente só calcula os
    itens daqui, pelo id; um item que só aparece no texto da conversa precisa ser confirmado antes.
    """

    regime: Regime
    itens: list[ItemEntrada] = Field(default=[], max_length=200)
    cnpj: str | None = Field(
        default=None, pattern=PADRAO_CNPJ, description="Empresa da tela: os alertas do chat são os dela (E4)."
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
# POST /catalogo/{itemId}/preco e POST /catalogo/{itemId}/classificacao (E5, ADR 0011)

# Id de item do catálogo (data/demo): vai no caminho das rotas do catálogo, por isso só letras minúsculas,
# dígitos e hífen. Os itens que a tela cadastra pelo chat (ItemBase.id) não passam por estas rotas.
PADRAO_ID_ITEM = r"^[a-z0-9][a-z0-9-]{0,63}$"


class AplicarPrecoRequisicao(_Modelo):
    """Preço de venda novo, escolhido pelo usuário na tela (ex.: a ação "aplicar_preco" do chat, P3)."""

    cnpj: str = Field(pattern=PADRAO_CNPJ)
    valorUnitario: Decimal = Field(
        gt=0, le=TETO_ENTRADA, decimal_places=2, description="Valor do produto por unidade (vUnCom), em centavos."
    )


class AplicarPrecoResposta(_Modelo):
    """O preço virou o preço de venda do item (lançamento de preço com origem na tela). Alertas abertos do
    item continuam abertos: eles fecham só pelo POST /alertas/{id}/aplicar."""

    itemId: str
    precoAnterior: Decimal
    precoNovo: Decimal
    vigenteDesde: datetime


class CorrigirClassificacaoRequisicao(_Modelo):
    """A classificação que o usuário confirmou (P3). O CST não vem da tela: o backend usa o da fundamentação
    oficial da classificação escolhida, e só aceita uma classificação válida para a NCM do item."""

    cnpj: str = Field(pattern=PADRAO_CNPJ)
    cClassTrib: str = Field(pattern=r"^[0-9]{6}$")


class CorrigirClassificacaoResposta(_Modelo):
    cstAnterior: str
    cClassTribAnterior: str
    classificacao: ClassificacaoCandidata
    item: ItemCatalogoEstado
    vigenteDesde: datetime


# ---------------------------------------------------------------------------
# Erros: Problem Details da RFC 9457 (application/problem+json), ADR 0009


class Problema(_Modelo):
    """Corpo de toda resposta de erro (4xx e 5xx). `type` identifica o problema: "about:blank" quando o
    código HTTP basta (title = frase do código), ou /problemas/<nome> (GET nesse caminho descreve o tipo).
    `detail` é para a pessoa ler, não para o frontend interpretar. Nunca traz URL, host, caminho do
    servidor nem corpo dos motores ou do provedor de IA."""

    type: str = Field(default="about:blank", description="URI do tipo do problema (relativa à API).")
    title: str = Field(description="Resumo do tipo do problema; não muda entre ocorrências.")
    status: int = Field(description="O mesmo código HTTP da resposta.")
    detail: str | None = Field(default=None, description="Explicação desta ocorrência, para a pessoa ler.")


OrigemCampo = Literal["body", "query", "path", "header", "cookie"]


class CampoInvalido(_Modelo):
    origem: OrigemCampo
    campo: str = Field(description='JSON Pointer do campo dentro da origem (ex.: "#/itens/0/ncm"); "#" = inteiro.')
    detalhe: str


class ProblemaValidacao(Problema):
    """422 /problemas/entrada-invalida: a requisição não passou na validação do contrato."""

    campos: list[CampoInvalido]


class ProblemaMotor(Problema):
    """Falha de um motor oficial: 422 /problemas/motor-recusou (com os erros do motor, ex.: VSN-015),
    502 /problemas/motor-resposta-invalida ou 503 /problemas/motor-indisponivel."""

    motor: Motor
    erros: list[ErroMotor] = []


class ProblemaCalculo(Problema):
    """422 /problemas/calculo-recusado: o cálculo pedido não tem resposta (margem impossível, item que o
    motor não calcula, preço-alvo que não converge). Traz os erros do motor quando eles explicam a recusa."""

    erros: list[ErroMotor] = []


class ClienteQueCompra(_Modelo):
    cnpj: str
    nome: str


class ProblemaItemEmUso(Problema):
    """409 /problemas/item-em-uso: o item está na compra mensal de clientes B2B e não pode sair do catálogo (C3-B,
    ADR 0017). `clientes` diz quais, para a tela levar a pessoa até eles."""

    clientes: list[ClienteQueCompra]


class TipoProblema(_Modelo):
    """Descrição de um tipo de problema (GET /problemas/{nome}), como pede a RFC 9457 para tipos novos."""

    type: str
    title: str
    status: list[int] = Field(description="Códigos HTTP em que o tipo aparece.")
    descricao: str


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


# ---------------------------------------------------------------------------
# Contas (C1, ADR 0015): cadastro com segundo fator (TOTP), entrada em duas etapas, sessão em cookie e exclusão.
# A sessão e o passe vão só em cookies HttpOnly; nenhum token aparece no corpo.

PADRAO_EMAIL = r"^[^@\s:]{1,64}@[^@\s:]+\.[^@\s:]+$"
PADRAO_CODIGO = r"^[0-9]{6}$"
PADRAO_RECUPERACAO = r"^[A-Za-z2-7]{4}-?[A-Za-z2-7]{4}-?[A-Za-z2-7]{5}$"
Email = Annotated[str, Field(pattern=PADRAO_EMAIL, max_length=254, description="E-mail de quem entra.")]
# O teto do contrato só evita corpo absurdo; a regra (8 a 128 caracteres, lista de senhas comuns) fica em
# app/contas/senha.py e responde com a frase dela.
SenhaEntrada = Annotated[str, Field(min_length=1, max_length=256)]


def _nome_com_texto(nome: str) -> str:
    """O nome sem os espaços das pontas (str.strip, que tira também os de Unicode). Só com espaços, ele ficaria
    vazio e passaria pelo min_length, que confere antes: a organização nasceria sem nome (achado da C2b)."""
    limpo = nome.strip()
    if not limpo:
        raise ValueError("Informe o nome da organização.")
    return limpo


NomeDaOrganizacao = Annotated[
    str,
    Field(min_length=1, max_length=120, description="Nome da organização (escritório ou empresa)."),
    AfterValidator(_nome_com_texto),
]
# A versão dos termos que a pessoa aceitou ao marcar a caixa do cadastro. O enum leva a versão ao tipo gerado da
# tela; o validador dá a frase em português para uma aba aberta com a versão antiga.
TermosAceitos = Annotated[
    str,
    AfterValidator(conferir_versao),
    Field(
        json_schema_extra={"enum": [VERSAO_TERMOS]},
        description="A versão dos termos de uso aceita ao marcar a caixa do cadastro (a atual, e só ela).",
    ),
]


class CadastroRequisicao(_Modelo):
    email: Email
    senha: SenhaEntrada = Field(
        description="De 8 a 128 caracteres, sem regra de composição. Senhas comuns, o "
        "e-mail e o nome do produto são recusados."
    )
    organizacao: NomeDaOrganizacao
    termosAceitos: TermosAceitos


class CadastroResposta(_Modelo):
    """O segredo do segundo fator. A conta só vale depois de POST /contas/ativar com o primeiro código, dentro de
    `expiraEm` (o passe vai no cookie)."""

    otpauth: str = Field(description="Endereço otpauth:// para o QR code do aplicativo autenticador.")
    segredo: str = Field(description="O mesmo segredo, em base32, para digitar à mão no aplicativo.")
    expiraEm: datetime
    aviso: str


class CodigoRequisicao(_Modelo):
    codigo: str = Field(pattern=PADRAO_CODIGO, description="Os 6 dígitos do aplicativo autenticador.")


class EntrarRequisicao(_Modelo):
    email: Email
    senha: SenhaEntrada


class EntrarResposta(_Modelo):
    """Senha certa: falta o código (POST /sessoes/codigo, com o passe que foi no cookie)."""

    etapa: Literal["codigo"]
    expiraEm: datetime


class EntrarAtivacaoResposta(_Modelo):
    """Senha certa numa conta que ainda não confirmou o primeiro código: um segredo novo do segundo fator e o passe
    da ativação no cookie. O próximo passo é POST /contas/ativar, como no cadastro. O segredo antigo deixa de
    valer."""

    etapa: Literal["ativacao"]
    otpauth: str = Field(description="Endereço otpauth:// para o QR code do aplicativo autenticador.")
    segredo: str = Field(description="O mesmo segredo, em base32, para digitar à mão no aplicativo.")
    expiraEm: datetime
    aviso: str


RespostaDaEntrada = Annotated[EntrarResposta | EntrarAtivacaoResposta, Field(discriminator="etapa")]


class SegundaEtapaRequisicao(_Modelo):
    codigo: str | None = Field(default=None, pattern=PADRAO_CODIGO, description="Código do aplicativo.")
    codigoRecuperacao: str | None = Field(
        default=None, pattern=PADRAO_RECUPERACAO, description="Um dos códigos de recuperação (uso único)."
    )

    @model_validator(mode="after")
    def um_dos_dois(self) -> SegundaEtapaRequisicao:
        if (self.codigo is None) == (self.codigoRecuperacao is None):
            raise ValueError("Envie o código do aplicativo ou um código de recuperação (um dos dois).")
        return self


class OrganizacaoDaConta(_Modelo):
    id: str
    nome: str
    papel: Literal["dono", "membro"]


class EventoSeguranca(_Modelo):
    tipo: Literal["codigo-recuperacao-usado"]
    em: datetime


class TermosDaConta(_Modelo):
    versao: str
    aceitosEm: datetime


class ContaResposta(_Modelo):
    email: str
    criadaEm: datetime
    organizacao: OrganizacaoDaConta
    termos: TermosDaConta | None = Field(
        description="A versão dos termos de uso aceita no cadastro e quando. Vazio para conta de antes do aceite."
    )
    empresas: list[str] = Field(description="CNPJs que a organização acessa (a C3 cadastra a empresa própria).")
    codigosRecuperacaoRestantes: int
    eventos: list[EventoSeguranca] = Field(description="Os mais recentes primeiro (ex.: código de recuperação usado).")
    sessaoExpiraEm: datetime = Field(description="Limite total da sessão (8 h). Sem uso por 30 min, ela acaba antes.")


class AtivacaoResposta(_Modelo):
    conta: ContaResposta
    codigosRecuperacao: list[str] = Field(description="Mostrados uma vez só. Cada um vale uma vez.")
    aviso: str


class SegundaEtapaResposta(_Modelo):
    conta: ContaResposta
    novoCodigoRecuperacao: str | None = Field(
        default=None, description="Com um código de recuperação: o código que entra no lugar dele (mostrado uma vez)."
    )
    aviso: str | None = None


class ExcluirContaRequisicao(_Modelo):
    senha: SenhaEntrada


# ---------------------------------------------------------------------------
# Empresa própria (C3-B, ADR 0017): cadastro, configurações e catálogo editável. Os dados de referência (UF, município
# e atividade do Simples) vêm dos motores oficiais, na versão fixada (P5).

_CONTROLE = re.compile(r"[\x00-\x1f\x7f]")


def _texto_de_cadastro(texto: str) -> str:
    """Sem os espaços das pontas e sem caractere de controle (o mesmo cuidado do leitor da NF-e)."""
    limpo = texto.strip()
    if not limpo:
        raise ValueError("Preencha este campo.")
    if _CONTROLE.search(limpo):
        raise ValueError("Use só texto, sem caracteres de controle.")
    return limpo


RazaoSocial = Annotated[
    str, Field(min_length=1, max_length=150, description="Razão social da empresa."), AfterValidator(_texto_de_cadastro)
]
DescricaoDoItem = Annotated[
    str,
    Field(min_length=1, max_length=200, description="Como a empresa chama o produto."),
    AfterValidator(_texto_de_cadastro),
]
CodigoDoFornecedor = Annotated[
    str,
    Field(min_length=1, max_length=60, description="cProd do item na NF-e do fornecedor (casa a nota com o item)."),
    AfterValidator(_texto_de_cadastro),
]
CnpjEmpresa = Annotated[
    str,
    Field(
        pattern=PADRAO_CNPJ,
        description="14 posições, sem pontos, barra nem traço: as 12 primeiras com dígitos ou letras maiúsculas "
        "(CNPJ alfanumérico, IN RFB 2.229/2024) e as 2 últimas com os dígitos verificadores.",
    ),
]
RegimeDoSimples = Literal["simples_tradicional", "simples_hibrido"]
Municipio = Annotated[int, Field(ge=1000000, le=9999999, description="Código IBGE do município (7 dígitos).")]
Uf = Annotated[str, Field(pattern=r"^[A-Z]{2}$", description="Sigla da UF.")]
CodigoAtividade = Annotated[
    str, Field(pattern=r"^[0-9]{2}$", description="Código da atividade do Simples (GET /referencias/atividades).")
]
PrecoDeVenda = Annotated[
    Decimal, Field(gt=0, le=TETO_ENTRADA, decimal_places=2, description="Preço de venda por unidade (vUnCom).")
]
MargemAlvo = Annotated[
    Decimal, Field(gt=0, lt=100, decimal_places=4, description="Margem que a empresa quer no item, em %.")
]


class UfReferencia(_Modelo):
    sigla: str
    nome: str
    codigo: int


class UfsResposta(_Modelo):
    ufs: list[UfReferencia]
    fonte: str


class MunicipioReferencia(_Modelo):
    codigo: int = Field(description="Código IBGE.")
    nome: str


class MunicipiosResposta(_Modelo):
    uf: str
    municipios: list[MunicipioReferencia]
    fonte: str


class AtividadeSimples(_Modelo):
    cAtivSN: str
    descricao: str
    anexo: Anexo


class AtividadesResposta(_Modelo):
    """As atividades do Simples que o ContaAI calcula: admissíveis na NF-e (modelo 55), disponíveis na data do
    cenário, com anexo e sem fator R."""

    data: date
    atividades: list[AtividadeSimples]
    fonte: str


class EmpresaCadastroRequisicao(_Modelo):
    """A empresa da conta. O nome do município e o anexo da atividade vêm dos motores, nunca da tela."""

    cnpj: CnpjEmpresa
    razaoSocial: RazaoSocial
    regimeAtual: RegimeDoSimples
    uf: Uf
    municipio: Municipio
    cAtivSN: CodigoAtividade


class PremissasDasDaEmpresa(_Modelo):
    """As alíquotas efetivas de CBS e de IBS do Simples, da apuração da própria empresa (P8)."""

    pCBSSN: PorcentagemEntrada = Field(ge=0, lt=100)
    pIBSSN: PorcentagemEntrada = Field(ge=0, lt=100)


class EmpresaConfiguracaoRequisicao(_Modelo):
    """Só os campos enviados mudam. O CNPJ não muda: outro CNPJ é outra empresa. `premissasDas: null` volta aos
    valores da simulação; `cargaAtualPct: null` apaga a carga informada."""

    razaoSocial: RazaoSocial | None = None
    regimeAtual: RegimeDoSimples | None = None
    uf: Uf | None = None
    municipio: Municipio | None = None
    cAtivSN: CodigoAtividade | None = None
    premissasDas: PremissasDasDaEmpresa | None = None
    cargaAtualPct: PorcentagemEntrada | None = Field(default=None, ge=0, lt=100)

    @model_validator(mode="after")
    def conferir(self) -> EmpresaConfiguracaoRequisicao:
        enviados = self.model_fields_set
        if not enviados:
            raise ValueError("Envie ao menos um campo para mudar.")
        if ("uf" in enviados) != ("municipio" in enviados):
            raise ValueError("Envie a UF e o município juntos.")
        obrigatorios = {"razaoSocial", "regimeAtual", "uf", "municipio", "cAtivSN"}
        if any(getattr(self, campo) is None for campo in enviados & obrigatorios):
            raise ValueError("Só premissasDas e cargaAtualPct aceitam null.")
        return self


class AtividadeDaEmpresa(AtividadeSimples):
    fonte: str


class EmpresaResposta(_Modelo):
    empresa: EmpresaResumo
    atividade: AtividadeDaEmpresa
    cenario: CenarioEmpresa
    premissasDasOrigem: Literal["simulacao", "usuario"] = Field(
        description="simulacao: valores de exemplo, rotulados; usuario: informados nas configurações."
    )
    aviso: str


class ParDaNota(_Modelo):
    """A linha da nota de onde o item nasce. A nota é a do fornecedor do item, com esta série e este número."""

    serie: str = Field(pattern=r"^[0-9]{1,3}$")
    numero: str = Field(pattern=r"^[1-9][0-9]{0,8}$")
    nItem: int = Field(ge=1, le=990, description="nItem da linha (de 1 a 990, leiaute da NF-e 4.00).")


class ItemNovoRequisicao(_Modelo):
    """Um item novo no catálogo. A classificação precisa ser uma das válidas para a NCM nos dados abertos do motor
    RR (GET /busca/ncm), e o CST é o da fundamentação oficial, como na correção (P3)."""

    cnpj: CnpjEmpresa
    descricao: DescricaoDoItem
    ncm: str = Field(pattern=r"^[0-9]{8}$")
    cClassTrib: str = Field(pattern=r"^[0-9]{6}$")
    unidade: Literal["UN", "KG"]
    cnpjFornecedor: CnpjEmpresa
    codigoFornecedor: CodigoDoFornecedor
    precoVenda: PrecoDeVenda
    margemAlvoPct: MargemAlvo
    daNota: ParDaNota | None = Field(
        default=None,
        description="O item nasce de uma linha sem par de uma nota já importada (do fornecedor `cnpjFornecedor`): o "
        "custo daquela linha entra no histórico. O código, a NCM e a unidade precisam ser os da linha.",
    )


class ItemAlteracaoRequisicao(_Modelo):
    """Só os campos enviados mudam. NCM e unidade não mudam (o histórico de custo é dessa NCM e dessa unidade): um
    item com outra NCM é outro item. Preço e classificação têm rotas próprias, com o histórico."""

    cnpj: CnpjEmpresa
    descricao: DescricaoDoItem | None = None
    margemAlvoPct: MargemAlvo | None = None
    cnpjFornecedor: CnpjEmpresa | None = None
    codigoFornecedor: CodigoDoFornecedor | None = None

    @model_validator(mode="after")
    def conferir(self) -> ItemAlteracaoRequisicao:
        enviados = self.model_fields_set - {"cnpj"}
        if not enviados:
            raise ValueError("Envie ao menos um campo para mudar.")
        if ("cnpjFornecedor" in enviados) != ("codigoFornecedor" in enviados):
            raise ValueError("Envie o CNPJ e o código do fornecedor juntos.")
        if any(getattr(self, campo) is None for campo in enviados):
            raise ValueError("Os campos enviados não aceitam null.")
        return self


class ItemArquivarRequisicao(_Modelo):
    cnpj: CnpjEmpresa


class ItemResposta(_Modelo):
    item: ItemCatalogoEstado


class ItemArquivadoResposta(_Modelo):
    """O item saiu do catálogo; custos, preços, classificações e alertas dele ficam no histórico."""

    itemId: str
    arquivadoEm: datetime


# Clientes B2B (C3-B, etapa 6): os clientes empresa e a compra mensal de cada um, a venda que a comparação de regimes
# usa (ClienteB2BEstado). A compra mensal cabe numa comparação: o mesmo teto de itens do POST /regime/comparar.

RegimeDoCliente = Literal["regime_regular", "simples_nacional"]
QuantidadeDaCompra = Annotated[
    Decimal, Field(gt=0, le=TETO_ENTRADA, decimal_places=4, description="Quantidade por mês, na unidade do item.")
]


class ItemDaCompraMensal(_Modelo):
    itemId: str = Field(pattern=PADRAO_ID_ITEM, description="Id de um item do catálogo da empresa.")
    quantidade: QuantidadeDaCompra


def _itens_sem_repeticao(compra: list[ItemDaCompraMensal]) -> list[ItemDaCompraMensal]:
    ids = [i.itemId for i in compra]
    if len(set(ids)) != len(ids):
        raise ValueError("Cada item entra uma vez na compra mensal.")
    return compra


CompraMensalEntrada = Annotated[
    list[ItemDaCompraMensal],
    Field(min_length=1, max_length=200, description="O que o cliente compra num mês; cada item entra uma vez."),
    AfterValidator(_itens_sem_repeticao),
]


class ClienteNovoRequisicao(_Modelo):
    """Um cliente empresa da empresa `cnpj`. A comparação de regimes é feita na venda a um cliente do regime
    regular: um cliente do Simples Nacional é recusado (422)."""

    cnpj: CnpjEmpresa = Field(description="A empresa que vende.")
    cnpjCliente: CnpjEmpresa
    razaoSocial: RazaoSocial
    regime: RegimeDoCliente
    uf: Uf
    municipio: Municipio
    compraMensal: CompraMensalEntrada


class ClienteAlteracaoRequisicao(_Modelo):
    """Só os campos enviados mudam. O CNPJ do cliente não muda: outro CNPJ é outro cliente."""

    cnpj: CnpjEmpresa = Field(description="A empresa que vende.")
    razaoSocial: RazaoSocial | None = None
    uf: Uf | None = None
    municipio: Municipio | None = None
    compraMensal: CompraMensalEntrada | None = None

    @model_validator(mode="after")
    def conferir(self) -> ClienteAlteracaoRequisicao:
        enviados = self.model_fields_set - {"cnpj"}
        if not enviados:
            raise ValueError("Envie ao menos um campo para mudar.")
        if ("uf" in enviados) != ("municipio" in enviados):
            raise ValueError("Envie a UF e o município juntos.")
        if any(getattr(self, campo) is None for campo in enviados):
            raise ValueError("Os campos enviados não aceitam null.")
        return self


class ClienteExcluirRequisicao(_Modelo):
    cnpj: CnpjEmpresa = Field(description="A empresa que vende.")


class ClienteResposta(_Modelo):
    cliente: ClienteB2BEstado


class ClienteExcluidoResposta(_Modelo):
    """O cliente saiu de vez: o ContaAI não guarda histórico de clientes."""

    cnpjCliente: str
    excluidoEm: datetime


# ---------------------------------------------------------------------------
# Dados e exclusão (C3-B, etapa 7; LGPD, arts. 18 II, V e VI, e 19): o arquivo com os dados da conta e das empresas
# da organização, e excluir a empresa sem excluir a conta.

DocumentoGravado = dict[str, Any]
"""Um documento JSON como está gravado no banco (empresa, cenário, item, cliente, alerta ou recibo), sem
transformação: o arquivo é a cópia do que o ContaAI guarda."""


class ContaDadosRequisicao(_Modelo):
    """O arquivo leva tudo o que a conta guarda: a senha de novo, como na exclusão da conta."""

    senha: SenhaEntrada


class EmpresaExcluirRequisicao(_Modelo):
    """Excluir a empresa é definitivo: a senha de novo e o CNPJ digitado para confirmar."""

    senha: SenhaEntrada
    cnpjConfirmacao: CnpjEmpresa = Field(description="O CNPJ da empresa, digitado de novo (o mesmo do caminho).")


class SessaoExportada(_Modelo):
    criadaEm: datetime
    ultimoUso: datetime
    expiraEm: datetime
    atual: bool = Field(description="A sessão que pediu o arquivo.")


class TentativasExportadas(_Modelo):
    falhasSeguidas: int
    esperaAte: datetime | None
    bloqueada: bool


class DadosDaPessoa(_Modelo):
    email: str
    criadaEm: datetime
    situacao: Literal["pendente", "ativa"]
    termos: TermosDaConta | None
    segundoFatorConfirmadoEm: datetime | None
    codigosRecuperacaoRestantes: int = Field(description="Só a quantidade: os códigos não ficam guardados.")
    tentativas: TentativasExportadas | None = Field(description="Falhas seguidas de entrada, se houver.")
    eventos: list[EventoSeguranca] = Field(description="Todos, os mais recentes primeiro.")
    sessoes: list[SessaoExportada]


class ItemExportado(_Modelo):
    itemId: str
    ncm: str
    unidade: str
    arquivadoEm: datetime | None
    item: DocumentoGravado


class CodigoFornecedorExportado(_Modelo):
    cnpjFornecedor: str
    codigo: str
    itemId: str


class NotaExportada(_Modelo):
    """A nota importada: o ContaAI não guarda o XML, só o resumo dele (sha256) e o recibo da importação."""

    id: int
    cnpjEmitente: str
    serie: str
    numero: str
    dataEmissao: datetime
    sha256: str
    importadaEm: datetime
    recibo: DocumentoGravado


class CustoExportado(_Modelo):
    id: int
    itemId: str
    notaId: int
    data: datetime
    quantidade: Decimal
    custoUnitario: Decimal
    creditoUnitario: Decimal | None
    fonteCredito: Literal["nfe", "motor"] | None


class PrecoExportado(_Modelo):
    id: int
    itemId: str
    valorUnitario: Decimal
    vigenteDesde: datetime
    origem: Literal["semente", "alerta", "tela"]
    alertaId: str | None


class AlertaExportado(_Modelo):
    id: str
    itemId: str
    notaId: int
    criadoEm: datetime
    aplicadoEm: datetime | None
    alerta: DocumentoGravado


class ClassificacaoExportada(_Modelo):
    id: int
    itemId: str
    cst: str
    cClassTrib: str
    fonte: str
    vigenteDesde: datetime
    origem: Literal["tela"]


class ClienteExportado(_Modelo):
    cnpjCliente: str
    cliente: DocumentoGravado = Field(description="Com a razão social do cliente, que pode ser dado pessoal.")


class EmpresaExportada(_Modelo):
    """Uma empresa da organização. `empresa` vazio: o acesso ficou sem a empresa no banco (uma falha no meio de
    uma exclusão); o recadastro aceita esse caso."""

    cnpj: str
    acessoDesde: datetime
    empresa: DocumentoGravado | None
    cenario: DocumentoGravado | None
    itens: list[ItemExportado] = Field(description="Inclusive os arquivados.")
    codigosFornecedor: list[CodigoFornecedorExportado]
    notas: list[NotaExportada]
    custos: list[CustoExportado]
    precos: list[PrecoExportado]
    alertas: list[AlertaExportado]
    classificacoes: list[ClassificacaoExportada]
    clientesB2B: list[ClienteExportado]


class OrganizacaoExportada(_Modelo):
    """Uma organização da pessoa, com as empresas dela. Os outros integrantes não aparecem (nem o e-mail deles)."""

    id: str
    nome: str
    criadaEm: datetime
    papel: Literal["dono", "membro"]
    desde: datetime
    empresas: list[EmpresaExportada]


class ContaDadosResposta(_Modelo):
    """A cópia dos dados (LGPD, art. 19, I e §3º): em formato simplificado, na hora, e num formato que permite
    usar de novo (JSON). Não leva a senha, o segredo do segundo fator nem nenhum hash de senha, token ou código."""

    formato: Literal["contaai-dados-1"] = Field(description="Versão do formato deste arquivo.")
    geradoEm: datetime
    conta: DadosDaPessoa
    organizacoes: list[OrganizacaoExportada]
    naoIncluido: list[str] = Field(description="O que o ContaAI guarda e não vai no arquivo, e por quê.")
    aviso: str
