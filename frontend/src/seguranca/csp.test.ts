import { describe, expect, it } from 'vitest';
import { cabecalhosDeSeguranca, origemDaApi, politicaDeSeguranca } from '../../csp.ts';

describe('política de segurança de conteúdo', () => {
  it('é a de docs/seguranca.md, com trusted-types none', () => {
    expect(politicaDeSeguranca({ cabecalho: true })).toBe(
      "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; font-src 'self'; " +
        "connect-src 'self'; base-uri 'none'; form-action 'none'; require-trusted-types-for 'script'; " +
        "trusted-types 'none'; frame-ancestors 'none'",
    );
  });

  it('no <meta> não leva frame-ancestors, que o navegador ignora ali', () => {
    const meta = politicaDeSeguranca({ cabecalho: false });
    expect(meta).not.toContain('frame-ancestors');
    expect(meta).toContain("require-trusted-types-for 'script'");
  });

  it('nunca libera script ou estilo embutido, eval ou outra origem de script', () => {
    const politica = politicaDeSeguranca({ api: 'https://api.exemplo', cabecalho: true });
    expect(politica).not.toMatch(/unsafe-inline|unsafe-eval|unsafe-hashes|strict-dynamic|data:|blob:|\*/);
    expect(politica).toMatch(/script-src 'self';/);
  });

  it.each([
    [undefined, "connect-src 'self';"],
    ['/api', "connect-src 'self';"],
    ['http://127.0.0.1:8010', "connect-src 'self' http://127.0.0.1:8010;"],
    ['https://api.exemplo/v1/', "connect-src 'self' https://api.exemplo;"],
  ])('com a API em %s, %s', (api, esperado) => {
    expect(politicaDeSeguranca({ api, cabecalho: false })).toContain(esperado);
  });

  it('a origem da API ignora caminho, consulta e fragmento', () => {
    expect(origemDaApi('https://api.exemplo:8443/caminho?x=1#y')).toBe('https://api.exemplo:8443');
    expect(origemDaApi('/api')).toBeNull();
  });

  it('os cabeçalhos para servir a tela', () => {
    expect(Object.keys(cabecalhosDeSeguranca(undefined)).sort()).toEqual([
      'Content-Security-Policy',
      'Referrer-Policy',
      'X-Content-Type-Options',
      'X-Frame-Options',
    ]);
    expect(cabecalhosDeSeguranca(undefined)['Content-Security-Policy']).toContain("frame-ancestors 'none'");
  });
});
