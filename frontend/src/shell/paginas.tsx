// As páginas da fundação. O conteúdo de cada tela entra no PR 3 da E5 (telas com o portão da skill).

import { Link } from './navegacao.tsx';
import { Pagina } from './Pagina.tsx';
import type { Caminho } from './rotas.ts';

function EmConstrucao() {
  return <p className="pagina__vazia">Esta tela entra na próxima etapa da interface.</p>;
}

export const PAGINAS: Record<Caminho, () => React.JSX.Element> = {
  '/': () => (
    <Pagina titulo="Painel">
      <EmConstrucao />
    </Pagina>
  ),
  '/catalogo': () => (
    <Pagina titulo="Catálogo">
      <EmConstrucao />
    </Pagina>
  ),
  '/regime': () => (
    <Pagina titulo="Regime">
      <EmConstrucao />
    </Pagina>
  ),
  '/notas': () => (
    <Pagina titulo="Notas">
      <EmConstrucao />
    </Pagina>
  ),
  '/contador': () => (
    <Pagina titulo="Contador">
      <EmConstrucao />
    </Pagina>
  ),
};

export function NaoEncontrada() {
  return (
    <Pagina titulo="Página não encontrada">
      <p className="pagina__vazia">
        Este endereço não existe. <Link para="/">Voltar ao painel</Link>
      </p>
    </Pagina>
  );
}
