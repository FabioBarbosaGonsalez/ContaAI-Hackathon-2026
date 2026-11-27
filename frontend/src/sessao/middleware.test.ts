// @vitest-environment node
import { describe, expect, it } from 'vitest';
import { CABECALHO_ESPACO, CABECALHO_TOKEN, chamar, criarCliente } from '../api/cliente.ts';
import { ErroApi } from '../api/problema.ts';
import { criarEspaco, verificarEspaco } from './acoes.ts';
import { CONTA_DE_TESTE as CONTA } from '../teste/sessaoDeTeste.ts';
import { SessaoConta } from './conta.ts';
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
  const conta = new SessaoConta();
  const cliente = criarCliente({
    baseUrl: 'http://api.teste',
    fetch: ((pedido: Request) => {
      pedidos.push(pedido);
      return Promise.resolve(resposta(pedido));
    }) as typeof globalThis.fetch,
  });
  cliente.use(middlewareDaSessao(espaco, token, conta));
  return { cliente, espaco, token, conta, pedidos };
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
    cliente.use(middlewareDaSessao(espaco, new SessaoToken(), new SessaoConta()));

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


/** Põe a sessão da conta no estado conectado, como o GET /conta faria. */
async function conectar(conta: SessaoConta): Promise<void> {
  const cliente = criarCliente({ baseUrl: 'http://api.teste', fetch: () => Promise.resolve(json(CONTA)) });
  const modo = { espacoDisponivel: () => true } as unknown as Parameters<SessaoConta['carregar']>[1];
  await conta.carregar(cliente, modo);
}

describe('middlewareDaSessao e a conta (ADR 0016)', () => {
  it('sem conta, os pedidos de dados saem sem o cookie, e as rotas da conta o levam', async () => {
    const { cliente, pedidos } = montar();
    await semFalha(chamar(cliente.GET('/catalogo', { params: { query: { cnpj: CNPJ } } })));
    await semFalha(chamar(cliente.GET('/conta')));
    await semFalha(chamar(cliente.POST('/sessoes', { body: { email: 'a@b.test', senha: 'x' } })));
    expect(pedidos.map((p) => p.credentials)).toEqual(['omit', 'same-origin', 'same-origin']);
  });

  it('na conta, os pedidos de dados levam o cookie e nem o espaço nem o token', async () => {
    const { cliente, espaco, token, conta, pedidos } = montar();
    espaco.ativar({ id: ID, expiraEm: Date.now() + 60_000 });
    token.definir('token-da-demo');
    await conectar(conta);
    await semFalha(chamar(cliente.GET('/catalogo', { params: { query: { cnpj: CNPJ } } })));
    await semFalha(chamar(cliente.POST('/chat', { body: { mensagem: 'oi' } as never })));
    expect(pedidos.map((p) => p.credentials)).toEqual(['same-origin', 'same-origin']);
    expect(pedidos.map((p) => p.headers.get(CABECALHO_ESPACO))).toEqual([null, null]);
    expect(pedidos.map((p) => p.headers.get(CABECALHO_TOKEN))).toEqual([null, null]);
  });

  it('com a conta vendo a demonstração, volta a ser como quem não tem conta', async () => {
    const { cliente, espaco, conta, pedidos } = montar();
    espaco.ativar({ id: ID, expiraEm: Date.now() + 60_000 });
    await conectar(conta);
    conta.verDemonstracao();
    await semFalha(chamar(cliente.GET('/catalogo', { params: { query: { cnpj: CNPJ } } })));
    expect(pedidos[0]?.credentials).toBe('omit');
    expect(pedidos[0]?.headers.get(CABECALHO_ESPACO)).toBe(ID);
    expect(conta.obter()).toMatchObject({ tipo: 'conectada', naDemo: true });
  });

  it('o corpo do POST passa inteiro pela cópia sem cookie', async () => {
    const { cliente, pedidos } = montar();
    await semFalha(chamar(cliente.POST('/carrinho/calcular', { body: { itens: [] } as never })));
    expect(pedidos[0]?.credentials).toBe('omit');
    expect(await pedidos[0]?.text()).toBe('{"itens":[]}');
  });

  it('401 com o cookie numa rota de dados encerra a sessão', async () => {
    const { cliente, conta } = montar(() => json({ title: 'x', status: 401, detail: 'Entre com a sua conta.' }, 401));
    await conectar(conta);
    await semFalha(chamar(cliente.GET('/catalogo', { params: { query: { cnpj: CNPJ } } })));
    expect(conta.obter().tipo).toBe('encerrada');
  });

  it('401 numa rota de entrada (senha ou código errado) não encerra a sessão', async () => {
    const { cliente, conta } = montar(() => json({ title: 'x', status: 401, detail: 'E-mail, senha ou código incorretos.' }, 401));
    await conectar(conta);
    await semFalha(chamar(cliente.POST('/conta/excluir', { body: { senha: 'errada' } })));
    expect(conta.obter().tipo).toBe('conectada');
  });

  it('as rotas da empresa da conta levam o cookie mesmo com a conta vendo a demonstração, sem o espaço (ADR 0018)', async () => {
    const { cliente, espaco, token, conta, pedidos } = montar();
    espaco.ativar({ id: ID, expiraEm: Date.now() + 60_000 });
    token.definir('token-da-demo');
    await conectar(conta);
    conta.verDemonstracao();
    await semFalha(chamar(cliente.GET('/empresas/{cnpj}', { params: { path: { cnpj: CNPJ } } })));
    await semFalha(chamar(cliente.GET('/referencias/ufs')));
    expect(pedidos.map((p) => p.credentials)).toEqual(['same-origin', 'omit']);
    expect(pedidos[0]?.headers.get(CABECALHO_ESPACO)).toBeNull();
    expect(pedidos[0]?.headers.get(CABECALHO_TOKEN)).toBeNull();
  });

  it('401 no cadastro da empresa encerra a sessão; ao excluir a empresa, o 401 é a senha e não encerra', async () => {
    const recusa = () => json({ title: 'x', status: 401, detail: 'Entre com a sua conta.' }, 401);
    const cadastro = montar(recusa);
    await conectar(cadastro.conta);
    await semFalha(
      chamar(
        cadastro.cliente.POST('/empresas', {
          body: { cnpj: '12ABC34501DE35', razaoSocial: 'X', regimeAtual: 'simples_tradicional', uf: 'SP', municipio: 3550308, cAtivSN: '01' }, // taste-skill-ignore: código oficial da atividade do Simples (cAtivSN), não é numeração
        }),
      ),
    );
    expect(cadastro.conta.obter().tipo).toBe('encerrada');

    const exclusao = montar(recusa);
    await conectar(exclusao.conta);
    await semFalha(
      chamar(
        exclusao.cliente.POST('/empresas/{cnpj}/excluir', {
          params: { path: { cnpj: '12ABC34501DE35' } },
          body: { senha: 'errada', cnpjConfirmacao: '12ABC34501DE35' },
        }),
      ),
    );
    expect(exclusao.conta.obter().tipo).toBe('conectada');
  });

  it('401 de um pedido sem cookie (na demonstração) não mexe na conta', async () => {
    const { cliente, conta } = montar(() => json({ title: 'x', status: 401, detail: 'Token' }, 401));
    await conectar(conta);
    conta.verDemonstracao();
    await semFalha(chamar(cliente.GET('/catalogo', { params: { query: { cnpj: CNPJ } } })));
    expect(conta.obter()).toMatchObject({ tipo: 'conectada', naDemo: true });
  });
});
