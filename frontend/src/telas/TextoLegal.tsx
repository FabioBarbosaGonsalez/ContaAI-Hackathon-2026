// Moldura dos termos de uso e da privacidade: o título, a versão, o aviso de rascunho, o índice e o texto.
//
// O índice e as seções saem da mesma lista: um título nunca diverge do link que leva a ele. Os links do índice
// são âncoras da própria página (Ancora, em shell/navegacao.tsx): não trocam de página.

import type { ReactNode } from 'react';
import { Ancora, Link } from '../shell/navegacao.tsx';
import { Pagina } from '../shell/Pagina.tsx';
import { AVISO_RASCUNHO } from './legal.ts';
import './publicas.css';

export interface SecaoLegal {
  /** Fixo no código, em minúsculas e com hífen: vira o id do h2 e a âncora do índice. */
  id: string;
  titulo: string;
  conteudo: ReactNode;
}

interface PropsTextoLegal {
  titulo: string;
  subtitulo: string;
  /** O outro documento, ao pé da página. */
  outro: { para: '/termos' | '/privacidade'; nome: string };
  secoes: SecaoLegal[];
}

export function TextoLegal({ titulo, subtitulo, outro, secoes }: PropsTextoLegal) {
  return (
    <Pagina titulo={titulo} subtitulo={subtitulo}>
      <div className="legal">
        <nav className="legal__indice" aria-label="Nesta página">
          <h2 className="legal__indice-titulo">Nesta página</h2>
          <ul>
            {secoes.map((secao) => (
              <li key={secao.id}>
                <Ancora id={secao.id}>{secao.titulo}</Ancora>
              </li>
            ))}
          </ul>
        </nav>
        <div className="legal__corpo">
          <p className="aviso-rascunho">{AVISO_RASCUNHO}</p>
          <article className="legal__texto">
            {secoes.map((secao) => (
              <section key={secao.id} aria-labelledby={secao.id} className="legal__secao">
                <h2 id={secao.id} tabIndex={-1}>
                  {secao.titulo}
                </h2>
                {secao.conteudo}
              </section>
            ))}
          </article>
          <p className="legal__outro">
            Veja também: <Link para={outro.para}>{outro.nome}</Link>.
          </p>
        </div>
      </div>
    </Pagina>
  );
}
