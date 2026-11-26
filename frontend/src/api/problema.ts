// Erros da API no formato da RFC 9457 (ADR 0009).
//
// Todo erro do cliente vira um ErroApi. O corpo da resposta de erro só é aproveitado se tiver o formato de
// um problema. Um corpo fora do formato (texto, HTML de um proxy, JSON qualquer) nunca é repassado à tela.
// Em seu lugar entra uma mensagem fixa. Mesmo o `detail` válido é texto de terceiro: a tela o exibe como
// texto, nunca como HTML (docs/seguranca.md, regras da interface, item 1).

import type { components } from './esquema.gen.ts';

export type Problema = components['schemas']['Problema'];

/**
 * - `resposta`: a API respondeu com erro (4xx ou 5xx);
 * - `rede`: a requisição não chegou (API fora do ar, CORS, redirecionamento recusado);
 * - `tempo`: passou do tempo limite;
 * - `cancelado`: quem chamou cancelou;
 * - `entrada`: o cliente recusou a requisição antes de enviar;
 * - `formato`: a API respondeu 2xx com um corpo que não é JSON.
 */
export type TipoErroApi = 'resposta' | 'rede' | 'tempo' | 'cancelado' | 'entrada' | 'formato';

/** Frases em português para quando o problema não traz `detail` (o `title` de about:blank vem em inglês). */
const FRASES: Readonly<Record<number, string>> = {
  400: 'A requisição não foi aceita.',
  401: 'Esta ação precisa do token de acesso.',
  403: 'Esta ação não é permitida.',
  404: 'Não encontrado.',
  409: 'Esta ação conflita com o estado atual.',
  411: 'A requisição precisa informar o tamanho do corpo.',
  413: 'O conteúdo enviado é grande demais.',
  415: 'O tipo de arquivo enviado não é aceito.',
  422: 'Os dados enviados não passaram na validação.',
  429: 'Muitas requisições. Espere um pouco e tente de novo.',
  501: 'Esta função não está disponível neste modo.',
  502: 'Um motor oficial respondeu de forma inesperada.',
  503: 'O serviço está indisponível no momento.',
};

const MENSAGENS: Readonly<Record<Exclude<TipoErroApi, 'resposta'>, string>> = {
  rede: 'Não foi possível falar com a API. Confira se ela está no ar.',
  tempo: 'A API demorou demais para responder.',
  cancelado: 'A requisição foi cancelada.',
  entrada: 'A requisição tem um parâmetro inválido.',
  formato: 'A API respondeu num formato inesperado.',
};

function fraseDoStatus(status: number): string {
  return FRASES[status] ?? (status >= 500 ? 'Erro no servidor.' : 'A requisição não foi aceita.');
}

function ehObjeto(valor: unknown): valor is Record<string, unknown> {
  return typeof valor === 'object' && valor !== null && !Array.isArray(valor);
}

/**
 * Lê o corpo de um erro como problema da RFC 9457. Se o corpo não tiver o formato, devolve um problema
 * montado só com o status HTTP. O `status` do resultado é sempre o da resposta, e não o do corpo.
 */
export function lerProblema(corpo: unknown, status: number): Problema {
  if (
    ehObjeto(corpo) &&
    typeof corpo.title === 'string' &&
    typeof corpo.status === 'number' &&
    (corpo.type === undefined || typeof corpo.type === 'string') &&
    (corpo.detail === undefined || corpo.detail === null || typeof corpo.detail === 'string')
  ) {
    return {
      type: corpo.type ?? 'about:blank',
      title: corpo.title,
      status,
      // Um detail vazio vira null, para a tela usar a frase do status.
      detail: typeof corpo.detail === 'string' && corpo.detail.trim() !== '' ? corpo.detail : null,
    };
  }
  return { type: 'about:blank', title: fraseDoStatus(status), status, detail: null };
}

/** Tempo máximo aceito do Retry-After (o backend usa até alguns minutos). */
const ESPERA_MAXIMA_S = 3600;

/** IMF-fixdate (RFC 9110, seção 5.6.7), o formato de data que o HTTP manda gerar. */
const DATA_HTTP = /^(Mon|Tue|Wed|Thu|Fri|Sat|Sun), \d{2} (Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) \d{4} \d{2}:\d{2}:\d{2} GMT$/;

/**
 * Lê o header Retry-After em segundos (RFC 9110, seção 10.2.3): um número de segundos ou uma data HTTP.
 * Devolve null se o header faltar ou for inválido, e limita o valor a uma hora.
 */
export function lerRetryAfter(valor: string | null, agora: number = Date.now()): number | null {
  if (valor === null) {
    return null;
  }
  const texto = valor.trim();
  let segundos: number;
  if (/^\d+$/.test(texto)) {
    segundos = Number(texto);
  } else {
    // Só a data no formato IMF-fixdate (ex.: "Wed, 25 Nov 2026 12:00:00 GMT"). O Date.parse sozinho aceita
    // textos como "-5" ou "1.5" como datas.
    if (!DATA_HTTP.test(texto)) {
      return null;
    }
    const quando = Date.parse(texto);
    if (Number.isNaN(quando)) {
      return null;
    }
    segundos = Math.ceil((quando - agora) / 1000);
  }
  return Math.min(Math.max(segundos, 0), ESPERA_MAXIMA_S);
}

/** A mensagem para a pessoa: o `detail` do problema, a frase do status ou a frase fixa do tipo. */
function mensagemDoErro(tipo: TipoErroApi, problema: Problema | undefined): string {
  if (tipo !== 'resposta') {
    return MENSAGENS[tipo];
  }
  if (problema === undefined) {
    return MENSAGENS.formato;
  }
  return problema.detail ?? fraseDoStatus(problema.status);
}

interface DadosErroApi {
  tipo: TipoErroApi;
  problema?: Problema;
  corpo?: unknown;
  retryAfterS?: number | null;
  causa?: unknown;
}

export class ErroApi extends Error {
  readonly tipo: TipoErroApi;
  /** Só em `resposta`: o problema já conferido. */
  readonly problema: Problema | null;
  /**
   * Só em `resposta`: o corpo JSON inteiro, para a tela ler campos extras de um tipo de problema (como
   * `campos` e `erros`) com a própria checagem. Nunca é exibido como HTML.
   */
  readonly corpo: unknown;
  /** Segundos do Retry-After (429 e 503), se vieram. */
  readonly retryAfterS: number | null;

  constructor({ tipo, problema, corpo, retryAfterS, causa }: DadosErroApi) {
    super(mensagemDoErro(tipo, problema), { cause: causa });
    this.name = 'ErroApi';
    this.tipo = tipo;
    this.problema = problema ?? null;
    this.corpo = corpo;
    this.retryAfterS = retryAfterS ?? null;
  }

  /** Código HTTP, se a API chegou a responder. */
  get status(): number | null {
    return this.problema?.status ?? null;
  }
}
