// Põe os headers da sessão nas requisições e reage às respostas que mudam a sessão.

import type { Middleware } from 'openapi-fetch';
import { CABECALHO_ESPACO, CABECALHO_TOKEN } from '../api/cliente.ts';
import { ROTAS_COM_ESPACO, ROTAS_COM_TOKEN, chaveDaRota } from '../api/rotas.ts';
import type { SessaoEspaco } from './espaco.ts';
import type { SessaoToken } from './token.ts';

export const PROBLEMA_ESPACO_INEXISTENTE = '/problemas/espaco-inexistente';

async function tipoDoProblema(resposta: Response): Promise<unknown> {
  try {
    const corpo: unknown = await resposta.clone().json();
    return typeof corpo === 'object' && corpo !== null ? (corpo as Record<string, unknown>).type : undefined;
  } catch {
    return undefined;
  }
}

/**
 * - O id do espaço só vai às rotas que o declaram no contrato; o token também.
 * - Um header que quem chamou já pôs não é trocado.
 * - 404 /problemas/espaco-inexistente numa requisição com espaço: o espaço venceu ou sumiu.
 * - 401 numa requisição que levou token: o token está errado, e a tela volta a pedi-lo.
 */
export function middlewareDaSessao(espaco: SessaoEspaco, token: SessaoToken): Middleware {
  return {
    onRequest({ request, schemaPath }) {
      const chave = chaveDaRota(request.method, schemaPath);
      if (ROTAS_COM_ESPACO.has(chave) && !request.headers.has(CABECALHO_ESPACO)) {
        const id = espaco.idAtual();
        if (id !== null) {
          request.headers.set(CABECALHO_ESPACO, id);
        }
      }
      if (ROTAS_COM_TOKEN.has(chave) && !request.headers.has(CABECALHO_TOKEN)) {
        const valor = token.atual();
        if (valor !== null) {
          request.headers.set(CABECALHO_TOKEN, valor);
        }
      }
      return request;
    },

    async onResponse({ request, response }) {
      if (response.status === 404 && request.headers.has(CABECALHO_ESPACO)) {
        const enviado = request.headers.get(CABECALHO_ESPACO);
        if ((await tipoDoProblema(response)) === PROBLEMA_ESPACO_INEXISTENTE && enviado === espaco.idAtual()) {
          espaco.marcarExpirado();
        }
      }
      if (response.status === 401 && request.headers.has(CABECALHO_TOKEN)) {
        token.limpar();
      }
      return undefined;
    },
  };
}
