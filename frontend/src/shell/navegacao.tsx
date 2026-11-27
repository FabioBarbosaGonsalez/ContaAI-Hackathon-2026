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

/**
 * Vai para outra página sem recarregar. `substituir` troca o endereço atual em vez de empilhar outro: usado quando
 * a página aberta não serve a quem chegou (ex.: quem já entrou e abre /entrar), para o voltar não cair nela de novo.
 */
export function navegar(caminho: Caminho, { substituir = false } = {}): void {
  if (globalThis.location.pathname !== caminho) {
    if (substituir) {
      globalThis.history.replaceState(null, '', caminho);
    } else {
      globalThis.history.pushState(null, '', caminho);
    }
  }
  globalThis.dispatchEvent(new Event(EVENTO));
  globalThis.scrollTo({ top: 0 });
}

type PropsLink = Omit<AnchorHTMLAttributes<HTMLAnchorElement>, 'href'> & { para: Caminho };

/**
 * Link para uma página da tela. Clique comum navega sem recarregar; Ctrl, Shift, botão do meio etc.
 * seguem o comportamento normal do navegador (abrir em nova aba). Com `target="_blank"` (os termos, abertos do
 * meio do cadastro sem perder o que foi digitado), o navegador abre a outra aba, sem `opener`.
 */
export function Link({ para, onClick, children, ...resto }: PropsLink) {
  const novaAba = resto.target === '_blank';
  const aoClicar = (evento: MouseEvent<HTMLAnchorElement>) => {
    onClick?.(evento);
    if (
      novaAba ||
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
    <a {...resto} rel={novaAba ? 'noopener noreferrer' : resto.rel} href={para} onClick={aoClicar}>
      {children}
    </a>
  );
}

const ID_DE_ANCORA = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

type PropsAncora = Omit<AnchorHTMLAttributes<HTMLAnchorElement>, 'href'> & { id: string };

/**
 * Link para uma seção da própria página (#id), como o índice dos termos. Só monta o fragmento: o navegador não
 * troca de página. O id precisa ser fixo no código, em minúsculas com hífen; fora disso, a tela quebra em vez de
 * montar o endereço.
 */
export function Ancora({ id, children, ...resto }: PropsAncora) {
  if (!ID_DE_ANCORA.test(id)) {
    throw new Error('Âncora com id fora do padrão');
  }
  return (
    <a {...resto} href={`#${id}`}>
      {children}
    </a>
  );
}

const NOME_DE_ARQUIVO = /^[a-z0-9]+(?:-[a-z0-9]+)*\.xml$/;

type PropsArquivo = Omit<AnchorHTMLAttributes<HTMLAnchorElement>, 'href' | 'download'> & {
  /** O endereço que o build deu ao arquivo (import.meta.glob com ?url): um caminho da própria tela. */
  endereco: string;
  /** O nome com que o arquivo é salvo. */
  nome: string;
};

/**
 * Link para baixar um arquivo servido pela própria tela, como as notas de exemplo (C2c). Só aceita um caminho que
 * começa com uma barra, na mesma origem, sem consulta nem fragmento e terminado no nome pedido (nada de esquema de
 * script, data: ou //outro.site), e um nome em minúsculas com hífen e .xml. Fora disso, a tela quebra em vez de
 * montar o endereço.
 */
export function ArquivoParaBaixar({ endereco, nome, children, ...resto }: PropsArquivo) {
  if (!NOME_DE_ARQUIVO.test(nome)) {
    throw new Error('Arquivo para baixar com nome fora do padrão');
  }
  // O build põe um hash no nome (nfe-compra-2-AbC12_-x.xml); o servidor de desenvolvimento serve o nome puro.
  const base = nome.slice(0, -'.xml'.length);
  const doArquivo = new RegExp(`/${base}(?:-[A-Za-z0-9_-]+)?\\.xml$`);
  const origem = globalThis.location.origin;
  const url = new URL(endereco, origem);
  if (
    !endereco.startsWith('/') ||
    endereco.startsWith('//') ||
    endereco.includes('\\') ||
    url.origin !== origem ||
    url.search !== '' ||
    url.hash !== '' ||
    !doArquivo.test(url.pathname)
  ) {
    throw new Error('Arquivo para baixar fora da própria tela');
  }
  return (
    <a {...resto} href={url.pathname} download={nome}>
      {children}
    </a>
  );
}
