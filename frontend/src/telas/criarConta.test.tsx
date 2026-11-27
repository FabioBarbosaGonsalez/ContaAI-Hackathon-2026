// C2b, etapas 6 e 7 (ADR 0016): Criar conta em três passos, com a API falsa (fetch do teste).

import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from '../App.tsx';
import { carregarSessao } from '../sessao/acoes.ts';
import { reiniciarFocoDePagina } from '../shell/Pagina.tsx';
import { CONTA_DE_TESTE, SAUDE_REAL, json, sessaoDeTeste } from '../teste/sessaoDeTeste.ts';
import { FRASE_DOS_TERMOS, PASSOS_DO_CADASTRO } from './CriarConta.tsx';
import { ARQUIVO_DOS_CODIGOS, prazoDoPasse, textoDosCodigos } from './SegundoFator.tsx';
import { REGRAS_DA_CONTA, VERSAO_TERMOS } from './legal.ts';

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

/** Um segredo de 32 caracteres de base32, como o do backend (totp.py), e o endereço dele. */
const SEGREDO = 'JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP';
const OTPAUTH = `otpauth://totp/ContaAI:pessoa%40exemplo.test?secret=${SEGREDO}&issuer=ContaAI&algorithm=SHA1&digits=6&period=30`;
const AVISO_DO_SEGREDO =
  'Leia o QR code (ou digite o segredo) num aplicativo autenticador e envie o primeiro código. O segredo não aparece de novo.';
const CODIGOS = Array.from({ length: 10 }, (_, i) => `ABCD-EFGH-IJKL${String.fromCharCode(65 + i)}`);
const AVISO_DOS_CODIGOS =
  'Guarde os códigos de recuperação fora do celular. Cada um vale uma vez, no lugar do código do aplicativo, e eles não aparecem de novo.';

type Rota = (pedido: Request, corpo: unknown) => Response | Promise<Response>;

