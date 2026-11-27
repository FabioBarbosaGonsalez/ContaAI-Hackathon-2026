// O medidor de força da senha (Criar conta), com o zxcvbn-ts de verdade.

import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { act, cleanup, render, renderHook, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import {
  MedidorDeForca,
  PALAVRAS_DO_PRODUTO,
  carregarAvaliador,
  forcaPelaNota,
  palavrasDaPessoa,
  useForcaDaSenha,
} from './forcaDaSenha.tsx';

afterEach(cleanup);

describe('forcaPelaNota', () => {
  it('0 a 2 = fraca; 3 = média; 4 = forte; abaixo de 8 caracteres, fraca sempre', () => {
    expect([0, 1, 2, 3, 4].map((n) => forcaPelaNota(n, 20))).toEqual(['fraca', 'fraca', 'fraca', 'media', 'forte']);
    expect(forcaPelaNota(4, 7)).toBe('fraca');
    expect(forcaPelaNota(4, 8)).toBe('forte');
  });
});

describe('palavrasDaPessoa', () => {
  it('o e-mail, a parte antes do @, a organização e as palavras do produto, em minúsculas', () => {
    expect(palavrasDaPessoa(' Ana.Souza@Exemplo.test ', ' Escritório Ana ')).toEqual([
      'ana.souza@exemplo.test',
      'ana.souza',
      'escritório ana',
      ...PALAVRAS_DO_PRODUTO,
    ]);
    expect(palavrasDaPessoa('', '')).toEqual([...PALAVRAS_DO_PRODUTO]);
  });

  it('as palavras do produto são as que o backend recusa (senha.py)', () => {
    const senhaPy = readFileSync(join(import.meta.dirname, '../../../backend/app/contas/senha.py'), 'utf8');
    const linha = /^PALAVRAS_DO_PRODUTO = \((.+)\)$/mu.exec(senhaPy)?.[1] ?? '';
    const doBackend = [...linha.matchAll(/"([^"]+)"/gu)].map((m) => m[1]);
    for (const palavra of PALAVRAS_DO_PRODUTO) {
      expect(doBackend).toContain(palavra);
    }
  });
});

describe('a nota do zxcvbn-ts', () => {
  it.each([
    ['password', 'fraca'],
    ['12345678', 'fraca'],
    ['qwertyuiop', 'fraca'],
    ['aaaaaaaaaaaa', 'fraca'],
    ['cachorro2024', 'fraca'],
    ['Brasil2024!', 'media'],
    ['minhacasa', 'media'],
    ['minha casa azul', 'forte'],
    ['correto cavalo bateria grampo', 'forte'],
  ])('%s é %s', async (senha, esperada) => {
    const avaliar = await carregarAvaliador();
    expect(forcaPelaNota(avaliar(senha, []), senha.length)).toBe(esperada);
  });

  it('a senha feita do e-mail ou da organização vale menos', async () => {
    const avaliar = await carregarAvaliador();
    const sozinha = avaliar('escritoriomodelo', []);
    const comAPessoa = avaliar('escritoriomodelo', palavrasDaPessoa('ana@exemplo.test', 'Escritoriomodelo'));
    expect(comAPessoa).toBeLessThan(sozinha);
    expect(forcaPelaNota(avaliar('contaai2026', palavrasDaPessoa('', '')), 11)).toBe('fraca');
  });
});

describe('useForcaDaSenha', () => {
  it('vazia: nada; curta: fraca na hora; longa: espera a biblioteca e dá a nota', async () => {
    const { result, rerender } = renderHook(({ senha }) => useForcaDaSenha(senha, []), {
      initialProps: { senha: '' },
    });
    expect(result.current).toBeNull();
    rerender({ senha: 'abc' });
    expect(result.current).toBe('fraca');
    rerender({ senha: 'correto cavalo bateria grampo' });
    await waitFor(() => {
      expect(result.current).toBe('forte');
    });
    await act(async () => {
      rerender({ senha: '' });
      await Promise.resolve();
    });
    expect(result.current).toBeNull();
  });
});

describe('MedidorDeForca', () => {
  it.each([
    ['fraca', 'Senha fraca'],
    ['media', 'Senha média'],
    ['forte', 'Senha forte'],
  ] as const)('%s: a palavra e a barra (só desenho)', (forca, texto) => {
    const { container } = render(<MedidorDeForca forca={forca} />);
    expect(screen.getByText(texto)).toBeDefined();
    const medidor = container.querySelector('.forca');
    expect(medidor?.getAttribute('data-forca')).toBe(forca);
    expect(container.querySelector('.forca__trilho')?.getAttribute('aria-hidden')).toBe('true');
  });
});
