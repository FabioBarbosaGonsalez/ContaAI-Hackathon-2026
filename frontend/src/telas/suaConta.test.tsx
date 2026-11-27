// C2b, etapa 9 (ADR 0016): o menu da conta na barra e a página Sua conta, com a API falsa (fetch do teste).

import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from '../App.tsx';
import { instante } from '../dados/formatar.ts';
import { carregarSessao } from '../sessao/acoes.ts';
import type { Conta } from '../sessao/conta.ts';
import { FRASE_SAIR_FALHOU } from '../shell/MenuDaConta.tsx';
import { reiniciarFocoDePagina } from '../shell/Pagina.tsx';
import { CONTA_DE_TESTE, SAUDE_REAL, json, sessaoDeTeste } from '../teste/sessaoDeTeste.ts';
import { AVISO_DE_CODIGOS, FRASE_DA_CONFIRMACAO } from './Conta.tsx';
import { TIPO_CONTA_BLOQUEADA } from './formulario.tsx';

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

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

type Rota = (pedido: Request) => Response | Promise<Response>;
type Rotas = Partial<Record<'GET /conta' | 'DELETE /sessoes/atual' | 'DELETE /sessoes' | 'POST /conta/excluir', Rota>>;

const SEM_SESSAO = () => json({ title: 'Unauthorized', status: 401, detail: 'Entre com a sua conta.' }, 401);
const NADA = () => new Response(null, { status: 204 });

async function montar(caminho: string, { conta = CONTA_DE_TESTE, rotas = {} }: { conta?: Conta; rotas?: Rotas } = {}) {
  history.replaceState(null, '', caminho);
  const pedidos: { rota: string; corpo: unknown }[] = [];
  const sessao = sessaoDeTeste(async (pedido) => {
    const caminhoDoPedido = new URL(pedido.url).pathname;
    const chave = `${pedido.method} ${caminhoDoPedido}` as keyof Rotas;
    if (caminhoDoPedido === '/saude') {
      return json(SAUDE_REAL);
    }
    const corpo: unknown = pedido.method === 'POST' ? await pedido.clone().json() : null;
    pedidos.push({ rota: chave, corpo });
    const responder = rotas[chave];
    if (responder !== undefined) {
      return responder(pedido);
    }
    if (chave === 'GET /conta') {
      return json(conta);
    }
    return json({ type: 'about:blank', title: 'Not Found', status: 404 }, 404);
  });
  render(<App sessao={sessao} />);
  await act(() => carregarSessao(sessao));
  return { sessao, pedidos };
}

const barra = () => within(screen.getByRole('banner'));
const principal = () => within(screen.getByRole('main'));
const botaoDoMenu = () => barra().getByRole('button', { name: `Conta: ${CONTA_DE_TESTE.email}` });

async function clicar(nome: string | RegExp, onde = principal()) {
  act(() => {
    fireEvent.click(onde.getByRole('button', { name: nome }));
  });
  await waitFor(() => {
    // Só os rótulos de envio ("Saindo…", "Excluindo…"); "Excluir a conta…" abre o formulário e fica.
    expect(screen.queryByRole('button', { name: /ndo…$/u })).toBeNull();
  });
}

