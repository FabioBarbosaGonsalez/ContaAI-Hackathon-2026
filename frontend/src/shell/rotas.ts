// Destinos da tela.
//
// - Rotas do app (inventário §3: Painel, Catálogo, Regime e Notas, mais Contador na D1): a barra só mostra estas.
// - Rotas públicas (C2, ADR 0016): a página inicial, os termos de uso e a privacidade. Elas não pedem dados da
//   empresa. Entrar e Criar conta entram no PR seguinte (C2b).
//
// Os links da tela só apontam para estes caminhos fixos: nenhum texto vindo da API vira href
// (docs/seguranca.md, regras da interface, item 2). O tipo Caminho garante isso na compilação.
//
// No mesmo endereço, /catalogo e /contador colidiriam com as rotas da API; por isso, publicada, a API fica
// em /api (ADR 0011, L11).

export const ROTAS = [
  { caminho: '/painel', nome: 'Painel' },
  { caminho: '/catalogo', nome: 'Catálogo' },
  { caminho: '/regime', nome: 'Regime' },
  { caminho: '/notas', nome: 'Notas' },
  { caminho: '/contador', nome: 'Contador' },
] as const;

export const ROTAS_PUBLICAS = [
  { caminho: '/', nome: 'Início' },
  { caminho: '/termos', nome: 'Termos de uso' },
  { caminho: '/privacidade', nome: 'Privacidade' },
] as const;

export type Rota = (typeof ROTAS)[number];
export type RotaPublica = (typeof ROTAS_PUBLICAS)[number];
export type CaminhoDoApp = Rota['caminho'];
export type CaminhoPublico = RotaPublica['caminho'];
export type Caminho = CaminhoDoApp | CaminhoPublico;

/** Onde o app começa: o primeiro destino da barra. */
export const INICIO_DO_APP: CaminhoDoApp = '/painel';

function normalizar(pathname: string): string {
  return pathname.length > 1 ? pathname.replace(/\/+$/, '').toLowerCase() : pathname;
}

/** A rota do app do endereço atual, ou null. Aceita a barra final ("/notas/") e ignora maiúsculas. */
export function rotaDe(pathname: string): Rota | null {
  const caminho = normalizar(pathname);
  return ROTAS.find((rota) => rota.caminho === caminho) ?? null;
}

/** A rota pública do endereço atual, ou null. */
export function rotaPublicaDe(pathname: string): RotaPublica | null {
  const caminho = normalizar(pathname);
  return ROTAS_PUBLICAS.find((rota) => rota.caminho === caminho) ?? null;
}
