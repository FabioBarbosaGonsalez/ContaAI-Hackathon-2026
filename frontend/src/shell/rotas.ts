// Destinos da tela.
//
// - Rotas do app (inventário §3: Painel, Catálogo, Regime e Notas, mais Contador na D1): a barra só mostra estas.
// - Rotas públicas (C2, ADR 0016): a página inicial, entrar, criar conta, os termos de uso e a privacidade. Elas
//   não pedem dados da empresa.
// - A página da conta (C2b): fica no app, com a barra, mas fora dos destinos; ela só lê o GET /conta.
// - O cadastro da empresa (C3a, ADR 0018): também no app e fora dos destinos. É para onde a primeira vez leva.
// - As configurações da empresa (C3b, ADR 0018): no app e fora dos destinos, pelo menu da conta e pelo Painel.
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
  { caminho: '/entrar', nome: 'Entrar' },
  { caminho: '/criar-conta', nome: 'Criar conta' },
  { caminho: '/termos', nome: 'Termos de uso' },
  { caminho: '/privacidade', nome: 'Privacidade' },
] as const;

export const ROTA_DA_CONTA = { caminho: '/conta', nome: 'Sua conta' } as const;

export const ROTA_DO_CADASTRO = { caminho: '/empresa/nova', nome: 'Cadastrar a empresa' } as const;

export const ROTA_DA_EMPRESA = { caminho: '/empresa', nome: 'Configurações da empresa' } as const;

export type Rota = (typeof ROTAS)[number];
export type RotaPublica = (typeof ROTAS_PUBLICAS)[number];
export type CaminhoDoApp = Rota['caminho'];
export type CaminhoPublico = RotaPublica['caminho'];
export type CaminhoDaConta =
  | (typeof ROTA_DA_CONTA)['caminho']
  | (typeof ROTA_DO_CADASTRO)['caminho']
  | (typeof ROTA_DA_EMPRESA)['caminho'];
export type Caminho = CaminhoDoApp | CaminhoPublico | CaminhoDaConta;

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

/** O endereço atual é a página da conta? */
export function ehPaginaDaConta(pathname: string): boolean {
  return normalizar(pathname) === ROTA_DA_CONTA.caminho;
}

/** O endereço atual são as configurações da empresa? */
export function ehPaginaDaEmpresa(pathname: string): boolean {
  return normalizar(pathname) === ROTA_DA_EMPRESA.caminho;
}

/** O endereço atual é o cadastro da empresa? */
export function ehPaginaDoCadastro(pathname: string): boolean {
  return normalizar(pathname) === ROTA_DO_CADASTRO.caminho;
}
