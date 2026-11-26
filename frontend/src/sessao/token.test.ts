import { describe, expect, it, vi } from 'vitest';
import { SessaoToken } from './token.ts';

describe('SessaoToken', () => {
  it('guarda só na memória e avisa quem assina', () => {
    const sessao = new SessaoToken();
    const ouvinte = vi.fn();
    sessao.assinar(ouvinte);

    expect(sessao.definir('  token-da-demo  ')).toBe(true);
    expect(sessao.atual()).toBe('token-da-demo');
    expect(sessao.temToken()).toBe(true);
    expect(ouvinte).toHaveBeenCalledTimes(1);

    sessao.limpar();
    expect(sessao.atual()).toBeNull();
    sessao.limpar();
    expect(ouvinte).toHaveBeenCalledTimes(2);
  });

  it.each([
    ['vazio', '   '],
    ['quebra de linha (injeção de header)', 'abc\r\nX-Outro: 1'],
    ['espaço no meio', 'abc def'],
    ['acento', 'tokén'],
    ['longo demais', 'a'.repeat(513)],
  ])('recusa %s', (_caso, valor) => {
    const sessao = new SessaoToken();
    expect(sessao.definir(valor)).toBe(false);
    expect(sessao.atual()).toBeNull();
  });

  it('não grava nada no armazenamento do navegador', () => {
    const antes = { local: localStorage.length, sessao: sessionStorage.length, cookie: document.cookie };
    new SessaoToken().definir('segredo-da-demo');
    expect({ local: localStorage.length, sessao: sessionStorage.length, cookie: document.cookie }).toEqual(antes);
  });
});
