// O menu da conta na barra (C2b, etapa 9; ADR 0016, decisão 2 da C2b): um botão com o e-mail, que abre "Sua conta",
// as configurações da empresa (C3b, quando a conta tem empresa) e "Sair". Os detalhes e as outras ações ficam nas
// páginas.
//
// - É um botão que mostra e esconde uma lista (aria-expanded e aria-controls), e não um role="menu": são só um link
//   e um botão, e o Tab percorre os dois como em qualquer página. Esc fecha e devolve o foco ao botão; clicar fora
//   ou tirar o foco do menu também fecha.
// - O e-mail e o nome da organização vêm da API e vão como texto (o React escapa), cortados com reticências.
// - Sair apaga a sessão no servidor (SessaoConta.sair). Se o pedido falha, a sessão pode continuar aberta: a frase
//   diz isso, e a pessoa tenta de novo. Saiu, a tela vai à página inicial, sem deixar a página de antes no voltar.
// - Na folha do menu do celular, o mesmo conteúdo aparece aberto, sem o botão (`naFolha`).

import { useEffect, useId, useRef, useState } from 'react';
import { useSessao } from '../sessao/contexto.tsx';
import type { Conta } from '../sessao/conta.ts';
import { Link, navegar } from './navegacao.tsx';
import { ROTA_DA_CONTA, ROTA_DA_EMPRESA } from './rotas.ts';

export const FRASE_SAIR_FALHOU = 'Não foi possível sair agora. A sessão pode continuar aberta: tente de novo.';

/** Sair neste aparelho e ir à página inicial. `erro` é a frase para mostrar se o pedido falhar. */
export function useSair(): { sair: () => Promise<void>; saindo: boolean; erro: string | null } {
  const sessao = useSessao();
  const [saindo, setSaindo] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const sair = async () => {
    setSaindo(true);
    setErro(null);
    try {
      await sessao.conta.sair(sessao.api);
      navegar('/', { substituir: true });
    } catch {
      setErro(FRASE_SAIR_FALHOU);
      setSaindo(false);
    }
  };
  return { sair, saindo, erro };
}

interface PropsMenu {
  conta: Conta;
  /** Na folha do celular: o conteúdo aberto, sem o botão. */
  naFolha?: boolean;
  /** Na folha: fecha a folha quando um link leva a outra página. */
  aoNavegar?: () => void;
}

function Opcoes({ conta, aoNavegar }: { conta: Conta; aoNavegar?: () => void }) {
  const { sair, saindo, erro } = useSair();
  return (
    <>
      <p className="menu-conta__organizacao">{conta.organizacao.nome}</p>
      <ul className="menu-conta__lista">
        <li>
          <Link para={ROTA_DA_CONTA.caminho} className="menu-conta__item" onClick={aoNavegar}>
            {ROTA_DA_CONTA.nome}
          </Link>
        </li>
        {conta.empresas.length > 0 && (
          <li>
            <Link para={ROTA_DA_EMPRESA.caminho} className="menu-conta__item" onClick={aoNavegar}>
              {ROTA_DA_EMPRESA.nome}
            </Link>
          </li>
        )}
        <li>
          <button type="button" className="menu-conta__item" disabled={saindo} onClick={() => void sair()}>
            {saindo ? 'Saindo…' : 'Sair'}
          </button>
        </li>
      </ul>
      <p role="status" className="menu-conta__erro">
        {erro}
      </p>
    </>
  );
}

export function MenuDaConta({ conta, naFolha = false, aoNavegar }: PropsMenu) {
  const [aberto, setAberto] = useState(false);
  const idLista = useId();
  const refRaiz = useRef<HTMLDivElement>(null);
  const refBotao = useRef<HTMLButtonElement>(null);

  // Com o menu aberto: clicar fora ou levar o foco para fora fecha; Esc fecha e devolve o foco ao botão. Os
  // ouvintes ficam no documento e só existem enquanto o menu está aberto.
  useEffect(() => {
    if (!aberto) {
      return undefined;
    }
    const dentro = (alvo: EventTarget | null) => alvo instanceof Node && refRaiz.current?.contains(alvo) === true;
    const fora = (evento: Event) => {
      if (!dentro(evento.target)) {
        setAberto(false);
      }
    };
    const tecla = (evento: KeyboardEvent) => {
      if (evento.key === 'Escape') {
        setAberto(false);
        refBotao.current?.focus();
      }
    };
    document.addEventListener('pointerdown', fora);
    document.addEventListener('focusin', fora);
    document.addEventListener('keydown', tecla);
    return () => {
      document.removeEventListener('pointerdown', fora);
      document.removeEventListener('focusin', fora);
      document.removeEventListener('keydown', tecla);
    };
  }, [aberto]);

  if (naFolha) {
    return (
      <div className="menu-conta menu-conta--folha">
        <p className="menu-conta__email" translate="no">
          {conta.email}
        </p>
        <Opcoes conta={conta} {...(aoNavegar ? { aoNavegar } : {})} />
      </div>
    );
  }

  return (
    <div ref={refRaiz} className="menu-conta">
      <button
        ref={refBotao}
        type="button"
        className="botao-texto menu-conta__botao"
        aria-expanded={aberto}
        aria-controls={idLista}
        aria-label={`Conta: ${conta.email}`}
        onClick={() => {
          setAberto((a) => !a);
        }}
      >
        <span className="menu-conta__rotulo" translate="no">
          {conta.email}
        </span>
      </button>
      <div id={idLista} className="menu-conta__painel" hidden={!aberto}>
        <Opcoes
          conta={conta}
          aoNavegar={() => {
            setAberto(false);
          }}
        />
      </div>
    </div>
  );
}
