import { describe, expect, it } from 'vitest';
import contrato from '../../../docs/contrato/openapi.json';
import { CABECALHO_ESPACO, CABECALHO_TOKEN } from './cliente.ts';
import { ROTAS_COM_ESPACO, ROTAS_COM_TOKEN, chaveDaRota } from './rotas.ts';

interface Parametro {
  in: string;
  name: string;
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
