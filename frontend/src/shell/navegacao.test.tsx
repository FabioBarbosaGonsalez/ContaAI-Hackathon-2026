import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ArquivoParaBaixar } from './navegacao.tsx';

afterEach(cleanup);

describe('ArquivoParaBaixar', () => {
  it.each([
    ['/assets/nfe-compra-1-B3x_9-Qa.xml', '/assets/nfe-compra-1-B3x_9-Qa.xml'],
    ['/@fs/C:/repo/data/demo/notas/nfe-compra-1.xml', '/@fs/C:/repo/data/demo/notas/nfe-compra-1.xml'],
    ['/assets/../assets/nfe-compra-1.xml', '/assets/nfe-compra-1.xml'],
  ])('monta o link para %s, com o nome do download', (endereco, href) => {
    render(
      <ArquivoParaBaixar endereco={endereco} nome="nfe-compra-1.xml">
        baixar
      </ArquivoParaBaixar>,
    );
    const link = screen.getByRole('link', { name: 'baixar' });
    expect(link.getAttribute('href')).toBe(href);
    expect(link.getAttribute('download')).toBe('nfe-compra-1.xml');
  });

  it.each([
    ['java', 'script:alert(1)'].join(''),
    'data:text/xml,<NFe/>',
    'blob:http://localhost/1',
    '//outro.site/assets/nfe-compra-1.xml',
    'https://outro.site/assets/nfe-compra-1.xml',
    `${globalThis.location.origin}/assets/nfe-compra-1.xml`,
    String.raw`/\outro.site/nfe-compra-1.xml`,
    '/assets/outra-nota.xml',
    '/assets/nfe-compra-1.xml.exe',
    '/assets/nfe-compra-1.xml?x=1',
    '/assets/nfe-compra-1.xml#a',
    '/assets/nfe-compra-1-x/../../segredo.xml',
    'assets/nfe-compra-1.xml',
  ])('recusa o endereço %s', (endereco) => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    expect(() =>
      render(
        <ArquivoParaBaixar endereco={endereco} nome="nfe-compra-1.xml">
          baixar
        </ArquivoParaBaixar>,
      ),
    ).toThrow('Arquivo para baixar fora da própria tela');
  });

  it.each(['NFE.xml', '../x.xml', 'nota.exe', 'nota', 'a b.xml', 'nota.xml/'])('recusa o nome %s', (nome) => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    expect(() =>
      render(
        <ArquivoParaBaixar endereco="/assets/nota.xml" nome={nome}>
          baixar
        </ArquivoParaBaixar>,
      ),
    ).toThrow('Arquivo para baixar com nome fora do padrão');
  });
});
