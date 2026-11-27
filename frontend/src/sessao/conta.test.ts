// @vitest-environment node
import { describe, expect, it } from 'vitest';
import { criarCliente } from '../api/cliente.ts';
import { CONTA_DE_TESTE } from '../teste/sessaoDeTeste.ts';
import { SessaoConta } from './conta.ts';
import { SessaoEspaco } from './espaco.ts';
import { middlewareDaSessao } from './middleware.ts';
import { SessaoModo } from './modo.ts';
import { SessaoToken } from './token.ts';

function json(corpo: unknown, status = 200, headers: Record<string, string> = {}): Response {
  const tipo = status >= 400 ? 'application/problem+json' : 'application/json';
  return new Response(JSON.stringify(corpo), { status, headers: { 'Content-Type': tipo, ...headers } });
}

const SAUDE = (modo: 'mock' | 'real') => ({ status: 'ok', modo, motores: [] });

/** Um cliente cujo /saude responde no modo pedido, e o /conta com o que o teste mandar. */
function montar(modo: 'mock' | 'real', conta: () => Response | Promise<Response>) {
  const pedidos: Request[] = [];
  const cliente = criarCliente({
    baseUrl: 'http://api.teste',
    fetch: ((pedido: Request) => {
      pedidos.push(pedido);
      return Promise.resolve(new URL(pedido.url).pathname === '/saude' ? json(SAUDE(modo)) : conta());
    }) as typeof globalThis.fetch,
  });
  return { cliente, pedidos, modo: new SessaoModo(), sessao: new SessaoConta() };
}

const SEM_SESSAO = () => json({ title: 'Unauthorized', status: 401, detail: 'Entre com a sua conta.' }, 401);

