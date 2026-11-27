// As páginas da tela. Painel e Catálogo entraram no PR 3a, Regime e Notas no 3b, as páginas públicas na C2a,
// Entrar, Criar conta e Sua conta na C2b, a primeira vez e o cadastro da empresa na C3a; Contador entra no 3c.

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
import { ROTA_DO_CADASTRO, type CaminhoDoApp, type CaminhoPublico } from './rotas.ts';
import '../telas/empresa.css';

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
 * A primeira vez da conta (C3a, ADR 0018): a organização ainda não tem empresa, e as páginas do app não têm o que
 * mostrar. A página mantém o título e diz o próximo passo, no lugar onde os dados vão aparecer (app-screens §11):
 * o dono cadastra a empresa; o membro (com os convites do 3c) fica sabendo quem cadastra.
 */
export function PrimeiraVez({ titulo, dono }: { titulo: string; dono: boolean }) {
  return (
    <Pagina titulo={titulo}>
      <div className="vazio primeira-vez">
        {dono ? (
          <>
            <h2 className="primeira-vez__titulo">Cadastre a empresa para começar</h2>
            <p>
              O ContaAI estima a CBS e o IBS de cada item que a empresa vende, com as calculadoras oficiais da Receita
              Federal. Para isso, ele precisa do CNPJ, do regime no Simples Nacional, do município e da atividade.
            </p>
            <p className="primeira-vez__acoes">
              <Link para={ROTA_DO_CADASTRO.caminho} className="botao-principal">
                {ROTA_DO_CADASTRO.nome}
              </Link>
              <BotaoDemonstracao className="botao-secundario" />
            </p>
          </>
        ) : (
          <>
            <p>Sua organização ainda não tem empresa. Só o dono da organização cadastra a empresa.</p>
            <p className="primeira-vez__acoes">
              <BotaoDemonstracao className="botao-principal" />
            </p>
          </>
        )}
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
