// Shell sem barra lateral (direction.json, shell "no-sidebar"):
// - barra de 48px no fundo da página sobre uma coluna centrada;
// - a marca na borda esquerda da coluna;
// - os destinos em texto e, à direita, onde a pessoa está (modo e espaço).
// No celular, a barra fica com a marca e um botão de menu, e os destinos vão para uma folha de tela cheia.

import { useRef } from 'react';
import './shell.css';
import { Link, useCaminho } from './navegacao.tsx';
import { NaoEncontrada, PAGINAS } from './paginas.tsx';
import { Rodape } from './Rodape.tsx';
import { ROTAS, rotaDe } from './rotas.ts';
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

export function Shell() {
  const caminho = useCaminho();
  const rota = rotaDe(caminho);
  const PaginaAtual = rota === null ? NaoEncontrada : PAGINAS[rota.caminho];
  const refMenu = useRef<HTMLDialogElement>(null);

  const abrirMenu = () => refMenu.current?.showModal();
  const fecharMenu = () => refMenu.current?.close();

  return (
    <>
      <a className="pular" href="#conteudo">
        Pular para o conteúdo
      </a>
      <header className="barra">
        <div className="coluna barra__linha">
          <Link para="/" className="marca">
            ContaAI
          </Link>
          <nav className="barra__destinos" aria-label="Principal">
            <Destinos atual={rota?.caminho ?? null} />
          </nav>
          <div className="barra__status">
            <StatusSessao />
          </div>
          <button type="button" className="barra__menu botao-secundario" aria-haspopup="dialog" onClick={abrirMenu}>
            Menu
          </button>
        </div>
      </header>

      <dialog ref={refMenu} className="folha" aria-label="Menu">
        <div className="folha__topo">
          <span className="marca">ContaAI</span>
          <button type="button" className="botao-secundario" onClick={fecharMenu}>
            Fechar
          </button>
        </div>
        <nav aria-label="Principal no celular">
          <Destinos atual={rota?.caminho ?? null} aoEscolher={fecharMenu} />
        </nav>
        <StatusSessao descricaoVisivel />
      </dialog>

      <main id="conteudo" className="coluna conteudo" tabIndex={-1}>
        <PaginaAtual />
      </main>

      <Rodape />
    </>
  );
}
