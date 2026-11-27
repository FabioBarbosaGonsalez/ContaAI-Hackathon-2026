// C2b, etapa 5 (ADR 0016): o QR code em SVG e o segredo em grupos.

import { cleanup, render, screen } from '@testing-library/react';
import { encode } from 'uqr';
import { afterEach, describe, expect, it } from 'vitest';
import { BORDA_DO_QR, PX_POR_MODULO, QrCode, SegredoParaDigitar, caminhoDoQr, gruposDoSegredo } from './QrCode.tsx';

afterEach(cleanup);

// O formato que a API devolve, conferido com a própria função do backend (backend/app/contas/totp.py,
// endereco): 160 bits em base32, 32 caracteres; o ":" do rótulo vai como %3A, e o "@" fica como está.
const SEGREDO = 'JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP';
const ENDERECO = `otpauth://totp/ContaAI%3Aana@exemplo.com.br?secret=${SEGREDO}&issuer=ContaAI&algorithm=SHA1&digits=6&period=30`;

/** Refaz a matriz a partir do `d`: cada "Mx yhLv1h-Lz" pinta L módulos da linha y. */
function matrizDoCaminho(d: string, lado: number): boolean[][] {
  const matriz = Array.from({ length: lado }, () => Array<boolean>(lado).fill(false));
  for (const [, x, y, largura, volta] of d.matchAll(/M(\d+) (\d+)h(\d+)v1h-(\d+)z/gu)) {
    expect(volta).toBe(largura);
    for (let i = 0; i < Number(largura); i += 1) {
      const linha = matriz[Number(y)];
      if (linha === undefined) throw new Error(`linha ${String(y)} fora do desenho`);
      linha[Number(x) + i] = true;
    }
  }
  return matriz;
}

describe('caminhoDoQr', () => {
  it('um retângulo por trecho seguido, deslocado pela borda', () => {
    expect(caminhoDoQr([[true, true, false, true]])).toBe('M4 4h2v1h-2z M7 4h1v1h-1z');
    expect(caminhoDoQr([[false], [true]], 0)).toBe('M0 1h1v1h-1z');
  });

  it('matriz toda clara não desenha nada', () => {
    expect(caminhoDoQr([[false, false], [false, false]])).toBe('');
  });
});

describe('QrCode', () => {
  it('desenha exatamente a matriz do encode(), com a borda de 4 módulos em branco', () => {
    render(<QrCode endereco={ENDERECO} />);
    const svg = screen.getByRole('img', { name: 'QR code para o aplicativo autenticador' });
    const qr = encode(ENDERECO, { ecc: 'M', border: 0 });
    const lado = qr.size + 2 * BORDA_DO_QR;
    expect(svg.getAttribute('viewBox')).toBe(`0 0 ${String(lado)} ${String(lado)}`);
    expect(svg.getAttribute('width')).toBe(String(lado * PX_POR_MODULO));
    expect(svg.getAttribute('height')).toBe(String(lado * PX_POR_MODULO));

    const d = svg.querySelector('path')?.getAttribute('d') ?? '';
    const desenhada = matrizDoCaminho(d, lado);
    const esperada = Array.from({ length: lado }, (_, y) =>
      Array.from({ length: lado }, (_, x) => qr.data[y - BORDA_DO_QR]?.[x - BORDA_DO_QR] ?? false),
    );
    expect(desenhada).toEqual(esperada);
  });

  it('fundo branco e módulos pretos, sem imagem, texto ou HTML embutido', () => {
    const { container } = render(<QrCode endereco={ENDERECO} />);
    const svg = container.querySelector('svg');
    expect(svg?.querySelector('rect')?.getAttribute('fill')).toBe('#ffffff');
    expect(svg?.querySelector('path')?.getAttribute('fill')).toBe('#000000');
    expect(svg?.querySelectorAll('image, foreignObject, text, use, a')).toHaveLength(0);
    // O segredo não aparece no desenho: só a matriz.
    expect(container.textContent).not.toContain(SEGREDO);
    for (const elemento of container.querySelectorAll('*')) {
      for (const atributo of elemento.attributes) {
        expect(atributo.value).not.toContain(SEGREDO);
      }
    }
  });

  it('a correção M dá a versão 8 para o endereço de um e-mail comum (49 módulos)', () => {
    expect(encode(ENDERECO, { ecc: 'M', border: 0 }).size).toBe(49);
  });

  it('o pior e-mail aceito (254 caracteres acentuados) ainda cabe: 149 módulos, mais a borda, a 4 px cada', () => {
    const email = `${'ã'.repeat(64)}@${'é'.repeat(185)}.com`;
    expect(email).toHaveLength(254);
    const rotulo = encodeURIComponent(`ContaAI:${email}`).replaceAll('%40', '@');
    const pior = `otpauth://totp/${rotulo}?secret=${SEGREDO}&issuer=ContaAI&algorithm=SHA1&digits=6&period=30`;
    render(<QrCode endereco={pior} />);
    const svg = screen.getByRole('img');
    expect(svg.getAttribute('viewBox')).toBe('0 0 157 157');
    expect(svg.getAttribute('width')).toBe('628');
  });

  it('o rótulo para o leitor de tela pode ser trocado', () => {
    render(<QrCode endereco={ENDERECO} rotulo="QR da conta" />);
    expect(screen.getByRole('img', { name: 'QR da conta' })).toBeTruthy();
  });
});

describe('segredo para digitar', () => {
  it('grupos de 4; o último pode ser menor', () => {
    expect(gruposDoSegredo(SEGREDO)).toEqual(['JBSW', 'Y3DP', 'EHPK', '3PXP', 'JBSW', 'Y3DP', 'EHPK', '3PXP']);
    expect(gruposDoSegredo('ABCDEF')).toEqual(['ABCD', 'EF']);
    expect(gruposDoSegredo('')).toEqual([]);
  });

  // O jsdom não tem layout: a cópia sem quebras só se confere no Chrome (grupos em linha, não em flex).
  it('o texto é o segredo inteiro, sem espaços; os grupos ficam em linha, com <wbr> só entre eles', () => {
    const { container } = render(<SegredoParaDigitar segredo={SEGREDO} />);
    const codigo = container.querySelector('code');
    expect(codigo?.textContent).toBe(SEGREDO);
    expect(codigo?.getAttribute('translate')).toBe('no');
    expect(Array.from(codigo?.children ?? []).map((filho) => filho.tagName)).toEqual(
      ['SPAN', 'WBR', 'SPAN', 'WBR', 'SPAN', 'WBR', 'SPAN', 'WBR', 'SPAN', 'WBR', 'SPAN', 'WBR', 'SPAN', 'WBR', 'SPAN'],
    );
  });
});
