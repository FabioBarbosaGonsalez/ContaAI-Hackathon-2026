// @vitest-environment node
import { describe, expect, it } from 'vitest';
import { CABECALHO_ESPACO, CABECALHO_TOKEN, chamar, criarCliente } from '../api/cliente.ts';
import { ErroApi } from '../api/problema.ts';
import { criarEspaco, verificarEspaco } from './acoes.ts';
import { SessaoEspaco } from './espaco.ts';
import { PROBLEMA_ESPACO_INEXISTENTE, middlewareDaSessao } from './middleware.ts';
import { SessaoToken } from './token.ts';

const ID = '0123456789abcdef0123456789abcdef';
const OUTRO_ID = 'fedcba9876543210fedcba9876543210';
const CNPJ = '36817420000113';

function json(corpo: unknown, status = 200): Response {
  return new Response(JSON.stringify(corpo), { status, headers: { 'Content-Type': 'application/json' } });
}

function montar(resposta: (pedido: Request) => Response = () => json({})) {
  const pedidos: Request[] = [];
  const espaco = new SessaoEspaco({ armazenamento: null });
  const token = new SessaoToken();
  const cliente = criarCliente({
    baseUrl: 'http://api.teste',
    fetch: ((pedido: Request) => {
      pedidos.push(pedido);
      return Promise.resolve(resposta(pedido));
    }) as typeof globalThis.fetch,
  });
  cliente.use(middlewareDaSessao(espaco, token));
  return { cliente, espaco, token, pedidos };
}

async function semFalha(promessa: Promise<unknown>): Promise<void> {
  await promessa.catch(() => undefined);
}

describe('middlewareDaSessao', () => {
  it('põe o espaço e o token só nas rotas que os declaram', async () => {
    const { cliente, espaco, token, pedidos } = montar();
    espaco.ativar({ id: ID, expiraEm: Date.now() + 60_000 });
    token.definir('token-da-demo');

    await chamar(cliente.GET('/catalogo', { params: { query: { cnpj: CNPJ } } }));
    await chamar(cliente.POST('/catalogo/{item_id}/preco', { params: { path: { item_id: 'cerveja' } }, body: { preco: '3.97' } as never }));
    await chamar(cliente.GET('/saude'));
    await chamar(cliente.GET('/busca/ncm', { params: { query: { q: 'arroz' } } }));
    await chamar(cliente.POST('/espacos'));

    const headers = pedidos.map((p) => [p.headers.get(CABECALHO_ESPACO), p.headers.get(CABECALHO_TOKEN)]);
    expect(headers).toEqual([
      [ID, null], // GET /catalogo: espaço, sem token
      [ID, 'token-da-demo'], // POST de estado: os dois
      [null, null], // /saude
      [null, null], // /busca/ncm
      [null, null], // POST /espacos: nem o espaço velho nem o token
    ]);
  });

  it('sem espaço ativo, não manda o header (vale a demonstração compartilhada)', async () => {
    const { cliente, pedidos } = montar();
    await chamar(cliente.GET('/contador/painel'));
    expect(pedidos[0]?.headers.has(CABECALHO_ESPACO)).toBe(false);
  });

  it('o espaço que vence some da sessão no 404 espaco-inexistente', async () => {
    const { cliente, espaco } = montar(() =>
      json({ type: PROBLEMA_ESPACO_INEXISTENTE, title: 'Espaço inexistente', status: 404, detail: 'Crie outro.' }, 404),
    );
    espaco.ativar({ id: ID, expiraEm: Date.now() + 60_000 });

    const erro = await chamar(cliente.GET('/contador/painel')).catch((e: unknown) => e);
    expect(erro).toBeInstanceOf(ErroApi);
    expect(espaco.obter()).toEqual({ tipo: 'expirado' });
  });

  it('outro 404 não mexe no espaço', async () => {
    const { cliente, espaco } = montar(() => json({ type: 'about:blank', title: 'Not Found', status: 404 }, 404));
    espaco.ativar({ id: ID, expiraEm: Date.now() + 60_000 });
    await semFalha(chamar(cliente.GET('/catalogo', { params: { query: { cnpj: CNPJ } } })));
    expect(espaco.idAtual()).toBe(ID);
  });

  it('o 404 de um espaço antigo não apaga o espaço novo', async () => {
    let liberar: () => void = () => undefined;
    const portao = new Promise<void>((resolver) => {
      liberar = resolver;
    });
    let enviou: () => void = () => undefined;
    const saiu = new Promise<void>((resolver) => {
      enviou = resolver;
    });
    const pedidos: Request[] = [];
    const espaco = new SessaoEspaco({ armazenamento: null });
    const cliente = criarCliente({
      baseUrl: 'http://api.teste',
      fetch: (async (pedido: Request) => {
        pedidos.push(pedido);
        enviou();
        await portao;
        return json({ type: PROBLEMA_ESPACO_INEXISTENTE, title: 'Espaço inexistente', status: 404 }, 404);
      }) as typeof globalThis.fetch,
    });
    cliente.use(middlewareDaSessao(espaco, new SessaoToken()));

    espaco.ativar({ id: ID, expiraEm: Date.now() + 60_000 });
    const pedido = chamar(cliente.GET('/contador/painel'));
    await saiu;
    expect(pedidos[0]?.headers.get(CABECALHO_ESPACO)).toBe(ID);

    // Enquanto a resposta do espaço antigo não chega, a pessoa cria outro espaço.
    espaco.ativar({ id: OUTRO_ID, expiraEm: Date.now() + 60_000 });
    liberar();
    await semFalha(pedido);
    expect(espaco.idAtual()).toBe(OUTRO_ID);
  });

  it('401 com token apaga o token; 401 sem token não mexe', async () => {
    const { cliente, token } = montar(() => json({ title: 'Unauthorized', status: 401 }, 401));
    await semFalha(chamar(cliente.POST('/chat', { body: { mensagem: 'oi' } as never })));
    expect(token.temToken()).toBe(false);

    token.definir('errado');
    await semFalha(chamar(cliente.POST('/chat', { body: { mensagem: 'oi' } as never })));
    expect(token.temToken()).toBe(false);
  });
});

