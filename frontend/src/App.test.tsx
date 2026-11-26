import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from './App.tsx';
import { AVISO_LEGAL } from './shell/aviso.ts';
import { reiniciarFocoDePagina } from './shell/Pagina.tsx';
import { DESCRICAO_ESPACO } from './shell/StatusSessao.tsx';
import { ROTAS } from './shell/rotas.ts';
import { SAUDE_MOCK, SAUDE_REAL, json, sessaoDeTeste, type Responder } from './teste/sessaoDeTeste.ts';

const ID = '0123456789abcdef0123456789abcdef';

beforeAll(() => {
  // O jsdom não implementa showModal/close do <dialog>; o comportamento real é conferido no Chrome.
  HTMLDialogElement.prototype.showModal = function showModal(this: HTMLDialogElement) {
    this.setAttribute('open', '');
  };
  HTMLDialogElement.prototype.close = function close(this: HTMLDialogElement) {
    this.removeAttribute('open');
  };
  globalThis.scrollTo = vi.fn();
});

beforeEach(() => {
  history.replaceState(null, '', '/');
  reiniciarFocoDePagina();
});

afterEach(cleanup);

async function montar(responder: Responder, caminho = '/') {
  history.replaceState(null, '', caminho);
  const sessao = sessaoDeTeste(responder);
  render(<App sessao={sessao} />);
  await act(() => sessao.modo.carregar(sessao.api));
  return sessao;
}

const barra = () => within(screen.getByRole('banner'));

describe('navegação', () => {
  it('tem os cinco destinos, com a página atual marcada', async () => {
    // Contador ainda não chama a API (entra no PR 3c); as telas com dados têm testes em src/telas.
    await montar(() => json(SAUDE_MOCK), '/contador');
    const nav = within(screen.getByRole('navigation', { name: 'Principal' }));
    expect(nav.getAllByRole('link').map((l) => l.textContent)).toEqual(ROTAS.map((r) => r.nome));
    expect(nav.getByRole('link', { name: 'Contador' }).getAttribute('aria-current')).toBe('page');
    expect(nav.getByRole('link', { name: 'Painel' }).getAttribute('aria-current')).toBeNull();
    expect(screen.getByRole('heading', { level: 1, name: 'Contador' })).toBeDefined();
    expect(document.title).toBe('Contador · ContaAI');
  });

  it('clique comum troca a página sem recarregar, põe o foco no título e o voltar funciona', async () => {
    await montar(() => json(SAUDE_MOCK));
    const link = within(screen.getByRole('navigation', { name: 'Principal' })).getByRole('link', { name: 'Notas' });

    fireEvent.click(link);
    expect(location.pathname).toBe('/notas');
    const titulo = screen.getByRole('heading', { level: 1, name: 'Notas' });
    expect(document.activeElement).toBe(titulo);

    act(() => {
      history.back();
    });
    // O jsdom dispara o popstate de forma assíncrona.
    await screen.findByRole('heading', { level: 1, name: 'Painel' });
  });

  it('Ctrl+clique fica com o navegador (abrir em nova aba)', async () => {
    await montar(() => json(SAUDE_MOCK));
    const link = within(screen.getByRole('navigation', { name: 'Principal' })).getByRole('link', { name: 'Regime' });
    const evento = new MouseEvent('click', { bubbles: true, cancelable: true, ctrlKey: true });
    link.dispatchEvent(evento);
    expect(evento.defaultPrevented).toBe(false);
    expect(location.pathname).toBe('/');
  });

  it('na primeira página o foco não é movido', async () => {
    await montar(() => json(SAUDE_MOCK), '/regime');
    expect(document.activeElement).toBe(document.body);
  });

  it('aceita a barra final e maiúsculas', async () => {
    await montar(() => json(SAUDE_MOCK), '/Contador/');
    expect(screen.getByRole('heading', { level: 1, name: 'Contador' })).toBeDefined();
  });

  it('endereço desconhecido mostra a página não encontrada, com caminho de volta', async () => {
    await montar(() => json(SAUDE_MOCK), '/nao-existe');
    expect(screen.getByRole('heading', { level: 1, name: 'Página não encontrada' })).toBeDefined();
    expect(within(screen.getByRole('main')).getByRole('link', { name: 'Voltar ao painel' }).getAttribute('href')).toBe('/');
  });

  it('todo link do shell aponta para um caminho fixo da tela', async () => {
    await montar(() => json(SAUDE_MOCK));
    const caminhos = new Set<string>(ROTAS.map((r) => r.caminho));
    for (const link of screen.getAllByRole('link', { hidden: true })) {
      const href = link.getAttribute('href') ?? '';
      expect(caminhos.has(href) || href === '#conteudo').toBe(true);
    }
  });

  it('o menu do celular abre, navega e fecha', async () => {
    await montar(() => json(SAUDE_MOCK));
    fireEvent.click(barra().getByRole('button', { name: 'Menu' }));
    const folha = screen.getByRole('dialog', { name: 'Menu' });
    expect(folha.hasAttribute('open')).toBe(true);

    fireEvent.click(within(folha).getByRole('link', { name: 'Contador' }));
    expect(location.pathname).toBe('/contador');
    expect(folha.hasAttribute('open')).toBe(false);
  });
});

