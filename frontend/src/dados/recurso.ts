// Um dado da API na tela: carrega, falha ou fica pronto, e recarrega sem apagar o que já está na tela
// (app-screens §11: uma atualização mantém os valores antigos até os novos chegarem).
//
// A chave diz de onde vem o dado (rota, empresa, regime e espaço). Trocou a chave, o pedido antigo é
// cancelado e o resultado dele é descartado: um espaço novo nunca mostra o catálogo do anterior.

import { useCallback, useEffect, useState } from 'react';
import type { Resposta } from '../api/cliente.ts';

export interface EstadoRecurso<T> {
  /** O último dado pronto desta chave (ou undefined antes do primeiro). */
  dados: T | undefined;
  /** Os dados vieram dos mocks (header X-ContaAI-Mock). */
  mock: boolean;
  carregando: boolean;
  erro: unknown;
  recarregar: () => void;
}

interface Resultado<T> {
  chave: string;
  dados?: T;
  mock: boolean;
  erro?: unknown;
}

export function useRecurso<T>(
  chave: string | null,
  carregar: (sinal: AbortSignal) => Promise<Resposta<T>>,
): EstadoRecurso<T> {
  const [versao, setVersao] = useState(0);
  const [resultado, setResultado] = useState<Resultado<T> | null>(null);
  const [pronta, setPronta] = useState<string | null>(null);

  useEffect(() => {
    if (chave === null) {
      return undefined;
    }
    const controle = new AbortController();
    const marca = `${chave}#${String(versao)}`;
    carregar(controle.signal).then(
      ({ dados, mock }) => {
        if (!controle.signal.aborted) {
          setResultado({ chave, dados, mock });
          setPronta(marca);
        }
      },
      (erro: unknown) => {
        if (!controle.signal.aborted) {
          setResultado((anterior) => {
            const novo: Resultado<T> = { chave, mock: anterior?.mock ?? false, erro };
            if (anterior?.chave === chave && anterior.dados !== undefined) {
              novo.dados = anterior.dados; // a falha de uma recarga não apaga o que já estava na tela
            }
            return novo;
          });
          setPronta(marca);
        }
      },
    );
    return () => {
      controle.abort();
    };
    // `carregar` muda a cada render; a chave é que diz quando o dado é outro.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chave, versao]);

  const recarregar = useCallback(() => {
    setVersao((v) => v + 1);
  }, []);

  const daChave = resultado !== null && resultado.chave === chave ? resultado : null;
  return {
    dados: daChave?.dados,
    mock: daChave?.mock ?? false,
    carregando: chave !== null && pronta !== `${chave}#${String(versao)}`,
    erro: daChave?.erro,
    recarregar,
  };
}