/** Abre /criar-conta como o main.tsx (/saude, depois /conta, sem sessão). `rotas` responde às da conta. */
async function montar(rotas: Partial<Record<'/contas' | '/contas/ativar', Rota>> = {}) {
  history.replaceState(null, '', '/criar-conta');
  const corpos: { rota: string; corpo: unknown; credenciais: RequestCredentials }[] = [];
  const sessao = sessaoDeTeste(async (pedido) => {
    const rota = new URL(pedido.url).pathname;
    if (rota === '/saude') {
      return json(SAUDE_REAL);
    }
    if (rota === '/conta') {
      return json({ title: 'Unauthorized', status: 401, detail: 'Entre com a sua conta.' }, 401);
    }
    if (rota === '/contas' || rota === '/contas/ativar') {
      const corpo: unknown = await pedido.clone().json();
      corpos.push({ rota, corpo, credenciais: pedido.credentials });
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

function preencher({
  email = 'pessoa@exemplo.test',
  senha = 'uma frase bem longa',
  organizacao = 'Escritório de teste',
  aceite = true,
} = {}) {
  fireEvent.change(campo('E-mail'), { target: { value: email } });
  fireEvent.change(campo('Senha'), { target: { value: senha } });
  fireEvent.change(campo('Organização'), { target: { value: organizacao } });
  if (aceite) {
    fireEvent.click(campo(/Li e aceito os termos de uso/u));
  }
}

/**
 * Envia e espera a resposta da API falsa: o botão sai de "Criando…"/"Confirmando…". Uma volta só do relógio não
 * basta com a máquina ocupada (a resposta falsa passa por várias promessas).
 */
async function enviar(botao: string) {
  act(() => {
    fireEvent.click(principal().getByRole('button', { name: botao }));
  });
  await waitFor(() => {
    expect(screen.queryByRole('button', { name: /…$/u })).toBeNull();
  });
}

const cadastroCerto: Rota = () =>
  json({ otpauth: OTPAUTH, segredo: SEGREDO, expiraEm: '2026-11-26T12:05:00Z', aviso: AVISO_DO_SEGREDO }, 201);
const ativacaoCerta: Rota = () =>
  json({ conta: CONTA_DE_TESTE, codigosRecuperacao: CODIGOS, aviso: AVISO_DOS_CODIGOS });

async function irAoQr(rotas: Partial<Record<'/contas/ativar', Rota>> = {}) {
  const montado = await montar({ '/contas': cadastroCerto, ...rotas });
  preencher();
  await enviar('Continuar');
  return montado;
}

async function irAosCodigos() {
  const montado = await irAoQr({ '/contas/ativar': ativacaoCerta });
  fireEvent.change(campo('Código do aplicativo'), { target: { value: '123456' } });
  await enviar('Confirmar o código');
  return montado;
}

function passoAtual(): string | null {
  const atual = within(screen.getByRole('list', { name: 'Passos' }))
    .getAllByRole('listitem')
    .find((li) => li.getAttribute('aria-current') === 'step');
  return atual?.textContent.replace(/^\d+\s*/u, '') ?? null;
}

describe('Criar conta, passo 1: os dados e o aceite', () => {
  it('campos com rótulo, autocomplete e name para o gerenciador de senhas; o formulário não tem action', async () => {
    await montar();
    expect(passoAtual()).toBe(PASSOS_DO_CADASTRO[0]);
    const email = campo('E-mail');
    expect([email.type, email.autocomplete, email.name]).toEqual(['email', 'username', 'email']);
    expect([email.getAttribute('spellcheck'), email.getAttribute('autocapitalize')]).toEqual(['false', 'off']);
    const senha = campo('Senha');
    expect([senha.type, senha.autocomplete, senha.name]).toEqual(['password', 'new-password', 'senha']);
    const organizacao = campo('Organização');
    expect(organizacao.autocomplete).toBe('organization');
    // Sem maxLength: o do HTML conta UTF-16 e corta o colado sem avisar.
    expect([email.getAttribute('maxlength'), organizacao.getAttribute('maxlength')]).toEqual([null, null]);
    const formulario = email.closest('form');
    expect(formulario?.getAttribute('action')).toBeNull();
    expect(formulario?.noValidate).toBe(true);
    expect(principal().getByRole('checkbox').getAttribute('name')).toBe('termos');
    expect(principal().getByText(/versão de 26\/11\/2026/u)).toBeDefined();
  });

  it('termos e privacidade abrem em outra aba, sem opener, e a página não sai do cadastro', async () => {
    await montar();
    for (const [nome, href] of [
      ['Termos de uso', '/termos'],
      ['Privacidade', '/privacidade'],
    ] as const) {
      const link = principal().getByRole('link', { name: nome });
      expect([link.getAttribute('href'), link.getAttribute('target'), link.getAttribute('rel')]).toEqual([
        href,
        '_blank',
        'noopener noreferrer',
      ]);
      fireEvent.click(link);
      expect(location.pathname).toBe('/criar-conta');
    }
  });

  it('o medidor de força aparece ao digitar a senha, é lido junto do campo e some com o campo vazio', async () => {
    await montar();
    const senha = campo('Senha');
    expect(principal().queryByText(/^Senha (fraca|média|forte)$/u)).toBeNull();
    fireEvent.change(senha, { target: { value: 'abc' } });
    const rotulo = principal().getByText('Senha fraca');
    const medidor = rotulo.closest('.forca');
    expect(medidor?.getAttribute('data-forca')).toBe('fraca');
    const descricao = (senha.getAttribute('aria-describedby') ?? '').split(' ');
    expect(descricao.some((id) => document.getElementById(id)?.contains(rotulo))).toBe(true);
    fireEvent.change(senha, { target: { value: 'correto cavalo bateria grampo' } });
    expect(await principal().findByText('Senha forte')).toBeDefined();
    fireEvent.change(senha, { target: { value: '' } });
    expect(principal().queryByText(/^Senha (fraca|média|forte)$/u)).toBeNull();
  });

  it('a senha feita do próprio e-mail fica fraca, mesmo longa', async () => {
    await montar();
    fireEvent.change(campo('E-mail'), { target: { value: 'escritoriomodelo@exemplo.test' } });
    fireEvent.change(campo('Senha'), { target: { value: 'escritoriomodelo' } });
    expect(await principal().findByText('Senha fraca')).toBeDefined();
  });

  it('o medidor só orienta: uma senha fraca de 8 caracteres ou mais é enviada, e o backend decide', async () => {
    const { corpos } = await montar({ '/contas': cadastroCerto });
    preencher({ senha: 'cachorro2024' });
    expect(await principal().findByText('Senha fraca')).toBeDefined();
    await enviar('Continuar');
    expect(corpos.map((c) => c.rota)).toEqual(['/contas']);
  });

  it('enviar vazio aponta os quatro erros, põe o foco no primeiro e não chama a API', async () => {
    const { corpos } = await montar();
    await enviar('Continuar');
    expect(campo('E-mail').getAttribute('aria-invalid')).toBe('true');
    expect(campo('Senha').getAttribute('aria-invalid')).toBe('true');
    expect(campo('Organização').getAttribute('aria-invalid')).toBe('true');
    expect(principal().getByRole('checkbox').getAttribute('aria-invalid')).toBe('true');
    expect(principal().getByText(FRASE_DOS_TERMOS)).toBeDefined();
    expect(document.activeElement).toBe(campo('E-mail'));
    expect(corpos).toEqual([]);
  });

  it('só falta o aceite: o foco vai à caixa', async () => {
    const { corpos } = await montar();
    preencher({ aceite: false });
    await enviar('Continuar');
    expect(document.activeElement).toBe(principal().getByRole('checkbox'));
    expect(campo('E-mail').getAttribute('aria-invalid')).toBeNull();
    expect(corpos).toEqual([]);
  });

  it('a senha é contada como o backend conta (pontos de código): 4 emojis são 4 caracteres', async () => {
    const { corpos } = await montar();
    preencher({ senha: '😀😀😀😀' }); // taste-skill-ignore: dado de teste (pontos de código), não é interface
    await enviar('Continuar');
    expect(principal().getByText(`A senha precisa ter pelo menos ${String(REGRAS_DA_CONTA.senhaMinima)} caracteres.`)).toBeDefined();
    expect(corpos).toEqual([]);
  });

  it('envia o e-mail e a organização sem espaços nas pontas, a senha como foi digitada e a versão dos termos', async () => {
    const { corpos } = await montar({ '/contas': cadastroCerto });
    preencher({ email: '  pessoa@exemplo.test ', senha: ' com espaço nas pontas ', organizacao: ' Escritório ' });
    await enviar('Continuar');
    expect(corpos.map(({ rota, corpo }) => ({ rota, corpo }))).toEqual([
      {
        rota: '/contas',
        corpo: {
          email: 'pessoa@exemplo.test',
          senha: ' com espaço nas pontas ',
          organizacao: 'Escritório',
          termosAceitos: VERSAO_TERMOS,
        },
      },
    ]);
    // O passe da ativação volta num cookie: o pedido não pode sair sem credenciais.
    expect(corpos[0]?.credenciais).not.toBe('omit');
  });

  it('409: a frase da API, com o foco, e o caminho para Entrar; o que foi digitado fica', async () => {
    const frase = 'Este e-mail já tem uma conta. Entre com a senha e o código.';
    await montar({ '/contas': () => json({ title: 'Conflict', status: 409, detail: frase }, 409) });
    preencher();
    await enviar('Continuar');
    const alerta = principal().getByRole('alert');
    expect(alerta.textContent).toBe(frase);
    await waitFor(() => {
      expect(document.activeElement).toBe(alerta);
    });
    const entrar = principal().getAllByRole('link', { name: 'Entrar' });
    expect(entrar.map((l) => l.getAttribute('href'))).toEqual(['/entrar', '/entrar']);
    expect(campo('E-mail').value).toBe('pessoa@exemplo.test');
    expect(passoAtual()).toBe(PASSOS_DO_CADASTRO[0]);
  });

  it('422 (senha recusada): a frase da API, sem o caminho para Entrar', async () => {
    const frase = 'Essa senha é muito comum ou fácil de adivinhar. Escolha outra.'; // senha.py
    await montar({ '/contas': () => json({ title: 'Unprocessable', status: 422, detail: frase }, 422) });
    preencher();
    await enviar('Continuar');
    expect(principal().getByRole('alert').textContent).toBe(frase);
    expect(principal().getAllByRole('link', { name: 'Entrar' })).toHaveLength(1);
  });

  it('429: o botão espera o Retry-After e volta sozinho', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    await montar({
      '/contas': () =>
        json({ title: 'Too Many Requests', status: 429, detail: 'Muitas requisições.' }, 429, { 'Retry-After': '30' }),
    });
    preencher();
    await enviar('Continuar');
    const botao = () => principal().getByRole<HTMLButtonElement>('button', { name: /^(Aguarde|Continuar)/u });
    expect(botao().disabled).toBe(true);
    // O relógio falso anda junto com o real (shouldAdvanceTime): com a máquina ocupada, já passou algum tempo.
    const segundos = Number(/^Aguarde (\d+) s$/u.exec(botao().textContent)?.[1]);
    expect(segundos).toBeGreaterThanOrEqual(20);
    expect(segundos).toBeLessThanOrEqual(30);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(31_000);
    });
    expect(botao().disabled).toBe(false);
    expect(botao().textContent).toBe('Continuar');
  });

  it('API fora do ar: a frase da rede', async () => {
    await montar({ '/contas': () => Promise.reject(new TypeError('Failed to fetch')) });
    preencher();
    await enviar('Continuar');
    expect(principal().getByRole('alert').textContent).toMatch(/Não foi possível falar com a API/u);
  });
});

describe('Criar conta, passo 2: o QR e o primeiro código', () => {
  it('mostra o QR, o segredo, o e-mail e a frase da API; a senha sai da tela e o título recebe o foco', async () => {
    await irAoQr();
    expect(passoAtual()).toBe(PASSOS_DO_CADASTRO[1]);
    expect(principal().getByRole('img', { name: 'QR code para o aplicativo autenticador' })).toBeDefined();
    expect(principal().getByText(AVISO_DO_SEGREDO)).toBeDefined();
    expect(principal().getByText('pessoa@exemplo.test')).toBeDefined();
    expect(document.querySelector('.segredo')?.textContent).toBe(SEGREDO);
    expect(document.querySelector('input[type="password"]')).toBeNull();
    expect(principal().queryByLabelText('Senha')).toBeNull();
    await waitFor(() => {
      expect(document.activeElement).toBe(principal().getByRole('heading', { level: 2, name: 'Ligue o aplicativo autenticador' }));
    });
    const codigo = campo('Código do aplicativo');
    expect([codigo.autocomplete, codigo.inputMode]).toEqual(['one-time-code', 'numeric']);
    expect(principal().getByRole('timer').textContent).toMatch(/^[45] min/u);
  });

  it('nada do cadastro vai ao endereço ou ao armazenamento do navegador', async () => {
    localStorage.clear();
    sessionStorage.clear();
    await irAoQr();
    expect(location.href).not.toContain(SEGREDO);
    expect(location.pathname + location.search + location.hash).toBe('/criar-conta');
    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
  });

  it('copiar o segredo leva o segredo exato, sem espaços', async () => {
    const escrever = vi.fn(() => Promise.resolve());
    Object.defineProperty(navigator, 'clipboard', { value: { writeText: escrever }, configurable: true });
    await irAoQr();
    await act(async () => {
      fireEvent.click(principal().getByRole('button', { name: 'Copiar o segredo' }));
      await Promise.resolve();
    });
    expect(escrever).toHaveBeenCalledWith(SEGREDO);
    expect(principal().getByText('Copiado.')).toBeDefined();
  });

  it('sem a área de transferência, pede para copiar à mão', async () => {
    Object.defineProperty(navigator, 'clipboard', { value: undefined, configurable: true });
    await irAoQr();
    await act(async () => {
      fireEvent.click(principal().getByRole('button', { name: 'Copiar o segredo' }));
      await Promise.resolve();
    });
    expect(principal().getByText('Não deu para copiar. Selecione o texto e copie.')).toBeDefined();
  });

  it('código fora do formato: o erro no campo, sem chamar a API', async () => {
    const { corpos } = await irAoQr();
    fireEvent.change(campo('Código do aplicativo'), { target: { value: '12a456' } });
    await enviar('Confirmar o código');
    expect(campo('Código do aplicativo').getAttribute('aria-invalid')).toBe('true');
    expect(document.activeElement).toBe(campo('Código do aplicativo'));
    expect(corpos.filter((c) => c.rota === '/contas/ativar')).toEqual([]);
  });

  it('código com espaço vai sem ele; o 401 mostra a frase da API, limpa o campo e fica no passo', async () => {
    const frase = 'E-mail, senha ou código incorretos.';
    const { corpos, sessao } = await irAoQr({
      '/contas/ativar': () => json({ title: 'Unauthorized', status: 401, detail: frase }, 401),
    });
    fireEvent.change(campo('Código do aplicativo'), { target: { value: '123 456' } });
    await enviar('Confirmar o código');
    expect(corpos.at(-1)).toMatchObject({ rota: '/contas/ativar', corpo: { codigo: '123456' } });
    expect(principal().getByRole('alert').textContent).toBe(frase);
    expect(campo('Código do aplicativo').value).toBe('');
    expect(passoAtual()).toBe(PASSOS_DO_CADASTRO[1]);
    expect(sessao.conta.obter().tipo).toBe('anonima');
  });

  it('o passe vencido tira o QR e o segredo da tela e leva a Entrar', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    await irAoQr();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(REGRAS_DA_CONTA.passeMin * 60_000 + 1000);
    });
    expect(principal().queryByRole('img')).toBeNull();
    expect(document.body.textContent).not.toContain(SEGREDO.slice(0, 4) + SEGREDO.slice(4, 8));
    expect(document.querySelector('.segredo')).toBeNull();
    expect(principal().getByRole('heading', { level: 2, name: 'O tempo para confirmar acabou' })).toBeDefined();
    expect(principal().getByRole('link', { name: 'Entrar' }).getAttribute('href')).toBe('/entrar');
  });

  it('o prazo é contado de quando a resposta chegou, com a duração do backend', () => {
    expect(prazoDoPasse(1000)).toBe(1000 + REGRAS_DA_CONTA.passeMin * 60_000);
  });
});

