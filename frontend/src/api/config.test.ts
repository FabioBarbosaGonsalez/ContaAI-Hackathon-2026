import { describe, expect, it } from 'vitest';
import { validarEnderecoApi } from './config.ts';

describe('validarEnderecoApi', () => {
  it.each([
    ['/api', '/api'],
    ['/api/', '/api'],
    ['http://127.0.0.1:8000', 'http://127.0.0.1:8000'],
    ['http://localhost:8000/', 'http://localhost:8000'],
    ['https://contaai.exemplo.com.br/api/', 'https://contaai.exemplo.com.br/api'],
  ])('aceita %s', (entrada, esperado) => {
    expect(validarEnderecoApi(entrada)).toBe(esperado);
  });

  it.each([
    ['vazio', ''],
    ['//host troca de origem sem parecer', '//malicioso.exemplo'],
    ['barra invertida', '/\\malicioso.exemplo'],
    ['http fora da máquina local', 'http://contaai.exemplo.com.br'],
    ['usuário e senha embutidos', 'https://usuario:senha@contaai.exemplo.com.br'],
    ['consulta', 'https://contaai.exemplo.com.br/api?x=1'],
    ['fragmento', '/api#x'],
    // eslint-disable-next-line no-script-url -- é o caso que o teste quer ver recusado
    ['javascript:', 'javascript:alert(1)'],
    ['data:', 'data:text/html,oi'],
    ['texto solto', 'api'],
  ])('recusa %s', (_motivo, entrada) => {
    expect(() => validarEnderecoApi(entrada)).toThrow();
  });
});
