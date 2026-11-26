import { describe, expect, it } from 'vitest';
import { ErroApi, lerProblema, lerRetryAfter } from './problema.ts';

describe('lerProblema', () => {
  it('aproveita um problema da RFC 9457 e usa o status da resposta', () => {
    const problema = lerProblema(
      { type: '/problemas/calculo-recusado', title: 'Cálculo recusado', status: 200, detail: 'Margem impossível.' },
      422,
    );
    expect(problema).toEqual({
      type: '/problemas/calculo-recusado',
      title: 'Cálculo recusado',
      status: 422,
      detail: 'Margem impossível.',
    });
  });

  it('sem type, assume about:blank; detail vazio vira null', () => {
    expect(lerProblema({ title: 'Not Found', status: 404, detail: '  ' }, 404)).toEqual({
      type: 'about:blank',
      title: 'Not Found',
      status: 404,
      detail: null,
    });
  });

  it.each([
    ['texto', '<html><script>alert(1)</script></html>'],
    ['null', null],
    ['lista', [1, 2]],
    ['sem title', { status: 500, detail: 'x' }],
    ['detail que não é texto', { title: 't', status: 500, detail: { html: '<b>' } }],
    ['type que não é texto', { title: 't', status: 500, type: 1 }],
  ])('corpo fora do formato (%s) vira mensagem fixa, sem repassar o corpo', (_caso, corpo) => {
    const problema = lerProblema(corpo, 502);
    expect(problema).toEqual({ type: 'about:blank', title: expect.any(String) as string, status: 502, detail: null });
    expect(JSON.stringify(problema)).not.toContain('<');
  });
});

describe('lerRetryAfter', () => {
  it('lê segundos', () => {
    expect(lerRetryAfter('30')).toBe(30);
  });

  it('lê data HTTP', () => {
    const agora = Date.parse('2026-11-25T12:00:00Z');
    expect(lerRetryAfter('Wed, 25 Nov 2026 12:01:30 GMT', agora)).toBe(90);
  });

  it('limita a uma hora e não deixa negativo', () => {
    expect(lerRetryAfter('999999')).toBe(3600);
    expect(lerRetryAfter('Wed, 25 Nov 2020 12:00:00 GMT')).toBe(0);
  });

  it.each([null, '', 'amanhã', '-5', '1.5'])('ignora %s', (valor) => {
    expect(lerRetryAfter(valor)).toBeNull();
  });
});

describe('ErroApi', () => {
  it('usa o detail como mensagem', () => {
    const erro = new ErroApi({
      tipo: 'resposta',
      problema: { type: 'about:blank', title: 'Conflict', status: 409, detail: 'Preço já aplicado.' },
    });
    expect(erro.message).toBe('Preço já aplicado.');
    expect(erro.status).toBe(409);
  });

  it('sem detail, usa a frase em português do status', () => {
    const erro = new ErroApi({ tipo: 'resposta', problema: lerProblema('x', 429) });
    expect(erro.message).toBe('Muitas requisições. Espere um pouco e tente de novo.');
  });

  it('erro sem resposta não tem status', () => {
    const erro = new ErroApi({ tipo: 'rede' });
    expect(erro.status).toBeNull();
    expect(erro.message).toContain('API');
  });
});
