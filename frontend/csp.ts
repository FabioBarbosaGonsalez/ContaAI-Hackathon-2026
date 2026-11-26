// Política de segurança de conteúdo (CSP) da tela: uma fonte só, usada pelo vite.config.ts e pelo roteiro
// scripts/checar-seguranca.mjs (docs/seguranca.md, regras da interface, item 3).
//
// - script-src 'self': o build do Vite só gera arquivos .js externos, sem script embutido.
// - style-src 'self': o CSS sai em arquivo; a tela não usa o atributo style.
// - require-trusted-types-for 'script' + trusted-types 'none': nenhum texto pode virar HTML ou script por
//   innerHTML, document.write e afins, e nenhuma política que liberaria isso pode ser criada. O React só usa
//   esses caminhos para dangerouslySetInnerHTML e para criar <script>, e os dois são proibidos no código.
// - connect-src 'self': publicada, a API fica em /api, no mesmo endereço (ADR 0011, L11). Se o build apontar
//   para outra origem (VITE_CONTAAI_API), só ela entra.
//
// No <meta>, o navegador ignora frame-ancestors (especificação CSP 3); essa diretiva vai só no cabeçalho
// (vite preview e o proxy da E6).
//
// Só vale no build e no `vite preview`. O servidor de desenvolvimento do Vite injeta script e estilo
// embutidos (React Refresh e CSS), e por isso fica sem CSP.

export interface OpcoesCsp {
  /** Endereço da API (VITE_CONTAAI_API). Um caminho como /api já está em 'self'. */
  api?: string | undefined;
  /** true no cabeçalho HTTP; false no <meta>, que não aceita frame-ancestors. */
  cabecalho: boolean;
}

/** A origem de um endereço absoluto da API, ou null para um caminho na mesma origem. */
export function origemDaApi(api: string | undefined): string | null {
  if (api === undefined || api === '' || api.startsWith('/')) {
    return null;
  }
  return new URL(api).origin;
}

export function politicaDeSeguranca({ api, cabecalho }: OpcoesCsp): string {
  const origem = origemDaApi(api);
  const diretivas: [string, string][] = [
    ['default-src', "'none'"],
    ['script-src', "'self'"],
    ['style-src', "'self'"],
    ['img-src', "'self'"],
    ['font-src', "'self'"],
    ['connect-src', origem === null ? "'self'" : `'self' ${origem}`],
    ['base-uri', "'none'"],
    ['form-action', "'none'"],
    ['require-trusted-types-for', "'script'"],
    ['trusted-types', "'none'"],
  ];
  if (cabecalho) {
    diretivas.push(['frame-ancestors', "'none'"]);
  }
  return diretivas.map(([nome, valor]) => `${nome} ${valor}`).join('; ');
}

/** Cabeçalhos de segurança para servir a tela (vite preview; o proxy da E6 deve repetir estes). */
export function cabecalhosDeSeguranca(api: string | undefined): Record<string, string> {
  return {
    'Content-Security-Policy': politicaDeSeguranca({ api, cabecalho: true }),
    'X-Content-Type-Options': 'nosniff',
    'Referrer-Policy': 'no-referrer',
    'X-Frame-Options': 'DENY',
  };
}
