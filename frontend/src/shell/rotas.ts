// Destinos da tela (inventário §3: Painel, Catálogo, Regime e Notas, mais Contador na D1).
//
// Os links da tela só apontam para estes caminhos fixos: nenhum texto vindo da API vira href
// (docs/seguranca.md, regras da interface, item 2). O tipo Caminho garante isso na compilação.
//
// No mesmo endereço, /catalogo e /contador colidiriam com as rotas da API; por isso, publicada, a API fica
// em /api (ADR 0011, L11).

export const ROTAS = [
  { caminho: '/', nome: 'Painel' },
  { caminho: '/catalogo', nome: 'Catálogo' },
  { caminho: '/regime', nome: 'Regime' },
  { caminho: '/notas', nome: 'Notas' },
  { caminho: '/contador', nome: 'Contador' },
] as const;

export type Rota = (typeof ROTAS)[number];
export type Caminho = Rota['caminho'];

/** A rota do endereço atual, ou null. Aceita a barra final ("/notas/") e ignora maiúsculas. */
export function rotaDe(pathname: string): Rota | null {
  const caminho = pathname.length > 1 ? pathname.replace(/\/+$/, '').toLowerCase() : pathname;
  return ROTAS.find((rota) => rota.caminho === caminho) ?? null;
}
