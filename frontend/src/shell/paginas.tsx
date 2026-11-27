// As páginas da tela. Painel e Catálogo entraram no PR 3a, Regime e Notas no 3b, as páginas públicas na C2a,
// Entrar, Criar conta e Sua conta na C2b; Contador entra no 3c.

import { Catalogo } from '../telas/Catalogo.tsx';
import { CriarConta } from '../telas/CriarConta.tsx';
import { Entrar } from '../telas/Entrar.tsx';
import { Inicio } from '../telas/Inicio.tsx';
import { Notas } from '../telas/Notas.tsx';
import { Painel } from '../telas/Painel.tsx';
import { Privacidade } from '../telas/Privacidade.tsx';
import { Regime } from '../telas/Regime.tsx';
import { Termos } from '../telas/Termos.tsx';
import { BotaoDemonstracao } from './demonstracao.tsx';
import { Link } from './navegacao.tsx';
import { Pagina } from './Pagina.tsx';
import type { CaminhoDoApp, CaminhoPublico } from './rotas.ts';

function EmConstrucao() {
  return <p className="pagina__vazia">Esta tela entra na próxima etapa da interface.</p>;
}

export const PAGINAS: Record<CaminhoDoApp, () => React.JSX.Element> = {
  '/painel': Painel,
  '/catalogo': Catalogo,
  '/regime': Regime,
  '/notas': Notas,
  '/contador': () => (
    <Pagina titulo="Contador">
      <EmConstrucao />
    </Pagina>
  ),
};

export const PAGINAS_PUBLICAS: Record<CaminhoPublico, () => React.JSX.Element> = {
  '/': Inicio,
  '/entrar': Entrar,
  '/criar-conta': CriarConta,
  '/termos': Termos,
  '/privacidade': Privacidade,
};

/**
 * A conta sem empresa (C2): as páginas do app não têm o que mostrar, porque o cadastro da empresa entra na C3.
 * A página mantém o título e diz o próximo passo, no lugar onde os dados vão aparecer (app-screens §11).
 */
export function SemEmpresa({ titulo }: { titulo: string }) {
  return (
    <Pagina titulo={titulo}>
      <div className="vazio sem-empresa">
        <p>
          Sua organização ainda não tem empresa, e o cadastro de empresas ainda não está disponível. Enquanto isso,
          veja todas as telas na demonstração.
        </p>
        <p>
          <BotaoDemonstracao className="botao-principal" />
        </p>
      </div>
    </Pagina>
  );
}

export function NaoEncontrada() {
  return (
    <Pagina titulo="Página não encontrada">
      <p className="pagina__vazia">
        Este endereço não existe. <Link para="/">Voltar ao início</Link>
      </p>
    </Pagina>
  );
}
