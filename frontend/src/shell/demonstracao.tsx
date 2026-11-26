// A demonstração e a conta (C2, ADR 0016):
// - quem não tem conta vê a demonstração sem cadastro (plano v2.1, decisão 1);
// - quem tem conta também pode vê-la, como todo mundo, e volta à conta pela faixa (C2, decisão 2);
// - a faixa diz, em toda página do app fora da conta, que os dados são fictícios (P10).

import type { MouseEvent } from 'react';
import { useSessao } from '../sessao/contexto.tsx';
import { useConta, useModo } from '../sessao/ganchos.ts';
import { Link } from './navegacao.tsx';
import { INICIO_DO_APP } from './rotas.ts';

export const TEXTO_DEMONSTRACAO = 'Demonstração: a empresa, as notas e o cliente são fictícios.';

interface PropsBotao {
  className?: string;
  /** Ex.: fechar a folha do menu. */
  aoEscolher?: () => void;
}

/** Abre o app na demonstração. Quem tem conta continua conectado; os pedidos de dados saem sem o cookie. */
export function BotaoDemonstracao({ className, aoEscolher }: PropsBotao) {
  const { conta } = useSessao();
  const aoClicar = (evento: MouseEvent<HTMLAnchorElement>) => {
    // Também no Ctrl+clique: a aba nova abre sem a escolha (ela não é guardada), e esta aba fica como está.
    if (evento.button === 0 && !evento.metaKey && !evento.ctrlKey && !evento.shiftKey && !evento.altKey) {
      conta.verDemonstracao();
    }
    aoEscolher?.();
  };
  return (
    <Link para={INICIO_DO_APP} className={className} onClick={aoClicar}>
      Explorar a demonstração
    </Link>
  );
}

/** Volta aos dados da conta. */
export function BotaoMinhaConta({ className, aoEscolher, texto = 'Minha conta' }: PropsBotao & { texto?: string }) {
  const { conta } = useSessao();
  const aoClicar = (evento: MouseEvent<HTMLAnchorElement>) => {
    if (evento.button === 0 && !evento.metaKey && !evento.ctrlKey && !evento.shiftKey && !evento.altKey) {
      conta.voltarParaConta();
    }
    aoEscolher?.();
  };
  return (
    <Link para={INICIO_DO_APP} className={className} onClick={aoClicar}>
      {texto}
    </Link>
  );
}

/** A faixa sob a barra, nas páginas do app fora da conta. */
export function AvisoDemonstracao() {
  const sessao = useSessao();
  const modo = useModo();
  const conta = useConta();
  if (modo.tipo !== 'pronto' || (conta.tipo === 'conectada' && !conta.naDemo)) {
    return null;
  }

  let complemento = null;
  let texto = TEXTO_DEMONSTRACAO;
  if (conta.tipo === 'encerrada') {
    texto = 'Sua sessão terminou, e você voltou à demonstração. A empresa, as notas e o cliente são fictícios.';
    complemento = (
      <button
        type="button"
        className="botao-texto"
        onClick={() => {
          sessao.conta.dispensarAviso();
        }}
      >
        Entendi
      </button>
    );
  } else if (conta.tipo === 'erro') {
    texto = `${TEXTO_DEMONSTRACAO} Não foi possível conferir a sua conta.`;
    complemento = (
      <button type="button" className="botao-texto" onClick={() => void sessao.conta.carregar(sessao.api, sessao.modo)}>
        Tentar de novo
      </button>
    );
  } else if (conta.tipo === 'conectada') {
    complemento = <BotaoMinhaConta className="botao-texto" texto="Voltar à minha conta" />;
  }

  return (
    <div className="aviso-demo">
      {/* role="status": a troca para "sua sessão terminou" é lida sem tirar o foco de onde a pessoa está. */}
      <div className="coluna aviso-demo__linha" role="status">
        <p>{texto}</p>
        {complemento}
      </div>
    </div>
  );
}
