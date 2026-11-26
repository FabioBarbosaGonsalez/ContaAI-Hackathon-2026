// Endereço da API (ADR 0011, L11; ADR 0015).
//
// A API fica em /api, no mesmo endereço da tela: no desenvolvimento e no `vite preview`, pelo proxy do Vite
// (vite.config.ts); publicada, pelo proxy da E6. Assim, as rotas /catalogo e /contador da tela não colidem
// com as da API, a CSP `connect-src 'self'` basta, e o cookie da sessão (SameSite=Strict, sem Domain) anda
// junto, porque a requisição é da mesma origem.
//
// VITE_CONTAAI_API troca o padrão. Como toda variável VITE_*, ela vai para o navegador e é pública:
// nunca ponha segredo nela (docs/seguranca.md, regras da interface, item 4). Com um endereço de outra origem, a
// demonstração funciona, mas a conta não: o cliente só manda cookies na mesma origem.

const PADRAO = '/api';

const HOSTS_LOCAIS = new Set(['127.0.0.1', 'localhost', '[::1]']);

/**
 * Confere o endereço da API e o devolve sem a barra final.
 *
 * Aceita um caminho na mesma origem (`/api`) ou um endereço completo. O endereço completo precisa ser https,
 * exceto na máquina local. Recusa usuário e senha embutidos, consulta e fragmento, e o `//host`, que trocaria
 * de origem sem parecer.
 */
export function validarEnderecoApi(valor: string): string {
  const endereco = valor.trim();
  if (endereco === '') {
    throw new Error('Endereço da API vazio');
  }

  if (endereco.startsWith('/')) {
    if (endereco.startsWith('//') || endereco.includes('\\') || /[?#]/.test(endereco)) {
      throw new Error('Endereço da API inválido: use um caminho simples, como /api');
    }
    return endereco.replace(/\/+$/, '');
  }

  let url: URL;
  try {
    url = new URL(endereco);
  } catch {
    throw new Error('Endereço da API inválido');
  }
  if (url.username !== '' || url.password !== '') {
    throw new Error('Endereço da API não pode trazer usuário ou senha');
  }
  if (url.search !== '' || url.hash !== '') {
    throw new Error('Endereço da API não pode trazer consulta nem fragmento');
  }
  const local = HOSTS_LOCAIS.has(url.hostname);
  if (url.protocol !== 'https:' && !(url.protocol === 'http:' && local)) {
    throw new Error('Endereço da API precisa ser https (http só na máquina local)');
  }
  return `${url.origin}${url.pathname}`.replace(/\/+$/, '');
}

/** O endereço da API para este build: VITE_CONTAAI_API, ou o padrão do modo. */
export function enderecoApi(): string {
  const configurado = import.meta.env.VITE_CONTAAI_API;
  if (configurado !== undefined && configurado !== '') {
    return validarEnderecoApi(configurado);
  }
  return PADRAO;
}
