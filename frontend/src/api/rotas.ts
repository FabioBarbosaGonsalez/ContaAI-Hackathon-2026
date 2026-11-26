// Rotas que aceitam os headers da sessão, como o contrato declara (docs/contrato/openapi.json).
// O teste rotas.test.ts compara estas listas com o contrato e falha se divergirem.
//
// O cliente só manda cada header às rotas que o declaram:
// - o id do espaço não vai a rotas que não precisam dele;
// - o token não vai a nenhuma rota fora destas.

/** Chave no formato "MÉTODO /caminho", com o caminho como está no contrato. */
export type ChaveRota = `${'GET' | 'POST'} /${string}`;

/** Rotas com o header X-ContaAI-Espaco (ADR 0010). */
export const ROTAS_COM_ESPACO: ReadonlySet<ChaveRota> = new Set<ChaveRota>([
  'POST /nfe/importar',
  'GET /alertas',
  'POST /alertas/{alerta_id}/aplicar',
  'POST /catalogo/{item_id}/preco',
  'POST /catalogo/{item_id}/classificacao',
  'GET /catalogo',
  'GET /contador/painel',
  'GET /espacos/atual',
  'GET /explicar/{item_id}',
  'POST /chat',
  'POST /demo/restaurar',
]);

/** Rotas com o header X-ContaAI-Token (ADR 0006 e ADR 0008). */
export const ROTAS_COM_TOKEN: ReadonlySet<ChaveRota> = new Set<ChaveRota>([
  'POST /nfe/importar',
  'POST /alertas/{alerta_id}/aplicar',
  'POST /catalogo/{item_id}/preco',
  'POST /catalogo/{item_id}/classificacao',
  'POST /chat',
  'POST /demo/restaurar',
]);

export function chaveDaRota(metodo: string, caminho: string): ChaveRota {
  return `${metodo.toUpperCase() as 'GET' | 'POST'} ${caminho as `/${string}`}`;
}
