// C2b (ADR 0016): as páginas Entrar, Criar conta e Sua conta, e os caminhos até elas.

import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from '../App.tsx';
import { carregarSessao } from '../sessao/acoes.ts';
import { reiniciarFocoDePagina } from '../shell/Pagina.tsx';
import { ROTAS, ROTAS_PUBLICAS, ROTA_DA_CONTA } from '../shell/rotas.ts';
import { CONTA_DE_TESTE, SAUDE_MOCK, SAUDE_REAL, json, sessaoDeTeste } from '../teste/sessaoDeTeste.ts';

beforeAll(() => {
  HTMLDialogElement.prototype.showModal = function showModal(this: HTMLDialogElement) {
    this.setAttribute('open', '');
  };
  HTMLDialogElement.prototype.close = function close(this: HTMLDialogElement) {
    this.removeAttribute('open');
  };
  globalThis.scrollTo = vi.fn();
});

beforeEach(() => {
  reiniciarFocoDePagina();
  vi.spyOn(console, 'error').mockImplementation(() => undefined);
});

afterEach(cleanup);

type Conta = typeof CONTA_DE_TESTE | null;

interface Opcoes {
  saude?: typeof SAUDE_REAL | null;
  conta?: Conta;
  /** Antes de abrir: a pessoa já tinha escolhido ver a demonstração. */
  naDemo?: boolean;
}

/** Abre a tela como o main.tsx: /saude, depois /conta. As rotas de dados respondem 404 (não importam aqui). */
async function montar(caminho: string, { saude = SAUDE_REAL, conta = null, naDemo = false }: Opcoes = {}) {
  history.replaceState(null, '', caminho);
  const sessao = sessaoDeTeste((pedido) => {
    const rota = new URL(pedido.url).pathname;
    if (rota === '/saude') {
      return saude === null ? Promise.reject(new TypeError('Failed to fetch')) : json(saude);
    }
    if (rota === '/conta') {
      return conta === null
        ? json({ title: 'Unauthorized', status: 401, detail: 'Entre com a sua conta.' }, 401)
        : json(conta);
    }
    return json({ type: 'about:blank', title: 'Not Found', status: 404 }, 404);
  });
  render(<App sessao={sessao} />);
  await act(() => carregarSessao(sessao));
  if (naDemo) {
    act(() => {
      sessao.conta.verDemonstracao();
    });
  }
  return sessao;
}

const principal = () => within(screen.getByRole('main'));
const barra = () => within(screen.getByRole('banner'));
const rotasPedidas = (pedidos: Request[]) => pedidos.map((p) => new URL(p.url).pathname);
const CAMINHOS = new Set<string>([...ROTAS, ...ROTAS_PUBLICAS, ROTA_DA_CONTA].map((r) => r.caminho));

/** Todo link da tela aponta para um caminho fixo (docs/seguranca.md, regras da interface, item 2). */
function conferirLinks() {
  for (const link of screen.getAllByRole('link', { hidden: true })) {
    const href = link.getAttribute('href') ?? '';
    expect(CAMINHOS.has(href) || href === '#conteudo', href).toBe(true);
  }
}

