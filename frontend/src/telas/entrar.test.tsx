// C2b, etapa 8 (ADR 0016): Entrar em duas etapas, com a API falsa (fetch do teste).

import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from '../App.tsx';
import { carregarSessao } from '../sessao/acoes.ts';
import { reiniciarFocoDePagina } from '../shell/Pagina.tsx';
import { CONTA_DE_TESTE, SAUDE_REAL, json, sessaoDeTeste } from '../teste/sessaoDeTeste.ts';
import { FRASE_DO_PASSE_VENCIDO } from './Entrar.tsx';
import { TIPO_CONTA_BLOQUEADA } from './formulario.tsx';
import { REGRAS_DA_CONTA } from './legal.ts';

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
  vi.useRealTimers();
  vi.restoreAllMocks();
});

const SEGREDO = 'JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP';
const OTPAUTH = `otpauth://totp/ContaAI:pessoa%40exemplo.test?secret=${SEGREDO}&issuer=ContaAI&algorithm=SHA1&digits=6&period=30`;
const FRASE_401 = 'E-mail, senha ou código incorretos.';
const FRASE_BLOQUEADA =
  'Conta bloqueada depois de muitas tentativas erradas. Peça o desbloqueio ao administrador do ContaAI.';
const CODIGOS = Array.from({ length: 10 }, (_, i) => `ABCD-EFGH-IJKL${String.fromCharCode(65 + i)}`);

type Rotas = '/sessoes' | '/sessoes/codigo' | '/contas/ativar';
type Rota = (pedido: Request, corpo: unknown) => Response | Promise<Response>;

async function montar(rotas: Partial<Record<Rotas, Rota>> = {}) {
  history.replaceState(null, '', '/entrar');
  const corpos: { rota: string; corpo: unknown }[] = [];
  const sessao = sessaoDeTeste(async (pedido) => {
    const rota = new URL(pedido.url).pathname;
    if (rota === '/saude') {
      return json(SAUDE_REAL);
    }
    if (rota === '/conta') {
      return json({ title: 'Unauthorized', status: 401, detail: 'Entre com a sua conta.' }, 401);
    }
    if (rota === '/sessoes' || rota === '/sessoes/codigo' || rota === '/contas/ativar') {
      const corpo: unknown = await pedido.clone().json();
      corpos.push({ rota, corpo });
      const responder = rotas[rota];
      if (responder !== undefined) {
        return responder(pedido, corpo);
      }
    }
    return json({ type: 'about:blank', title: 'Not Found', status: 404 }, 404);
  });
  render(<App sessao={sessao} />);
  await act(() => carregarSessao(sessao));
  return { sessao, corpos };
}

const principal = () => within(screen.getByRole('main'));
const campo = (rotulo: string | RegExp) => principal().getByLabelText<HTMLInputElement>(rotulo);

function preencher(email = 'pessoa@exemplo.test', senha = 'a senha da pessoa') {
  fireEvent.change(campo('E-mail'), { target: { value: email } });
  fireEvent.change(campo('Senha'), { target: { value: senha } });
}

async function enviar(botao: string) {
  act(() => {
    fireEvent.click(principal().getByRole('button', { name: botao }));
  });
  await waitFor(() => {
    expect(screen.queryByRole('button', { name: /…$/u })).toBeNull();
  });
}

const pedeCodigo: Rota = () => json({ etapa: 'codigo', expiraEm: '2026-11-26T12:05:00Z' });
const entrou: Rota = () => json({ conta: CONTA_DE_TESTE, novoCodigoRecuperacao: null, aviso: null });
const recusa401: Rota = () => json({ title: 'Unauthorized', status: 401, detail: FRASE_401 }, 401);

async function irAoCodigo(rotas: Partial<Record<Rotas, Rota>> = {}) {
  const montado = await montar({ '/sessoes': pedeCodigo, ...rotas });
  preencher();
  await enviar('Continuar');
  // O `enviar` só espera o botão sair do "…"; com a máquina ocupada, a resposta pode nem ter
  // chegado. O passo 2 aparece quando chega.
  await waitFor(() => {
    expect(principal().queryByRole('heading', { level: 2, name: 'Código do aplicativo' })).not.toBeNull();
  });
  return montado;
}

