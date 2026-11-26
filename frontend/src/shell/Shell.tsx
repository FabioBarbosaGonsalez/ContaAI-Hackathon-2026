// Shell sem barra lateral (direction.json, shell "no-sidebar"):
// - barra preta de 48px, com o texto em branco (pedido do usuário em 2026-11-26), sobre uma coluna centrada;
// - a marca na borda esquerda da coluna;
// - no app: os destinos em texto e, à direita, onde a pessoa está (modo, espaço ou conta). No celular, a barra
//   fica com a marca e um botão de menu, e os destinos vão para uma folha de tela cheia;
// - nas páginas públicas (C2, ADR 0016): só a marca e o caminho para a demonstração, sem os destinos do app.

import { useRef, type ReactNode } from 'react';
import './shell.css';
import { useConta } from '../sessao/ganchos.ts';
import { BarreiraDeErro } from './BarreiraDeErro.tsx';
import { AvisoDemonstracao, BotaoDemonstracao, BotaoMinhaConta } from './demonstracao.tsx';
import { Marca } from './Marca.tsx';
import { Link, useCaminho } from './navegacao.tsx';
import { NaoEncontrada, PAGINAS, PAGINAS_PUBLICAS, SemEmpresa } from './paginas.tsx';
import { Rodape } from './Rodape.tsx';
import { ROTAS, rotaDe, rotaPublicaDe } from './rotas.ts';
import { StatusSessao } from './StatusSessao.tsx';

function Destinos({ atual, aoEscolher }: { atual: string | null; aoEscolher?: () => void }) {
  return (
    <ul className="destinos">
      {ROTAS.map((rota) => (
        <li key={rota.caminho}>
          <Link
            para={rota.caminho}
            className="destinos__link"
            aria-current={rota.caminho === atual ? 'page' : undefined}
            onClick={aoEscolher}
          >
            {rota.nome}
          </Link>
        </li>
      ))}
    </ul>
  );
}

interface PropsMoldura {
  barra: ReactNode;
  /** Fora da barra preta: a folha do menu e a faixa da demonstração (elas têm o fundo claro). */
  depoisDaBarra?: ReactNode;
  chave: string;
  children: ReactNode;
}

/** O que toda página tem: pular para o conteúdo, a barra, o conteúdo e o rodapé. */
function Moldura({ barra, depoisDaBarra, chave, children }: PropsMoldura) {
  return (
    <>
      <a className="pular" href="#conteudo">
        Pular para o conteúdo
      </a>
      <header className="barra">
        <div className="coluna barra__linha">
          <Link para="/" className="marca">
            <Marca />
          </Link>
          {barra}
        </div>
      </header>
      {depoisDaBarra}

      <main id="conteudo" className="coluna conteudo" tabIndex={-1}>
        <BarreiraDeErro key={chave}>{children}</BarreiraDeErro>
      </main>

      <Rodape />
    </>
  );
}

function ShellPublico({ caminho, children }: { caminho: string; children: ReactNode }) {
  const conta = useConta();
  const conectada = conta.tipo === 'conectada';
  return (
    <Moldura
      chave={caminho}
      barra={
        <div className="barra__publica">
          {conectada ? <BotaoMinhaConta className="botao-texto" /> : <BotaoDemonstracao className="botao-texto" />}
        </div>
      }
    >
      {children}
    </Moldura>
  );
}

function ShellDoApp({ caminho, atual, children }: { caminho: string; atual: string | null; children: ReactNode }) {
  const refMenu = useRef<HTMLDialogElement>(null);
  const abrirMenu = () => refMenu.current?.showModal();
  const fecharMenu = () => refMenu.current?.close();

  return (
    <Moldura
      chave={caminho}
      depoisDaBarra={
        <>
          <dialog ref={refMenu} className="folha" aria-label="Menu">
            <div className="folha__topo">
              <span className="marca">
                <Marca />
              </span>
              <button type="button" className="botao-secundario" onClick={fecharMenu}>
                Fechar
              </button>
            </div>
            <nav aria-label="Principal no celular">
              <Destinos atual={atual} aoEscolher={fecharMenu} />
            </nav>
            <StatusSessao descricaoVisivel aoNavegar={fecharMenu} />
          </dialog>
          <AvisoDemonstracao />
        </>
      }
      barra={
        <>
          <nav className="barra__destinos" aria-label="Principal">
            <Destinos atual={atual} />
          </nav>
          <div className="barra__status">
            <StatusSessao />
          </div>
          <button type="button" className="barra__menu botao-secundario" aria-haspopup="dialog" onClick={abrirMenu}>
            Menu
          </button>
        </>
      }
    >
      {children}
    </Moldura>
  );
}

export function Shell() {
  const caminho = useCaminho();
  const conta = useConta();

  const publica = rotaPublicaDe(caminho);
  if (publica !== null) {
    const PaginaPublica = PAGINAS_PUBLICAS[publica.caminho];
    return (
      <ShellPublico caminho={caminho}>
        <PaginaPublica />
      </ShellPublico>
    );
  }

  const rota = rotaDe(caminho);
  // Na conta, as páginas do app dão lugar ao estado vazio: a organização ainda não tem empresa (C3).
  const naConta = conta.tipo === 'conectada' && !conta.naDemo;
  let pagina: ReactNode;
  if (rota === null) {
    pagina = <NaoEncontrada />;
  } else if (naConta) {
    pagina = <SemEmpresa titulo={rota.nome} />;
  } else {
    const PaginaAtual = PAGINAS[rota.caminho];
    pagina = <PaginaAtual />;
  }
  return (
    <ShellDoApp caminho={caminho} atual={rota?.caminho ?? null}>
      {pagina}
    </ShellDoApp>
  );
}