describe('estado da sessão na barra', () => {
  it('modo mock: só leitura, sem botão de espaço', async () => {
    await montar(() => json(SAUDE_MOCK));
    const status = within(barra().getByRole('status'));
    expect(status.getByText('Dados de demonstração, só leitura')).toBeDefined();
    expect(status.queryByRole('button')).toBeNull();
  });

  it('API fora do ar: diz e oferece tentar de novo', async () => {
    let fora = true;
    const sessao = await montar(() => (fora ? new Response(null, { status: 503, headers: { 'Content-Length': '0' } }) : json(SAUDE_MOCK)));
    const status = within(barra().getByRole('status'));
    expect(status.getByText('API fora do ar.')).toBeDefined();

    fora = false;
    await act(async () => {
      fireEvent.click(status.getByRole('button', { name: 'Tentar de novo' }));
      await sessao.modo.carregar(sessao.api);
    });
    expect(within(barra().getByRole('status')).getByText('Dados de demonstração, só leitura')).toBeDefined();
  });

  it('modo real: cria o espaço, mostra o aviso da API e o prazo, e sai', async () => {
    const agora = Date.now();
    const sessao = await montar((pedido) => {
      if (new URL(pedido.url).pathname === '/espacos') {
        return json(
          {
            id: ID,
            criadoEm: new Date(agora).toISOString(),
            expiraEm: new Date(agora + 120 * 60_000).toISOString(),
            aviso: 'Espaço com uma cópia própria dos dados fictícios.',
          },
          201,
        );
      }
      return json(SAUDE_REAL);
    });
    expect(within(barra().getByRole('status')).getByText('Demonstração compartilhada')).toBeDefined();
    // O botão diz o que faz a quem usa leitor de tela.
    expect(barra().getByRole('button', { name: 'Criar meu espaço' }).getAttribute('aria-describedby')).toBeTruthy();
    expect(
      barra().getByRole('button', { name: 'Criar meu espaço', description: DESCRICAO_ESPACO }),
    ).toBeDefined();

    await act(async () => {
      fireEvent.click(barra().getByRole('button', { name: 'Criar meu espaço' }));
      await vi.waitFor(() => {
        expect(sessao.espaco.obter().tipo).toBe('ativo');
      });
    });
    expect(barra().getByText(/vence em/).textContent).toMatch(/Seu espaço · vence em (2 h|1 h 59 min)/);
    // O aviso da API fala do header e do token, para quem integra a API: a tela não o mostra.
    expect(screen.queryByText('Espaço com uma cópia própria dos dados fictícios.')).toBeNull();
    // O id é a chave do espaço: nunca aparece na tela nem no endereço.
    expect(document.body.textContent).not.toContain(ID);
    expect(location.href).not.toContain(ID);

    act(() => {
      fireEvent.click(barra().getByRole('button', { name: 'Sair do espaço' }));
    });
    expect(sessao.espaco.obter().tipo).toBe('ausente');
    expect(barra().getByRole('button', { name: 'Criar meu espaço' })).toBeDefined();
  });

  it('espaços esgotados: mostra o motivo e o tempo de espera', async () => {
    await montar((pedido) =>
      new URL(pedido.url).pathname === '/espacos'
        ? json(
            { type: '/problemas/espacos-esgotados', title: 'Espaços esgotados', status: 503, detail: 'Todos os espaços de avaliação estão em uso.' },
            503,
            { 'Retry-After': '600' },
          )
        : json(SAUDE_REAL),
    );
    act(() => {
      fireEvent.click(barra().getByRole('button', { name: 'Criar meu espaço' }));
    });
    await barra().findByText(/Tente de novo em 10 min/);
    expect(barra().getByText('Todos os espaços de avaliação estão em uso. Tente de novo em 10 min.')).toBeDefined();
  });

  it('espaço vencido: diz e oferece criar outro', async () => {
    const sessao = await montar(() => json(SAUDE_REAL));
    act(() => {
      sessao.espaco.marcarExpirado();
    });
    expect(barra().getByText('Seu espaço venceu.')).toBeDefined();
    expect(barra().getByRole('button', { name: 'Criar outro espaço' })).toBeDefined();
  });

  it('texto da API é mostrado como texto, nunca como HTML', async () => {
    await montar((pedido) =>
      new URL(pedido.url).pathname === '/espacos'
        ? json({ title: 'x', status: 503, detail: '<img src=x onerror=alert(1)>' }, 503)
        : json(SAUDE_REAL),
    );
    act(() => {
      fireEvent.click(barra().getByRole('button', { name: 'Criar meu espaço' }));
    });
    await barra().findByText('<img src=x onerror=alert(1)>');
    expect(document.querySelector('img')).toBeNull();
  });
});

