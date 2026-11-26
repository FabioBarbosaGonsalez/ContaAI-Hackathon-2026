// Os pedidos de cálculo montados só com o que o GET /catalogo devolveu (ADR 0011).
//
// Nenhuma alíquota, data ou premissa fica escrita na tela (P6): tudo vem de `cenario.operacao`. O lote de
// cada linha é `loteReferencia`, o mesmo da explicação e do preço-alvo. A conta é a do teste do backend
// test_tela.py::entrada, que confere a margem refeita pela tela contra a do alerta.

import type { components } from '../api/esquema.gen.ts';

export type Esquemas = components['schemas'];
export type Catalogo = Esquemas['CatalogoResposta'];
export type ItemCatalogo = Esquemas['ItemCatalogoEstado'];
export type Carrinho = Esquemas['CarrinhoResposta'];
export type ItemCalculado = Esquemas['ItemCalculado'];
export type Regime = Esquemas['Regime'];
export type Alerta = Esquemas['Alerta'];
export type ErroMotor = Esquemas['ErroMotor'];
export type Premissa = Esquemas['Premissa'];
export type Explicacao = Esquemas['ExplicarResposta'];
export type Candidata = Esquemas['ClassificacaoCandidata'];
export type ReciboNota = Esquemas['NfeImportarResposta'];
export type Notas = Esquemas['NotasResposta'];
export type NotaImportada = Esquemas['NotaImportada'];
export type ClienteB2B = Esquemas['ClienteB2BEstado'];
export type PedidoDeRegime = Esquemas['RegimeCompararRequisicao'];
export type Comparacao = Esquemas['RegimeCompararResposta'];

type ItemCarrinho = Esquemas['CarrinhoRequisicao']['itens'][number];

/** Tira os campos vazios: a API recusa `null` onde o campo é opcional só por omissão. */
function semVazios<T extends object>(objeto: T): T {
  return Object.fromEntries(Object.entries(objeto).filter(([, v]) => v !== null && v !== undefined)) as T;
}

/** O item do catálogo como linha do carrinho, na quantidade pedida e ao preço de venda atual. */
export function linhaDoItem(item: ItemCatalogo, quantidade: string | number): ItemCarrinho {
  const linha: ItemCarrinho = {
    id: item.id,
    descricao: item.descricao,
    cst: item.cst,
    cClassTrib: item.cClassTrib,
    unidade: item.unidade,
    quantidade: String(quantidade),
    valorUnitario: item.precoVenda,
  };
  // Os opcionais só vão quando têm valor (o contrato não aceita `undefined`).
  if (item.ncm) {
    linha.ncm = item.ncm;
  }
  if (item.nbs) {
    linha.nbs = item.nbs;
  }
  if (item.impostoSeletivo) {
    linha.impostoSeletivo = item.impostoSeletivo;
  }
  const custo = item.custoAtual;
  if (custo) {
    linha.custoUnitario = custo.custoUnitario;
    if (custo.creditoCompraUnitario !== null) {
      linha.creditoCompraUnitario = custo.creditoCompraUnitario;
    }
  }
  return linha;
}

/** O carrinho do catálogo inteiro, um lote de referência por item, no regime pedido. */
export function pedidoDoCatalogo(catalogo: Catalogo, regime: Regime): Esquemas['CarrinhoRequisicao'] {
  return {
    ...semVazios(catalogo.cenario.operacao),
    regime,
    itens: catalogo.itens.map((item) => linhaDoItem(item, catalogo.loteReferencia)),
  };
}

/** A data do cenário é anterior a 2027: não há lado tradicional para comparar (VSN-015, ADR 0007). */
export function antesDaComparacao(catalogo: Catalogo): boolean {
  return Number(catalogo.cenario.operacao.data.slice(0, 4)) < 2027;
}

