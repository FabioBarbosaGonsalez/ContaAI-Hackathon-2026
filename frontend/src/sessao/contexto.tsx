// A sessão chega aos componentes por contexto: o main.tsx passa as instâncias da página, e os testes
// passam instâncias próprias, com um fetch falso.

import { createContext, useContext, type ReactNode } from 'react';
import type { ClienteApi } from '../api/cliente.ts';
import type { SessaoConta } from './conta.ts';
import type { SessaoEspaco } from './espaco.ts';
import type { SessaoModo } from './modo.ts';
import type { SessaoToken } from './token.ts';

export interface Sessao {
  api: ClienteApi;
  espaco: SessaoEspaco;
  token: SessaoToken;
  modo: SessaoModo;
  conta: SessaoConta;
}

const ContextoSessao = createContext<Sessao | null>(null);

export function ProvedorSessao({ sessao, children }: { sessao: Sessao; children: ReactNode }) {
  return <ContextoSessao value={sessao}>{children}</ContextoSessao>;
}

export function useSessao(): Sessao {
  const sessao = useContext(ContextoSessao);
  if (sessao === null) {
    throw new Error('useSessao fora do ProvedorSessao');
  }
  return sessao;
}