describe('rodapé', () => {
  // A igualdade com AVISO_LEGAL do backend é conferida em backend/tests/test_contrato.py: o Vite não deixa o
  // teste ler arquivos fora de frontend/ com ?raw, e abrir essa permissão valeria para o servidor de desenvolvimento.
  it('mostra o aviso legal', async () => {
    await montar(() => json(SAUDE_MOCK));
    expect(within(screen.getByRole('contentinfo')).getByText(AVISO_LEGAL)).toBeDefined();
  });

  it('mostra as versões dos motores em execução', async () => {
    await montar(() => json(SAUDE_MOCK));
    const motores = within(screen.getByRole('list', { name: 'Motores oficiais' }));
    expect(motores.getAllByRole('listitem').map((li) => li.textContent)).toEqual([
      'Regime regular 1.7.2 · banco V0073',
      'Simples Nacional 1.0.2 · banco V0073',
    ]);
  });

  it('avisa motor fora do ar e versão diferente da fixada', async () => {
    const [rr, sn] = SAUDE_MOCK.motores;
    await montar(() =>
      json({
        ...SAUDE_MOCK,
        status: 'degradado',
        motores: [
          { ...rr, ok: false, versaoEmExecucao: null, banco: null, coerente: false },
          { ...sn, versaoEmExecucao: '1.0.3', coerente: false },
        ],
      }),
    );
    const itens = within(screen.getByRole('list', { name: 'Motores oficiais' })).getAllByRole('listitem');
    expect(itens.map((li) => li.textContent)).toEqual([
      'Regime regular 1.7.2 · fora do ar',
      'Simples Nacional 1.0.3 · banco V0073 · versão diferente da fixada',
    ]);
  });
});