describe('Criar conta, passo 3: os códigos de recuperação', () => {
  it('a conta abre, a página fica (não vai ao Painel) e mostra os 10 códigos e a frase da API', async () => {
    const { sessao } = await irAosCodigos();
    expect(sessao.conta.obter()).toMatchObject({ tipo: 'conectada', naDemo: false });
    expect(location.pathname).toBe('/criar-conta');
    expect(passoAtual()).toBe(PASSOS_DO_CADASTRO[2]);
    const lista = within(principal().getByRole('list', { name: 'Códigos de recuperação' }));
    expect(lista.getAllByRole('listitem').map((li) => li.textContent)).toEqual(CODIGOS);
    expect(principal().getByText(`Conta criada. ${AVISO_DOS_CODIGOS}`)).toBeDefined();
    // O QR e o segredo já saíram da tela.
    expect(principal().queryByRole('img')).toBeNull();
    await waitFor(() => {
      expect(document.activeElement).toBe(principal().getByRole('heading', { level: 2, name: 'Guarde os códigos de recuperação' }));
    });
  });

  it('copiar leva os 10 códigos, um por linha', async () => {
    const escrever = vi.fn(() => Promise.resolve());
    Object.defineProperty(navigator, 'clipboard', { value: { writeText: escrever }, configurable: true });
    await irAosCodigos();
    await act(async () => {
      fireEvent.click(principal().getByRole('button', { name: 'Copiar os códigos' }));
      await Promise.resolve();
    });
    expect(escrever).toHaveBeenCalledWith(CODIGOS.join('\n'));
  });

  it('baixar entrega um .txt por blob: e revoga o endereço logo depois', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const blobs: Blob[] = [];
    const criar = vi.fn((b: Blob) => {
      blobs.push(b);
      return 'blob:http://localhost/teste';
    });
    const revogar = vi.fn();
    Object.assign(URL, { createObjectURL: criar, revokeObjectURL: revogar });
    const cliques: HTMLAnchorElement[] = [];
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function clicar(this: HTMLAnchorElement) {
      cliques.push(this);
    });
    await irAosCodigos();
    fireEvent.click(principal().getByRole('button', { name: 'Baixar (.txt)' }));
    expect(cliques).toHaveLength(1);
    expect([cliques[0]?.download, cliques[0]?.getAttribute('href')]).toEqual([
      ARQUIVO_DOS_CODIGOS,
      'blob:http://localhost/teste',
    ]);
    expect(cliques[0]?.isConnected).toBe(false);
    expect(blobs[0]?.type).toBe('text/plain;charset=utf-8');
    const texto = await blobs[0]?.text();
    for (const c of CODIGOS) {
      expect(texto).toContain(c);
    }
    expect(texto).toContain('Conta: pessoa@exemplo.test');
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10);
    });
    expect(revogar).toHaveBeenCalledWith('blob:http://localhost/teste');
  });

  it('fechar a aba neste passo pede confirmação; "Guardei os códigos" vai ao Painel sem deixar o cadastro no voltar', async () => {
    await irAosCodigos();
    // O ouvinte entra num efeito, logo depois de a tela aparecer.
    await waitFor(() => {
      const fechar = new Event('beforeunload', { cancelable: true });
      dispatchEvent(fechar);
      expect(fechar.defaultPrevented).toBe(true);
    });

    const antes = history.length;
    act(() => {
      fireEvent.click(principal().getByRole('button', { name: 'Guardei os códigos' }));
    });
    expect(location.pathname).toBe('/painel');
    expect(history.length).toBe(antes);
    expect(screen.queryByText(CODIGOS[0] ?? '')).toBeNull();
    const depois = new Event('beforeunload', { cancelable: true });
    dispatchEvent(depois);
    expect(depois.defaultPrevented).toBe(false);
  });
});

