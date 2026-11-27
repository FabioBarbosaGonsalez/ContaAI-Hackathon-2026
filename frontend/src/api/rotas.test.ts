import { describe, expect, it } from 'vitest';
import contrato from '../../../docs/contrato/openapi.json';
import { CABECALHO_ESPACO, CABECALHO_TOKEN } from './cliente.ts';
import {
  ROTAS_COM_ESPACO,
  ROTAS_COM_TOKEN,
  ROTAS_DA_CONTA,
  ROTAS_DA_EMPRESA,
  ROTAS_DE_ENTRADA,
  chaveDaRota,
} from './rotas.ts';

interface Parametro {
  in: string;
  name: string;
}

interface Operacao {
  parameters?: Parametro[];
  tags?: string[];
  responses?: Record<string, unknown>;
}

function operacoes(): [string, Operacao][] {
  return Object.entries(contrato.paths).flatMap(([caminho, metodos]) =>
    Object.entries(metodos as Record<string, Operacao>).map(([metodo, op]): [string, Operacao] => [
      chaveDaRota(metodo, caminho),
      op,
    ]),
  );
}

/** As rotas do contrato que declaram o header pedido. */
function rotasComHeader(nome: string): string[] {
  const rotas: string[] = [];
  for (const [caminho, metodos] of Object.entries(contrato.paths)) {
    for (const [metodo, operacao] of Object.entries(metodos as Record<string, { parameters?: Parametro[] }>)) {
      if ((operacao.parameters ?? []).some((p) => p.in === 'header' && p.name === nome)) {
        rotas.push(chaveDaRota(metodo, caminho));
      }
    }
  }
  return rotas.sort();
}

describe('rotas com headers da sessão', () => {
  it('a lista do espaço é a do contrato', () => {
    expect([...ROTAS_COM_ESPACO].sort()).toEqual(rotasComHeader(CABECALHO_ESPACO));
  });

  it('a lista do token é a do contrato', () => {
    expect([...ROTAS_COM_TOKEN].sort()).toEqual(rotasComHeader(CABECALHO_TOKEN));
  });
});

describe('rotas da conta', () => {
  it('são as da tag contas do contrato', () => {
    const doContrato = operacoes()
      .filter(([, op]) => (op.tags ?? []).includes('contas'))
      .map(([chave]) => chave)
      .sort();
    expect([...ROTAS_DA_CONTA].sort()).toEqual(doContrato);
  });

  it('as da empresa da conta são as do caminho /empresas no contrato, e nenhuma aceita o espaço', () => {
    const doContrato = operacoes()
      .map(([chave]) => chave)
      .filter((chave) => /^[A-Z]+ \/empresas(\/|$)/u.test(chave))
      .sort();
    expect([...ROTAS_DA_EMPRESA].sort()).toEqual(doContrato);
    for (const chave of ROTAS_DA_EMPRESA) {
      expect(ROTAS_COM_ESPACO.has(chave)).toBe(false);
      expect(ROTAS_COM_TOKEN.has(chave)).toBe(false);
    }
  });

  it('as de entrada sempre levam o cookie e declaram 401', () => {
    const declaram401 = new Map(operacoes().map(([chave, op]) => [chave, '401' in (op.responses ?? {})]));
    for (const chave of ROTAS_DE_ENTRADA) {
      expect(ROTAS_DA_CONTA.has(chave) || ROTAS_DA_EMPRESA.has(chave)).toBe(true);
      expect(declaram401.get(chave)).toBe(true);
    }
  });
});