describe('Entrar, passo 1: e-mail e senha', () => {
  it('campos com rótulo, autocomplete e name para o gerenciador de senhas; o formulário não tem action', async () => {
    await montar();
    const email = campo('E-mail');
    const senha = campo('Senha');
    expect(email.getAttribute('autocomplete')).toBe('username');
    expect(email.getAttribute('name')).toBe('email');
    expect(senha.getAttribute('autocomplete')).toBe('current-password');
    expect(senha.getAttribute('type')).toBe('password');
    expect(senha.getAttribute('name')).toBe('senha');
    const formulario = email.closest('form');
    expect(formulario?.hasAttribute('action')).toBe(false);
    expect(formulario?.noValidate).toBe(true);
    expect(principal().getByRole('link', { name: 'Criar conta' }).getAttribute('href')).toBe('/criar-conta');
  });

  it('enviar vazio aponta os dois erros, põe o foco no e-mail e não chama a API', async () => {
    const { corpos } = await montar();
    await enviar('Continuar');
    expect(campo('E-mail').getAttribute('aria-invalid')).toBe('true');
    expect(campo('Senha').getAttribute('aria-invalid')).toBe('true');
    expect(document.activeElement).toBe(campo('E-mail'));
    expect(corpos).toEqual([]);
  });

  it('só falta a senha: o foco vai à senha. Qualquer senha vai à API (a regra de tamanho é do cadastro)', async () => {
    const { corpos } = await montar({ '/sessoes': pedeCodigo });
    fireEvent.change(campo('E-mail'), { target: { value: ' pessoa@exemplo.test ' } });
    await enviar('Continuar');
    expect(document.activeElement).toBe(campo('Senha'));
    fireEvent.change(campo('Senha'), { target: { value: 'curta' } });
    await enviar('Continuar');
    expect(corpos).toEqual([{ rota: '/sessoes', corpo: { email: 'pessoa@exemplo.test', senha: 'curta' } }]);
  });

  it('401: a frase da API com o foco; a senha sai do campo e o e-mail fica', async () => {
    await montar({ '/sessoes': recusa401 });
    preencher();
    await enviar('Continuar');
    const alerta = principal().getByRole('alert');
    expect(alerta.textContent).toBe(FRASE_401);
    await waitFor(() => {
      expect(document.activeElement).toBe(alerta);
    });
    expect(campo('Senha').value).toBe('');
    expect(campo('E-mail').value).toBe('pessoa@exemplo.test');
  });

  it('429: o botão espera o Retry-After e volta sozinho', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    await montar({
      '/sessoes': () =>
        json({ title: 'Too Many Requests', status: 429, detail: 'Muitas tentativas erradas.' }, 429, {
          'Retry-After': '30',
        }),
    });
    preencher();
    await enviar('Continuar');
    const botao = () => principal().getByRole<HTMLButtonElement>('button', { name: /^(Aguarde|Continuar)/u });
    expect(botao().disabled).toBe(true);
    expect(botao().textContent).toMatch(/^Aguarde \d+ s$/u);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(31_000);
    });
    expect(botao().disabled).toBe(false);
  });

  it('conta bloqueada: a frase da API, sem contagem de 60 min (só o administrador desbloqueia)', async () => {
    await montar({
      '/sessoes': () =>
        json({ type: TIPO_CONTA_BLOQUEADA, title: 'Conta bloqueada', status: 429, detail: FRASE_BLOQUEADA }, 429, {
          'Retry-After': '3600',
        }),
    });
    preencher();
    await enviar('Continuar');
    expect(principal().getByRole('alert').textContent).toBe(FRASE_BLOQUEADA);
    const botao = principal().getByRole<HTMLButtonElement>('button', { name: 'Continuar' });
    expect(botao.disabled).toBe(false);
    expect(document.body.textContent).not.toMatch(/Aguarde/u);
  });

  it('API fora do ar: a frase da rede', async () => {
    await montar({ '/sessoes': () => Promise.reject(new TypeError('Failed to fetch')) });
    preencher();
    await enviar('Continuar');
    expect(principal().getByRole('alert').textContent).toMatch(/Não foi possível falar com a API/u);
  });
});

