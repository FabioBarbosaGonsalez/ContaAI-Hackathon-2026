// As páginas da tela. Painel e Catálogo entraram no PR 3a, Regime e Notas no 3b; Contador entra no 3c.

import { Catalogo } from '../telas/Catalogo.tsx';
import { Notas } from '../telas/Notas.tsx';
import { Painel } from '../telas/Painel.tsx';
import { Regime } from '../telas/Regime.tsx';
import { Link } from './navegacao.tsx';
import { Pagina } from './Pagina.tsx';
import type { Caminho } from './rotas.ts';

function EmConstrucao() {
  return <p className="pagina__vazia">Esta tela entra na próxima etapa da interface.</p>;
}

export const PAGINAS: Record<Caminho, () => React.JSX.Element> = {
  '/': Painel,
  '/catalogo': Catalogo,
  '/regime': Regime,
  '/notas': Notas,
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