describe('menu da conta na barra', () => {
  it('o botão mostra o e-mail; abre a organização, Sua conta e Sair', async () => {
    await montar('/painel');
    const botao = botaoDoMenu();
    expect(botao.textContent).toBe(CONTA_DE_TESTE.email);
    expect(botao.getAttribute('aria-expanded')).toBe('false');
    const painel = document.getElementById(botao.getAttribute('aria-controls') ?? '');
    expect(painel?.hidden).toBe(true);
    fireEvent.click(botao);
    expect(botao.getAttribute('aria-expanded')).toBe('true');
    expect(painel?.hidden).toBe(false);
    const dentro = within(painel as HTMLElement);
    expect(dentro.getByText(CONTA_DE_TESTE.organizacao.nome)).toBeDefined();
    expect(dentro.getByRole('link', { name: 'Sua conta' }).getAttribute('href')).toBe('/conta');
    expect(dentro.getByRole('button', { name: 'Sair' })).toBeDefined();
  });

  it('Esc fecha e devolve o foco ao botão; clicar fora e levar o foco para fora também fecham', async () => {
    await montar('/painel');
    const botao = botaoDoMenu();
    fireEvent.click(botao);
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(botao.getAttribute('aria-expanded')).toBe('false');
    expect(document.activeElement).toBe(botao);

    fireEvent.click(botao);
    fireEvent.pointerDown(screen.getByRole('main'));
    expect(botao.getAttribute('aria-expanded')).toBe('false');

    fireEvent.click(botao);
    fireEvent.focusIn(screen.getByRole('main'));
    expect(botao.getAttribute('aria-expanded')).toBe('false');
  });

  it('Sua conta leva à página e fecha o menu', async () => {
    await montar('/painel');
    fireEvent.click(botaoDoMenu());
    fireEvent.click(barra().getByRole('link', { name: 'Sua conta' }));
    expect(location.pathname).toBe('/conta');
    expect(botaoDoMenu().getAttribute('aria-expanded')).toBe('false');
    expect(principal().getByRole('heading', { level: 1, name: 'Sua conta' })).toBeDefined();
  });

  it('Sair apaga a sessão no servidor e vai à página inicial, sem deixar a página de antes no voltar', async () => {
    const { sessao, pedidos } = await montar('/painel', { rotas: { 'DELETE /sessoes/atual': NADA } });
    const antes = history.length;
    fireEvent.click(botaoDoMenu());
    await clicar('Sair', barra());
    expect(pedidos.map((p) => p.rota)).toContain('DELETE /sessoes/atual');
    expect(sessao.conta.obter().tipo).toBe('anonima');
    expect(location.pathname).toBe('/');
    expect(history.length).toBe(antes);
  });

  it('Sair que falha avisa que a sessão pode continuar aberta, e a conta segue na tela', async () => {
    const { sessao } = await montar('/painel', {
      rotas: { 'DELETE /sessoes/atual': () => Promise.reject(new TypeError('Failed to fetch')) },
    });
    fireEvent.click(botaoDoMenu());
    await clicar('Sair', barra());
    expect(barra().getByText(FRASE_SAIR_FALHOU)).toBeDefined();
    expect(sessao.conta.obter().tipo).toBe('conectada');
    expect(location.pathname).toBe('/painel');
  });

  it('aparece também na demonstração e nas páginas públicas; não aparece para quem não entrou', async () => {
    const { sessao } = await montar('/painel');
    act(() => {
      sessao.conta.verDemonstracao();
    });
    expect(botaoDoMenu()).toBeDefined();
    cleanup();
    await montar('/termos');
    expect(botaoDoMenu()).toBeDefined();
    cleanup();
    await montar('/painel', { rotas: { 'GET /conta': SEM_SESSAO } });
    expect(barra().queryByRole('button', { name: /^Conta:/u })).toBeNull();
  });

  it('na folha do celular: o e-mail e as opções abertas, sem o botão', async () => {
    await montar('/painel');
    fireEvent.click(barra().getByRole('button', { name: 'Menu' }));
    const folha = within(screen.getByRole('dialog', { name: 'Menu' }));
    expect(folha.getByText(CONTA_DE_TESTE.email)).toBeDefined();
    expect(folha.queryByRole('button', { name: /^Conta:/u })).toBeNull();
    fireEvent.click(folha.getByRole('link', { name: 'Sua conta' }));
    expect(location.pathname).toBe('/conta');
    expect(screen.queryByRole('dialog', { name: 'Menu' })).toBeNull();
  });
});

describe('Sua conta: os dados', () => {
  it('mostra o que o GET /conta devolveu, sem pedir nada além dele', async () => {
    const { pedidos } = await montar('/conta');
    const p = principal();
    expect(p.getByText(CONTA_DE_TESTE.email)).toBeDefined();
    expect(p.getByText(`${CONTA_DE_TESTE.organizacao.nome} · Dono`)).toBeDefined();
    expect(p.getByText(instante(CONTA_DE_TESTE.criadaEm))).toBeDefined();
    expect(p.getByText(`Versão de 26/11/2026, aceita em ${instante(CONTA_DE_TESTE.termos?.aceitosEm)}.`)).toBeDefined();
    expect(p.getByText('Nenhuma empresa cadastrada.')).toBeDefined();
    expect(p.getByText(/^10 de 10 válidos\./u)).toBeDefined();
    expect(p.getByText('Nenhum aviso.')).toBeDefined();
    expect(
      p.getByText(`Termina em ${instante(CONTA_DE_TESTE.sessaoExpiraEm)}, ou antes, com 30 minutos sem uso.`),
    ).toBeDefined();
    expect(p.queryByRole('note')).toBeNull();
    expect(pedidos.map((x) => x.rota)).toEqual(['GET /conta']);
  });

  it('as empresas com a máscara do CNPJ, os avisos com nome e momento, e a conta sem aceite registrado', async () => {
    await montar('/conta', {
      conta: {
        ...CONTA_DE_TESTE,
        termos: null,
        empresas: ['36817420000113'],
        eventos: [{ tipo: 'codigo-recuperacao-usado', em: '2026-11-26T15:30:00Z' }],
      },
    });
    const p = principal();
    expect(p.getByText('36.817.420/0001-13')).toBeDefined();
    expect(p.getByText('Código de recuperação usado para entrar')).toBeDefined();
    expect(p.getByText(instante('2026-11-26T15:30:00Z'))).toBeDefined();
    expect(p.getByText(/Sem registro do aceite/u)).toBeDefined();
  });

  it(`o aviso de poucos códigos aparece com ${String(AVISO_DE_CODIGOS)} ou menos`, async () => {
    await montar('/conta', { conta: { ...CONTA_DE_TESTE, codigosRecuperacaoRestantes: AVISO_DE_CODIGOS + 1 } });
    expect(principal().queryByRole('note')).toBeNull();
    cleanup();
    await montar('/conta', { conta: { ...CONTA_DE_TESTE, codigosRecuperacaoRestantes: AVISO_DE_CODIGOS } });
    expect(principal().getByRole('note').textContent).toMatch(/Restam poucos códigos/u);
  });

  it('o e-mail e a organização vão como texto, nunca como HTML', async () => {
    await montar('/conta', {
      conta: { ...CONTA_DE_TESTE, organizacao: { ...CONTA_DE_TESTE.organizacao, nome: '<img src=x onerror=alert(1)>' } },
    });
    expect(document.querySelector('main img')).toBeNull();
    expect(principal().getByText('<img src=x onerror=alert(1)> · Dono')).toBeDefined();
  });
});

