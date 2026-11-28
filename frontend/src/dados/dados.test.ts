import { describe, expect, it } from 'vitest';
import {
  cnpj,
  dataDoDocumento,
  inteiro,
  ncm,
  noMeioDaFrase,
  pontos,
  porcentagem,
  reais,
  reaisComSinal,
  reaisPorUnidade,
  TRACO,
} from './formatar.ts';
import {
  abaixoDoAlvo,
  estadoEmPalavras,
  linhaDoItem,
  pedidoDoCatalogo,
  precisaCorrigirClassificacao,
  ultimaNota,
  type Catalogo,
  type ItemCatalogo,
} from './pedidos.ts';

describe('formatar', () => {
  it('valor com sinal tipográfico, e valor por unidade com as casas que a API manda', () => {
    expect(reaisComSinal('-125.79')).toBe('−R$ 125,79');
    expect(reaisComSinal('0.03')).toBe('+R$ 0,03');
    expect(reaisComSinal('0.00')).toBe('R$ 0,00');
    expect(reaisComSinal(null)).toBe(TRACO);
    expect(reaisPorUnidade('0.2715')).toBe('R$ 0,2715');
    expect(reaisPorUnidade('3.05')).toBe('R$ 3,05');
    expect(reaisPorUnidade('0.12345')).toBe('R$ 0,1235');
    expect(reaisPorUnidade(undefined)).toBe(TRACO);
  });

  it('dinheiro e porcentagem no padrão brasileiro; ausente é traço, zero é zero', () => {
    expect(reais('3.97')).toBe('R$ 3,97');
    expect(reais('2790.00')).toBe('R$ 2.790,00');
    expect(reais('0.00')).toBe('R$ 0,00');
    expect(reais(null)).toBe(TRACO);
    expect(reais('abc')).toBe(TRACO);
    expect(porcentagem('11.19')).toBe('11,19%');
    expect(porcentagem('15')).toBe('15,00%');
    expect(porcentagem(undefined)).toBe(TRACO);
    expect(pontos('-12.93')).toBe('−12,93 p.p.');
    expect(pontos('0')).toBe('0,00 p.p.');
    expect(inteiro(1200)).toBe('1.200');
  });

  it('a data do documento não troca de fuso', () => {
    expect(dataDoDocumento('2027-03-16T23:30:00-03:00')).toBe('16/03/2027');
    expect(dataDoDocumento('2027-03-16')).toBe('16/03/2027');
    expect(dataDoDocumento(null)).toBe(TRACO);
    expect(dataDoDocumento('ontem')).toBe(TRACO);
  });

  it('máscaras de CNPJ e NCM, e o nome no meio da frase', () => {
    expect(cnpj('36817420000113')).toBe('36.817.420/0001-13');
    expect(cnpj('123')).toBe('123');
    // CNPJ alfanumérico: o exemplo do manual do Serpro, com a mesma máscara; minúsculas não são o formato oficial.
    expect(cnpj('12ABC34501DE35')).toBe('12.ABC.345/01DE-35');
    expect(cnpj('12abc34501de35')).toBe('12abc34501de35');
    expect(cnpj('12ABC34501DEAB')).toBe('12ABC34501DEAB');
    expect(ncm('22030000')).toBe('2203.00.00');
    expect(ncm(null)).toBe(TRACO);
    expect(noMeioDaFrase('Cerveja de malte')).toBe('cerveja de malte');
    expect(noMeioDaFrase('NCM errada')).toBe('NCM errada');
  });
});

const ITEM: ItemCatalogo = {
  id: 'cerveja-lata',
  descricao: 'Cerveja de malte, lata 350 ml',
  ncm: '22030000',
  nbs: null,
  cst: '000',
  cClassTrib: '000001',
  impostoSeletivo: { cst: '200', cClassTrib: '200007', litrosPorUnidade: '0.35' },
  unidade: 'UN',
  fornecedor: { cnpj: '71604258000156', codigo: 'AE-CRV-350' },
  ncmDescricaoOficial: 'Cervejas de malte.',
  classificacaoFonte: 'dados abertos',
  margemAlvoPct: '15',
  precoVenda: '3.79',
  custoAtual: {
    data: '2027-03-16T09:00:00-03:00',
    notaNumero: '1002',
    custoUnitario: '3.05',
    creditoCompraUnitario: '0.2715',
    fonteCredito: 'nfe',
  },
  historicoCusto: [],
};