describe('SessaoConta', () => {
  it('no modo mock, as contas ficam desligadas e o /conta não é pedido', async () => {
    const { cliente, pedidos, modo, sessao } = montar('mock', () => json(CONTA_DE_TESTE));
    await modo.carregar(cliente);
    await sessao.carregar(cliente, modo);
    expect(sessao.obter()).toEqual({ tipo: 'desligada' });
    expect(pedidos.map((p) => new URL(p.url).pathname)).toEqual(['/saude']);
  });

  it('antes do /saude responder, também fica desligada', async () => {
    const { cliente, pedidos, modo, sessao } = montar('real', () => json(CONTA_DE_TESTE));
    await sessao.carregar(cliente, modo);
    expect(sessao.obter().tipo).toBe('desligada');
    expect(pedidos).toHaveLength(0);
  });

  it('aguardar: "carregando" até o /saude e o /conta responderem; no mock, depois fica desligada', async () => {
    const { cliente, modo, sessao } = montar('mock', () => json(CONTA_DE_TESTE));
    sessao.aguardar();
    expect(sessao.obter().tipo).toBe('carregando');
    await modo.carregar(cliente);
    await sessao.carregar(cliente, modo);
    expect(sessao.obter().tipo).toBe('desligada');
  });

  it('no modo real, sem sessão: anônima', async () => {
    const { cliente, modo, sessao } = montar('real', SEM_SESSAO);
    await modo.carregar(cliente);
    const pedido = sessao.carregar(cliente, modo);
    expect(sessao.obter().tipo).toBe('carregando');
    await pedido;
    expect(sessao.obter().tipo).toBe('anonima');
    expect(sessao.naConta()).toBe(false);
  });

  it('com sessão: conectada, mostrando os dados da conta', async () => {
    const { cliente, modo, sessao } = montar('real', () => json(CONTA_DE_TESTE));
    await modo.carregar(cliente);
    await sessao.carregar(cliente, modo);
    expect(sessao.obter()).toEqual({ tipo: 'conectada', conta: CONTA_DE_TESTE, naDemo: false });
    expect(sessao.naConta()).toBe(true);
  });

  it('o /conta vai com o cookie da mesma origem', async () => {
    const { cliente, pedidos, modo, sessao } = montar('real', () => json(CONTA_DE_TESTE));
    await modo.carregar(cliente);
    await sessao.carregar(cliente, modo);
    expect(pedidos[1]?.credentials).toBe('same-origin');
  });

  it('ver a demonstração e voltar à conta, sem perder a conta', async () => {
    const { cliente, modo, sessao } = montar('real', () => json(CONTA_DE_TESTE));
    await modo.carregar(cliente);
    await sessao.carregar(cliente, modo);
    sessao.verDemonstracao();
    expect(sessao.obter()).toMatchObject({ tipo: 'conectada', naDemo: true });
    expect(sessao.naConta()).toBe(false);
    // Recarregar a conta mantém a escolha.
    await sessao.carregar(cliente, modo);
    expect(sessao.obter()).toMatchObject({ tipo: 'conectada', naDemo: true });
    sessao.voltarParaConta();
    expect(sessao.naConta()).toBe(true);
  });

  it('a sessão que acaba vira "encerrada", e o aviso lido vira anônima', async () => {
    let conectada = true;
    const { cliente, modo, sessao } = montar('real', () => (conectada ? json(CONTA_DE_TESTE) : SEM_SESSAO()));
    await modo.carregar(cliente);
    await sessao.carregar(cliente, modo);
    conectada = false;
    await sessao.carregar(cliente, modo);
    expect(sessao.obter().tipo).toBe('encerrada');
    sessao.dispensarAviso();
    expect(sessao.obter().tipo).toBe('anonima');
  });

  it('marcarEncerrada só muda quem estava conectado', async () => {
    const { cliente, modo, sessao } = montar('real', SEM_SESSAO);
    await modo.carregar(cliente);
    await sessao.carregar(cliente, modo);
    sessao.marcarEncerrada();
    expect(sessao.obter().tipo).toBe('anonima');
  });

  it('outra falha do /conta vira erro, e a tela segue como quem não tem conta', async () => {
    const { cliente, modo, sessao } = montar('real', () => json({ title: 'Erro', status: 500, detail: null }, 500));
    await modo.carregar(cliente);
    await sessao.carregar(cliente, modo);
    expect(sessao.obter().tipo).toBe('erro');
    expect(sessao.naConta()).toBe(false);
  });

  it('chamadas ao mesmo tempo esperam o mesmo pedido', async () => {
    const { cliente, pedidos, modo, sessao } = montar('real', () => json(CONTA_DE_TESTE));
    await modo.carregar(cliente);
    await Promise.all([sessao.carregar(cliente, modo), sessao.carregar(cliente, modo)]);
    expect(pedidos.filter((p) => new URL(p.url).pathname === '/conta')).toHaveLength(1);
  });

  it('nada da conta vai ao armazenamento do navegador', async () => {
    const { cliente, modo, sessao } = montar('real', () => json(CONTA_DE_TESTE));
    const gravados: string[] = [];
    const armazenamento = { setItem: (chave: string) => gravados.push(chave) };
    Object.defineProperty(globalThis, 'localStorage', { value: armazenamento, configurable: true });
    Object.defineProperty(globalThis, 'sessionStorage', { value: armazenamento, configurable: true });
    try {
      await modo.carregar(cliente);
      await sessao.carregar(cliente, modo);
      sessao.verDemonstracao();
      expect(gravados).toEqual([]);
    } finally {
      Reflect.deleteProperty(globalThis, 'localStorage');
      Reflect.deleteProperty(globalThis, 'sessionStorage');
    }
  });
});

// ---- Ações da conta (C2b, etapa 4) ----

