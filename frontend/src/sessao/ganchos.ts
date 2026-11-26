// Ganchos do React para a sessão (useSyncExternalStore: o estado mora fora dos componentes).

import { useSyncExternalStore } from 'react';
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

/** Só diz se há token; o valor nunca passa pelos componentes. */
export function useTemToken(): boolean {
  const { token } = useSessao();
  return useSyncExternalStore(token.assinar, token.temToken);
}
