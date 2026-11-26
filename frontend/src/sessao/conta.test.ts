// @vitest-environment node
import { describe, expect, it } from 'vitest';
import { criarCliente } from '../api/cliente.ts';
import { CONTA_DE_TESTE } from '../teste/sessaoDeTeste.ts';
import { SessaoConta } from './conta.ts';
import { SessaoModo } from './modo.ts';

function json(corpo: unknown, status = 200): Response {
  const tipo = status >= 400 ? 'application/problem+json' : 'application/json';
  return new Response(JSON.stringify(corpo), { status, headers: { 'Content-Type': tipo } });
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