describe('ao lado dos passos', () => {
  it('como a conta é protegida, com as regras do backend (legal.ts), em todos os passos', async () => {
    await irAoQr();
    const lado = within(principal().getByRole('complementary', { name: 'Como a conta é protegida' }));
    const frases = lado.getAllByRole('definition').map((d) => d.textContent);
    expect(frases).toContain(
      `Um código de ${String(REGRAS_DA_CONTA.digitosDoCodigo)} dígitos do aplicativo autenticador a cada entrada.`,
    );
    expect(frases).toContain(
      `Termina com ${String(REGRAS_DA_CONTA.sessaoOciosaMin)} minutos sem uso ou ${String(REGRAS_DA_CONTA.sessaoTotalH)} horas depois de entrar.`,
    );
    // O mesmo que os termos de uso dizem (Termos.tsx): não há recuperação de senha.
    expect(frases).toContain('Guardada só como resumo (Argon2id). Não há recuperação de senha.');
    expect(frases.some((f) => f.startsWith(`${String(REGRAS_DA_CONTA.codigosDeRecuperacao)} códigos`))).toBe(true);
  });
});

describe('textoDosCodigos', () => {
  it('o e-mail, a data e os códigos numerados, em texto puro', () => {
    const texto = textoDosCodigos('pessoa@exemplo.test', ['AAAA-BBBB-CCCCC', 'DDDD-EEEE-FFFFF'], new Date(2026, 10, 26));
    expect(texto.split('\n')).toEqual([
      'ContaAI: códigos de recuperação',
      'Conta: pessoa@exemplo.test',
      'Gerados em 26/11/2026',
      '',
      'Cada código vale uma vez, no lugar do código do aplicativo autenticador.',
      'Guarde este arquivo fora do celular e apague as cópias que não forem precisas.',
      '',
      ' 1. AAAA-BBBB-CCCCC',
      ' 2. DDDD-EEEE-FFFFF',
      '',
    ]);
  });
});