describe('Entrar, passo 2: o código', () => {
  it('a senha sai da tela; o título recebe o foco; o campo é one-time-code, com a contagem do passe', async () => {
    await irAoCodigo();
    expect(principal().queryByLabelText('Senha')).toBeNull();
    const titulo = principal().getByRole('heading', { level: 2, name: 'Código do aplicativo' });
    // O foco vem de um useEffect, que pode rodar depois de o passo aparecer.
    await waitFor(() => {
      expect(document.activeElement).toBe(titulo);
    });
    expect(campo('Código do aplicativo').getAttribute('autocomplete')).toBe('one-time-code');
    expect(principal().getByRole('timer').textContent).toMatch(/^[45] min/u);
    expect(principal().getByText('pessoa@exemplo.test')).toBeDefined();
  });

  it('código certo: a sessão começa e a página vai ao Painel, sem deixar Entrar no voltar', async () => {
    const { corpos, sessao } = await irAoCodigo({ '/sessoes/codigo': entrou });
    const replace = vi.spyOn(history, 'replaceState');
    fireEvent.change(campo('Código do aplicativo'), { target: { value: '123 456' } });
    await enviar('Entrar');
    expect(corpos.at(-1)).toEqual({ rota: '/sessoes/codigo', corpo: { codigo: '123456' } });
    expect(sessao.conta.obter().tipo).toBe('conectada');
    expect(location.pathname).toBe('/painel');
    expect(replace).toHaveBeenCalled();
  });

  it('código fora do formato: o erro no campo, sem chamar a API', async () => {
    const { corpos } = await irAoCodigo();
    fireEvent.change(campo('Código do aplicativo'), { target: { value: '12a' } });
    await enviar('Entrar');
    expect(campo('Código do aplicativo').getAttribute('aria-invalid')).toBe('true');
    expect(corpos.filter((c) => c.rota === '/sessoes/codigo')).toEqual([]);
  });

  it('401: a frase da API, o campo limpo e o passo fica', async () => {
    const { sessao } = await irAoCodigo({ '/sessoes/codigo': recusa401 });
    fireEvent.change(campo('Código do aplicativo'), { target: { value: '000000' } });
    await enviar('Entrar');
    expect(principal().getByRole('alert').textContent).toBe(FRASE_401);
    expect(campo('Código do aplicativo').value).toBe('');
    expect(sessao.conta.obter().tipo).toBe('anonima');
  });

  it('o passe vencido volta ao passo 1 com o e-mail, sem a senha, e diz por quê', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    await irAoCodigo();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(REGRAS_DA_CONTA.passeMin * 60_000 + 1000);
    });
    expect(principal().getByRole('alert').textContent).toBe(FRASE_DO_PASSE_VENCIDO);
    expect(campo('E-mail').value).toBe('pessoa@exemplo.test');
    expect(campo('Senha').value).toBe('');
  });

  it('com um código de recuperação: envia normalizado, mostra o código novo uma vez e vai ao Painel', async () => {
    const novo = 'WXYZ-2345-ABCDE';
    const aviso = 'Você entrou com um código de recuperação, que deixou de valer. Guarde o novo código no lugar dele.';
    const { corpos } = await irAoCodigo({
      '/sessoes/codigo': () => json({ conta: CONTA_DE_TESTE, novoCodigoRecuperacao: novo, aviso }),
    });
    fireEvent.click(principal().getByRole('button', { name: /Use um código de recuperação/u }));
    await waitFor(() => {
      expect(document.activeElement).toBe(campo('Código de recuperação'));
    });
    expect(campo('Código de recuperação').getAttribute('autocomplete')).toBe('off');
    fireEvent.change(campo('Código de recuperação'), { target: { value: ' abcd-efgh-ijkla ' } });
    await enviar('Entrar');
    expect(corpos.at(-1)).toEqual({ rota: '/sessoes/codigo', corpo: { codigoRecuperacao: 'ABCD-EFGH-IJKLA' } });
    // A sessão começou, mas a página fica até o código novo ser guardado.
    expect(location.pathname).toBe('/entrar');
    expect(principal().getByRole('heading', { level: 2, name: 'Guarde o código novo' })).toBeDefined();
    expect(principal().getByText(aviso)).toBeDefined();
    expect(within(principal().getByRole('list', { name: 'Código de recuperação novo' })).getByText(novo)).toBeDefined();
    // Fechar a aba aqui pede confirmação (o ouvinte entra num efeito, logo depois de a tela aparecer).
    await waitFor(() => {
      const evento = new Event('beforeunload', { cancelable: true });
      globalThis.dispatchEvent(evento);
      expect(evento.defaultPrevented).toBe(true);
    });
    fireEvent.click(principal().getByRole('button', { name: 'Guardei o código' }));
    expect(location.pathname).toBe('/painel');
    expect(screen.queryByText(novo)).toBeNull();
    const depois = new Event('beforeunload', { cancelable: true });
    globalThis.dispatchEvent(depois);
    expect(depois.defaultPrevented).toBe(false);
  });

  it('o botão volta ao código do aplicativo, e o código de recuperação fora do formato não vai à API', async () => {
    const { corpos } = await irAoCodigo();
    fireEvent.click(principal().getByRole('button', { name: /Use um código de recuperação/u }));
    fireEvent.change(campo('Código de recuperação'), { target: { value: 'curto' } });
    await enviar('Entrar');
    expect(campo('Código de recuperação').getAttribute('aria-invalid')).toBe('true');
    fireEvent.click(principal().getByRole('button', { name: 'Usar o código do aplicativo' }));
    expect(campo('Código do aplicativo').value).toBe('');
    expect(corpos.filter((c) => c.rota === '/sessoes/codigo')).toEqual([]);
  });

  it('conta bloqueada no código: sem contagem', async () => {
    await irAoCodigo({
      '/sessoes/codigo': () =>
        json({ type: TIPO_CONTA_BLOQUEADA, title: 'Conta bloqueada', status: 429, detail: FRASE_BLOQUEADA }, 429, {
          'Retry-After': '3600',
        }),
    });
    fireEvent.change(campo('Código do aplicativo'), { target: { value: '123456' } });
    await enviar('Entrar');
    expect(principal().getByRole('alert').textContent).toBe(FRASE_BLOQUEADA);
    expect(principal().getByRole<HTMLButtonElement>('button', { name: 'Entrar' }).disabled).toBe(false);
  });
});

