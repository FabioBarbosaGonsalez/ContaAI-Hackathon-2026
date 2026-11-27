import { readdirSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { arquivosNaPasta, DESCRICOES, notasDeExemplo } from './notasDeExemplo.ts';

// A pasta do repositório, lida direto do disco: o teste não depende do padrão do import.meta.glob para saber o
// que existe lá.
const PASTA = resolve(import.meta.dirname, '../../../data/demo/notas');
const NO_DISCO = readdirSync(PASTA)
  .filter((nome) => nome.endsWith('.xml'))
  .sort();

describe('notas de exemplo', () => {
  it('o Vite acha todos os XML da pasta, e só eles', () => {
    expect(NO_DISCO).toEqual(['nfe-compra-1.xml', 'nfe-compra-2.xml', 'nfe-item-sem-par.xml']);
    expect(arquivosNaPasta()).toEqual(NO_DISCO);
  });

  it('cada arquivo tem uma frase, e nenhuma frase fica sem arquivo', () => {
    expect(DESCRICOES.map(([arquivo]) => arquivo).sort()).toEqual(NO_DISCO);
    expect(new Set(DESCRICOES.map(([arquivo]) => arquivo)).size).toBe(DESCRICOES.length);
  });

  it('sai na ordem das frases, com o endereço do próprio arquivo', () => {
    const notas = notasDeExemplo();
    expect(notas.map((n) => n.arquivo)).toEqual(['nfe-compra-2.xml', 'nfe-item-sem-par.xml', 'nfe-compra-1.xml']);
    for (const n of notas) {
      expect(n.endereco.endsWith(`/data/demo/notas/${n.arquivo}`)).toBe(true);
      expect(n.descricao).not.toBe('');
    }
  });

  it('uma frase sem arquivo fica de fora, sem link quebrado', () => {
    const notas = notasDeExemplo({ '../../../data/demo/notas/nfe-compra-1.xml': '/assets/nfe-compra-1-abc.xml' });
    expect(notas).toEqual([
      {
        arquivo: 'nfe-compra-1.xml',
        endereco: '/assets/nfe-compra-1-abc.xml',
        descricao: 'Já está na demonstração: importar de novo mostra o recibo gravado.',
      },
    ]);
    expect(notasDeExemplo({})).toEqual([]);
  });
});
