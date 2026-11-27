// O que as páginas da conta (C2b, ADR 0016) mostram antes do próprio conteúdo: Entrar, Criar conta e Sua conta.
//
// - No modo mock as rotas da conta respondem 501: a página diz que as contas não existem nesta instalação e não
//   mostra formulário.
// - Antes do /saude e do /conta, a página espera: não oferece o formulário a quem talvez já tenha entrado.
// - Entrar e Criar conta são para quem não entrou. Quem já entrou e abre uma delas vai ao Painel da conta, com o
//   endereço trocado (o voltar não cai de novo na página). A exceção é `fluxoAberto`: a página acabou de entrar
//   ou de criar a conta e ainda mostra algo que só aparece uma vez (os códigos de recuperação).
// - Sua conta e o cadastro da empresa (C3a) são para quem entrou. Quem não entrou vê o caminho para entrar ou criar
//   a conta.

import { useEffect, type ReactNode } from 'react';
import { carregarSessao } from '../sessao/acoes.ts';
import { useSessao } from '../sessao/contexto.tsx';
import { useConta, useModo } from '../sessao/ganchos.ts';
import { BotaoDemonstracao } from '../shell/demonstracao.tsx';
import { Link, navegar } from '../shell/navegacao.tsx';
import { INICIO_DO_APP } from '../shell/rotas.ts';

interface PropsPorta {
  /** `visitante`: Entrar e Criar conta. `conta`: Sua conta. */
  exige: 'visitante' | 'conta';
  /** Só em `visitante`: a página acabou de abrir a sessão e ainda mostra algo; não vai ao Painel sozinha. */
  fluxoAberto?: boolean;
  /** Só em `conta`: o que a página faz, na frase para quem não entrou (ex.: "ver a sua conta"). */
  paraQue?: string;
  children: ReactNode;
}

function Espera({ texto }: { texto: string }) {
  return (
    <p className="pagina__vazia" role="status">
      {texto}
    </p>
  );
}

export function PortaDaConta({ exige, fluxoAberto = false, paraQue = 'ver a sua conta', children }: PropsPorta) {
  const sessao = useSessao();
  const modo = useModo();
  const conta = useConta();
  const irAoPainel = exige === 'visitante' && conta.tipo === 'conectada' && !fluxoAberto;

  useEffect(() => {
    if (irAoPainel) {
      sessao.conta.voltarParaConta();
      navegar(INICIO_DO_APP, { substituir: true });
    }
  }, [irAoPainel, sessao]);

  if (modo.tipo === 'carregando') {
    return <Espera texto="Conectando à API…" />;
  }
  if (modo.tipo === 'erro') {
    return (
      <div className="vazio porta__curta">
        <p>A API está fora do ar, e não dá para entrar nem criar a conta agora.</p>
        <p>
          <button type="button" className="botao-secundario" onClick={() => void carregarSessao(sessao)}>
            Tentar de novo
          </button>
        </p>
      </div>
    );
  }
  if (modo.saude.modo === 'mock') {
    return (
      <div className="vazio porta__curta">
        <p>Nesta instalação, as contas não existem: só a demonstração, para leitura.</p>
        <p>
          <BotaoDemonstracao className="botao-principal" />
        </p>
      </div>
    );
  }
  if (conta.tipo === 'carregando' || conta.tipo === 'desligada') {
    return <Espera texto="Conferindo a sua conta…" />;
  }

  if (exige === 'visitante') {
    if (irAoPainel) {
      return <Espera texto="Você já entrou. Abrindo o Painel…" />;
    }
    return children;
  }

  if (conta.tipo === 'conectada') {
    return children;
  }
  if (conta.tipo === 'erro') {
    return (
      <div className="vazio porta__curta">
        <p>Não foi possível conferir a sua conta.</p>
        <p>
          <button
            type="button"
            className="botao-secundario"
            onClick={() => void sessao.conta.carregar(sessao.api, sessao.modo)}
          >
            Tentar de novo
          </button>
        </p>
      </div>
    );
  }
  return (
    <div className="vazio porta__curta">
      <p>
        {conta.tipo === 'encerrada' ? `Sua sessão terminou. Entre de novo para ${paraQue}.` : `Entre para ${paraQue}.`}
      </p>
      <p className="porta__acoes">
        <Link para="/entrar" className="botao-principal">
          Entrar
        </Link>
        <Link para="/criar-conta" className="botao-secundario">
          Criar conta
        </Link>
      </p>
    </div>
  );
}
