// Cliente tipado da API. Os tipos são gerados de docs/contrato/openapi.json (npm run contrato).
//
// Toda requisição:
// - leva cookies só na mesma origem (`credentials: 'same-origin'`): a sessão da conta é um cookie HttpOnly que
//   o JavaScript não lê, e a API fica em /api, no mesmo endereço (ADR 0015). Para outra origem, nada vai;
// - sem Referer e sem cache;
// - recusa redirecionamento, para nunca seguir para outro endereço;
// - tem tempo limite, que vale mesmo que o fetch não chegue a ver o sinal (ver o comentário em criarCliente);
// - só leva parâmetros de caminho com letras, dígitos e hífen. Sem isso, um id como ".." trocaria a rota
//   pedida por outra; todos os parâmetros de caminho do contrato já seguem esse padrão.

import createClient, { type Client, type Middleware } from 'openapi-fetch';
import { enderecoApi } from './config.ts';
import type { paths } from './esquema.gen.ts';
import { ErroApi, lerProblema, lerRetryAfter } from './problema.ts';

/** Headers do contrato (ADR 0010 e ADR 0011). */
export const CABECALHO_ESPACO = 'X-ContaAI-Espaco';
export const CABECALHO_TOKEN = 'X-ContaAI-Token';
export const CABECALHO_MOCK = 'X-ContaAI-Mock';

/** Tempo limite padrão. O cálculo chama os motores oficiais e pode levar alguns segundos. */
export const TEMPO_LIMITE_PADRAO_MS = 30_000;

const PARAMETRO_DE_CAMINHO = /^[A-Za-z0-9-]{1,128}$/;

export type ClienteApi = Client<paths>;

export interface OpcoesCliente {
  /** Endereço da API. Padrão: o de src/api/config.ts. */
  baseUrl?: string;
  /** Tempo limite de cada requisição, em milissegundos. */
  tempoLimiteMs?: number;
  /** Troca o fetch do navegador (testes). */
  fetch?: typeof globalThis.fetch;
}

/** Recusa parâmetros de caminho fora do padrão antes de enviar a requisição. */
export const guardaDeCaminho: Middleware = {
  onRequest({ params }) {
    const caminho: Record<string, unknown> = params.path ?? {};
    for (const valor of Object.values(caminho)) {
      if (typeof valor !== 'string' || !PARAMETRO_DE_CAMINHO.test(valor)) {
        throw new ErroApi({ tipo: 'entrada' });
      }
    }
    return undefined;
  },
};

export function criarCliente(opcoes: OpcoesCliente = {}): ClienteApi {
  const tempoLimiteMs = opcoes.tempoLimiteMs ?? TEMPO_LIMITE_PADRAO_MS;
  const fetchBase = opcoes.fetch ?? globalThis.fetch.bind(globalThis);

  const cliente = createClient<paths>({
    baseUrl: opcoes.baseUrl ?? enderecoApi(),
    // Junta o cancelamento de quem chamou ao tempo limite, numa cópia da requisição com o sinal novo.
    // Pelo padrão Fetch, copiar uma Request com opções zera o referrer e a política de referrer:
    // por isso os dois vão de novo aqui (teste em cliente.test.ts).
    //
    // A promessa também termina pelo próprio sinal: no Node 24.21 (onde rodam os testes), depois de uma coleta de
    // lixo o abort deixa de chegar à cópia da Request, e o pedido ficava pendurado. Conferido num rascunho com o
    // coletor forçado: a cópia perdeu o abort em 5 de 5 rodadas, e um ouvinte no sinal combinado o recebeu em 10 de
    // 10. O Chrome 158 não perde (5 de 5 com o coletor forçado), e no navegador o resultado é o mesmo de antes.
    fetch: (pedido: Request) => {
      const sinal = AbortSignal.any([pedido.signal, AbortSignal.timeout(tempoLimiteMs)]);
      const copia = new Request(pedido, { signal: sinal, referrer: '', referrerPolicy: 'no-referrer' });
      return new Promise<Response>((resolver, rejeitar) => {
        const aoAbortar = () => {
          rejeitar(sinal.reason instanceof Error ? sinal.reason : new DOMException('Pedido cancelado.', 'AbortError'));
        };
        if (sinal.aborted) {
          aoAbortar();
          return;
        }
        sinal.addEventListener('abort', aoAbortar, { once: true });
        fetchBase(copia)
          .then(resolver, rejeitar)
          .finally(() => {
            sinal.removeEventListener('abort', aoAbortar);
          });
      });
    },
    headers: { Accept: 'application/json, application/problem+json' },
    credentials: 'same-origin',
    mode: 'cors',
    cache: 'no-store',
    redirect: 'error',
    referrerPolicy: 'no-referrer',
  });
  cliente.use(guardaDeCaminho);
  return cliente;
}

/** Resposta de sucesso: os dados e se vieram dos mocks (header X-ContaAI-Mock: 1). */
export interface Resposta<T> {
  dados: T;
  mock: boolean;
}

type Resultado<T> =
  | { data: T; error?: never; response: Response }
  | { data?: never; error: unknown; response: Response };

function erroDeEnvio(erro: unknown): ErroApi {
  if (erro instanceof ErroApi) {
    return erro;
  }
  if (erro instanceof DOMException && erro.name === 'TimeoutError') {
    return new ErroApi({ tipo: 'tempo', causa: erro });
  }
  if (erro instanceof DOMException && erro.name === 'AbortError') {
    return new ErroApi({ tipo: 'cancelado', causa: erro });
  }
  // A resposta 2xx com corpo que não é JSON chega aqui como SyntaxError do JSON.parse.
  if (erro instanceof SyntaxError) {
    return new ErroApi({ tipo: 'formato', causa: erro });
  }
  return new ErroApi({ tipo: 'rede', causa: erro });
}

/**
 * Espera a requisição e devolve os dados, ou lança ErroApi.
 *
 * ```ts
 * const { dados, mock } = await chamar(cliente.GET('/saude'));
 * ```
 */
export async function chamar<T>(pedido: Promise<Resultado<T>>): Promise<Resposta<T>> {
  let resultado: Resultado<T>;
  try {
    resultado = await pedido;
  } catch (erro) {
    throw erroDeEnvio(erro);
  }

  const { response } = resultado;
  if (!response.ok) {
    throw new ErroApi({
      tipo: 'resposta',
      problema: lerProblema(resultado.error, response.status),
      corpo: typeof resultado.error === 'object' ? resultado.error : undefined,
      retryAfterS: lerRetryAfter(response.headers.get('Retry-After')),
    });
  }
  // Com resposta 2xx, o openapi-fetch sempre preenche `data` (com o corpo JSON lido).
  return { dados: resultado.data as T, mock: response.headers.get(CABECALHO_MOCK) === '1' };
}
