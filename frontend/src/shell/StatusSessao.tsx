// Onde a pessoa está: o modo da API e, no modo real, a demonstração compartilhada ou o próprio espaço.

import { useEffect, useId, useState } from 'react';
import { ErroApi } from '../api/problema.ts';
import { criarEspaco } from '../sessao/acoes.ts';
import { useSessao } from '../sessao/contexto.tsx';
import { useEspaco, useModo } from '../sessao/ganchos.ts';
import { formatarPrazo } from './prazo.ts';

/**
 * O que é o espaço, para quem avalia (ADR 0010). O aviso que POST /espacos devolve é escrito para quem
 * integra a API (fala do header e do token) e não é mostrado na tela.
 */
export const DESCRICAO_ESPACO =
  'Uma cópia própria dos dados fictícios. O que você mudar nela não afeta a demonstração compartilhada.';

/** A hora atual, atualizada a cada 30 s (o prazo é mostrado em minutos). */
function useAgora(): number {
  const [agora, setAgora] = useState(() => Date.now());
  useEffect(() => {
    const relogio = setInterval(() => {
      setAgora(Date.now());
    }, 30_000);
    return () => {
      clearInterval(relogio);
    };
  }, []);
  return agora;
}

function mensagemDeErroAoCriar(erro: unknown): string {
  if (!(erro instanceof ErroApi)) {
    return 'Não foi possível criar o espaço.';
  }
  if (erro.retryAfterS !== null && erro.retryAfterS > 0) {
    const espera = formatarPrazo(erro.retryAfterS * 1000);
    return `${erro.message} Tente de novo em ${espera}.`;
  }
  return erro.message;
}

interface PropsStatus {
  /** Na folha do menu, a descrição do espaço aparece; na barra, fica só para leitor de tela. */
  descricaoVisivel?: boolean;
}

export function StatusSessao({ descricaoVisivel = false }: PropsStatus) {
  const sessao = useSessao();
  const modo = useModo();
  const espaco = useEspaco();
  const agora = useAgora();
  const idDescricao = useId();
  const [criando, setCriando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  const criar = async () => {
    setCriando(true);
    setErro(null);
    try {
      await criarEspaco(sessao.api, sessao.espaco);
    } catch (e) {
      setErro(mensagemDeErroAoCriar(e));
    } finally {
      setCriando(false);
    }
  };

  const sair = () => {
    sessao.espaco.esquecer();
  };

  let conteudo;
  if (modo.tipo === 'carregando') {
    conteudo = <span className="status__texto">Conectando à API…</span>;
  } else if (modo.tipo === 'erro') {
    conteudo = (
      <>
        <span className="status__texto">API fora do ar.</span>
        <button type="button" className="botao-texto" onClick={() => void sessao.modo.carregar(sessao.api)}>
          Tentar de novo
        </button>
      </>
    );
  } else if (modo.saude.modo === 'mock') {
    conteudo = <span className="status__texto">Dados de demonstração, só leitura</span>;
  } else if (espaco.tipo === 'ativo') {
    conteudo = (
      <>
        <span className="status__texto">
          Seu espaço · vence em {formatarPrazo(espaco.espaco.expiraEm - agora)}
        </span>
        <button type="button" className="botao-texto" onClick={sair}>
          Sair do espaço
        </button>
      </>
    );
  } else {
    conteudo = (
      <>
        <span className="status__texto">
          {espaco.tipo === 'expirado' ? 'Seu espaço venceu.' : 'Demonstração compartilhada'}
        </span>
        <button
          type="button"
          className="botao-secundario"
          disabled={criando}
          aria-describedby={idDescricao}
          onClick={() => void criar()}
        >
          {espaco.tipo === 'expirado' ? 'Criar outro espaço' : 'Criar meu espaço'}
        </button>
      </>
    );
  }

  return (
    <div className="status">
      {/* role="status": quem usa leitor de tela ouve a troca de estado sem perder o foco. */}
      <div className="status__linha" role="status">
        {conteudo}
      </div>
      {modo.tipo === 'pronto' && modo.saude.modo === 'real' && (
        <p id={idDescricao} className={descricaoVisivel ? 'status__descricao' : 'so-leitor'}>
          {DESCRICAO_ESPACO}
        </p>
      )}
      {erro !== null && <p className="status__nota">{erro}</p>}
    </div>
  );
}
