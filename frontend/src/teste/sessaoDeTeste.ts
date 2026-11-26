// Uma sessão completa para testes de componente, com respostas da API escolhidas pelo teste.

import { criarCliente } from '../api/cliente.ts';
import type { Sessao } from '../sessao/contexto.tsx';
import { SessaoEspaco } from '../sessao/espaco.ts';
import { middlewareDaSessao } from '../sessao/middleware.ts';
import { SessaoModo } from '../sessao/modo.ts';
import { SessaoToken } from '../sessao/token.ts';

export type Responder = (pedido: Request) => Response | Promise<Response>;

export function json(corpo: unknown, status = 200, headers: Record<string, string> = {}): Response {
  const tipo = status >= 400 ? 'application/problem+json' : 'application/json';
  return new Response(JSON.stringify(corpo), { status, headers: { 'Content-Type': tipo, ...headers } });
}

export const SAUDE_MOCK = {
  status: 'ok',
  modo: 'mock',
  motores: [
    { motor: 'regime_regular', ok: true, versaoFixada: '1.7.2', versaoEmExecucao: '1.7.2', banco: 'V0073', coerente: true, detalhe: null },
    { motor: 'simples_nacional', ok: true, versaoFixada: '1.0.2', versaoEmExecucao: '1.0.2', banco: 'V0073', coerente: true, detalhe: null },
  ],
};

export const SAUDE_REAL = { ...SAUDE_MOCK, modo: 'real' };

export function sessaoDeTeste(responder: Responder): Sessao & { pedidos: Request[] } {
  const pedidos: Request[] = [];
  const espaco = new SessaoEspaco({ armazenamento: null });
  const token = new SessaoToken();
  const api = criarCliente({
    baseUrl: 'http://api.teste',
    fetch: ((pedido: Request) => {
      pedidos.push(pedido);
      return Promise.resolve(responder(pedido));
    }) as typeof globalThis.fetch,
  });
  api.use(middlewareDaSessao(espaco, token));
  return { api, espaco, token, modo: new SessaoModo(), pedidos };
}
