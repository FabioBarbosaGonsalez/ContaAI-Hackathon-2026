// Põe os headers da sessão nas requisições e reage às respostas que mudam a sessão.

import type { Middleware } from 'openapi-fetch';
import { CABECALHO_ESPACO, CABECALHO_TOKEN } from '../api/cliente.ts';
import { ROTAS_COM_ESPACO, ROTAS_COM_TOKEN, ROTAS_DA_CONTA, ROTAS_DE_ENTRADA, chaveDaRota } from '../api/rotas.ts';
import type { SessaoConta } from './conta.ts';
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
 * - O cookie da sessão (ADR 0016):
 *   - as rotas da conta sempre o levam;
 *   - as outras só o levam quando a tela mostra os dados da conta. Fora disso (sem conta, ou com a conta vendo a
 *     demonstração), o pedido sai com `credentials: 'omit'`, e a API responde como a quem não tem conta;
 *   - na conta, nem o id do espaço nem o token da demo vão: para a API, o espaço do header vence o cookie.
 * - 404 /problemas/espaco-inexistente numa requisição com espaço: o espaço venceu ou sumiu.
 * - 401 numa requisição que levou token: o token está errado, e a tela volta a pedi-lo.
 * - 401 numa requisição que levou o cookie, sem token e fora das rotas de entrada: a sessão da conta acabou.
 */
export function middlewareDaSessao(espaco: SessaoEspaco, token: SessaoToken, conta: SessaoConta): Middleware {
  return {
    onRequest({ request, schemaPath }) {
      const chave = chaveDaRota(request.method, schemaPath);
      const naConta = conta.naConta();
      if (ROTAS_COM_ESPACO.has(chave) && !naConta && !request.headers.has(CABECALHO_ESPACO)) {
        const id = espaco.idAtual();
        if (id !== null) {
          request.headers.set(CABECALHO_ESPACO, id);
        }
      }
      if (ROTAS_COM_TOKEN.has(chave) && !naConta && !request.headers.has(CABECALHO_TOKEN)) {
        const valor = token.atual();
        if (valor !== null) {
          request.headers.set(CABECALHO_TOKEN, valor);
        }
      }
      if (!ROTAS_DA_CONTA.has(chave) && !naConta) {
        // Copiar a Request com opções zera o referrer; o fetch do cliente o zera de novo de qualquer forma.
        return new Request(request, { credentials: 'omit' });
      }
      return request;
    },

    async onResponse({ request, response, schemaPath }) {
      if (response.status === 404 && request.headers.has(CABECALHO_ESPACO)) {
        const enviado = request.headers.get(CABECALHO_ESPACO);
        if ((await tipoDoProblema(response)) === PROBLEMA_ESPACO_INEXISTENTE && enviado === espaco.idAtual()) {
          espaco.marcarExpirado();
        }
      }
      if (response.status === 401 && request.headers.has(CABECALHO_TOKEN)) {
        token.limpar();
      } else if (
        response.status === 401 &&
        request.credentials !== 'omit' &&
        !ROTAS_DE_ENTRADA.has(chaveDaRota(request.method, schemaPath))
      ) {
        conta.marcarEncerrada();
      }
      return undefined;
    },
  };
}
