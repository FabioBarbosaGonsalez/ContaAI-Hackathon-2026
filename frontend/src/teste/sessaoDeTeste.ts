// Uma sessão completa para testes de componente, com respostas da API escolhidas pelo teste.

import { criarCliente } from '../api/cliente.ts';
import { SessaoConta, type Conta } from '../sessao/conta.ts';
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

/** Uma conta fictícia, como o GET /conta a devolve (o domínio .test é reservado e não existe, RFC 2606). */
export const CONTA_DE_TESTE: Conta = {
  email: 'pessoa@exemplo.test',
  criadaEm: '2026-11-26T12:00:00Z',
  organizacao: { id: 'b'.repeat(32), nome: 'Organização de teste', papel: 'dono' },
  termos: { versao: '2026-11-26', aceitosEm: '2026-11-26T12:00:00Z' },
  empresas: [],
  codigosRecuperacaoRestantes: 10,
  eventos: [],
  sessaoExpiraEm: '2026-11-26T20:00:00Z',
};


export function sessaoDeTeste(responder: Responder): Sessao & { pedidos: Request[] } {
  const pedidos: Request[] = [];
  const espaco = new SessaoEspaco({ armazenamento: null });
  const token = new SessaoToken();
  const conta = new SessaoConta();
  const api = criarCliente({
    baseUrl: 'http://api.teste',
    fetch: ((pedido: Request) => {
      pedidos.push(pedido);
      return Promise.resolve(responder(pedido));
    }) as typeof globalThis.fetch,
  });
  api.use(middlewareDaSessao(espaco, token, conta));
  return { api, espaco, token, modo: new SessaoModo(), conta, pedidos };
}
