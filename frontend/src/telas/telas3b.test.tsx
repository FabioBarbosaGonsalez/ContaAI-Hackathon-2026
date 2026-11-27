// Telas do PR 3b (Notas e Regime) com respostas reais gravadas da API (src/teste/fixtures: modo real, motores
// RR 1.7.2 e SN 1.0.2, num espaço de avaliação com a nota 2 da demonstração importada e, para a lista, a nota
// do item sem par). O fetch é falso: os testes conferem o que a tela pede e o que ela mostra.

import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from '../App.tsx';
import { CABECALHO_ESPACO, CABECALHO_TOKEN } from '../api/cliente.ts';
import { pedidoDeRegime, type Catalogo, type Comparacao, type ReciboNota } from '../dados/pedidos.ts';
import { reiniciarFocoDePagina } from '../shell/Pagina.tsx';
import alertas from '../teste/fixtures/alertas.json';
import catalogoGravado from '../teste/fixtures/catalogo.json';
import erroNaoENfe from '../teste/fixtures/erro-nao-e-nfe.json';
import erroNotaRepetida from '../teste/fixtures/erro-nota-repetida.json';
import reciboDeNovo from '../teste/fixtures/nfe-importar-2-de-novo.json';
import reciboNota2 from '../teste/fixtures/nfe-importar-2.json';
import reciboSemPar from '../teste/fixtures/nfe-importar-sem-par.json';
import notas from '../teste/fixtures/notas.json';
import regimeComparar from '../teste/fixtures/regime-comparar.json';
import { SAUDE_MOCK, SAUDE_REAL, json, sessaoDeTeste } from '../teste/sessaoDeTeste.ts';
import { achadoDoRecibo } from './Notas.tsx';
import { achadoDoRegime } from './Regime.tsx';

const catalogo = catalogoGravado as Catalogo;
const comparacao = regimeComparar as Comparacao;
const ID_ESPACO = '0123456789abcdef0123456789abcdef';

beforeAll(() => {
  HTMLDialogElement.prototype.showModal = function showModal(this: HTMLDialogElement) {
    this.setAttribute('open', '');
  };
  HTMLDialogElement.prototype.close = function close(this: HTMLDialogElement) {
    this.removeAttribute('open');
    this.dispatchEvent(new Event('close'));
  };
  globalThis.scrollTo = vi.fn();
});

beforeEach(() => {
  reiniciarFocoDePagina();
});

afterEach(cleanup);

type Rota = (pedido: Request) => Response | Promise<Response> | undefined;

/** A API falsa: responde com as fixtures; `extra` troca a resposta de uma rota. */
function api(saude: object, extra: Rota = () => undefined, dados: { catalogo?: object } = {}) {
  return async (pedido: Request): Promise<Response> => {
    const especial = await extra(pedido);
    if (especial) {
      return especial;
    }
    const url = new URL(pedido.url);
    switch (`${pedido.method} ${url.pathname}`) {
      case 'GET /saude':
        return json(saude);
      case 'GET /catalogo':
        return json(dados.catalogo ?? catalogo);
      case 'GET /alertas':
        return json(alertas);
      case 'GET /notas':
        return json(notas);
      case 'POST /regime/comparar':
        return json(comparacao);
      case 'POST /nfe/importar':
        return json(reciboNota2);
      default:
        return json({ type: 'about:blank', title: 'Not Found', status: 404 }, 404);
    }
  };
}

async function montar(caminho: string, responder: (p: Request) => Promise<Response>, comToken = false) {
  history.replaceState(null, '', caminho);
  const sessao = sessaoDeTeste(responder);
  if (comToken) {
    sessao.token.definir('token-de-teste');
  }
  render(<App sessao={sessao} />);
  await act(() => sessao.modo.carregar(sessao.api));
  return sessao;
}

const pedidosA = (sessao: { pedidos: Request[] }, metodo: string, caminho: string) =>
  sessao.pedidos.filter((p) => p.method === metodo && new URL(p.url).pathname === caminho);

function arquivoXml(nome = 'nfe-compra-2.xml', conteudo = '<NFe/>', tipo = 'text/xml'): File {
  return new File([conteudo], nome, { type: tipo });
}

async function escolherArquivo(arquivo: File) {
  const campo = await screen.findByLabelText('Arquivo XML da NF-e');
  fireEvent.change(campo, { target: { files: [arquivo] } });
}

// ---------------------------------------------------------------------------
// Notas

