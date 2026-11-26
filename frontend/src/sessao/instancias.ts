// A sessão da página: uma instância de cada, ligadas ao cliente da API.

import { criarCliente, type ClienteApi } from '../api/cliente.ts';
import { verificarEspaco } from './acoes.ts';
import { CHAVE_ARMAZENAMENTO_ESPACO, SessaoEspaco } from './espaco.ts';
import { middlewareDaSessao } from './middleware.ts';
import { SessaoModo } from './modo.ts';
import { SessaoToken } from './token.ts';

export const sessaoEspaco = new SessaoEspaco();
export const sessaoToken = new SessaoToken();
export const sessaoModo = new SessaoModo();

export const api: ClienteApi = criarCliente();
api.use(middlewareDaSessao(sessaoEspaco, sessaoToken));

/**
 * Ao abrir a página: lê o modo da API e, no modo real, confere se o espaço salvo ainda existe.
 * Uma falha aqui não derruba a página: o modo fica em erro, e a tela diz que a API está fora do ar.
 */
export async function iniciarSessao(): Promise<void> {
  await sessaoModo.carregar(api);
  if (sessaoModo.espacoDisponivel()) {
    // O 404 de um espaço vencido já é tratado pelo middleware; outra falha mantém o espaço salvo.
    await verificarEspaco(api, sessaoEspaco).catch(() => undefined);
  }
}

// Outra aba criou, venceu ou esqueceu o espaço: esta aba acompanha.
globalThis.addEventListener('storage', (evento: StorageEvent) => {
  if (evento.key === null || evento.key === CHAVE_ARMAZENAMENTO_ESPACO) {
    sessaoEspaco.recarregar();
  }
});
