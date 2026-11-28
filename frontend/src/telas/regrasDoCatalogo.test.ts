/// <reference types="node" />
// As regras dos formulários do catálogo e dos clientes (C3b2), com os limites conferidos no contrato publicado
// (docs/contrato/openapi.json) e as linhas sem par das respostas reais gravadas (src/teste/fixtures).

import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import type { ClienteB2B, ItemCatalogo, LinhaSemPar } from '../dados/pedidos.ts';
import catalogoDaDemo from '../teste/fixtures/catalogo.json';
import recibo1001 from '../teste/fixtures/c3b2-recibo-1001.json';
import { mudancasDoItem } from './CadastroDoItem.tsx';
import { lerCompra, mudancasDoCliente } from './Clientes.tsx';
import {
  CODIGO_MAXIMO,
  DESCRICAO_MAXIMA,
  QUANTIDADE_MAXIMA,
  UNIDADES,
  cadastravelDaNota,
  conferirCnpjDeTerceiro,
  conferirTexto,
  lerMargem,
  lerNcm,
  lerQuantidade,
} from './regrasDoCatalogo.ts';

const CONTRATO = JSON.parse(
  readFileSync(join(import.meta.dirname, '..', '..', '..', 'docs', 'contrato', 'openapi.json'), 'utf8'),
) as { components: { schemas: Record<string, { properties: Record<string, Record<string, unknown>> }> } };

function propriedade(esquema: string, campo: string): Record<string, unknown> {
  const p = CONTRATO.components.schemas[esquema]?.properties[campo];
  if (p === undefined) {
    throw new Error(`${esquema}.${campo} não está no contrato`);
  }
  return p;
}

/** O número do `anyOf` (número ou texto) de um Decimal do contrato. */
function numero(esquema: string, campo: string): Record<string, unknown> {
  const opcoes = propriedade(esquema, campo).anyOf as Record<string, unknown>[];
  const achado = opcoes.find((o) => o.type === 'number');
  if (achado === undefined) {
    throw new Error(`${esquema}.${campo} sem o número`);
  }
  return achado;
}

describe('os limites são os do contrato', () => {
  it('a descrição, o código do fornecedor, a unidade, a margem e a quantidade', () => {
    expect(propriedade('ItemNovoRequisicao', 'descricao').maxLength).toBe(DESCRICAO_MAXIMA);
    expect(propriedade('ItemNovoRequisicao', 'codigoFornecedor').maxLength).toBe(CODIGO_MAXIMO);
    expect(propriedade('ItemNovoRequisicao', 'unidade').enum).toEqual([...UNIDADES]);
    expect(propriedade('ItemNovoRequisicao', 'ncm').pattern).toBe('^[0-9]{8}$');
    const margem = numero('ItemNovoRequisicao', 'margemAlvoPct');
    expect([margem.exclusiveMinimum, margem.exclusiveMaximum]).toEqual([0, 100]);
    const quantidade = numero('ItemDaCompraMensal', 'quantidade');
    expect([quantidade.exclusiveMinimum, quantidade.maximum]).toEqual([0, QUANTIDADE_MAXIMA]);
    expect(numero('ItemNovoRequisicao', 'precoVenda').maximum).toBe(QUANTIDADE_MAXIMA);
  });
});

describe('as leituras dos campos', () => {
  it('a NCM com ou sem os pontos; fora de 8 dígitos, nada', () => {
    expect(lerNcm('1806.32.10')).toBe('18063210');
    expect(lerNcm(' 1806 32 10 ')).toBe('18063210');
    expect(lerNcm('1806321')).toBeNull();
    expect(lerNcm('chocolate')).toBeNull();
  });

  it('a margem: maior que 0 e menor que 100, até 4 casas', () => {
    expect(lerMargem('20')).toBe('20');
    expect(lerMargem('17,5 %')).toBe('17.5');
    expect(lerMargem('0,0001')).toBe('0.0001');
    for (const ruim of ['0', '100', '-5', '12,12345', '', 'vinte']) {
      expect(lerMargem(ruim)).toBeNull();
    }
  });

  it('a quantidade da compra mensal: maior que 0, até um bilhão, até 4 casas', () => {
    expect(lerQuantidade('2485')).toBe('2485');
    expect(lerQuantidade('12,5')).toBe('12.5');
    expect(lerQuantidade('1000000000')).toBe('1000000000');
    for (const ruim of ['0', '1000000001', '1,23456', '-1', 'dez']) {
      expect(lerQuantidade(ruim)).toBeNull();
    }
  });

  it('o texto do cadastro: as pontas fora, o tamanho e os caracteres de controle', () => {
    expect(conferirTexto('  Arroz 5 kg ', DESCRICAO_MAXIMA, 'a descrição')).toBeNull();
    expect(conferirTexto('   ', DESCRICAO_MAXIMA, 'a descrição')).toBe('Informe a descrição.');
    expect(conferirTexto('x'.repeat(61), CODIGO_MAXIMO, 'o código')).toBe('Use no máximo 60 caracteres.');
    expect(conferirTexto('a\u0007b', CODIGO_MAXIMO, 'o código')).toBe('Use só texto, sem caracteres de controle.');
  });

  it('o CNPJ do fornecedor e do cliente: o dígito só na empresa da conta, como no backend', () => {
    // 71604258000156 é o fornecedor fictício da demonstração, com o dígito errado de propósito (ADR 0008).
    expect(conferirCnpjDeTerceiro('71.604.258/0001-56', false)).toBeNull();
    expect(conferirCnpjDeTerceiro('71.604.258/0001-56', true)).toBe('CNPJ inválido: confira os dígitos verificadores.');
    expect(conferirCnpjDeTerceiro('AB.12C.D34/EF56-02', true)).toBeNull();
    expect(conferirCnpjDeTerceiro('123', false)).toMatch(/^Confira o CNPJ/u);
    expect(conferirCnpjDeTerceiro('', true)).toBe('Informe o CNPJ.');
  });
});