describe('ações do espaço', () => {
  it('criarEspaco ativa o espaço e devolve o aviso da API', async () => {
    const { cliente, espaco, pedidos } = montar(() =>
      json(
        { id: ID, criadoEm: '2026-11-25T12:00:00Z', expiraEm: '2026-11-25T14:00:00Z', aviso: 'Dados fictícios.' },
        201,
      ),
    );
    const antes = Date.now();
    await expect(criarEspaco(cliente, espaco)).resolves.toBe('Dados fictícios.');
    const estado = espaco.obter();
    expect(estado.tipo).toBe('ativo');
    if (estado.tipo === 'ativo') {
      expect(estado.espaco.expiraEm - antes).toBeGreaterThanOrEqual(120 * 60_000);
      expect(estado.espaco.expiraEm - Date.now()).toBeLessThanOrEqual(120 * 60_000);
    }
    expect(new URL(pedidos[0]?.url ?? '').pathname).toBe('/espacos');
  });

  it('criarEspaco recusa resposta com id fora do contrato', async () => {
    const { cliente, espaco } = montar(() =>
      json({ id: '../x', criadoEm: '2026-11-25T12:00:00Z', expiraEm: '2026-11-25T14:00:00Z', aviso: '' }, 201),
    );
    const erro = await criarEspaco(cliente, espaco).catch((e: unknown) => e);
    expect(erro).toBeInstanceOf(ErroApi);
    expect((erro as ErroApi).tipo).toBe('formato');
    expect(espaco.obter()).toEqual({ tipo: 'ausente' });
  });

  it('criarEspaco no modo mock (501) não mexe na sessão', async () => {
    const { cliente, espaco } = montar(() => json({ title: 'Not Implemented', status: 501 }, 501));
    const erro = await criarEspaco(cliente, espaco).catch((e: unknown) => e);
    expect((erro as ErroApi).status).toBe(501);
    expect(espaco.obter()).toEqual({ tipo: 'ausente' });
  });

  it('verificarEspaco não chama a API sem espaço, e confere o espaço ativo sem esticar o prazo', async () => {
    const { cliente, espaco, pedidos } = montar(() =>
      json({ id: ID, criadoEm: '2026-11-25T12:00:00Z', expiraEm: '2026-11-25T14:00:00Z', aviso: '' }),
    );
    await verificarEspaco(cliente, espaco);
    expect(pedidos).toHaveLength(0);

    const expiraEm = Date.now() + 5 * 60_000;
    espaco.ativar({ id: ID, expiraEm });
    await verificarEspaco(cliente, espaco);
    expect(pedidos[0]?.headers.get(CABECALHO_ESPACO)).toBe(ID);
    expect(espaco.obter()).toEqual({ tipo: 'ativo', espaco: { id: ID, expiraEm } });
  });
});
