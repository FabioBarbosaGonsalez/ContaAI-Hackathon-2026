// @vitest-environment node
// O cliente não usa DOM. No ambiente Node, Request, Response e AbortSignal são os do próprio Node,
// como os do navegador.
import { describe, expect, it, vi } from 'vitest';
import { CABECALHO_MOCK, chamar, criarCliente } from './cliente.ts';
import { ErroApi } from './problema.ts';

const BASE = 'http://127.0.0.1:8000';

function json(corpo: unknown, status = 200, headers: Record<string, string> = {}): Response {
  const tipo = status >= 400 ? 'application/problem+json' : 'application/json';
  return new Response(JSON.stringify(corpo), { status, headers: { 'Content-Type': tipo, ...headers } });
}

const SAUDE = { status: 'ok', modo: 'mock', motores: [] };

function clienteCom(resposta: (pedido: Request) => Response | Promise<Response>, tempoLimiteMs?: number) {
  const pedidos: Request[] = [];
  const fetch = vi.fn(async (pedido: Request) => {
    pedidos.push(pedido);
    return resposta(pedido);
  });
  const cliente = criarCliente({
    baseUrl: BASE,
    fetch: fetch as unknown as typeof globalThis.fetch,
    ...(tempoLimiteMs === undefined ? {} : { tempoLimiteMs }),
  });
  return { cliente, fetch, pedidos };
}

async function erroDe(promessa: Promise<unknown>): Promise<ErroApi> {
  try {
    await promessa;
  } catch (erro) {
    if (erro instanceof ErroApi) {
      return erro;
    }
    throw erro;
  }
  throw new Error('esperava ErroApi');
}

describe('criarCliente', () => {
  it('envia sem credenciais, sem Referer, sem cache e recusando redirecionamento', async () => {
    const { cliente, pedidos } = clienteCom(() => json(SAUDE));
    await chamar(cliente.GET('/saude'));

    const pedido = pedidos[0];
    expect(pedido?.url).toBe(`${BASE}/saude`);
    expect(pedido?.credentials).toBe('omit');
    expect(pedido?.redirect).toBe('error');
    expect(pedido?.cache).toBe('no-store');
    expect(pedido?.referrerPolicy).toBe('no-referrer');
    expect(pedido?.headers.get('Accept')).toContain('application/problem+json');
  });

  it('codifica parâmetros de consulta', async () => {
    const { cliente, pedidos } = clienteCom(() => json([]));
    await chamar(cliente.GET('/busca/ncm', { params: { query: { q: 'a&b=c d' } } }));
    expect(pedidos[0]?.url).toBe(`${BASE}/busca/ncm?q=a%26b%3Dc%20d`);
  });

  it.each(['..', '.', 'a/b', '../saude', '', 'x?y'])(
    'recusa o parâmetro de caminho %j sem enviar nada',
    async (itemId) => {
      const { cliente, fetch } = clienteCom(() => json({}));
      const erro = await erroDe(chamar(cliente.GET('/explicar/{item_id}', { params: { path: { item_id: itemId } } })));
      expect(erro.tipo).toBe('entrada');
      expect(fetch).not.toHaveBeenCalled();
    },
  );

  it('aceita os ids no padrão do contrato', async () => {
    const { cliente, pedidos } = clienteCom(() => json({}));
    await chamar(cliente.GET('/explicar/{item_id}', { params: { path: { item_id: 'arroz-5kg' } } }));
    await chamar(cliente.POST('/alertas/{alerta_id}/aplicar', { params: { path: { alerta_id: 'alerta-0123456789abcdef' } } }));
    expect(pedidos.map((p) => new URL(p.url).pathname)).toEqual([
      '/explicar/arroz-5kg',
      '/alertas/alerta-0123456789abcdef/aplicar',
    ]);
  });
});