describe('a linha sem par que vira item a partir da nota', () => {
  const { recibo } = recibo1001;
  const linhas = recibo.itensSemPar as LinhaSemPar[];
  const chocolate = linhas.find((l) => l.ncm === '18063210');

  it('o código sem cadastro, com a unidade, o custo e o número da linha: pode, com o fornecedor da nota', () => {
    expect(chocolate).toBeDefined();
    const r = cadastravelDaNota(chocolate as LinhaSemPar, recibo.nota, linhas);
    expect(r.pode).toBe(true);
    if (r.pode) {
      expect(r.origem).toMatchObject({ cnpjFornecedor: recibo.nota.emitente.cnpj, serie: '1', numero: '1001' });
      expect(r.origem.linha).toMatchObject({ nItem: 2, unidade: 'UN', codigoFornecedor: 'AE-CHO-90', custoUnitario: '3.50' });
    }
  });

  it('as recusas do backend, cada uma com o motivo', () => {
    const base = chocolate as LinhaSemPar;
    const antiga = { ...base, causa: null, custoUnitario: null };
    expect(cadastravelDaNota(antiga, recibo.nota, [antiga])).toEqual({
      pode: false,
      motivo: expect.stringMatching(/^Esta nota foi importada antes/u) as unknown,
    });
    const outraCausa = { ...base, causa: 'ncm' as const };
    expect(cadastravelDaNota(outraCausa, recibo.nota, [outraCausa])).toEqual({ pode: false, motivo: null });
    expect(cadastravelDaNota(base, recibo.nota, [base, { ...base, nItem: 9 }])).toMatchObject({
      pode: false,
      motivo: expect.stringMatching(/mais de uma vez/u) as unknown,
    });
    const caixa = { ...base, unidade: 'CX' };
    expect(cadastravelDaNota(caixa, recibo.nota, [caixa])).toMatchObject({
      pode: false,
      motivo: expect.stringMatching(/\(CX\) não é UN nem KG/u) as unknown,
    });
    expect(cadastravelDaNota(base, { ...recibo.nota, serie: null }, [base])).toMatchObject({ pode: false });
  });
});

describe('o que vai no PATCH', () => {
  const arroz = (catalogoDaDemo.itens as ItemCatalogo[]).find((i) => i.id === 'arroz-5kg') as ItemCatalogo;
  const cnpj = catalogoDaDemo.empresa.cnpj;
  const iguais = {
    descricao: arroz.descricao,
    margem: arroz.margemAlvoPct,
    cnpjFornecedor: arroz.fornecedor.cnpj,
    codigo: arroz.fornecedor.codigo,
  };

  it('do item: só o que mudou, e o fornecedor com o CNPJ e o código juntos', () => {
    expect(mudancasDoItem(arroz, cnpj, iguais)).toEqual({ cnpj });
    expect(mudancasDoItem(arroz, cnpj, { ...iguais, margem: '20', descricao: ` ${arroz.descricao} ` })).toEqual({
      cnpj,
      margemAlvoPct: '20',
    });
    expect(mudancasDoItem(arroz, cnpj, { ...iguais, codigo: 'AE-ARZ-5B' })).toEqual({
      cnpj,
      cnpjFornecedor: arroz.fornecedor.cnpj,
      codigoFornecedor: 'AE-ARZ-5B',
    });
  });

  it('do cliente: só o que mudou, a UF e o município juntos, a compra pela soma das quantidades', () => {
    const [cliente] = catalogoDaDemo.clientesB2B as ClienteB2B[];
    if (cliente === undefined) {
      throw new Error('a demonstração tem um cliente');
    }
    const mesma = cliente.compraMensal.map((c) => ({ itemId: c.itemId, quantidade: String(Number(c.quantidade)) })).reverse();
    const valores = { razaoSocial: cliente.nome, uf: cliente.uf, municipio: String(cliente.municipio), compra: mesma };
    expect(mudancasDoCliente(cliente, cnpj, valores)).toEqual({ cnpj });
    expect(mudancasDoCliente(cliente, cnpj, { ...valores, municipio: '4305108' })).toEqual({ cnpj, uf: 'RS', municipio: 4305108 });
    const outra = [{ itemId: 'arroz-5kg', quantidade: '10' }];
    expect(mudancasDoCliente(cliente, cnpj, { ...valores, compra: outra })).toEqual({ cnpj, compraMensal: outra });
  });

  it('a compra mensal lida dos campos: o vazio fica fora; a quantidade errada aponta o item', () => {
    const itens = [{ id: 'a' }, { id: 'b' }, { id: 'c' }];
    expect(lerCompra({ a: '10', b: '', c: '2,5' }, itens)).toEqual({
      compra: [
        { itemId: 'a', quantidade: '10' },
        { itemId: 'c', quantidade: '2.5' },
      ],
    });
    expect(lerCompra({ a: '', b: ' ' }, itens)).toEqual({ erro: 'Informe a quantidade por mês de ao menos um item.', itemId: null });
    expect(lerCompra({ a: '1', b: 'zero' }, itens)).toMatchObject({ itemId: 'b' });
  });
});