/** Um cliente com a sessão completa (middleware incluído) e respostas por "MÉTODO /caminho". */
function montarAcoes(respostas: Record<string, () => Response>) {
  const pedidos: { rota: string; credenciais: RequestCredentials; headers: Headers; corpo: string }[] = [];
  const espaco = new SessaoEspaco();
  const token = new SessaoToken();
  const sessao = new SessaoConta();
  const cliente = criarCliente({
    baseUrl: 'http://api.teste',
    fetch: (async (pedido: Request) => {
      const rota = `${pedido.method} ${new URL(pedido.url).pathname}`;
      pedidos.push({ rota, credenciais: pedido.credentials, headers: pedido.headers, corpo: await pedido.clone().text() });
      if (rota === 'GET /saude') {
        return json(SAUDE('real'));
      }
      const responder = respostas[rota];
      return responder === undefined ? json({ title: 'Not Found', status: 404, detail: null }, 404) : responder();
    }) as typeof globalThis.fetch,
  });
  cliente.use(middlewareDaSessao(espaco, token, sessao));
  return { cliente, pedidos, sessao, token, modo: new SessaoModo() };
}

type Montado = ReturnType<typeof montarAcoes>;

async function conectar(m: Montado): Promise<void> {
  await m.modo.carregar(m.cliente);
  await m.sessao.carregar(m.cliente, m.modo);
}

const SEM_CORPO = () => new Response(null, { status: 204 });
const NA_CONTA = () => json(CONTA_DE_TESTE);
const recusa = (status: number, detail: string | null, headers: Record<string, string> = {}) => () =>
  json({ title: 'x', status, detail }, status, headers);

const CADASTRO = {
  otpauth: 'otpauth://totp/ContaAI:pessoa%40exemplo.test?secret=JBSWY3DPEHPK3PXP&issuer=ContaAI',
  segredo: 'JBSWY3DPEHPK3PXP',
  expiraEm: '2026-11-26T12:05:00Z',
  aviso: 'Leia o QR code.',
};
const CODIGOS = Array.from({ length: 10 }, (_, i) => `AAAA-BBBB-CCCC${String(i)}`);
const DADOS_DO_CADASTRO = {
  email: 'pessoa@exemplo.test',
  senha: 'uma senha longa de teste',
  organizacao: 'Organização de teste',
  termosAceitos: '2026-11-26',
} as const;
const ENTROU = () => json({ conta: CONTA_DE_TESTE, novoCodigoRecuperacao: null, aviso: null });