describe('Notas', () => {
  it('lista as notas importadas na ordem da API, com as contagens de itens e de alertas', async () => {
    await montar('/notas', api(SAUDE_REAL));
    const bloco = await screen.findByRole('region', { name: 'Notas importadas' });
    const linhas = await within(bloco).findAllByRole('row');
    // cabeçalho + 3 notas, da emissão mais recente para a mais antiga
    expect(linhas.slice(1).map((l) => within(l).getByRole('rowheader').textContent)).toEqual([
      'Nota 1003série 1 · homologação',
      'Nota 1002série 1 · homologação',
      'Nota 1001série 1 · homologação',
    ]);
    const nota1002 = linhas[2];
    expect(nota1002 && within(nota1002).getByText('16/03/2027')).toBeDefined();
    expect(nota1002 && within(nota1002).getByText('1 aberto')).toBeDefined();
    const nota1003 = linhas[1];
    // 1 item casado e 2 sem par
    expect(nota1003 && within(nota1003).getAllByText(/^[0-9]$/u).map((c) => c.textContent)).toEqual(['1', '2', '0']);
    expect(screen.getByText('Distribuidora Serra Azul ME (fictícia)')).toBeDefined();
  });

  it('sem espaço nem token, importar fica desligado e diz por quê', async () => {
    await montar('/notas', api(SAUDE_REAL));
    const campo = await screen.findByLabelText('Arquivo XML da NF-e');
    expect((campo as HTMLInputElement).disabled).toBe(true);
    expect(screen.getByRole<HTMLButtonElement>('button', { name: 'Importar nota' }).disabled).toBe(true);
    expect(screen.getByText('Para gravar, crie seu espaço no alto da tela.')).toBeDefined();
  });

  it('no modo mock, importar é só leitura', async () => {
    await montar('/notas', api(SAUDE_MOCK));
    await screen.findByRole('button', { name: 'Importar nota' });
    expect(screen.getByText(/só leitura: nada é gravado/u)).toBeDefined();
  });

  it('oferece as três notas de exemplo para baixar, cada uma com o que ela mostra', async () => {
    await montar('/notas', api(SAUDE_REAL));
    const secao = await screen.findByRole('region', { name: 'Notas de exemplo para baixar (fictícias)' });
    const links = within(secao).getAllByRole('link');
    expect(links.map((l) => [l.textContent, l.getAttribute('download')])).toEqual([
      ['nfe-compra-2.xml', 'nfe-compra-2.xml'],
      ['nfe-item-sem-par.xml', 'nfe-item-sem-par.xml'],
      ['nfe-compra-1.xml', 'nfe-compra-1.xml'],
    ]);
    for (const link of links) {
      expect(link.getAttribute('href')?.endsWith(`/data/demo/notas/${link.textContent}`)).toBe(true);
    }
    // A frase do que a nota mostra é a descrição do link, para o leitor de tela.
    expect(links[0]?.getAttribute('aria-describedby')).not.toBeNull();
    const descricao = document.getElementById(links[0]?.getAttribute('aria-describedby') ?? '');
    expect(descricao?.textContent).toBe('A cerveja sobe de R$ 2,60 para R$ 3,05 e gera um alerta de margem.');
    // Sem espaço, importar fica desligado, mas baixar continua valendo: a pessoa baixa e cria o espaço.
    expect(screen.getByRole<HTMLButtonElement>('button', { name: 'Importar nota' }).disabled).toBe(true);
  });

  it('no modo mock, as notas de exemplo também aparecem', async () => {
    await montar('/notas', api(SAUDE_MOCK));
    const secao = await screen.findByRole('region', { name: 'Notas de exemplo para baixar (fictícias)' });
    expect(within(secao).getAllByRole('link')).toHaveLength(3);
  });

  it('o campo só oferece XML', async () => {
    await montar('/notas', api(SAUDE_REAL), true);
    const campo = await screen.findByLabelText('Arquivo XML da NF-e');
    expect(campo.getAttribute('accept')).toBe('.xml,application/xml,text/xml');
  });

  it.each([
    ['um arquivo que não é XML', arquivoXml('nota.pdf', '%PDF', 'application/pdf'), 'Escolha o arquivo XML da nota (termina em .xml).'],
    ['um arquivo vazio', arquivoXml('nota.xml', ''), 'O arquivo está vazio.'],
    [
      'um arquivo maior que 1 MB',
      arquivoXml('nota.xml', 'x'.repeat(1_000_001)),
      'O arquivo passa de 1 MB, maior que qualquer XML de NF-e de compra comum.',
    ],
  ])('recusa na hora %s, sem chamar a API', async (_caso, arquivo, motivo) => {
    const sessao = await montar('/notas', api(SAUDE_REAL), true);
    await escolherArquivo(arquivo);
    expect(screen.getByRole('alert').textContent).toBe(motivo);
    expect(screen.getByRole<HTMLButtonElement>('button', { name: 'Importar nota' }).disabled).toBe(true);
    expect(pedidosA(sessao, 'POST', '/nfe/importar')).toHaveLength(0);
  });

  it('importa com o token: o multipart leva o campo arquivo, e o recibo diz o que mudou no custo', async () => {
    const sessao = await montar('/notas', api(SAUDE_REAL), true);
    await screen.findByRole('region', { name: 'Notas importadas' });
    const antes = pedidosA(sessao, 'GET', '/notas').length;
    // No jsdom, o Request do Node não lê o conteúdo de um File do jsdom (o corpo sai vazio, com o nome "blob").
    // Por isso o teste confere o que a tela põe no FormData; o envio real foi conferido no Chrome (ADR 0014).
    const anexados: unknown[][] = [];
    const anexar = vi.spyOn(FormData.prototype, 'append').mockImplementation(function (this: FormData, ...args: unknown[]) {
      anexados.push(args);
    });
    const arquivo = arquivoXml('nfe-compra-2.xml', '<NFe>conteúdo da nota</NFe>');
    await escolherArquivo(arquivo);
    fireEvent.click(screen.getByRole('button', { name: 'Importar nota' }));

    const recibo = await screen.findByRole('region', { name: 'Recibo da nota 1002' });
    const [envio] = pedidosA(sessao, 'POST', '/nfe/importar');
    expect(envio?.headers.get(CABECALHO_TOKEN)).toBe('token-de-teste');
    expect(envio?.headers.get('Content-Type')).toMatch(/^multipart\/form-data; boundary=/u);
    anexar.mockRestore();
    expect(anexados).toEqual([['arquivo', arquivo, 'nfe-compra-2.xml']]);

    expect(
      within(recibo).getByText(
        'O custo de cerveja de malte, lata 350 ml subiu 17,31% (de R$ 2,60 para R$ 3,05), e a margem caiu para 11,19%, ' +
          'abaixo do alvo de 15,00%. Os outros 2 itens ficaram com o mesmo custo.',
      ),
    ).toBeDefined();
    expect(within(recibo).getByText('Lido do grupo IBSCBS da nota.')).toBeDefined();
    expect(within(recibo).getByText('Nota de homologação, sem valor fiscal.')).toBeDefined();
    // O crédito por unidade aparece com as 4 casas que a API manda.
    const cerveja = within(recibo).getByText('Cerveja de malte, lata 350 ml', { selector: '.tabela__nome' }).closest('tr');
    expect(cerveja && within(cerveja).getByText('R$ 0,2715')).toBeDefined();
    expect(cerveja && within(cerveja).getByText('+17,31%')).toBeDefined();
    expect(cerveja && within(cerveja).getAllByText('da nota')).toHaveLength(1);
    // A lista recarrega depois da importação.
    await waitFor(() => {
      expect(pedidosA(sessao, 'GET', '/notas').length).toBeGreaterThan(antes);
    });
  });

  it('no espaço próprio, importa sem token e com o id do espaço', async () => {
    history.replaceState(null, '', '/notas');
    const sessao = sessaoDeTeste(api(SAUDE_REAL));
    sessao.espaco.ativar({ id: ID_ESPACO, expiraEm: Date.now() + 3_600_000 });
    render(<App sessao={sessao} />);
    await act(() => sessao.modo.carregar(sessao.api));
    await escolherArquivo(arquivoXml());
    fireEvent.click(screen.getByRole('button', { name: 'Importar nota' }));
    await screen.findByRole('region', { name: 'Recibo da nota 1002' });
    const [envio] = pedidosA(sessao, 'POST', '/nfe/importar');
    expect(envio?.headers.get(CABECALHO_ESPACO)).toBe(ID_ESPACO);
    expect(envio?.headers.has(CABECALHO_TOKEN)).toBe(false);
  });

  it('aplica o preço do alerta pelo recibo e depois diz que já foi aplicado', async () => {
    let aberto = true;
    const sessao = await montar(
      '/notas',
      api(SAUDE_REAL, (pedido) => {
        const url = new URL(pedido.url);
        if (pedido.method === 'POST' && url.pathname.startsWith('/alertas/')) {
          aberto = false;
          return json({ alerta: reciboNota2.alertas[0], precoAnterior: '3.79', precoNovo: '3.97' });
        }
        if (url.pathname === '/alertas') {
          return json({ alertas: aberto ? reciboNota2.alertas : [] });
        }
        return undefined;
      }),
      true,
    );
    await escolherArquivo(arquivoXml());
    fireEvent.click(screen.getByRole('button', { name: 'Importar nota' }));
    const recibo = await screen.findByRole('region', { name: 'Recibo da nota 1002' });
    fireEvent.click(await within(recibo).findByRole('button', { name: 'Aplicar R$ 3,97' }));
    await within(recibo).findByText('Preço sugerido já aplicado.');
    const [aplicar] = pedidosA(sessao, 'POST', `/alertas/${reciboNota2.alertas[0]?.id ?? ''}/aplicar`);
    expect(aplicar?.headers.get(CABECALHO_TOKEN)).toBe('token-de-teste');
  });

  it('a mesma nota de novo mostra o recibo da primeira vez, sem gravar', async () => {
    await montar(
      '/notas',
      api(SAUDE_REAL, (p) => (p.method === 'POST' && new URL(p.url).pathname === '/nfe/importar' ? json(reciboDeNovo) : undefined)),
      true,
    );
    await escolherArquivo(arquivoXml());
    fireEvent.click(screen.getByRole('button', { name: 'Importar nota' }));
    const recibo = await screen.findByRole('region', { name: 'Recibo da nota 1002' });
    expect(within(recibo).getByRole('status').textContent).toBe(
      'Esta nota já tinha sido importada: nada foi gravado de novo. Este é o recibo da primeira vez.',
    );
  });

  it('itens sem par viram pergunta, com o motivo da API, e a nota sem o grupo IBSCBS diz de onde veio o crédito', async () => {
    await montar(
      '/notas',
      api(SAUDE_REAL, (p) => (p.method === 'POST' && new URL(p.url).pathname === '/nfe/importar' ? json(reciboSemPar) : undefined)),
      true,
    );
    await escolherArquivo(arquivoXml('nfe-item-sem-par.xml'));
    fireEvent.click(screen.getByRole('button', { name: 'Importar nota' }));
    const recibo = await screen.findByRole('region', { name: 'Recibo da nota 1003' });
    const semPar = within(recibo).getByRole('heading', { name: 'Itens que não casaram com o catálogo (2)' }).parentElement;
    expect(semPar && within(semPar).getByText('Refrigerante de cola, garrafa 2 L')).toBeDefined();
    expect(semPar && within(semPar).getByText('Código do produto deste fornecedor sem cadastro no catálogo.')).toBeDefined();
    expect(semPar && within(semPar).getByText('NCM da nota diferente da do cadastro (19053100): confira a classificação.')).toBeDefined();
    expect(within(recibo).getByText('A nota não traz o grupo IBSCBS: o crédito foi estimado sobre o custo.')).toBeDefined();
    expect(within(recibo).getByText('estimado')).toBeDefined();
    // As premissas do crédito calculado ficam junto do resultado (P6).
    expect(within(recibo).getByText('Crédito da compra sem grupo IBSCBS na nota')).toBeDefined();
    expect(within(recibo).getByText('Nenhum custo mudou com a nota 1003.')).toBeDefined();
  });

  it.each([
    ['nota repetida com outro conteúdo (409)', erroNotaRepetida, 409],
    ['arquivo que não é NF-e (422)', erroNaoENfe, 422],
    [
      'destinatário fora das empresas cadastradas (422)',
      {
        type: '/problemas/nota-recusada',
        title: 'NF-e não pode ser importada',
        status: 422,
        detail: 'O destinatário da nota não é uma empresa cadastrada no ContaAI. Nada foi gravado.',
      },
      422,
    ],
    ['arquivo maior que o limite do servidor (413)', { type: 'about:blank', title: 'Payload Too Large', status: 413, detail: 'Arquivo maior que o limite para uma NF-e.' }, 413],
    ['tipo de arquivo recusado pelo servidor (415)', { type: 'about:blank', title: 'Unsupported Media Type', status: 415, detail: 'Envie o arquivo XML da NF-e.' }, 415],
  ])('mostra a frase da API para %s, e o recibo anterior não aparece', async (_caso, problema, status) => {
    await montar(
      '/notas',
      api(SAUDE_REAL, (p) => (p.method === 'POST' && new URL(p.url).pathname === '/nfe/importar' ? json(problema, status) : undefined)),
      true,
    );
    await escolherArquivo(arquivoXml());
    fireEvent.click(screen.getByRole('button', { name: 'Importar nota' }));
    const alerta = await screen.findByRole('alert');
    expect(alerta.textContent).toBe(problema.detail);
    expect(screen.queryByRole('region', { name: /Recibo da nota/u })).toBeNull();
    // O arquivo continua escolhido: dá para tentar de novo sem escolher outra vez.
    expect(screen.getByRole<HTMLButtonElement>('button', { name: 'Importar nota' }).disabled).toBe(false);
  });

  it('um corpo de erro fora do formato nunca vai para a tela', async () => {
    await montar(
      '/notas',
      api(SAUDE_REAL, (p) =>
        p.method === 'POST' && new URL(p.url).pathname === '/nfe/importar'
          ? new Response('<html><script>alert(1)</script></html>', { status: 502, headers: { 'Content-Type': 'text/html' } })
          : undefined,
      ),
      true,
    );
    await escolherArquivo(arquivoXml());
    fireEvent.click(screen.getByRole('button', { name: 'Importar nota' }));
    expect((await screen.findByRole('alert')).textContent).toBe('Um motor oficial respondeu de forma inesperada.');
    expect(document.querySelector('script')).toBeNull();
  });

  it('a lista vazia diz que não há nota', async () => {
    await montar(
      '/notas',
      api(SAUDE_REAL, (p) => (new URL(p.url).pathname === '/notas' ? json({ ...notas, notas: [] }) : undefined)),
    );
    expect(await screen.findByText('Nenhuma nota importada ainda.')).toBeDefined();
  });
});