const CATALOGO = {
  empresa: {
    cnpj: '36817420000113',
    razaoSocial: 'Distribuidora Serra Azul ME (fictícia)',
    regimeAtual: 'simples_tradicional',
    uf: 'RS',
    municipio: 4314902,
    municipioNome: 'Porto Alegre',
    dataCenario: '2027-03-16',
  },
  cenario: {
    descricao: 'Simulação de março de 2027',
    operacao: {
      data: '2027-03-16',
      uf: 'RS',
      municipio: 4314902,
      aliquotasNominais: { cbs: '8.8', ibsEstadual: '0.05', ibsMunicipal: '0.05', fonte: 'demo' },
      premissasDas: { anexo: 'I', cAtivSN: '01', pCBSSN: '1.1612', pIBSSN: '0.0129', fonte: 'demo' },
    },
    cargaAtualPct: null,
  },
  clientesB2B: [],
  loteReferencia: 100,
  itens: [
    ITEM,
    {
      ...ITEM,
      id: 'arroz-5kg',
      descricao: 'Arroz',
      ncm: '10063021',
      impostoSeletivo: null,
      custoAtual: { ...ITEM.custoAtual, data: '2027-03-02T09:00:00-03:00', notaNumero: '1001', creditoCompraUnitario: null },
    },
  ],
} as unknown as Catalogo;

describe('pedidos a partir do catálogo', () => {
  it('a linha leva só campos que a API devolveu, como test_tela.py::entrada', () => {
    expect(linhaDoItem(ITEM, 100)).toEqual({
      id: 'cerveja-lata',
      descricao: 'Cerveja de malte, lata 350 ml',
      ncm: '22030000',
      cst: '000',
      cClassTrib: '000001',
      impostoSeletivo: { cst: '200', cClassTrib: '200007', litrosPorUnidade: '0.35' },
      unidade: 'UN',
      quantidade: '100',
      valorUnitario: '3.79',
      custoUnitario: '3.05',
      creditoCompraUnitario: '0.2715',
    });
    // Sem crédito informado, o campo não vai (o backend calcula no motor RR, com a hipótese impressa).
    const arroz = CATALOGO.itens[1];
    expect(arroz && 'creditoCompraUnitario' in linhaDoItem(arroz, 100)).toBe(false);
  });

  it('o carrinho usa a operação do cenário, sem alíquota escrita na tela (P6)', () => {
    const pedido = pedidoDoCatalogo(CATALOGO, 'simples_hibrido');
    expect(pedido.regime).toBe('simples_hibrido');
    expect(pedido.data).toBe('2027-03-16');
    expect(pedido.aliquotasNominais).toEqual(CATALOGO.cenario.operacao.aliquotasNominais);
    expect(pedido.itens.map((i) => i.quantidade)).toEqual(['100', '100']);
    expect('cargaAtualPct' in pedido).toBe(false);
  });

  it('a última nota é a mais recente pelo instante, com quantos itens ela atualizou', () => {
    expect(ultimaNota(CATALOGO)).toEqual({ numero: '1002', data: '2027-03-16T09:00:00-03:00', itens: 1 });
    expect(ultimaNota({ ...CATALOGO, itens: [{ ...ITEM, custoAtual: null }] })).toBeNull();
  });
});

describe('estado em palavras do ofício', () => {
  const erro = (codigo: string) => ({ codigo, titulo: 'NCM não aplicável', campo: null, detalhe: null });

  it('REG-011 e VSN-047 dizem a mesma coisa para quem vende', () => {
    for (const codigo of ['REG-011', 'VSN-047']) {
      const item = { estado: 'INCONSISTENCIA_ENTRADA' as const, erros: [erro(codigo)], motivoEstado: null };
      expect(estadoEmPalavras(item)).toBe('NCM não combina com a classificação');
      expect(precisaCorrigirClassificacao(item)).toBe(true);
    }
  });

  it('os outros estados', () => {
    expect(estadoEmPalavras({ estado: 'CALCULADO', erros: [], motivoEstado: null })).toBe('Calculado');
    expect(estadoEmPalavras({ estado: 'CALCULO_SIMULADO', erros: [], motivoEstado: null })).toBe(
      'Calculado com as premissas',
    );
    expect(estadoEmPalavras({ estado: 'NAO_CALCULADO', erros: [], motivoEstado: 'Atividade fora do anexo' })).toBe(
      'Atividade fora do anexo',
    );
    expect(estadoEmPalavras({ estado: 'INCONSISTENCIA_ENTRADA', erros: [erro('REG-035')], motivoEstado: null })).toBe(
      'NCM não aplicável',
    );
    expect(precisaCorrigirClassificacao({ erros: [erro('REG-035')] })).toBe(false);
  });

  it('abaixo do alvo só com margem calculada', () => {
    expect(abaixoDoAlvo('11.19', '15')).toBe(true);
    expect(abaixoDoAlvo('15.00', '15')).toBe(false);
    expect(abaixoDoAlvo(null, '15')).toBe(false);
  });
});
