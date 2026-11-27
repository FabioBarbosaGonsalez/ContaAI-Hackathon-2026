// Rotas que aceitam os headers da sessão, como o contrato declara (docs/contrato/openapi.json).
// O teste rotas.test.ts compara estas listas com o contrato e falha se divergirem.
//
// O cliente só manda cada header às rotas que o declaram:
// - o id do espaço não vai a rotas que não precisam dele;
// - o token não vai a nenhuma rota fora destas;
// - o cookie da sessão da conta só vai às rotas da conta, às da empresa da conta e, na conta, às rotas de dados
//   (ADR 0015, ADR 0016 e ADR 0018).

/** Chave no formato "MÉTODO /caminho", com o caminho como está no contrato. */
type Metodo = 'GET' | 'POST' | 'PATCH' | 'DELETE';

export type ChaveRota = `${Metodo} /${string}`;

/** Rotas com o header X-ContaAI-Espaco (ADR 0010). */
export const ROTAS_COM_ESPACO: ReadonlySet<ChaveRota> = new Set<ChaveRota>([
  'POST /nfe/importar',
  'GET /alertas',
  'POST /alertas/{alerta_id}/aplicar',
  'POST /catalogo/{item_id}/preco',
  'POST /catalogo/{item_id}/classificacao',
  'POST /catalogo/itens',
  'PATCH /catalogo/{item_id}',
  'POST /catalogo/{item_id}/arquivar',
  'POST /clientes',
  'PATCH /clientes/{cnpj_cliente}',
  'POST /clientes/{cnpj_cliente}/excluir',
  'GET /catalogo',
  'GET /notas',
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
  'POST /catalogo/itens',
  'PATCH /catalogo/{item_id}',
  'POST /catalogo/{item_id}/arquivar',
  'POST /clientes',
  'PATCH /clientes/{cnpj_cliente}',
  'POST /clientes/{cnpj_cliente}/excluir',
  'POST /chat',
  'POST /demo/restaurar',
]);

/**
 * As rotas da conta (tag `contas` do contrato, ADR 0015). Elas sempre levam o cookie da sessão: é por ele que a
 * API sabe quem entrou. As outras rotas só o levam quando a tela mostra os dados da conta (ADR 0016).
 */
export const ROTAS_DA_CONTA: ReadonlySet<ChaveRota> = new Set<ChaveRota>([
  'POST /contas',
  'POST /contas/ativar',
  'POST /sessoes',
  'POST /sessoes/codigo',
  'GET /conta',
  'DELETE /sessoes/atual',
  'DELETE /sessoes',
  'POST /conta/excluir',
  'POST /conta/dados',
]);

/**
 * As rotas da empresa da conta (`/empresas`, ADR 0017). Elas só existem com a sessão: a API lê a organização no
 * cookie e não aceita o header do espaço. Por isso sempre levam o cookie, também quando a pessoa está vendo a
 * demonstração (sem ele, o cadastro receberia 401 com a sessão aberta, ADR 0018).
 */
export const ROTAS_DA_EMPRESA: ReadonlySet<ChaveRota> = new Set<ChaveRota>([
  'POST /empresas',
  'GET /empresas/{cnpj}',
  'PATCH /empresas/{cnpj}',
  'POST /empresas/{cnpj}/excluir',
]);

/**
 * Rotas com o cookie em que o 401 quer dizer "e-mail, senha ou código incorretos", e não "a sessão acabou". Quem
 * chamou mostra a frase da API; a sessão da tela não muda. Excluir a empresa pede a senha de novo (ADR 0017,
 * etapa 7).
 */
export const ROTAS_DE_ENTRADA: ReadonlySet<ChaveRota> = new Set<ChaveRota>([
  'POST /contas/ativar',
  'POST /sessoes',
  'POST /sessoes/codigo',
  'POST /conta/excluir',
  'POST /conta/dados',
  'POST /empresas/{cnpj}/excluir',
]);

export function chaveDaRota(metodo: string, caminho: string): ChaveRota {
  return `${metodo.toUpperCase() as Metodo} ${caminho as `/${string}`}`;
}
