/// <reference types="node" />
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { TIPO_CONTA_BLOQUEADA } from './formulario.tsx';
import { COOKIES, REGRAS_DA_CONTA, VERSAO_TERMOS, dataDaVersao } from './legal.ts';

// A fonte das regras citadas nos termos e na privacidade: os arquivos do backend, lidos como texto.
const APP = join(import.meta.dirname, '..', '..', '..', 'backend', 'app');

function constante(arquivo: string, nome: string): string {
  const fonte = readFileSync(join(APP, arquivo), 'utf8');
  const achado = new RegExp(`^${nome} = (.+)$`, 'm').exec(fonte);
  if (achado?.[1] === undefined) {
    throw new Error(`${nome} não encontrado em backend/app/${arquivo}`);
  }
  return achado[1].replace(/\s+#.*$/, '').trim();
}

describe('regras da conta citadas nos termos e na privacidade', () => {
  it('são as do backend', () => {
    expect(Number(constante('contas/senha.py', 'MINIMO'))).toBe(REGRAS_DA_CONTA.senhaMinima);
    expect(Number(constante('contas/senha.py', 'MAXIMO'))).toBe(REGRAS_DA_CONTA.senhaMaxima);
    expect(Number(constante('contas/totp.py', 'DIGITOS'))).toBe(REGRAS_DA_CONTA.digitosDoCodigo);
    expect(Number(constante('contas/servico.py', 'CODIGOS_RECUPERACAO'))).toBe(REGRAS_DA_CONTA.codigosDeRecuperacao);
    expect(Number(constante('contas/servico.py', 'FALHAS_PARA_ESPERAR'))).toBe(REGRAS_DA_CONTA.falhasParaEsperar);
    expect(Number(constante('contas/servico.py', 'ESPERA_INICIAL_S'))).toBe(REGRAS_DA_CONTA.esperaInicialS);
    expect(Number(constante('contas/servico.py', 'ESPERA_MAXIMA_S'))).toBe(REGRAS_DA_CONTA.esperaMaximaS);
    expect(Number(constante('contas/servico.py', 'FALHAS_PARA_BLOQUEAR'))).toBe(REGRAS_DA_CONTA.falhasParaBloquear);
    expect(constante('contas/servico.py', 'SESSAO_OCIOSA')).toBe(`timedelta(minutes=${String(REGRAS_DA_CONTA.sessaoOciosaMin)})`);
    expect(constante('contas/servico.py', 'SESSAO_TOTAL')).toBe(`timedelta(hours=${String(REGRAS_DA_CONTA.sessaoTotalH)})`);
    expect(constante('contas/servico.py', 'PASSE')).toBe(`timedelta(minutes=${String(REGRAS_DA_CONTA.passeMin)})`);
    expect(constante('contas/servico.py', 'PENDENTE')).toBe(`timedelta(minutes=${String(REGRAS_DA_CONTA.pendenteMin)})`);
  });

  it('o tipo do 429 da conta bloqueada existe no backend (problemas.py)', () => {
    const fonte = readFileSync(join(APP, 'api', 'problemas.py'), 'utf8');
    expect(TIPO_CONTA_BLOQUEADA.startsWith('/problemas/')).toBe(true);
    expect(fonte).toContain(`type=f"{PREFIXO}${TIPO_CONTA_BLOQUEADA.slice('/problemas/'.length)}"`);
  });

  it('a versão dos termos é a do backend', () => {
    expect(constante('contas/termos.py', 'VERSAO_TERMOS')).toBe(`"${VERSAO_TERMOS}"`);
  });

  it('os cookies são os da API', () => {
    expect(constante('api/dependencias.py', 'COOKIE_SESSAO')).toBe(`"${COOKIES.sessao}"`);
    expect(constante('api/dependencias.py', 'COOKIE_PASSE')).toBe(`"${COOKIES.passe}"`);
  });

  it('a data da versão sai sem passar por fuso', () => {
    expect(dataDaVersao('2026-11-26')).toBe('26/11/2026');
  });
});
