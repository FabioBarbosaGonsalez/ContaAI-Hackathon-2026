import { describe, expect, it } from 'vitest';
import direcao from '../../../.taste-skill/app/direction.json';
import tokensCss from './tokens.css?raw';

/** Os tokens de :root como mapa nome → valor. */
function lerTokens(css: string): Map<string, string> {
  const tokens = new Map<string, string>();
  for (const [, nome, valor] of css.matchAll(/(--[a-z0-9-]+)\s*:\s*([^;]+);/g)) {
    if (nome !== undefined && valor !== undefined) {
      tokens.set(nome, valor.trim());
    }
  }
  return tokens;
}

const tokens = lerTokens(tokensCss);

function cor(nome: string): string {
  const valor = tokens.get(nome);
  if (valor === undefined || !/^#[0-9a-f]{6}$/i.test(valor)) {
    throw new Error(`Token ${nome} ausente ou fora do formato #rrggbb: ${String(valor)}`);
  }
  return valor;
}

/** Luminância relativa, como a define a WCAG 2.2 (sRGB, limiar 0,04045). */
function luminancia(hex: string): number {
  const canais = [1, 3, 5].map((i) => Number.parseInt(hex.slice(i, i + 2), 16) / 255);
  const [r, g, b] = canais.map((c) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4)) as [
    number,
    number,
    number,
  ];
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contraste(a: string, b: string): number {
  const [claro, escuro] = [luminancia(a), luminancia(b)].sort((x, y) => y - x) as [number, number];
  return (claro + 0.05) / (escuro + 0.05);
}

describe('fórmula de contraste', () => {
  it('confere com os extremos e um valor conhecido', () => {
    expect(contraste('#000000', '#ffffff')).toBeCloseTo(21, 5);
    expect(contraste('#ffffff', '#ffffff')).toBeCloseTo(1, 5);
    // #767676 no branco é o cinza clássico de 4,54:1.
    expect(contraste('#767676', '#ffffff')).toBeCloseTo(4.54, 2);
  });
});

describe('texto: 4,5:1 (WCAG 2.2, 1.4.3)', () => {
  const pares: [string, string][] = [
    ['--texto', '--superficie'],
    ['--texto', '--fundo'],
    ['--texto', '--elevado'],
    ['--texto-suave', '--superficie'],
    ['--texto-suave', '--fundo'],
    ['--texto-suave', '--elevado'],
    ['--positivo', '--superficie'],
    ['--positivo', '--fundo'],
    ['--negativo', '--superficie'],
    ['--negativo', '--fundo'],
    ['--atencao', '--superficie'],
    ['--atencao', '--fundo'],
    ['--acao-texto', '--acao'],
    ['--acao-texto', '--negativo'], // o botão de excluir a conta (conta.css, .botao-perigo)
    ['--acao-texto', '--selo-negativo-tinta'], // o mesmo botão sob o ponteiro
    ['--texto', '--acao-secundaria'],
    ['--selo-positivo-tinta', '--selo-positivo-fundo'],
    ['--selo-negativo-tinta', '--selo-negativo-fundo'],
    ['--selo-atencao-tinta', '--selo-atencao-fundo'],
    ['--selo-neutro-tinta', '--selo-neutro-fundo'],
  ];
  it.each(pares)('%s sobre %s', (frente, fundo) => {
    expect(contraste(cor(frente), cor(fundo))).toBeGreaterThanOrEqual(4.5);
  });
});

describe('gráfico, foco e borda de campo: 3:1 (WCAG 2.2, 1.4.11 e 2.4.13)', () => {
  const pares: [string, string][] = [
    ['--grafico-destaque', '--superficie'],
    ['--grafico-tinta', '--superficie'],
    ['--grafico-comparacao', '--superficie'],
    ['--negativo', '--superficie'],
    ['--foco', '--superficie'],
    ['--foco', '--fundo'],
    ['--borda-campo', '--superficie'],
    ['--forca-fraca', '--fundo'],
    ['--forca-media', '--fundo'],
    ['--forca-forte', '--fundo'],
    ['--forca-fraca', '--superficie'],
    ['--forca-media', '--superficie'],
    ['--forca-forte', '--superficie'],
  ];
  it.each(pares)('%s sobre %s', (frente, fundo) => {
    expect(contraste(cor(frente), cor(fundo))).toBeGreaterThanOrEqual(3);
  });
});

describe('os tokens seguem a folha sorteada (direction.json)', () => {
  const folha = direcao.style.tokens;
  it.each([
    ['--superficie', folha.surface],
    ['--elevado', folha.raised],
    ['--borda', folha.border],
    ['--regua', folha.rule],
    ['--controle', folha.control],
    ['--texto', folha.text],
    ['--texto-suave', folha.muted],
    ['--acao', folha.accent],
    ['--positivo', folha.positive],
    ['--negativo', folha.negative],
    ['--atencao', folha.warning],
    ['--grafico-tinta', folha.chart[0] ?? 'ausente'],
    ['--grafico-comparacao', folha.chart[1] ?? 'ausente'],
    ['--grafico-destaque', folha.chart[2] ?? 'ausente'],
    ['--selo-positivo-fundo', folha.pills.positive[0]],
    ['--selo-positivo-tinta', folha.pills.positive[1]],
    ['--selo-negativo-fundo', folha.pills.negative[0]],
    ['--selo-negativo-tinta', folha.pills.negative[1]],
    ['--selo-atencao-fundo', folha.pills.warning[0]],
    ['--selo-atencao-tinta', folha.pills.warning[1]],
    ['--selo-neutro-fundo', folha.pills.neutral[0]],
    ['--selo-neutro-tinta', folha.pills.neutral[1]],
    ['--raio-cartao', `${String(folha.radius.card)}px`],
    ['--raio-controle', `${String(folha.radius.control)}px`],
    ['--tamanho-titulo', `${String(folha.font.sizes.title)}px`],
    ['--tamanho-secao', `${String(folha.font.sizes.section)}px`],
    ['--tamanho-kpi', `${String(folha.font.sizes.kpi)}px`],
    ['--tamanho-corpo', `${String(folha.font.sizes.body)}px`],
    ['--tamanho-pequeno', `${String(folha.font.sizes.small)}px`],
    ['--espaco', `${String(folha.gap)}px`],
    ['--respiro', `${String(folha.pad)}px`],
    ['--altura-controle', `${String(folha.controlHeight)}px`],
    ['--altura-linha', `${String(folha.rowHeight)}px`],
  ])('%s = %s', (nome, esperado) => {
    // String(): um valor ausente na folha vira "undefined" e não casa com nenhum token.
    expect(tokens.get(nome)?.toLowerCase()).toBe(String(esperado).toLowerCase());
  });

  it('o fundo é a troca que a própria folha sugere para um livro-caixa', () => {
    expect(folha.ground).toBe('#f8f8f8');
    expect(direcao.style.identity[0]).toContain('a blue-grey (#f2f4f7) for a ledger');
    expect(cor('--fundo')).toBe('#f2f4f7');
  });
});
