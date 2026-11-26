// Ações do espaço de avaliação que chamam a API.

import { chamar, type ClienteApi } from '../api/cliente.ts';
import { ErroApi } from '../api/problema.ts';
import { espacoDaResposta, type SessaoEspaco } from './espaco.ts';

/**
 * Cria um espaço (POST /espacos) e o ativa. Devolve o aviso que a API manda mostrar.
 * Lança ErroApi: 501 no modo mock, 503 /problemas/espacos-esgotados com Retry-After, 429.
 */
export async function criarEspaco(cliente: ClienteApi, sessao: SessaoEspaco): Promise<string> {
  const { dados } = await chamar(cliente.POST('/espacos'));
  const espaco = espacoDaResposta(dados, Date.now());
  if (espaco === null) {
    throw new ErroApi({ tipo: 'formato' });
  }
  sessao.ativar(espaco);
  return dados.aviso;
}

/**
 * Confere com a API se o espaço salvo ainda existe (GET /espacos/atual), por exemplo ao abrir a página.
 *
 * - A validade local não é recontada aqui: a resposta não traz a hora do servidor, e somar a duração inteira
 *   de novo esticaria o prazo.
 * - Se a API não reconhecer o espaço, o middleware da sessão o marca como expirado.
 * - Sem espaço ativo, não chama nada.
 */
export async function verificarEspaco(cliente: ClienteApi, sessao: SessaoEspaco): Promise<void> {
  const id = sessao.idAtual();
  if (id === null) {
    return;
  }
  await chamar(cliente.GET('/espacos/atual', { params: { header: { 'X-ContaAI-Espaco': id } } }));
}
