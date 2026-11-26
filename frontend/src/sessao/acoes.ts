// Ações da sessão que chamam a API: o espaço de avaliação, o modo e a conta.

import { chamar, type ClienteApi } from '../api/cliente.ts';
import { ErroApi } from '../api/problema.ts';
import type { SessaoConta } from './conta.ts';
import { espacoDaResposta, type SessaoEspaco } from './espaco.ts';
import type { SessaoModo } from './modo.ts';

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

/**
 * Lê o modo da API (GET /saude) e, depois, a conta (GET /conta, só no modo real). A conta espera o modo: sem ele,
 * a tela não sabe se as rotas de conta existem. Serve para abrir a página e para o "Tentar de novo".
 */
export async function carregarSessao(sessao: { api: ClienteApi; modo: SessaoModo; conta: SessaoConta }): Promise<void> {
  sessao.conta.aguardar();
  await sessao.modo.carregar(sessao.api);
  await sessao.conta.carregar(sessao.api, sessao.modo);
}