describe('achado do recibo', () => {
  const recibo = reciboNota2 as ReciboNota;

  it('uma nota mais antiga que o custo atual entra no histórico, sem mudar o custo', () => {
    const antiga: ReciboNota = {
      ...recibo,
      alertas: [],
      itensCasados: recibo.itensCasados.map((i) => ({ ...i, atualizaCusto: false })),
    };
    expect(achadoDoRecibo(antiga, catalogo)).toBe(
      '3 itens entraram só no histórico: a nota é mais antiga que o custo atual deles, que foi mantido.',
    );
  });

  it('um alerta de item que não mudou de custo ganha a própria frase', () => {
    const [alerta] = recibo.alertas;
    if (!alerta) {
      throw new Error('fixture sem alerta');
    }
    const outro: ReciboNota = { ...recibo, alertas: [{ ...alerta, itemId: 'chocolate-barra', descricaoItem: 'Chocolate não recheado, barra 90 g' }] };
    expect(achadoDoRecibo(outro, catalogo)).toBe(
      'O custo de cerveja de malte, lata 350 ml subiu 17,31% (de R$ 2,60 para R$ 3,05). A margem de chocolate não ' +
        'recheado, barra 90 g caiu para 11,19%, abaixo do alvo de 15,00%. Os outros 2 itens ficaram com o mesmo custo.',
    );
  });

  it('sem item casado, diz que nenhum custo mudou', () => {
    expect(achadoDoRecibo({ ...recibo, itensCasados: [], alertas: [] }, catalogo)).toBe(
      'Nenhum item da nota 1002 casou com o catálogo: nenhum custo mudou.',
    );
  });

  it('usa o nome do catálogo, e o texto da nota só sem ele', () => {
    const outroNome: Catalogo = {
      ...catalogo,
      itens: catalogo.itens.map((i) => (i.id === 'cerveja-lata' ? { ...i, descricao: 'Cerveja da casa' } : i)),
    };
    expect(achadoDoRecibo(recibo, outroNome)).toMatch(/^O custo de cerveja da casa subiu 17,31%/u);
    expect(achadoDoRecibo(recibo, undefined)).toMatch(/^O custo de cerveja de malte, lata 350 ml subiu/u);
  });
});