describe('Entrar e Criar conta, para quem não entrou', () => {
  it.each([
    ['/entrar', 'Entrar', 'Criar conta'],
    ['/criar-conta', 'Criar conta', 'Entrar'],
  ])('%s: título, caminho para a outra página e a barra pública', async (caminho, titulo, outra) => {
    await montar(caminho);
    expect(screen.getByRole('heading', { level: 1, name: titulo })).toBeDefined();
    expect(document.title).toBe(`${titulo} · ContaAI`);
    expect(principal().getByRole('link', { name: outra }).getAttribute('href')).toBe(
      outra === 'Entrar' ? '/entrar' : '/criar-conta',
    );
    expect(screen.queryByRole('navigation', { name: 'Principal' })).toBeNull();
    expect(barra().getByRole('link', { name: 'Explorar a demonstração' })).toBeDefined();
    conferirLinks();
  });

  it('a barra pública mostra Entrar, menos na própria página de entrar', async () => {
    await montar('/criar-conta');
    expect(barra().getByRole('link', { name: 'Entrar' }).getAttribute('href')).toBe('/entrar');
    cleanup();
    await montar('/entrar');
    expect(barra().queryByRole('link', { name: 'Entrar' })).toBeNull();
  });

  it('não pede dados da empresa', async () => {
    const sessao = await montar('/criar-conta');
    expect(rotasPedidas(sessao.pedidos)).toEqual(['/saude', '/conta']);
  });

  it('no modo mock, diz que as contas não existem nesta instalação e só oferece a demonstração', async () => {
    for (const caminho of ['/entrar', '/criar-conta', '/conta']) {
      cleanup();
      const sessao = await montar(caminho, { saude: SAUDE_MOCK });
      expect(principal().getByText(/as contas não existem/u)).toBeDefined();
      expect(principal().getByRole('link', { name: 'Explorar a demonstração' }).getAttribute('href')).toBe('/painel');
      expect(principal().queryByRole('link', { name: 'Criar conta' })).toBeNull();
      expect(screen.queryByRole('textbox')).toBeNull();
      // No mock, as rotas da conta dão 501: a tela nem pergunta.
      expect(rotasPedidas(sessao.pedidos)).toEqual(['/saude']);
    }
  });

  it('com a API fora do ar, diz e oferece tentar de novo', async () => {
    const sessao = await montar('/entrar', { saude: null });
    expect(principal().getByText(/A API está fora do ar/u)).toBeDefined();
    fireEvent.click(principal().getByRole('button', { name: 'Tentar de novo' }));
    await act(async () => {
      await Promise.resolve();
    });
    expect(rotasPedidas(sessao.pedidos).filter((r) => r === '/saude')).toHaveLength(2);
  });

  it('enquanto a API não respondeu, espera sem mostrar a página', () => {
    history.replaceState(null, '', '/entrar');
    const sessao = sessaoDeTeste(() => new Promise<Response>(() => undefined));
    render(<App sessao={sessao} />);
    void carregarSessao(sessao);
    expect(principal().getByRole('status').textContent).toBe('Conectando à API…');
    expect(principal().queryByRole('link', { name: 'Criar conta' })).toBeNull();
  });
});

describe('quem já entrou e abre Entrar ou Criar conta', () => {
  it.each(['/entrar', '/criar-conta'])('%s vai ao Painel da conta, sem deixar a página no voltar', async (caminho) => {
    const antes = history.length;
    const sessao = await montar(caminho, { conta: CONTA_DE_TESTE });
    expect(location.pathname).toBe('/painel');
    expect(history.length).toBe(antes);
    expect(sessao.conta.obter()).toMatchObject({ tipo: 'conectada', naDemo: false });
    expect(screen.getByRole('heading', { level: 1, name: 'Painel' })).toBeDefined();
  });

  it('quem estava vendo a demonstração também volta à conta', async () => {
    history.replaceState(null, '', '/painel');
    const sessao = await montar('/painel', { conta: CONTA_DE_TESTE, naDemo: true });
    expect(sessao.conta.obter()).toMatchObject({ naDemo: true });
    act(() => {
      history.pushState(null, '', '/criar-conta');
      dispatchEvent(new PopStateEvent('popstate'));
    });
    expect(location.pathname).toBe('/painel');
    expect(sessao.conta.obter()).toMatchObject({ tipo: 'conectada', naDemo: false });
  });
});

describe('Sua conta', () => {
  it('quem não entrou vê o caminho para entrar ou criar a conta, na barra do app sem destino marcado', async () => {
    await montar('/conta');
    expect(screen.getByRole('heading', { level: 1, name: 'Sua conta' })).toBeDefined();
    expect(principal().getByText('Entre para ver a sua conta.')).toBeDefined();
    expect(principal().getByRole('link', { name: 'Entrar' }).getAttribute('href')).toBe('/entrar');
    expect(principal().getByRole('link', { name: 'Criar conta' }).getAttribute('href')).toBe('/criar-conta');
    const destinos = within(screen.getByRole('navigation', { name: 'Principal' })).getAllByRole('link');
    expect(destinos.map((l) => l.getAttribute('aria-current'))).toEqual(destinos.map(() => null));
    conferirLinks();
  });

  it('quem entrou fica na página (não vai ao Painel) e não vê o caminho para entrar', async () => {
    await montar('/conta', { conta: CONTA_DE_TESTE });
    expect(location.pathname).toBe('/conta');
    expect(screen.getByRole('heading', { level: 1, name: 'Sua conta' })).toBeDefined();
    expect(principal().queryByRole('link', { name: 'Entrar' })).toBeNull();
  });

  it('aceita a barra final e maiúsculas', async () => {
    await montar('/Conta/');
    expect(screen.getByRole('heading', { level: 1, name: 'Sua conta' })).toBeDefined();
  });

  it('sessão encerrada: pede para entrar de novo', async () => {
    const sessao = await montar('/conta', { conta: CONTA_DE_TESTE });
    act(() => {
      sessao.conta.marcarEncerrada();
    });
    expect(principal().getByText('Sua sessão terminou. Entre de novo para ver a sua conta.')).toBeDefined();
  });
});