describe('SessaoConta: ações', () => {
  it('cadastrar devolve o segredo a quem chamou, não muda o estado e leva o cookie', async () => {
    const m = montarAcoes({ 'POST /contas': () => json(CADASTRO, 201), 'GET /conta': SEM_SESSAO });
    await conectar(m);
    const cadastro = await m.sessao.cadastrar(m.cliente, DADOS_DO_CADASTRO);
    expect(cadastro.segredo).toBe(CADASTRO.segredo);
    expect(m.sessao.obter()).toEqual({ tipo: 'anonima' });
    expect(JSON.stringify(m.sessao.obter())).not.toContain(CADASTRO.segredo);
    const pedido = m.pedidos.at(-1);
    expect(pedido?.rota).toBe('POST /contas');
    expect(pedido?.credenciais).toBe('same-origin');
    expect(JSON.parse(pedido?.corpo ?? '{}')).toEqual(DADOS_DO_CADASTRO);
  });

  it('cadastro recusado (409): o erro sobe com a frase da API', async () => {
    const m = montarAcoes({ 'POST /contas': recusa(409, 'Este e-mail já tem uma conta.'), 'GET /conta': SEM_SESSAO });
    await conectar(m);
    await expect(m.sessao.cadastrar(m.cliente, DADOS_DO_CADASTRO)).rejects.toMatchObject({
      status: 409,
      message: 'Este e-mail já tem uma conta.',
    });
    expect(m.sessao.obter().tipo).toBe('anonima');
  });

  it('ativar abre a sessão na conta e devolve os códigos, que não ficam no estado', async () => {
    const m = montarAcoes({
      'GET /conta': SEM_SESSAO,
      'POST /contas/ativar': () => json({ conta: CONTA_DE_TESTE, codigosRecuperacao: CODIGOS, aviso: 'Guarde.' }),
    });
    await conectar(m);
    const ativacao = await m.sessao.ativar(m.cliente, '123456');
    expect(ativacao).toEqual({ codigosRecuperacao: CODIGOS, aviso: 'Guarde.' });
    expect(m.sessao.obter()).toEqual({ tipo: 'conectada', conta: CONTA_DE_TESTE, naDemo: false });
    expect(JSON.stringify(m.sessao.obter())).not.toContain(CODIGOS[0]);
    expect(m.pedidos.at(-1)?.corpo).toBe('{"codigo":"123456"}');
  });

  it('código errado na ativação: o erro sobe e a tela não vira "sessão encerrada"', async () => {
    const m = montarAcoes({ 'GET /conta': SEM_SESSAO, 'POST /contas/ativar': recusa(401, 'Código incorreto.') });
    await conectar(m);
    await expect(m.sessao.ativar(m.cliente, '000000')).rejects.toMatchObject({
      status: 401,
      message: 'Código incorreto.',
    });
    expect(m.sessao.obter().tipo).toBe('anonima');
  });

  it('entrar devolve o prazo do passe sem mudar o estado; o código abre a sessão', async () => {
    const m = montarAcoes({
      'GET /conta': SEM_SESSAO,
      'POST /sessoes': () => json({ etapa: 'codigo', expiraEm: '2026-11-26T12:05:00Z' }),
      'POST /sessoes/codigo': ENTROU,
    });
    await conectar(m);
    expect(await m.sessao.entrar(m.cliente, { email: 'pessoa@exemplo.test', senha: 'x' })).toEqual({
      etapa: 'codigo',
      expiraEm: '2026-11-26T12:05:00Z',
    });
    expect(m.sessao.obter().tipo).toBe('anonima');
    expect(await m.sessao.confirmarCodigo(m.cliente, { codigo: '123456' })).toEqual({
      novoCodigoRecuperacao: null,
      aviso: null,
    });
    expect(m.sessao.naConta()).toBe(true);
  });

  it('conta pendente: a entrada devolve o QR de novo (fora do estado), e a ativação abre a sessão', async () => {
    const m = montarAcoes({
      'GET /conta': SEM_SESSAO,
      'POST /sessoes': () => json({ etapa: 'ativacao', ...CADASTRO }),
      'POST /contas/ativar': () => json({ conta: CONTA_DE_TESTE, codigosRecuperacao: CODIGOS, aviso: 'Guarde.' }),
    });
    await conectar(m);
    const passo = await m.sessao.entrar(m.cliente, { email: 'pessoa@exemplo.test', senha: 'x' });
    expect(passo).toEqual({ etapa: 'ativacao', cadastro: CADASTRO });
    expect(m.sessao.obter()).toEqual({ tipo: 'anonima' });
    expect(JSON.stringify(m.sessao.obter())).not.toContain(CADASTRO.segredo);
    await m.sessao.ativar(m.cliente, '123456');
    expect(m.sessao.naConta()).toBe(true);
  });

  it('senha errada (401 no POST /sessoes): o erro sobe e o estado não muda', async () => {
    const m = montarAcoes({ 'GET /conta': SEM_SESSAO, 'POST /sessoes': recusa(401, 'E-mail ou senha incorretos.') });
    await conectar(m);
    await expect(m.sessao.entrar(m.cliente, { email: 'a@b.test', senha: 'x' })).rejects.toMatchObject({ status: 401 });
    expect(m.sessao.obter().tipo).toBe('anonima');
  });

  it('com um código de recuperação, devolve o código novo (fora do estado)', async () => {
    const m = montarAcoes({
      'GET /conta': SEM_SESSAO,
      'POST /sessoes/codigo': () =>
        json({ conta: CONTA_DE_TESTE, novoCodigoRecuperacao: 'NOVO-CODI-GO234', aviso: 'Guarde o novo.' }),
    });
    await conectar(m);
    const entrada = await m.sessao.confirmarCodigo(m.cliente, { codigoRecuperacao: 'AAAA-BBBB-CCCC2' });
    expect(entrada).toEqual({ novoCodigoRecuperacao: 'NOVO-CODI-GO234', aviso: 'Guarde o novo.' });
    expect(JSON.stringify(m.sessao.obter())).not.toContain('NOVO-CODI-GO234');
    expect(m.pedidos.at(-1)?.corpo).toBe('{"codigoRecuperacao":"AAAA-BBBB-CCCC2"}');
  });

  it('o 429 sobe com a espera do Retry-After', async () => {
    const m = montarAcoes({
      'GET /conta': SEM_SESSAO,
      'POST /sessoes': recusa(429, 'Aguarde.', { 'Retry-After': '30' }),
    });
    await conectar(m);
    await expect(m.sessao.entrar(m.cliente, { email: 'a@b.test', senha: 'x' })).rejects.toMatchObject({
      status: 429,
      retryAfterS: 30,
    });
  });

  it('quem via a demonstração e entra de novo passa a ver a conta; o token da demo não vai às rotas da conta', async () => {
    const m = montarAcoes({ 'GET /conta': NA_CONTA, 'POST /sessoes/codigo': ENTROU });
    await conectar(m);
    m.sessao.verDemonstracao();
    m.token.definir('token-da-demo');
    await m.sessao.confirmarCodigo(m.cliente, { codigo: '123456' });
    expect(m.sessao.obter()).toMatchObject({ tipo: 'conectada', naDemo: false });
    const pedido = m.pedidos.at(-1);
    expect(pedido?.headers.has('X-ContaAI-Token')).toBe(false);
    expect(pedido?.headers.has('X-ContaAI-Espaco')).toBe(false);
  });

  it('sair: a sessão termina sem o aviso de "encerrada", e o pedido leva o cookie', async () => {
    const m = montarAcoes({ 'GET /conta': NA_CONTA, 'DELETE /sessoes/atual': SEM_CORPO });
    await conectar(m);
    await m.sessao.sair(m.cliente);
    expect(m.sessao.obter()).toEqual({ tipo: 'anonima' });
    expect(m.pedidos.at(-1)?.credenciais).toBe('same-origin');
  });

  it('sair com a API fora do ar: o estado não muda (a sessão pode seguir aberta no servidor) e o erro sobe', async () => {
    const m = montarAcoes({ 'GET /conta': NA_CONTA, 'DELETE /sessoes/atual': recusa(503, null) });
    await conectar(m);
    await expect(m.sessao.sair(m.cliente)).rejects.toMatchObject({ status: 503 });
    expect(m.sessao.naConta()).toBe(true);
  });

  it('sair de todos: 204 ou 401 (já tinha acabado) dão no mesmo', async () => {
    for (const responder of [SEM_CORPO, SEM_SESSAO]) {
      const m = montarAcoes({ 'GET /conta': NA_CONTA, 'DELETE /sessoes': responder });
      await conectar(m);
      await m.sessao.sairDeTodos(m.cliente);
      expect(m.sessao.obter()).toEqual({ tipo: 'anonima' });
    }
  });

  it('sair de todos com outro erro: o erro sobe e a conta continua', async () => {
    const m = montarAcoes({ 'GET /conta': NA_CONTA, 'DELETE /sessoes': recusa(500, null) });
    await conectar(m);
    await expect(m.sessao.sairDeTodos(m.cliente)).rejects.toMatchObject({ status: 500 });
    expect(m.sessao.naConta()).toBe(true);
  });

  it('excluir: 204 fecha a sessão; a senha só vai no corpo', async () => {
    const m = montarAcoes({ 'GET /conta': NA_CONTA, 'POST /conta/excluir': SEM_CORPO });
    await conectar(m);
    await m.sessao.excluir(m.cliente, 'a senha certa');
    expect(m.sessao.obter()).toEqual({ tipo: 'anonima' });
    const pedido = m.pedidos.at(-1);
    expect(pedido?.rota).toBe('POST /conta/excluir');
    expect(pedido?.corpo).toBe('{"senha":"a senha certa"}');
    expect(m.pedidos.some((p) => p.rota.includes('senha'))).toBe(false);
  });

  it('excluir com a senha errada: o erro sobe e a conta continua', async () => {
    const m = montarAcoes({ 'GET /conta': NA_CONTA, 'POST /conta/excluir': recusa(401, 'Senha incorreta.') });
    await conectar(m);
    await expect(m.sessao.excluir(m.cliente, 'errada')).rejects.toMatchObject({ status: 401 });
    expect(m.sessao.naConta()).toBe(true);
  });

  it('excluir com a sessão já vencida (401 nos dois): vira "encerrada"', async () => {
    let conectada = true;
    const m = montarAcoes({
      'GET /conta': () => (conectada ? json(CONTA_DE_TESTE) : SEM_SESSAO()),
      'POST /conta/excluir': recusa(401, 'Entre com a sua conta.'),
    });
    await conectar(m);
    conectada = false;
    await expect(m.sessao.excluir(m.cliente, 'qualquer')).rejects.toMatchObject({ status: 401 });
    expect(m.sessao.obter().tipo).toBe('encerrada');
  });

  it('excluir com 409 (a posse da organização): a conta continua', async () => {
    const m = montarAcoes({ 'GET /conta': NA_CONTA, 'POST /conta/excluir': recusa(409, 'Passe a posse.') });
    await conectar(m);
    await expect(m.sessao.excluir(m.cliente, 'certa')).rejects.toMatchObject({ status: 409 });
    expect(m.sessao.naConta()).toBe(true);
  });

  it('um GET /conta que sai antes de entrar e chega depois não desfaz a entrada', async () => {
    const m = montarAcoes({ 'GET /conta': SEM_SESSAO, 'POST /sessoes/codigo': ENTROU });
    await conectar(m);
    let liberar: (r: Response) => void = () => undefined;
    const lento = new Promise<Response>((resolver) => {
      liberar = resolver;
    });
    const clienteLento = criarCliente({ baseUrl: 'http://api.teste', fetch: () => lento });
    const consulta = m.sessao.carregar(clienteLento, m.modo);
    await m.sessao.confirmarCodigo(m.cliente, { codigo: '123456' });
    liberar(SEM_SESSAO());
    await consulta;
    expect(m.sessao.obter()).toMatchObject({ tipo: 'conectada', naDemo: false });
  });

  it('nenhuma ação grava no armazenamento do navegador', async () => {
    const gravados: string[] = [];
    const armazenamento = { setItem: (chave: string) => gravados.push(chave), getItem: () => null };
    Object.defineProperty(globalThis, 'localStorage', { value: armazenamento, configurable: true });
    Object.defineProperty(globalThis, 'sessionStorage', { value: armazenamento, configurable: true });
    try {
      const m = montarAcoes({
        'GET /conta': SEM_SESSAO,
        'POST /contas': () => json(CADASTRO, 201),
        'POST /contas/ativar': () => json({ conta: CONTA_DE_TESTE, codigosRecuperacao: CODIGOS, aviso: 'Guarde.' }),
        'DELETE /sessoes/atual': SEM_CORPO,
      });
      await conectar(m);
      await m.sessao.cadastrar(m.cliente, DADOS_DO_CADASTRO);
      await m.sessao.ativar(m.cliente, '123456');
      await m.sessao.sair(m.cliente);
      expect(gravados).toEqual([]);
    } finally {
      Reflect.deleteProperty(globalThis, 'localStorage');
      Reflect.deleteProperty(globalThis, 'sessionStorage');
    }
  });
});
