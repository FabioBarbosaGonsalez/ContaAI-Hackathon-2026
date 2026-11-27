// Ganchos do React para a sessão (useSyncExternalStore: o estado mora fora dos componentes).

import { useSyncExternalStore } from 'react';
import type { EstadoConta } from './conta.ts';
import { useSessao } from './contexto.tsx';
import type { EstadoEspaco } from './espaco.ts';
import type { EstadoModo } from './modo.ts';

export function useEspaco(): EstadoEspaco {
  const { espaco } = useSessao();
  return useSyncExternalStore(espaco.assinar, espaco.obter);
}

export function useModo(): EstadoModo {
  const { modo } = useSessao();
  return useSyncExternalStore(modo.assinar, modo.obter);
}

export function useConta(): EstadoConta {
  const { conta } = useSessao();
  return useSyncExternalStore(conta.assinar, conta.obter);
}

/**
 * As contas existem nesta instalação: a API respondeu ao /saude no modo real. No modo mock, as rotas da conta
 * respondem 501, e a tela não mostra Entrar nem Criar conta.
 */
export function useContasLigadas(): boolean {
  const modo = useModo();
  return modo.tipo === 'pronto' && modo.saude.modo === 'real';
}

/** Só diz se há token; o valor nunca passa pelos componentes. */
export function useTemToken(): boolean {
  const { token } = useSessao();
  return useSyncExternalStore(token.assinar, token.temToken);
}