// ---------------------------------------------------------------------------
// Regime

describe('Regime', () => {
  it('monta a venda só com o catálogo: a compra mensal do cliente, o preço e o custo atuais e a operação', async () => {
    const sessao = await montar('/regime', api(SAUDE_REAL));
    await screen.findByRole('region', { name: 'A venda a Mercado Bom Preço Ltda (fictício)' });
    const [pedido] = pedidosA(sessao, 'POST', '/regime/comparar');
    const corpo = (await pedido?.clone().json()) as Record<string, unknown>;
    const { operacao } = catalogo.cenario;
    expect(corpo.data).toBe(operacao.data);
    expect(corpo.uf).toBe(operacao.uf);
    expect(corpo.municipio).toBe(operacao.municipio);
    expect(corpo.aliquotasNominais).toEqual(operacao.aliquotasNominais);
    expect(corpo.premissasDas).toEqual(operacao.premissasDas);
    const [cliente] = catalogo.clientesB2B;
    expect(corpo.cliente).toEqual({ nome: cliente?.nome, regime: 'regime_regular' });
    const itens = corpo.itens as Record<string, unknown>[];
    expect(itens.map((i) => [i.id, i.quantidade])).toEqual(cliente?.compraMensal.map((c) => [c.itemId, c.quantidade]));
    for (const linha of itens) {
      const item = catalogo.itens.find((i) => i.id === linha.id);
      expect(linha.valorUnitario).toBe(item?.precoVenda);
      expect(linha.custoUnitario).toBe(item?.custoAtual?.custoUnitario);
      expect(linha.creditoCompraUnitario).toBe(item?.custoAtual?.creditoCompraUnitario);
    }
    // A venda vai ao cálculo sem o id do espaço nem o token (a rota não os declara).
    expect(pedido?.headers.has(CABECALHO_TOKEN)).toBe(false);
  });

  it('o crédito que o motor calculou numa nota sem o grupo IBSCBS não vai como se fosse da nota', () => {
    const semGrupo: Catalogo = {
      ...catalogo,
      itens: catalogo.itens.map((i) =>
        i.id === 'chocolate-barra' && i.custoAtual ? { ...i, custoAtual: { ...i.custoAtual, fonteCredito: 'motor' } } : i,
      ),
    };
    const [cliente] = semGrupo.clientesB2B;
    const pedido = cliente ? pedidoDeRegime(semGrupo, cliente) : null;
    const chocolate = pedido?.itens.find((i) => i.id === 'chocolate-barra');
    expect(chocolate?.custoUnitario).toBe('4.10');
    expect(chocolate && 'creditoCompraUnitario' in chocolate).toBe(false);
    expect(pedido?.itens.find((i) => i.id === 'cerveja-lata')?.creditoCompraUnitario).toBe('0.2715');
  });

  it('um item da venda fora do catálogo não vira pedido', () => {
    const [cliente] = catalogo.clientesB2B;
    expect(cliente && pedidoDeRegime({ ...catalogo, itens: catalogo.itens.filter((i) => i.id !== 'cerveja-lata') }, cliente)).toBeNull();
  });

  it('o achado: o crédito do cliente em cada regime e o custo no caixa, sem dizer qual escolher', async () => {
    await montar('/regime', api(SAUDE_REAL));
    const bloco = await screen.findByRole('region', { name: 'A venda a Mercado Bom Preço Ltda (fictício)' });
    expect(
      within(bloco).getByText(
        'No híbrido, o cliente leva R$ 1.626,26 de crédito por mês; no tradicional, R$ 233,63. Em troca, a empresa ' +
          'paga R$ 125,79 a mais de imposto.',
      ),
    ).toBeDefined();
    expect(document.body.textContent).not.toMatch(/\bopte\b|recomend|escolha o/iu);
    // A frase de simulação vem da resposta da API, no subtítulo.
    expect(screen.getByText(new RegExp(comparacao.avisoSimulacao?.slice(0, 40) ?? '-', 'u'))).toBeDefined();
  });

  it('a régua: duas barras na mesma escala, o custo líquido mais o crédito dá o preço ao cliente', async () => {
    await montar('/regime', api(SAUDE_REAL));
    const tradicional = await screen.findByRole('img', { name: /^Simples tradicional: preço de R\$ 19\.898,65/u });
    const hibrido = screen.getByRole('img', { name: /^Simples híbrido: preço de R\$ 19\.898,68/u });
    expect(tradicional.getAttribute('aria-label')).toBe(
      'Simples tradicional: preço de R$ 19.898,65, com R$ 19.665,02 de custo líquido e R$ 233,63 de crédito para o cliente',
    );
    expect(hibrido.getAttribute('aria-label')).toBe(
      'Simples híbrido: preço de R$ 19.898,68, com R$ 18.272,42 de custo líquido e R$ 1.626,26 de crédito para o cliente',
    );
    const larguras = (svg: Element) => [...svg.querySelectorAll('rect')].map((r) => Number(r.getAttribute('width')));
    const escala = 19898.68;
    const [, custoH, creditoH] = larguras(hibrido);
    const [, custoT, creditoT] = larguras(tradicional);
    expect(custoH).toBeCloseTo((18272.42 / escala) * 1000, 6);
    expect(creditoH).toBeCloseTo((1626.26 / escala) * 1000, 6);
    expect(custoT).toBeCloseTo((19665.02 / escala) * 1000, 6);
    expect(creditoT).toBeCloseTo((233.63 / escala) * 1000, 6);
    // Os números fecham na resposta: custo líquido + crédito = preço ao cliente, nos dois lados.
    for (const lado of [comparacao.tradicional, comparacao.hibrido]) {
      expect(Math.round(Number(lado.custoLiquidoCliente) * 100) + Math.round(Number(lado.creditoCliente) * 100)).toBe(
        Math.round(Number(lado.precoCliente) * 100),
      );
    }
    expect(screen.getByText('+R$ 0,03 de arredondamento.')).toBeDefined();
  });

  it('o caixa: o tributo de cada regime e a diferença por mês', async () => {
    await montar('/regime', api(SAUDE_REAL));
    const caixa = await screen.findByRole('region', { name: 'O caixa da empresa' });
    await within(caixa).findByText('−R$ 125,79');
    // O tributo do mês aparece na barra e na conta de cada regime.
    expect(within(caixa).getAllByText('R$ 233,63')).toHaveLength(2);
    expect(within(caixa).getAllByText('R$ 359,42')).toHaveLength(2);
    expect(within(caixa).getByText('R$ 1.626,26')).toBeDefined();
    expect(within(caixa).getByText('−R$ 1.266,84')).toBeDefined();
    expect(within(caixa).getByRole('img').getAttribute('aria-label')).toBe(
      'Tributo por mês: R$ 233,63 no DAS do tradicional e R$ 359,42 líquidos no híbrido, depois do crédito das compras',
    );
    // Diferença = tributo tradicional − tributo líquido híbrido (contrato, test_contrato.py).
    expect(Math.round((233.63 - 359.42) * 100)).toBe(Math.round(Number(comparacao.diferencaCaixa) * 100));
  });

  it('o empate e a venda por item, com a origem do crédito das compras', async () => {
    await montar('/regime', api(SAUDE_REAL));
    const empate = await screen.findByRole('region', { name: 'Preço de empate no tradicional' });
    expect(within(empate).getByText('R$ 18.489,49')).toBeDefined();
    expect(empate.textContent).toContain('(R$ 1.409,16 a menos)');
    const itens = screen.getByRole('region', { name: 'A venda por item' });
    // Os três itens têm o crédito da nota: a origem aparece uma vez, no cabeçalho da coluna.
    expect(within(itens).getAllByText('da nota')).toHaveLength(1);
    expect(within(itens).getByRole('columnheader', { name: /Crédito das compras/u }).textContent).toContain('da nota');
    const total = within(itens).getByText('Total da venda').closest('tr');
    expect(total && within(total).getByText('R$ 19.898,65')).toBeDefined();
    expect(total && within(total).getByText('R$ 1.266,84')).toBeDefined();
  });

  it('o nome e o valor das premissas ficam à vista; as simplificações e a hipótese do empate abrem com um clique', async () => {
    await montar('/regime', api(SAUDE_REAL));
    const premissas = await screen.findByRole('region', { name: 'Premissas da comparação' });
    for (const p of comparacao.premissas) {
      expect(within(premissas).getByText(p.nome)).toBeDefined();
      expect(within(premissas).getByText(p.valor)).toBeDefined();
    }
    const detalhe = within(premissas).getByText('Simplificações do cálculo').closest('details');
    expect(detalhe?.open).toBe(false);
    const itens = detalhe ? within(detalhe).getAllByRole('listitem', { hidden: true }) : [];
    expect(itens.map((i) => i.textContent)).toEqual([
      ...comparacao.simplificacoes,
      comparacao.empateTradicional?.hipotese,
    ]);
    // Nenhum nome de campo da API vira texto da tela.
    expect(document.body.textContent).not.toMatch(/diferencaCaixa|diferencaPrecoCliente|custoLiquidoAlvo/u);
  });

  it('antes de 2027 a comparação não existe, e a tela diz por quê sem chamar a API', async () => {
    const operacao2026 = { ...catalogo.cenario.operacao, data: '2026-08-10' };
    delete (operacao2026 as { aliquotasNominais?: unknown }).aliquotasNominais;
    const sessao = await montar(
      '/regime',
      api(SAUDE_REAL, () => undefined, { catalogo: { ...catalogo, cenario: { ...catalogo.cenario, operacao: operacao2026 } } }),
    );
    const bloco = await screen.findByRole('region', { name: 'Comparação de regimes' });
    expect(bloco.textContent).toContain('A comparação começa em 2027:');
    expect(bloco.textContent).toContain('(VSN-015)');
    expect(within(bloco).getByText('10/08/2026')).toBeDefined();
    expect(pedidosA(sessao, 'POST', '/regime/comparar')).toHaveLength(0);
  });

  it('sem cliente empresa, a tela diz que não há venda para comparar', async () => {
    const sessao = await montar('/regime', api(SAUDE_REAL, () => undefined, { catalogo: { ...catalogo, clientesB2B: [] } }));
    expect(await screen.findByText('Nenhum cliente empresa cadastrado.')).toBeDefined();
    expect(pedidosA(sessao, 'POST', '/regime/comparar')).toHaveLength(0);
  });

  it('uma recusa da API aparece no bloco, com "Tentar de novo"', async () => {
    await montar(
      '/regime',
      api(SAUDE_REAL, (p) =>
        new URL(p.url).pathname === '/regime/comparar'
          ? json(
              {
                type: '/problemas/validacao',
                title: 'Dados inválidos',
                status: 422,
                detail: 'Informe custoUnitario dos itens cerveja-lata: sem o custo não há crédito das compras.',
              },
              422,
            )
          : undefined,
      ),
    );
    const falha = await screen.findByRole('alert');
    expect(falha.textContent).toContain('Informe custoUnitario dos itens cerveja-lata');
    expect(within(falha).getByRole('button', { name: 'Tentar de novo' })).toBeDefined();
  });

  it('com dois clientes, troca a venda pelo seletor', async () => {
    const [bomPreco] = catalogo.clientesB2B;
    if (!bomPreco) {
      throw new Error('fixture sem cliente');
    }
    const outro = { ...bomPreco, cnpj: '11222333000181', nome: 'Outro Cliente Ltda (fictício)', compraMensal: bomPreco.compraMensal.slice(0, 1) };
    const sessao = await montar('/regime', api(SAUDE_REAL, () => undefined, { catalogo: { ...catalogo, clientesB2B: [bomPreco, outro] } }));
    await screen.findByRole('region', { name: 'A venda a Mercado Bom Preço Ltda (fictício)' });
    fireEvent.change(screen.getByLabelText('Cliente'), { target: { value: outro.cnpj } });
    await waitFor(() => {
      expect(pedidosA(sessao, 'POST', '/regime/comparar')).toHaveLength(2);
    });
    const ultimo = pedidosA(sessao, 'POST', '/regime/comparar')[1];
    const corpo = (await ultimo?.clone().json()) as { cliente: { nome: string }; itens: unknown[] };
    expect(corpo.cliente.nome).toBe('Outro Cliente Ltda (fictício)');
    expect(corpo.itens).toHaveLength(1);
  });
});

describe('a origem do crédito na venda por item', () => {
  it('com origens diferentes, cada linha diz a sua', async () => {
    const misturada = {
      ...comparacao,
      itens: comparacao.itens.map((i, n) => (n === 0 ? { ...i, fonteCredito: 'motor' as const } : i)),
    };
    await montar('/regime', api(SAUDE_REAL, (p) => (new URL(p.url).pathname === '/regime/comparar' ? json(misturada) : undefined)));
    const itens = await screen.findByRole('region', { name: 'A venda por item' });
    await within(itens).findByText('estimado');
    expect(within(itens).getAllByText('da nota')).toHaveLength(misturada.itens.length - 1);
    expect(within(itens).getByRole('columnheader', { name: /Crédito das compras/u }).textContent).toBe('Crédito das compras');
  });
});

describe('achado do regime', () => {
  it('quando o híbrido deixa mais caixa, diz isso, e quando empata, diz que fica igual', () => {
    expect(achadoDoRegime({ ...comparacao, diferencaCaixa: '40.10' })).toContain(
      'E a empresa fica com R$ 40,10 a mais de caixa.',
    );
    expect(achadoDoRegime({ ...comparacao, diferencaCaixa: '0.00' })).toContain('O caixa da empresa fica igual.');
  });
});