describe('Sua conta: sessão', () => {
  it('Sair de todos os aparelhos chama DELETE /sessoes e vai à página inicial', async () => {
    const { sessao, pedidos } = await montar('/conta', { rotas: { 'DELETE /sessoes': NADA } });
    await clicar('Sair de todos os aparelhos');
    expect(pedidos.map((p) => p.rota)).toContain('DELETE /sessoes');
    expect(sessao.conta.obter().tipo).toBe('anonima');
    expect(location.pathname).toBe('/');
  });

  it('Sair de todos que falha mostra a frase, com o foco, e a conta segue', async () => {
    const { sessao } = await montar('/conta', {
      rotas: { 'DELETE /sessoes': () => Promise.reject(new TypeError('Failed to fetch')) },
    });
    await clicar('Sair de todos os aparelhos');
    const alerta = principal().getByRole('alert');
    expect(alerta.textContent).toBe(FRASE_SAIR_FALHOU);
    await waitFor(() => {
      expect(document.activeElement).toBe(alerta);
    });
    expect(sessao.conta.obter().tipo).toBe('conectada');
  });
});

describe('Sua conta: excluir', () => {
  async function abrirExclusao(rotas: Rotas = {}) {
    const montado = await montar('/conta', { rotas });
    fireEvent.click(principal().getByRole('button', { name: 'Excluir a conta…' }));
    await waitFor(() => {
      expect(document.activeElement).toBe(principal().getByLabelText('Senha'));
    });
    return montado;
  }

  it('o formulário pede a senha (current-password) e a confirmação; vazio, aponta os dois e não chama a API', async () => {
    const { pedidos } = await abrirExclusao();
    expect(principal().getByLabelText('Senha').getAttribute('autocomplete')).toBe('current-password');
    // O e-mail oculto diz ao gerenciador de senhas de qual conta é a senha; não aparece nem recebe o foco.
    const usuario = document.querySelector<HTMLInputElement>('.conta__perigo input[autocomplete="username"]');
    expect(usuario?.value).toBe(CONTA_DE_TESTE.email);
    expect(usuario?.hidden).toBe(true);
    expect(usuario?.readOnly).toBe(true);
    await clicar('Excluir a conta');
    expect(principal().getByLabelText('Senha').getAttribute('aria-invalid')).toBe('true');
    expect(principal().getByText(FRASE_DA_CONFIRMACAO)).toBeDefined();
    expect(document.activeElement).toBe(principal().getByLabelText('Senha'));
    expect(pedidos.map((p) => p.rota)).not.toContain('POST /conta/excluir');
  });

  it('só falta a confirmação: o foco vai à caixa', async () => {
    await abrirExclusao();
    fireEvent.change(principal().getByLabelText('Senha'), { target: { value: 'a senha' } });
    await clicar('Excluir a conta');
    expect(document.activeElement).toBe(principal().getByLabelText(/Entendo que a exclusão/u));
  });

  it('certo: envia a senha, a sessão acaba e a página diz que a conta foi excluída', async () => {
    const { sessao, pedidos } = await abrirExclusao({ 'POST /conta/excluir': NADA });
    fireEvent.change(principal().getByLabelText('Senha'), { target: { value: 'a senha da pessoa' } });
    fireEvent.click(principal().getByLabelText(/Entendo que a exclusão/u));
    await clicar('Excluir a conta');
    expect(pedidos.find((p) => p.rota === 'POST /conta/excluir')?.corpo).toEqual({ senha: 'a senha da pessoa' });
    expect(sessao.conta.obter().tipo).toBe('anonima');
    expect(principal().getByRole('heading', { level: 2, name: 'A conta foi excluída' })).toBeDefined();
    expect(principal().getByRole('link', { name: 'Ir à página inicial' }).getAttribute('href')).toBe('/');
    expect(barra().queryByRole('button', { name: /^Conta:/u })).toBeNull();
  });

  it('senha errada (401, a sessão continua): a frase da API, a senha limpa, e o formulário fica', async () => {
    await abrirExclusao({
      'POST /conta/excluir': () => json({ title: 'Unauthorized', status: 401, detail: 'Senha incorreta.' }, 401),
    });
    fireEvent.change(principal().getByLabelText('Senha'), { target: { value: 'errada' } });
    fireEvent.click(principal().getByLabelText(/Entendo que a exclusão/u));
    await clicar('Excluir a conta');
    expect(principal().getByRole('alert').textContent).toBe('Senha incorreta.');
    expect(principal().getByLabelText<HTMLInputElement>('Senha').value).toBe('');
  });

  it('401 com a sessão acabada: a página diz que a sessão terminou', async () => {
    let chamadas = 0;
    await abrirExclusao({
      'POST /conta/excluir': () => json({ title: 'Unauthorized', status: 401, detail: 'Entre com a sua conta.' }, 401),
      'GET /conta': () => {
        chamadas += 1;
        return chamadas === 1 ? json(CONTA_DE_TESTE) : SEM_SESSAO();
      },
    });
    fireEvent.change(principal().getByLabelText('Senha'), { target: { value: 'qualquer' } });
    fireEvent.click(principal().getByLabelText(/Entendo que a exclusão/u));
    await clicar('Excluir a conta');
    await waitFor(() => {
      expect(principal().getByText('Sua sessão terminou. Entre de novo para ver a sua conta.')).toBeDefined();
    });
  });

  it('409 (dono com outros membros): a frase da API', async () => {
    const frase = 'Passe a posse da organização a outro membro antes de excluir a conta.';
    await abrirExclusao({ 'POST /conta/excluir': () => json({ title: 'Conflict', status: 409, detail: frase }, 409) });
    fireEvent.change(principal().getByLabelText('Senha'), { target: { value: 'a senha' } });
    fireEvent.click(principal().getByLabelText(/Entendo que a exclusão/u));
    await clicar('Excluir a conta');
    expect(principal().getByRole('alert').textContent).toBe(frase);
  });

  it('conta bloqueada: a frase, sem contagem', async () => {
    const frase = 'Conta bloqueada depois de muitas tentativas erradas. Peça o desbloqueio ao administrador do ContaAI.';
    await abrirExclusao({
      'POST /conta/excluir': () =>
        json({ type: TIPO_CONTA_BLOQUEADA, title: 'Conta bloqueada', status: 429, detail: frase }, 429, {
          'Retry-After': '3600',
        }),
    });
    fireEvent.change(principal().getByLabelText('Senha'), { target: { value: 'a senha' } });
    fireEvent.click(principal().getByLabelText(/Entendo que a exclusão/u));
    await clicar('Excluir a conta');
    expect(principal().getByRole('alert').textContent).toBe(frase);
    expect(document.body.textContent).not.toMatch(/Aguarde/u);
  });

  it('Cancelar fecha o formulário, apaga a senha e devolve o foco ao botão', async () => {
    await abrirExclusao();
    fireEvent.change(principal().getByLabelText('Senha'), { target: { value: 'a senha' } });
    fireEvent.click(principal().getByRole('button', { name: 'Cancelar' }));
    expect(principal().queryByLabelText('Senha')).toBeNull();
    await waitFor(() => {
      expect(document.activeElement).toBe(principal().getByRole('button', { name: 'Excluir a conta…' }));
    });
    fireEvent.click(principal().getByRole('button', { name: 'Excluir a conta…' }));
    expect(principal().getByLabelText<HTMLInputElement>('Senha').value).toBe('');
  });

  it('nada vai ao endereço ou ao armazenamento do navegador', async () => {
    await abrirExclusao();
    fireEvent.change(principal().getByLabelText('Senha'), { target: { value: 'a senha' } });
    expect(location.search + location.hash).toBe('');
    expect(localStorage.length + sessionStorage.length).toBe(0);
  });
});
