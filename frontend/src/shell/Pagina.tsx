// Moldura de cada página: o título (h1), o nome na aba do navegador e o foco depois de navegar.

import { useEffect, useRef, type ReactNode } from 'react';

const PRODUTO = 'ContaAI';

interface PropsPagina {
  titulo: string;
  /** Uma frase cinza sobre os dados da página (opcional). */
  subtitulo?: string;
  /** Um link ao lado dos dados da página, abaixo do título (opcional): ex. as configurações da empresa no Painel. */
  acao?: ReactNode;
  children?: ReactNode;
}

/** Na primeira página aberta, o foco fica onde o navegador o pôs; só as navegações seguintes o movem. */
let primeiraPagina = true;

export function Pagina({ titulo, subtitulo, acao, children }: PropsPagina) {
  const refTitulo = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    document.title = `${titulo} · ${PRODUTO}`;
    if (primeiraPagina) {
      primeiraPagina = false;
      return;
    }
    // Quem usa leitor de tela ou teclado ouve o novo título e segue dele (a página não recarrega).
    refTitulo.current?.focus({ preventScroll: true });
  }, [titulo]);

  return (
    <>
      <div className="pagina__cabecalho">
        <h1 ref={refTitulo} tabIndex={-1}>
          {titulo}
        </h1>
        {subtitulo !== undefined && <p className="pagina__subtitulo">{subtitulo}</p>}
        {acao !== undefined && <p className="pagina__acao">{acao}</p>}
      </div>
      {children}
    </>
  );
}

/** Só para os testes: volta ao estado de página recém-aberta. */
export function reiniciarFocoDePagina(): void {
  primeiraPagina = true;
}