/**
 * A venda mensal ao cliente empresa, como o catálogo a descreve (`compraMensal`), ao preço de venda atual
 * e com o custo da última nota de cada item (teste do backend test_tela.py::entrada).
 *
 * O crédito por unidade só vai quando veio do grupo IBSCBS da nota (`fonteCredito: 'nfe'`), que é o que o
 * contrato define para `creditoCompraUnitario`. O crédito que o motor calculou numa nota sem o grupo fica
 * de fora: o backend o refaz sobre o custo e responde `fonteCredito: 'motor'`, com a hipótese impressa.
 * Mandar esse crédito faria a comparação dizer que ele foi lido da nota (ADR 0014).
 *
 * Devolve null se algum item da venda não estiver no catálogo (o backend não deixa isso acontecer nas
 * sementes, mas a tela não inventa um item).
 */
export function pedidoDeRegime(catalogo: Catalogo, cliente: ClienteB2B): PedidoDeRegime | null {
  const itens: ItemCarrinho[] = [];
  for (const compra of cliente.compraMensal) {
    const item = catalogo.itens.find((i) => i.id === compra.itemId);
    if (!item) {
      return null;
    }
    const linha = linhaDoItem(item, compra.quantidade);
    if (item.custoAtual?.fonteCredito !== 'nfe') {
      delete linha.creditoCompraUnitario;
    }
    itens.push(linha);
  }
  return {
    ...semVazios(catalogo.cenario.operacao),
    cliente: { nome: cliente.nome, regime: cliente.regime },
    itens,
  };
}

/** A nota mais recente que mexeu no custo dos itens, e quantos itens ela atualizou. */
export function ultimaNota(catalogo: Catalogo): { numero: string | null; data: string; itens: number } | null {
  const custos = catalogo.itens.flatMap((i) => (i.custoAtual ? [i.custoAtual] : []));
  if (custos.length === 0) {
    return null;
  }
  // As datas vêm com fuso; a ordem é a do instante (ADR 0003).
  const maisRecente = custos.reduce((a, b) => (Date.parse(b.data) > Date.parse(a.data) ? b : a));
  const itens = custos.filter((c) => c.notaNumero === maisRecente.notaNumero && c.data === maisRecente.data);
  return { numero: maisRecente.notaNumero ?? null, data: maisRecente.data, itens: itens.length };
}

export const NOME_REGIME: Record<Regime, string> = {
  simples_tradicional: 'Simples tradicional',
  simples_hibrido: 'Simples híbrido',
};

/**
 * O estado do item em palavras do ofício (plano, seção 12), nunca um selo genérico.
 * Os erros de classificação dos dois motores (REG-011 e VSN-047) dizem a mesma coisa para quem vende.
 */
export function estadoEmPalavras(item: Pick<ItemCalculado, 'estado' | 'erros' | 'motivoEstado'>): string {
  const codigos = item.erros.map((e) => e.codigo);
  if (codigos.includes('REG-011') || codigos.includes('VSN-047')) {
    return 'NCM não combina com a classificação';
  }
  switch (item.estado) {
    case 'CALCULADO':
      return 'Calculado';
    case 'CALCULO_SIMULADO':
      return 'Calculado com as premissas';
    case 'NAO_CALCULADO':
      return item.motivoEstado ?? 'O motor não calculou este item';
    case 'NAO_IMPLEMENTADO':
      return 'O motor ainda não calcula este caso';
    case 'FALHA_TECNICA':
      return 'O motor falhou neste item';
    case 'INCONSISTENCIA_ENTRADA':
      return item.erros[0]?.titulo ?? 'Dados do item não conferem';
  }
}

/** O item volta com erro de classificação, que a tela corrige com as candidatas oficiais. */
export function precisaCorrigirClassificacao(item: Pick<ItemCalculado, 'erros'>): boolean {
  return item.erros.some((e) => e.codigo === 'REG-011' || e.codigo === 'VSN-047');
}

export function calculado(item: Pick<ItemCalculado, 'estado'>): boolean {
  return item.estado === 'CALCULADO' || item.estado === 'CALCULO_SIMULADO';
}

/** Margem abaixo do alvo: o único dado que leva a cor negativa na tela. */
export function abaixoDoAlvo(margemPct: string | null | undefined, alvoPct: string): boolean {
  return margemPct !== null && margemPct !== undefined && Number(margemPct) < Number(alvoPct);
}