describe('Entrar numa conta pendente (etapa: "ativacao")', () => {
  const ativacao: Rota = () =>
    json({
      etapa: 'ativacao',
      otpauth: OTPAUTH,
      segredo: SEGREDO,
      expiraEm: '2026-11-26T12:05:00Z',
      aviso: 'Leia o QR code num aplicativo autenticador e envie o primeiro código.',
    });

  it('vai ao QR, ativa e mostra os 10 códigos; a página fica até "Guardei os códigos"', async () => {
    const { corpos, sessao } = await montar({
      '/sessoes': ativacao,
      '/contas/ativar': () => json({ conta: CONTA_DE_TESTE, codigosRecuperacao: CODIGOS, aviso: 'Guarde.' }),
    });
    preencher();
    await enviar('Continuar');
    expect(principal().getByRole('img')).toBeDefined();
    expect(principal().getByText(/ainda não confirmou o primeiro código/u)).toBeDefined();
    fireEvent.change(campo('Código do aplicativo'), { target: { value: '123456' } });
    await enviar('Confirmar o código');
    expect(corpos.at(-1)).toEqual({ rota: '/contas/ativar', corpo: { codigo: '123456' } });
    expect(sessao.conta.obter().tipo).toBe('conectada');
    expect(location.pathname).toBe('/entrar');
    expect(within(principal().getByRole('list', { name: 'Códigos de recuperação' })).getAllByRole('listitem')).toHaveLength(
      10,
    );
    fireEvent.click(principal().getByRole('button', { name: 'Guardei os códigos' }));
    expect(location.pathname).toBe('/painel');
  });

  it('o passe vencido no QR volta ao e-mail e à senha na mesma página (sem link para a própria página)', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    await montar({ '/sessoes': ativacao });
    preencher();
    await enviar('Continuar');
    await act(async () => {
      await vi.advanceTimersByTimeAsync(REGRAS_DA_CONTA.passeMin * 60_000 + 1000);
    });
    expect(principal().queryByRole('img')).toBeNull();
    expect(document.querySelector('.segredo')).toBeNull();
    fireEvent.click(principal().getByRole('button', { name: 'Entrar de novo' }));
    expect(principal().getByRole('alert').textContent).toBe(FRASE_DO_PASSE_VENCIDO);
    expect(campo('E-mail').value).toBe('pessoa@exemplo.test');
  });
});

describe('Entrar não guarda nada fora da memória', () => {
  it('nada da entrada vai ao endereço ou ao armazenamento do navegador', async () => {
    await irAoCodigo();
    expect(location.search).toBe('');
    expect(location.hash).toBe('');
    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
  });
});
