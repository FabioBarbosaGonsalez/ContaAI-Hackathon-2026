// Telas do PR 3a com respostas reais gravadas da API (src/teste/fixtures, modo real com os motores, nota 2
// da demonstração importada). O fetch é falso: os testes conferem o que a tela pede e o que ela mostra.

import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from '../App.tsx';
import { reiniciarFocoDePagina } from '../shell/Pagina.tsx';
import alertas from '../teste/fixtures/alertas.json';
import buscaCarne from '../teste/fixtures/busca-carne.json';
import catalogo from '../teste/fixtures/catalogo.json';
import carrinhoHibrido from '../teste/fixtures/carrinho-simples_hibrido.json';
import carrinhoTradicional from '../teste/fixtures/carrinho-simples_tradicional.json';
import explicarCerveja from '../teste/fixtures/explicar-cerveja.json';
import { SAUDE_MOCK, SAUDE_REAL, json, sessaoDeTeste } from '../teste/sessaoDeTeste.ts';
import { achadoDoCatalogo } from './Catalogo.tsx';
import { lerPreco } from './Dialogos.tsx';

beforeAll(() => {
  // O jsdom não implementa showModal/close do <dialog>; o comportamento real é conferido no Chrome.
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

type Rota = (pedido: Request, corpo: unknown) => Response | undefined;

function api(saude: object, extra: Rota = () => undefined) {
  return async (pedido: Request): Promise<Response> => {
    const url = new URL(pedido.url);
    const corpo: unknown = pedido.method === 'POST' && pedido.body ? await pedido.clone().json() : undefined;
    const especial = extra(pedido, corpo);
    if (especial) {
      return especial;
    }
    const chave = `${pedido.method} ${url.pathname}`;
    switch (chave) {
      case 'GET /saude':
        return json(saude);
      case 'GET /catalogo':
        return json(catalogo);
      case 'GET /alertas':
        return json(alertas);
      case 'POST /carrinho/calcular':
        return json((corpo as { regime: string }).regime === 'simples_hibrido' ? carrinhoHibrido : carrinhoTradicional);
      case 'GET /explicar/cerveja-lata':
        return json(explicarCerveja);
      case 'GET /busca/ncm':
        return json(buscaCarne);
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

const corpoDe = async (pedido: Request) => (await pedido.clone().json()) as Record<string, unknown>;

describe('Painel', () => {
  it('o alerta vem primeiro: a frase, o preço sugerido e a margem abaixo do alvo', async () => {
    await montar('/painel', api(SAUDE_REAL));
    const bloco = await screen.findByRole('region', { name: 'Margem abaixo do alvo' });
    await within(bloco).findByText(/A margem de cerveja de malte, lata 350 ml caiu de 24,12% para 11,19%/u);
    expect(within(bloco).getByText('depois da nota 1002, de 16/03/2027.', { exact: false })).toBeDefined();
    expect(within(bloco).getByText('R$ 3,97')).toBeDefined();
    expect(within(bloco).getByRole('button', { name: 'Aplicar R$ 3,97' })).toBeDefined();
    // A frase de simulação vem da API, no subtítulo do título.
    expect(screen.getByText(/Simulação de 2027 com alíquotas efetivas do Simples assumidas/u)).toBeDefined();
  });

  it('um fato, uma variável: a margem da cerveja na lista é a do alerta', async () => {
    await montar('/painel', api(SAUDE_REAL));
    const margens = await screen.findByRole('region', { name: 'Margem de cada item contra o alvo' });
    const linha = (await within(margens).findByText('Cerveja de malte, lata 350 ml')).closest('tr');
    expect(linha && within(linha).getByText('11,19%').className).toContain('negativo');
    const carne = within(margens).getByText('Carne bovina desossada, resfriada (kg)').closest('tr');
    expect(carne && within(carne).getByText('NCM não combina com a classificação')).toBeDefined();
  });

  it('sem espaço nem token, o Aplicar fica desligado e diz por quê', async () => {
    await montar('/painel', api(SAUDE_REAL));
    const botao = await screen.findByRole('button', { name: 'Aplicar R$ 3,97' });
    expect((botao as HTMLButtonElement).disabled).toBe(true);
    expect(botao.getAttribute('aria-describedby')).not.toBeNull();
    expect(screen.getByText('Para gravar, crie seu espaço no alto da tela.')).toBeDefined();
  });

  it('no modo mock, a tela diz que é só leitura', async () => {
    await montar('/painel', api(SAUDE_MOCK));
    await screen.findByRole('button', { name: 'Aplicar R$ 3,97' });
    expect(screen.getByText(/só leitura: nada é gravado/u)).toBeDefined();
  });

  it('aplicar o alerta grava pelo id e recarrega os alertas', async () => {
    const aplicados: string[] = [];
    let aberto = true;
    const sessao = await montar(
      '/painel',
      api(SAUDE_REAL, (pedido) => {
        const url = new URL(pedido.url);
        if (pedido.method === 'POST' && url.pathname.endsWith('/aplicar')) {
          aplicados.push(url.pathname);
          aberto = false;
          return json({ alerta: alertas.alertas[0], precoAnterior: '3.79', precoNovo: '3.97' });
        }
        if (url.pathname === '/alertas' && !aberto) {
          return json({ alertas: [] });
        }
        return undefined;
      }),
      true,
    );
    fireEvent.click(await screen.findByRole('button', { name: 'Aplicar R$ 3,97' }));
    await screen.findByText('Nenhum item com a margem abaixo do alvo.');
    expect(aplicados).toEqual([`/alertas/${alertas.alertas[0]?.id ?? ''}/aplicar`]);
    const aplicar = sessao.pedidos.find((p) => p.url.endsWith('/aplicar'));
    expect(aplicar?.headers.get('X-ContaAI-Token')).toBe('token-de-teste');
  });

  it('sem alerta aberto, a resposta fica no topo das margens, na linha inteira, sem cartão vazio', async () => {
    await montar(
      '/painel',
      api(SAUDE_REAL, (pedido) => (new URL(pedido.url).pathname === '/alertas' ? json({ alertas: [] }) : undefined)),
    );
    const margens = await screen.findByRole('region', { name: 'Margem de cada item contra o alvo' });
    await within(margens).findByText('Nenhum item com a margem abaixo do alvo.');
    expect(margens.className).toContain('painel__margens--inteira');
    expect(within(margens).getByRole('link', { name: 'Importar uma nota' }).getAttribute('href')).toBe('/notas');
    expect(screen.queryByRole('region', { name: 'Margem abaixo do alvo' })).toBeNull();
  });

  it('corrigir a classificação: as candidatas oficiais da NCM e a escolhida gravada', async () => {
    const gravados: Record<string, unknown>[] = [];
    await montar(
      '/painel',
      api(SAUDE_REAL, (pedido) => {
        if (pedido.method === 'POST' && pedido.url.endsWith('/catalogo/carne-bovina-kg/classificacao')) {
          void corpoDe(pedido).then((c) => gravados.push(c));
          return json({});
        }
        return undefined;
      }),
      true,
    );
    const bloco = await screen.findByRole('region', { name: 'Cadastro a corrigir' });
    fireEvent.click(await within(bloco).findByRole('button', { name: 'Corrigir' }));
    const dialogo = await screen.findByRole('dialog', { name: 'Corrigir a classificação' });
    const opcoes = await within(dialogo).findAllByRole('radio');
    expect(opcoes.map((o) => (o as HTMLInputElement).value)).toEqual(['200003', '000001']);
    fireEvent.click(within(dialogo).getByLabelText(/200003/u));
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Gravar a classificação' }));
    await waitFor(() => {
      expect(gravados).toEqual([{ cnpj: '36817420000113', cClassTrib: '200003' }]);
    });
  });
});

describe('Catálogo', () => {
  it('troca de regime refaz o cálculo nos motores e muda o achado', async () => {
    const sessao = await montar('/catalogo', api(SAUDE_REAL));
    await screen.findByText(/No Simples tradicional, arroz polido não parboilizado, pacote 5 kg é o que mais carrega/u);
    fireEvent.click(screen.getByRole('button', { name: 'Simples híbrido' }));
    await screen.findByText(/No Simples híbrido, chocolate não recheado, barra 90 g é o que mais carrega/u);
    expect(screen.getByText(/Com redução de alíquota: arroz polido não parboilizado, pacote 5 kg \(100,00%\)/u)).toBeDefined();
    const regimes = await Promise.all(
      sessao.pedidos.filter((p) => p.url.endsWith('/carrinho/calcular')).map(async (p) => (await corpoDe(p)).regime),
    );
    expect(regimes).toEqual(['simples_tradicional', 'simples_hibrido']);
  });

  it('a carne mostra o erro em palavras e o Corrigir na própria linha', async () => {
    await montar('/catalogo', api(SAUDE_REAL));
    const linha = (await screen.findByText('Carne bovina desossada, resfriada (kg)')).closest('tr');
    expect(linha).not.toBeNull();
    if (linha) {
      expect(within(linha).getByText('NCM não combina com a classificação')).toBeDefined();
      expect(within(linha).getByRole('button', { name: 'Corrigir' })).toBeDefined();
    }
  });

  it('explicar abre a lateral com a lei, a memória do motor e as premissas', async () => {
    await montar('/catalogo', api(SAUDE_REAL));
    const linha = (await screen.findByText('Cerveja de malte, lata 350 ml')).closest('tr');
    if (!linha) {
      throw new Error('sem linha');
    }
    fireEvent.click(within(linha).getByRole('button', { name: 'Explicar' }));
    const lateral = await screen.findByRole('dialog', { name: 'Cerveja de malte, lata 350 ml' });
    await within(lateral).findByRole('heading', { name: 'Memória de cálculo do motor' });
    expect(within(lateral).getByText(explicarCerveja.aviso)).toBeDefined();
    fireEvent.click(within(lateral).getByRole('button', { name: 'Fechar' }));
    expect(lateral.hasAttribute('open')).toBe(false);
  });

  it('alterar o preço manda o valor com ponto e 2 casas', async () => {
    const gravados: Record<string, unknown>[] = [];
    await montar(
      '/catalogo',
      api(SAUDE_REAL, (pedido) => {
        if (pedido.method === 'POST' && pedido.url.endsWith('/catalogo/cerveja-lata/preco')) {
          void corpoDe(pedido).then((c) => gravados.push(c));
          return json({});
        }
        return undefined;
      }),
      true,
    );
    const linha = (await screen.findByText('Cerveja de malte, lata 350 ml')).closest('tr');
    if (!linha) {
      throw new Error('sem linha');
    }
    fireEvent.click(within(linha).getByRole('button', { name: 'Preço' }));
    const dialogo = await screen.findByRole('dialog', { name: 'Alterar o preço de venda' });
    fireEvent.change(within(dialogo).getByLabelText('Novo preço por unidade'), { target: { value: '3,99' } });
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Gravar o preço' }));
    await waitFor(() => {
      expect(gravados).toEqual([{ cnpj: '36817420000113', valorUnitario: '3.99' }]);
    });
  });

  it('falha do cálculo aparece dentro do bloco, com Tentar de novo', async () => {
    await montar(
      '/catalogo',
      api(SAUDE_REAL, (pedido) =>
        pedido.url.endsWith('/carrinho/calcular')
          ? json({ type: '/problemas/motor-indisponivel', title: 'Motor oficial indisponível', status: 503, detail: 'x' }, 503)
          : undefined,
      ),
    );
    const alerta = await screen.findByRole('alert');
    expect(within(alerta).getByRole('button', { name: 'Tentar de novo' })).toBeDefined();
  });
});

describe('barreira de erro', () => {
  it('resposta fora do formato quebra só a página: a barra e o rodapé continuam', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    await montar(
      '/painel',
      api(SAUDE_REAL, (pedido) => (pedido.url.includes('/catalogo') ? json({ inesperado: true }) : undefined)),
    );
    await screen.findByRole('heading', { level: 1, name: 'Não foi possível mostrar esta tela' });
    expect(screen.getByRole('navigation', { name: 'Principal' })).toBeDefined();
    expect(screen.getByRole('contentinfo')).toBeDefined();
  });
});

describe('regras puras', () => {
  it('lerPreco aceita vírgula ou ponto, até 2 casas e positivo', () => {
    expect(lerPreco('3,99')).toBe('3.99');
    expect(lerPreco('R$ 4')).toBe('4');
    expect(lerPreco('3,999')).toBeNull();
    expect(lerPreco('0')).toBeNull();
    expect(lerPreco('-1')).toBeNull();
    expect(lerPreco('1e3')).toBeNull();
  });

  it('o achado soma CBS e IBS como a tela os mostra', () => {
    const achado = achadoDoCatalogo(carrinhoTradicional as never, 100);
    // Arroz: R$ 32,40 + R$ 0,36 = R$ 32,76 (a conta do inventário, §1).
    expect(achado).toContain('R$ 32,76 de CBS e IBS a cada 100 unidades');
  });
});
