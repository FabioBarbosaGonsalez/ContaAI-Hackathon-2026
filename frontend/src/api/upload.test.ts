import { describe, expect, it } from 'vitest';
import { ACEITA_NOTA, TAMANHO_MAX_NOTA_BYTES, conferirArquivoDaNota } from './upload.ts';

const arquivo = (name: string, size: number, type = 'text/xml') => ({ name, size, type });

describe('conferirArquivoDaNota', () => {
  it.each([
    ['XML comum', arquivo('nfe-1002.xml', 12_000)],
    ['extensão maiúscula', arquivo('NFE.XML', 12_000, 'application/xml')],
    ['sem tipo informado', arquivo('nfe.xml', 12_000, '')],
    ['no limite exato', arquivo('nfe.xml', TAMANHO_MAX_NOTA_BYTES)],
  ])('aceita %s', (_caso, a) => {
    expect(conferirArquivoDaNota(a)).toEqual({ ok: true });
  });

  it.each([
    ['outra extensão', arquivo('nota.pdf', 12_000, 'application/pdf')],
    ['extensão disfarçada', arquivo('nota.xml.exe', 12_000, 'application/octet-stream')],
    ['HTML com nome de XML', arquivo('nota.xml', 12_000, 'text/html')],
    ['SVG (XML com script)', arquivo('nota.xml', 12_000, 'image/svg+xml')],
    ['vazio', arquivo('nota.xml', 0)],
    ['1 byte acima do limite', arquivo('nota.xml', TAMANHO_MAX_NOTA_BYTES + 1)],
  ])('recusa %s com um motivo', (_caso, a) => {
    const resultado = conferirArquivoDaNota(a);
    expect(resultado.ok).toBe(false);
    expect(resultado.ok ? '' : resultado.motivo).not.toBe('');
  });

  it('o campo de arquivo só oferece XML', () => {
    expect(ACEITA_NOTA.split(',')).toEqual(['.xml', 'application/xml', 'text/xml']);
  });
});