describe('chamar', () => {
  it('devolve os dados e diz se vieram dos mocks', async () => {
    const comMock = clienteCom(() => json(SAUDE, 200, { [CABECALHO_MOCK]: '1' }));
    await expect(chamar(comMock.cliente.GET('/saude'))).resolves.toEqual({ dados: SAUDE, mock: true });

    const real = clienteCom(() => json(SAUDE));
    await expect(chamar(real.cliente.GET('/saude'))).resolves.toEqual({ dados: SAUDE, mock: false });
  });

  it('erro da API vira ErroApi com o problema e o corpo', async () => {
    const corpo = {
      type: '/problemas/entrada-invalida',
      title: 'Entrada inválida',
      status: 422,
      detail: 'A requisição não passou na validação.',
      campos: [{ origem: 'query', campo: '#', detalhe: 'obrigatório' }],
    };
    const { cliente } = clienteCom(() => json(corpo, 422));
    const erro = await erroDe(chamar(cliente.GET('/busca/ncm', { params: { query: { q: 'ar' } } })));

    expect(erro.tipo).toBe('resposta');
    expect(erro.status).toBe(422);
    expect(erro.message).toBe('A requisição não passou na validação.');
    expect(erro.problema?.type).toBe('/problemas/entrada-invalida');
    expect(erro.corpo).toEqual(corpo);
  });

  it('corpo de erro fora do formato não chega à mensagem', async () => {
    const html = '<html><body><script>alert(1)</script>Bad Gateway</body></html>';
    const { cliente } = clienteCom(() => new Response(html, { status: 502, headers: { 'Content-Type': 'text/html' } }));
    const erro = await erroDe(chamar(cliente.GET('/saude')));

    expect(erro.tipo).toBe('resposta');
    expect(erro.status).toBe(502);
    expect(erro.message).toBe('Um motor oficial respondeu de forma inesperada.');
    expect(erro.corpo).toBeUndefined();
  });

  it('erro sem corpo usa a frase do status', async () => {
    const { cliente } = clienteCom(() => new Response(null, { status: 503, headers: { 'Content-Length': '0' } }));
    const erro = await erroDe(chamar(cliente.GET('/saude')));
    expect(erro.status).toBe(503);
    expect(erro.message).toBe('O serviço está indisponível no momento.');
  });

  it('lê o Retry-After do 429', async () => {
    const { cliente } = clienteCom(() =>
      json({ title: 'Too Many Requests', status: 429 }, 429, { 'Retry-After': '42' }),
    );
    const erro = await erroDe(chamar(cliente.GET('/saude')));
    expect(erro.retryAfterS).toBe(42);
  });

  it('falha de rede vira tipo rede', async () => {
    const { cliente } = clienteCom(() => {
      throw new TypeError('Failed to fetch');
    });
    const erro = await erroDe(chamar(cliente.GET('/saude')));
    expect(erro.tipo).toBe('rede');
    expect(erro.status).toBeNull();
  });

  it('passou do tempo limite vira tipo tempo', async () => {
    const { cliente } = clienteCom(
      (pedido) =>
        new Promise<Response>((_resolver, rejeitar) => {
          pedido.signal.addEventListener('abort', () => {
            const motivo: unknown = pedido.signal.reason;
            rejeitar(motivo instanceof Error ? motivo : new Error('abortado'));
          });
        }),
      20,
    );
    const erro = await erroDe(chamar(cliente.GET('/saude')));
    expect(erro.tipo).toBe('tempo');
  });

  it('cancelamento de quem chamou vira tipo cancelado', async () => {
    const controle = new AbortController();
    const { cliente } = clienteCom(
      (pedido) =>
        new Promise<Response>((_resolver, rejeitar) => {
          pedido.signal.addEventListener('abort', () => {
            const motivo: unknown = pedido.signal.reason;
            rejeitar(motivo instanceof Error ? motivo : new Error('abortado'));
          });
          controle.abort();
        }),
    );
    const erro = await erroDe(chamar(cliente.GET('/saude', { signal: controle.signal })));
    expect(erro.tipo).toBe('cancelado');
  });

  it('2xx com corpo que não é JSON vira tipo formato', async () => {
    const { cliente } = clienteCom(() => new Response('<html>oi</html>', { status: 200 }));
    const erro = await erroDe(chamar(cliente.GET('/saude')));
    expect(erro.tipo).toBe('formato');
  });
});

describe('tipos gerados do contrato', () => {
  it('recusam rota e parâmetro fora do contrato na checagem de tipos', () => {
    const { cliente } = clienteCom(() => json({}));
    // Estas linhas só existem para o tsc: se o contrato aceitasse, o @ts-expect-error falharia.
    const nuncaChamar = () => {
      // @ts-expect-error rota inexistente
      void cliente.GET('/rota-inexistente');
      // @ts-expect-error cnpj é obrigatório em GET /catalogo
      void cliente.GET('/catalogo', { params: { query: {} } });
    };
    expect(typeof nuncaChamar).toBe('function');
  });
});