describe('os caminhos até a conta', () => {
  it('página inicial: Explorar a demonstração primeiro, depois Criar conta e Entrar', async () => {
    await montar('/');
    const acoes = principal()
      .getAllByRole('link')
      .map((l) => [l.textContent, l.getAttribute('href')]);
    expect(acoes.slice(0, 3)).toEqual([
      ['Explorar a demonstração', '/painel'],
      ['Criar conta', '/criar-conta'],
      ['Entrar', '/entrar'],
    ]);
    expect(barra().getByRole('link', { name: 'Entrar' })).toBeDefined();
  });

  it('página inicial no mock: sem Criar conta nem Entrar', async () => {
    await montar('/', { saude: SAUDE_MOCK });
    expect(screen.queryByRole('link', { name: 'Criar conta' })).toBeNull();
    expect(screen.queryByRole('link', { name: 'Entrar' })).toBeNull();
  });

  it('página inicial de quem entrou: sem Criar conta nem Entrar', async () => {
    await montar('/', { conta: CONTA_DE_TESTE });
    expect(screen.queryByRole('link', { name: 'Criar conta' })).toBeNull();
    expect(screen.queryByRole('link', { name: 'Entrar' })).toBeNull();
    expect(barra().getByRole('link', { name: 'Ir ao Painel' })).toBeDefined();
    expect(barra().getByRole('button', { name: `Conta: ${CONTA_DE_TESTE.email}` })).toBeDefined();
  });

  it('a faixa da demonstração leva a Criar conta só quando as contas existem', async () => {
    await montar('/painel');
    const faixa = () => {
      const achada = screen.getAllByRole('status').find((s) => s.closest('.aviso-demo') !== null);
      if (achada === undefined) {
        throw new Error('A faixa da demonstração não apareceu.');
      }
      return within(achada);
    };
    expect(faixa().getByRole('link', { name: 'Criar conta' }).getAttribute('href')).toBe('/criar-conta');
    cleanup();
    await montar('/painel', { saude: SAUDE_MOCK });
    expect(faixa().queryByRole('link', { name: 'Criar conta' })).toBeNull();
  });

  it('sessão encerrada: a faixa oferece entrar de novo, e "Entendi" dispensa o aviso', async () => {
    const sessao = await montar('/painel', { conta: CONTA_DE_TESTE });
    act(() => {
      sessao.conta.marcarEncerrada();
    });
    const entrar = screen.getByRole('link', { name: 'Entrar de novo' });
    expect(entrar.getAttribute('href')).toBe('/entrar');
    fireEvent.click(screen.getByRole('button', { name: 'Entendi' }));
    expect(sessao.conta.obter()).toEqual({ tipo: 'anonima' });
    expect(screen.queryByRole('link', { name: 'Entrar de novo' })).toBeNull();
  });

  it('"Entrar de novo" abre Entrar, que serve a quem teve a sessão encerrada', async () => {
    const sessao = await montar('/painel', { conta: CONTA_DE_TESTE });
    act(() => {
      sessao.conta.marcarEncerrada();
    });
    fireEvent.click(screen.getByRole('link', { name: 'Entrar de novo' }));
    expect(location.pathname).toBe('/entrar');
    expect(screen.getByRole('heading', { level: 1, name: 'Entrar' })).toBeDefined();
    expect(principal().getByRole('link', { name: 'Criar conta' })).toBeDefined();
  });
});
