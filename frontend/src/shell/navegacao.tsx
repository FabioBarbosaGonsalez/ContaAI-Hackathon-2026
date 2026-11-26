// Navegação entre as páginas, com a History API do navegador (sem biblioteca de rotas).
//
// - O endereço é a única fonte da página atual: voltar e avançar do navegador funcionam.
// - O id do espaço e o token nunca entram no endereço (docs/seguranca.md, regras da interface, item 5).

import { useSyncExternalStore, type AnchorHTMLAttributes, type MouseEvent } from 'react';
import type { Caminho } from './rotas.ts';

const EVENTO = 'contaai:navegou';

function assinar(aviso: () => void): () => void {
  globalThis.addEventListener('popstate', aviso);
  globalThis.addEventListener(EVENTO, aviso);
  return () => {
    globalThis.removeEventListener('popstate', aviso);
    globalThis.removeEventListener(EVENTO, aviso);
  };
}

function caminhoAtual(): string {
  return globalThis.location.pathname;
}

export function useCaminho(): string {
  return useSyncExternalStore(assinar, caminhoAtual);
}

/** Vai para outra página sem recarregar. */
export function navegar(caminho: Caminho): void {
  if (globalThis.location.pathname !== caminho) {
    globalThis.history.pushState(null, '', caminho);
  }
  globalThis.dispatchEvent(new Event(EVENTO));
  globalThis.scrollTo({ top: 0 });
}

type PropsLink = Omit<AnchorHTMLAttributes<HTMLAnchorElement>, 'href'> & { para: Caminho };

/**
 * Link para uma página da tela. Clique comum navega sem recarregar; Ctrl, Shift, botão do meio etc.
 * seguem o comportamento normal do navegador (abrir em nova aba).
 */
export function Link({ para, onClick, children, ...resto }: PropsLink) {
  const aoClicar = (evento: MouseEvent<HTMLAnchorElement>) => {
    onClick?.(evento);
    if (
      evento.defaultPrevented ||
      evento.button !== 0 ||
      evento.metaKey ||
      evento.ctrlKey ||
      evento.shiftKey ||
      evento.altKey
    ) {
      return;
    }
    evento.preventDefault();
    navegar(para);
  };
  return (
    <a {...resto} href={para} onClick={aoClicar}>
      {children}
    </a>
  );
}
