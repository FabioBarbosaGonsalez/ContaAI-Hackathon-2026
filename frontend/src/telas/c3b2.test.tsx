// C3b, etapas 6 a 9 (ADR 0018, seção da C3b2): cadastrar, alterar e arquivar o item, o item a partir da nota e os
// clientes empresa, com respostas reais gravadas da API (src/teste/fixtures/c3b2-*: modo real, motores RR 1.7.2 e
// SN 1.0.2, banco temporário, conta fictícia do domínio .test, o CNPJ do exemplo do Serpro; e a demonstração num
// espaço de avaliação). O fetch é falso: os testes conferem o que a tela pede e o que ela mostra.

import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from '../App.tsx';
import { carregarSessao } from '../sessao/acoes.ts';
import type { Conta } from '../sessao/conta.ts';
import { reiniciarFocoDePagina } from '../shell/Pagina.tsx';
import { ROTA_DOS_CLIENTES } from '../shell/rotas.ts';
import alertasDaDemo from '../teste/fixtures/alertas.json';
import alertasDaEmpresaNova from '../teste/fixtures/alertas-empresa-nova.json';
import busca18063210 from '../teste/fixtures/c3b2-busca-18063210.json';
import buscaArroz from '../teste/fixtures/c3b2-busca-arroz.json';
import busca22030000 from '../teste/fixtures/c3b2-busca-22030000.json';
import catalogoComCliente from '../teste/fixtures/c3b2-catalogo-com-cliente.json';
import catalogoComItens from '../teste/fixtures/c3b2-catalogo-com-itens.json';
import clienteAlterado from '../teste/fixtures/c3b2-cliente-alterado.json';
import clienteCadastrado from '../teste/fixtures/c3b2-cliente-cadastrado.json';
import clienteExcluido from '../teste/fixtures/c3b2-cliente-excluido.json';
import erroClienteRepetido from '../teste/fixtures/c3b2-erro-cliente-repetido.json';
import erroItemEmUsoDemo from '../teste/fixtures/c3b2-erro-item-em-uso-demo.json';
import erroItemFornecedor from '../teste/fixtures/c3b2-erro-item-fornecedor.json';
import itemAlteradoDemo from '../teste/fixtures/c3b2-item-alterado-demo.json';
import itemCadastrado from '../teste/fixtures/c3b2-item-cadastrado.json';
import itemDaNota from '../teste/fixtures/c3b2-item-da-nota.json';
import importacao1001 from '../teste/fixtures/c3b2-nfe-importar-1001.json';
import notasDaConta from '../teste/fixtures/c3b2-notas.json';
import recibo1001 from '../teste/fixtures/c3b2-recibo-1001.json';
import recibo1001Cadastrado from '../teste/fixtures/c3b2-recibo-1001-cadastrado.json';
import carrinhoDaDemo from '../teste/fixtures/carrinho-simples_tradicional.json';
import catalogoDaDemo from '../teste/fixtures/catalogo.json';
import catalogoDaEmpresaNova from '../teste/fixtures/catalogo-empresa-nova.json';
import municipiosRs from '../teste/fixtures/referencias-municipios-rs.json';
import ufs from '../teste/fixtures/referencias-ufs.json';
import { CONTA_DE_TESTE, SAUDE_MOCK, SAUDE_REAL, json, sessaoDeTeste } from '../teste/sessaoDeTeste.ts';
import { FRASE_DO_SELETIVO, FRASE_ITEM_SEM_MUDANCA } from './CadastroDoItem.tsx';
import { FRASE_CLIENTE_SEM_MUDANCA, FRASE_SEM_ITENS } from './Clientes.tsx';

const CNPJ = catalogoDaEmpresaNova.empresa.cnpj;
const EMITENTE = importacao1001.nota.emitente.cnpj;
const COM_EMPRESA: Conta = { ...CONTA_DE_TESTE, empresas: [CNPJ] };
const RECIBO = `GET /notas/${EMITENTE}/1/1001`;

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

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

interface Pedido {
  rota: string;
  busca: URLSearchParams;
  corpo: unknown;
}

/** Uma rota que o teste responde: devolve a resposta, ou undefined para seguir as respostas padrão. */
type Rotas = Record<string, (pedido: Pedido) => Response>;

interface Opcoes {
  /** null: ninguém entrou (a demonstração). */
  conta?: Conta | null;
  saude?: object;
  token?: boolean;
  catalogo?: () => object;
  rotas?: Rotas;
}

async function montar(caminho: string, { conta = COM_EMPRESA, saude = SAUDE_REAL, token = false, catalogo, rotas = {} }: Opcoes = {}) {
  history.replaceState(null, '', caminho);
  const pedidos: Pedido[] = [];
  const naConta = conta !== null;
  const sessao = sessaoDeTeste(async (req) => {
    const url = new URL(req.url);
    const texto = req.method === 'GET' ? '' : await req.clone().text();
    const pedido: Pedido = {
      rota: `${req.method} ${url.pathname}`,
      busca: url.searchParams,
      corpo: texto === '' ? null : (req.headers.get('content-type') ?? '').includes('json') ? (JSON.parse(texto) as unknown) : texto,
    };
    pedidos.push(pedido);
    const especial = rotas[pedido.rota];
    if (especial) {
      return especial(pedido);
    }
    switch (pedido.rota) {
      case 'GET /saude':
        return json(saude);
      case 'GET /conta':
        return conta === null ? json({ title: 'Unauthorized', status: 401, detail: 'Entre com a sua conta.' }, 401) : json(conta);
      case 'GET /referencias/ufs':
        return json(ufs);
      case 'GET /referencias/municipios':
        return json(municipiosRs);
      case 'GET /catalogo':
        return json(catalogo ? catalogo() : naConta ? catalogoDaEmpresaNova : catalogoDaDemo);
      case 'POST /carrinho/calcular':
        return json(carrinhoDaDemo);
      case 'GET /alertas':
        return json(naConta ? alertasDaEmpresaNova : alertasDaDemo);
      case 'GET /notas':
        return json(notasDaConta);
      case 'GET /busca/ncm': {
        const q = pedido.busca.get('q');
        const achada = { '18063210': busca18063210, arroz: buscaArroz, '22030000': busca22030000 }[q ?? ''];
        return json(achada ?? { ...busca18063210, consulta: q, candidatos: [] });
      }
      default:
        return json({ type: 'about:blank', title: 'Not Found', status: 404 }, 404);
    }
  });
  if (token) {
    sessao.token.definir('token-de-teste');
  }
  render(<App sessao={sessao} />);
  await act(() => carregarSessao(sessao));
  return { sessao, pedidos };
}

const principal = () => within(screen.getByRole('main'));
const dialogo = (nome: string | RegExp) => within(screen.getByRole('dialog', { name: nome }));
const deRota = (pedidos: Pedido[], rota: string) => pedidos.filter((p) => p.rota === rota);
const digitar = (alvo: HTMLElement, valor: string) => {
  fireEvent.change(alvo, { target: { value: valor } });
};

// ---------------------------------------------------------------------------
// Etapa 6: cadastrar o item pelo Catálogo

describe('cadastrar o item pelo Catálogo', () => {
  it('o catálogo vazio da conta oferece o cadastro; enviar sem nada acusa os campos e não chama a API', async () => {
    const { pedidos } = await montar('/catalogo');
    await principal().findByText('Nenhum item no catálogo ainda.');
    fireEvent.click(principal().getByRole('button', { name: 'Cadastrar o primeiro item' }));
    const d = dialogo('Cadastrar item');
    fireEvent.click(d.getByRole('button', { name: 'Cadastrar o item' }));
    expect(d.getByText('Informe a descrição do item.')).toBeTruthy();
    expect(d.getByText('Busque e escolha a NCM do produto.')).toBeTruthy();
    expect(d.getByText('Escolha a unidade.')).toBeTruthy();
    expect(document.activeElement).toBe(d.getByLabelText('Descrição do item'));
    expect(deRota(pedidos, 'POST /catalogo/itens')).toHaveLength(0);
  });

  it('pela NCM: a classificação válida para ela, o dígito do fornecedor na conta, e o pedido com o que foi escolhido', async () => {
    let cadastrou = false;
    const { pedidos } = await montar('/catalogo', {
      catalogo: () => (cadastrou ? catalogoComItens : catalogoDaEmpresaNova),
      rotas: {
        'POST /catalogo/itens': () => {
          cadastrou = true;
          return json(itemCadastrado, 201);
        },
      },
    });
    fireEvent.click(await principal().findByRole('button', { name: 'Cadastrar o primeiro item' }));
    const d = dialogo('Cadastrar item');
    digitar(d.getByLabelText('Descrição do item'), '  Chocolate ao leite 90 g ');
    digitar(d.getByLabelText('NCM ou nome do produto'), '1806.32.10');
    fireEvent.click(d.getByRole('button', { name: 'Buscar' }));
    const classificacao = await d.findByRole('radio', { name: /^000001/u });
    const [busca] = deRota(pedidos, 'GET /busca/ncm');
    expect(busca?.busca.get('q')).toBe('18063210');
    expect(busca?.busca.get('data')).toBe(catalogoDaEmpresaNova.cenario.operacao.data);
    fireEvent.click(classificacao);
    fireEvent.click(d.getByRole('radio', { name: 'Unidade (UN)' }));
    // 71604258000156 é o fornecedor fictício da demonstração: na conta, o dígito é conferido.
    digitar(d.getByLabelText('CNPJ do fornecedor'), '71.604.258/0001-56');
    digitar(d.getByLabelText('Código do produto no fornecedor'), 'AE-CHO-90');
    digitar(d.getByLabelText('Preço de venda por unidade (R$)'), '4,20');
    digitar(d.getByLabelText('Margem-alvo (%)'), '20');
    fireEvent.click(d.getByRole('button', { name: 'Cadastrar o item' }));
    expect(d.getByText('CNPJ inválido: confira os dígitos verificadores.')).toBeTruthy();
    expect(deRota(pedidos, 'POST /catalogo/itens')).toHaveLength(0);

    digitar(d.getByLabelText('CNPJ do fornecedor'), EMITENTE);
    fireEvent.click(d.getByRole('button', { name: 'Cadastrar o item' }));
    await principal().findByText(`Item cadastrado: ${itemCadastrado.item.descricao}.`);
    expect(deRota(pedidos, 'POST /catalogo/itens')[0]?.corpo).toEqual({
      cnpj: CNPJ,
      descricao: 'Chocolate ao leite 90 g',
      ncm: '18063210',
      cClassTrib: '000001',
      unidade: 'UN',
      cnpjFornecedor: EMITENTE,
      codigoFornecedor: 'AE-CHO-90',
      precoVenda: '4.20',
      margemAlvoPct: '20',
    });
    expect(screen.queryByRole('dialog')).toBeNull();
    await waitFor(() => {
      expect(deRota(pedidos, 'GET /catalogo').length).toBeGreaterThanOrEqual(2);
    });
  });

  it('pelo nome: as NCMs encontradas para escolher, e as classificações da escolhida', async () => {
    await montar('/catalogo');
    fireEvent.click(await principal().findByRole('button', { name: 'Cadastrar o primeiro item' }));
    const d = dialogo('Cadastrar item');
    const busca = d.getByLabelText('NCM ou nome do produto');
    digitar(busca, 'arroz');
    fireEvent.keyDown(busca, { key: 'Enter' });
    const opcoes = await d.findAllByRole('radio', { name: /^\d{4}\.\d{2}\.\d{2}/u });
    expect(opcoes).toHaveLength(buscaArroz.candidatos.length);
    expect(d.queryByRole('group', { name: 'Classificação (cClassTrib)' })).toBeNull();
    fireEvent.click(opcoes[0] as HTMLElement);
    const grupo = within(d.getByRole('group', { name: 'Classificação (cClassTrib)' }));
    expect(grupo.getAllByRole('radio')).toHaveLength(buscaArroz.candidatos[0]?.classificacoes.length ?? -1);
  });

  it('a NCM com Imposto Seletivo aparece fora da escolha, com o motivo', async () => {
    await montar('/catalogo');
    fireEvent.click(await principal().findByRole('button', { name: 'Cadastrar o primeiro item' }));
    const d = dialogo('Cadastrar item');
    digitar(d.getByLabelText('NCM ou nome do produto'), '22030000');
    fireEvent.click(d.getByRole('button', { name: 'Buscar' }));
    await d.findByText(/O cadastro ainda não aceita itens com Imposto Seletivo:/u);
    expect(d.queryByRole('group', { name: 'Classificação (cClassTrib)' })).toBeNull();
    fireEvent.click(d.getByRole('button', { name: 'Cadastrar o item' }));
    expect(d.getAllByText(FRASE_DO_SELETIVO).length).toBeGreaterThan(0);
  });

  it('na demonstração com o token, o CNPJ fictício passa na tela; a recusa da API aparece no diálogo', async () => {
    const { pedidos } = await montar('/catalogo', {
      conta: null,
      token: true,
      rotas: { 'POST /catalogo/itens': () => json(erroItemFornecedor, 422) },
    });
    fireEvent.click(await principal().findByRole('button', { name: 'Cadastrar item' }));
    const d = dialogo('Cadastrar item');
    digitar(d.getByLabelText('Descrição do item'), 'Chocolate 90 g');
    digitar(d.getByLabelText('NCM ou nome do produto'), '18063210');
    fireEvent.click(d.getByRole('button', { name: 'Buscar' }));
    fireEvent.click(await d.findByRole('radio', { name: /^000001/u }));
    fireEvent.click(d.getByRole('radio', { name: 'Quilo (KG)' }));
    digitar(d.getByLabelText('CNPJ do fornecedor'), '71604258000156');
    digitar(d.getByLabelText('Código do produto no fornecedor'), 'X1');
    digitar(d.getByLabelText('Preço de venda por unidade (R$)'), '1');
    digitar(d.getByLabelText('Margem-alvo (%)'), '10');
    fireEvent.click(d.getByRole('button', { name: 'Cadastrar o item' }));
    expect(await d.findByRole('alert')).toHaveProperty('textContent', erroItemFornecedor.detail);
    expect(deRota(pedidos, 'POST /catalogo/itens')[0]?.corpo).toMatchObject({ cnpj: catalogoDaDemo.empresa.cnpj, unidade: 'KG' });
  });

  it('o Painel da empresa sem itens leva ao cadastro no Catálogo', async () => {
    await montar('/painel');
    const link = await principal().findByRole('link', { name: 'Cadastrar os itens no Catálogo' });
    expect(link.getAttribute('href')).toBe('/catalogo');
  });

  it('no modo mock, o botão fica desligado e diz por quê', async () => {
    await montar('/catalogo', { conta: null, saude: SAUDE_MOCK });
    const botao = await principal().findByRole('button', { name: 'Cadastrar item' });
    expect(botao).toHaveProperty('disabled', true);
    const motivo = document.getElementById(botao.getAttribute('aria-describedby') ?? '');
    expect(motivo?.textContent).toMatch(/só leitura/u);
  });
});

// ---------------------------------------------------------------------------
// Etapa 7: alterar e arquivar

describe('alterar e arquivar o item', () => {
  async function abrirArroz(rotas: Rotas = {}) {
    const montado = await montar('/catalogo', { conta: null, token: true, rotas });
    const linha = (await principal().findByText('Arroz polido não parboilizado, pacote 5 kg')).closest('tr') as HTMLElement;
    fireEvent.click(within(linha).getByRole('button', { name: 'Alterar' }));
    return { ...montado, d: dialogo('Alterar o item') };
  }

  it('os campos vêm com os valores do item, o fornecedor incluso; sem mudança, nada é enviado', async () => {
    const { d, pedidos } = await abrirArroz();
    const arroz = catalogoDaDemo.itens.find((i) => i.id === 'arroz-5kg');
    expect(d.getByLabelText('CNPJ do fornecedor')).toHaveProperty('value', '71.604.258/0001-56');
    expect(arroz?.fornecedor.cnpj).toBe('71604258000156');
    expect(d.getByLabelText('Código do produto no fornecedor')).toHaveProperty('value', arroz?.fornecedor.codigo);
    expect(d.getByText(/A NCM e a unidade não mudam/u)).toBeTruthy();
    fireEvent.click(d.getByRole('button', { name: 'Salvar o item' }));
    expect(d.getByText(FRASE_ITEM_SEM_MUDANCA)).toBeTruthy();
    expect(deRota(pedidos, 'PATCH /catalogo/arroz-5kg')).toHaveLength(0);
  });

  it('salva só o que mudou e diz que salvou', async () => {
    const { d, pedidos } = await abrirArroz({ 'PATCH /catalogo/arroz-5kg': () => json(itemAlteradoDemo) });
    digitar(d.getByLabelText('Margem-alvo (%)'), '20');
    fireEvent.click(d.getByRole('button', { name: 'Salvar o item' }));
    await principal().findByText(`Item salvo: ${itemAlteradoDemo.item.descricao}.`);
    expect(deRota(pedidos, 'PATCH /catalogo/arroz-5kg')[0]?.corpo).toEqual({ cnpj: catalogoDaDemo.empresa.cnpj, margemAlvoPct: '20' });
  });

  it('arquivar pede a confirmação; o item na compra de um cliente não sai, e a tela leva aos clientes', async () => {
    const montado = await montar('/catalogo', {
      conta: null,
      token: true,
      rotas: { 'POST /catalogo/cerveja-lata/arquivar': () => json(erroItemEmUsoDemo, 409) },
    });
    const linha = (await principal().findByText('Cerveja de malte, lata 350 ml')).closest('tr') as HTMLElement;
    fireEvent.click(within(linha).getByRole('button', { name: 'Alterar' }));
    const d = dialogo('Alterar o item');
    expect(d.getByText(/Arquivar não tem volta/u)).toBeTruthy();
    fireEvent.click(d.getByRole('button', { name: 'Arquivar o item…' }));
    expect(deRota(montado.pedidos, 'POST /catalogo/cerveja-lata/arquivar')).toHaveLength(0);
    fireEvent.click(d.getByRole('button', { name: 'Arquivar Cerveja de malte, lata 350 ml' }));
    expect(await d.findByRole('alert')).toHaveProperty('textContent', erroItemEmUsoDemo.detail);
    expect(d.getByText(erroItemEmUsoDemo.clientes[0]?.nome ?? '')).toBeTruthy();
    expect(d.getByRole('link', { name: /clientes empresa/u }).getAttribute('href')).toBe(ROTA_DOS_CLIENTES.caminho);
    expect(deRota(montado.pedidos, 'POST /catalogo/cerveja-lata/arquivar')[0]?.corpo).toEqual({ cnpj: catalogoDaDemo.empresa.cnpj });
  });
});

// ---------------------------------------------------------------------------
// Etapa 8: o item a partir da nota

describe('"Cadastrar este item" na tela de Notas', () => {
  function rotasDaNota(estado: { cadastrou: boolean }): Rotas {
    return {
      'POST /nfe/importar': () => json(importacao1001),
      [RECIBO]: () => json(estado.cadastrou ? recibo1001Cadastrado : recibo1001),
      'POST /catalogo/itens': () => {
        estado.cadastrou = true;
        return json(itemDaNota, 201);
      },
    };
  }

  async function importar(estado = { cadastrou: false }) {
    const montado = await montar('/notas', { catalogo: () => (estado.cadastrou ? catalogoComItens : catalogoDaEmpresaNova), rotas: rotasDaNota(estado) });
    const campo = await principal().findByLabelText('Arquivo XML da NF-e');
    await waitFor(() => {
      expect(campo).toHaveProperty('disabled', false);
    });
    fireEvent.change(campo, { target: { files: [new File(['<NFe/>'], 'nota.xml', { type: 'text/xml' })] } });
    fireEvent.click(principal().getByRole('button', { name: 'Importar nota' }));
    await principal().findByRole('heading', { name: 'Recibo da nota 1001' });
    return montado;
  }

  const linhaDe = (texto: string) => principal().getByText(texto).closest('li') as HTMLElement;

  it('a linha de código sem cadastro abre o cadastro com os dados dela; o item nasce com o custo da nota', async () => {
    const estado = { cadastrou: false };
    const { pedidos } = await importar(estado);
    const chocolate = linhaDe('Chocolate não recheado, barra 90 g');
    expect(chocolate.textContent).toMatch(/custo R\$\s3,50/u);
    fireEvent.click(within(chocolate).getByRole('button', { name: 'Cadastrar este item' }));
    const d = dialogo('Cadastrar este item');
    expect(d.getByLabelText('Descrição do item')).toHaveProperty('value', 'Chocolate não recheado, barra 90 g');
    expect(d.queryByLabelText('CNPJ do fornecedor')).toBeNull();
    expect(d.getByText(/O item nasce com o custo desta nota/u)).toBeTruthy();
    fireEvent.click(await d.findByRole('radio', { name: /^000001/u }));
    digitar(d.getByLabelText('Descrição do item'), 'Chocolate ao leite 90 g');
    digitar(d.getByLabelText('Preço de venda por unidade (R$)'), '4,20');
    digitar(d.getByLabelText('Margem-alvo (%)'), '20');
    fireEvent.click(d.getByRole('button', { name: 'Cadastrar o item' }));
    await principal().findByText(`Item cadastrado: ${itemDaNota.item.descricao}, com o custo desta nota.`);
    expect(deRota(pedidos, 'POST /catalogo/itens')[0]?.corpo).toEqual({
      cnpj: CNPJ,
      descricao: 'Chocolate ao leite 90 g',
      ncm: '18063210',
      cClassTrib: '000001',
      unidade: 'UN',
      cnpjFornecedor: EMITENTE,
      codigoFornecedor: 'AE-CHO-90',
      precoVenda: '4.20',
      margemAlvoPct: '20',
      daNota: { serie: '1', numero: '1001', nItem: 2 },
    });
    // O recibo é lido de novo (sem o XML), e a linha passa a citar o item.
    await principal().findByText(`Cadastrado no catálogo: ${itemDaNota.item.descricao}.`);
    expect(principal().getByText(/Depois, um item foi cadastrado a partir desta nota, com o custo dela\./u)).toBeTruthy();
    expect(deRota(pedidos, RECIBO)[0]?.busca.get('cnpj')).toBe(CNPJ);
  });

  it('a cerveja não entra (Imposto Seletivo): o diálogo diz por quê e não deixa enviar', async () => {
    await importar();
    fireEvent.click(within(linhaDe('Cerveja de malte, lata 350 ml')).getByRole('button', { name: 'Cadastrar este item' }));
    const d = dialogo('Cadastrar este item');
    await d.findByText(/O cadastro ainda não aceita itens com Imposto Seletivo:/u);
    expect(d.getByRole('button', { name: 'Cadastrar o item' })).toHaveProperty('disabled', true);
  });

  it('"Ver o recibo" na lista abre o recibo gravado, sem enviar o XML', async () => {
    const { pedidos } = await montar('/notas', { rotas: { [RECIBO]: () => json(recibo1001) } });
    fireEvent.click(await principal().findByRole('button', { name: 'Ver o recibo da nota 1001' }));
    await principal().findByRole('heading', { name: 'Recibo da nota 1001' });
    expect(principal().getByText('Recibo aberto')).toBeTruthy();
    expect(principal().queryByText(/já tinha sido importada/u)).toBeNull();
    expect(deRota(pedidos, 'POST /nfe/importar')).toHaveLength(0);
    expect(principal().getAllByRole('button', { name: 'Cadastrar este item' })).toHaveLength(3);
  });

  it('no modo mock, o botão da linha fica desligado e diz por quê', async () => {
    await montar('/notas', { conta: null, saude: SAUDE_MOCK, rotas: { [RECIBO]: () => json(recibo1001) } });
    fireEvent.click(await principal().findByRole('button', { name: 'Ver o recibo da nota 1001' }));
    await principal().findByRole('heading', { name: 'Recibo da nota 1001' });
    const [botao] = principal().getAllByRole('button', { name: 'Cadastrar este item' });
    expect(botao).toHaveProperty('disabled', true);
    expect(principal().getAllByText(/só leitura/u).length).toBeGreaterThan(0);
  });
});

// ---------------------------------------------------------------------------
// Etapa 9: os clientes empresa

describe('a página "Clientes empresa"', () => {
  it('na demonstração: o cliente, o município pelo nome, a compra em palavras e o caminho ao Regime', async () => {
    const { pedidos } = await montar(ROTA_DOS_CLIENTES.caminho, { conta: null });
    expect(await screen.findByRole('heading', { level: 1, name: ROTA_DOS_CLIENTES.nome })).toBeTruthy();
    const [cliente] = catalogoDaDemo.clientesB2B;
    const linha = (await principal().findByText(cliente?.nome ?? '')).closest('tr') as HTMLElement;
    await within(linha).findByText('Porto Alegre · RS');
    expect(within(linha).getByText(/Biscoito doce.*\(2485 UN\)/u)).toBeTruthy();
    expect(principal().getByRole('link', { name: 'Comparar no Regime' }).getAttribute('href')).toBe('/regime');
    // Sem o token nem o espaço, a demonstração não grava.
    expect(principal().getByRole('button', { name: 'Cadastrar cliente' })).toHaveProperty('disabled', true);
    expect(deRota(pedidos, 'GET /catalogo')[0]?.busca.get('cnpj')).toBe(catalogoDaDemo.empresa.cnpj);
  });

  it('o catálogo vazio não deixa montar a compra e leva ao Catálogo', async () => {
    await montar(ROTA_DOS_CLIENTES.caminho);
    await principal().findByText('Nenhum cliente empresa cadastrado.');
    expect(principal().getByRole('button', { name: 'Cadastrar cliente' })).toHaveProperty('disabled', true);
    expect(principal().getByText(FRASE_SEM_ITENS)).toBeTruthy();
    expect(principal().getByRole('link', { name: 'cadastre os itens' }).getAttribute('href')).toBe('/catalogo');
  });

  it('cadastrar: o CNPJ, o local e a compra conferidos na tela, e o pedido com o regime regular', async () => {
    let cadastrou = false;
    const { pedidos } = await montar(ROTA_DOS_CLIENTES.caminho, {
      catalogo: () => (cadastrou ? catalogoComCliente : catalogoComItens),
      rotas: {
        'POST /clientes': () => {
          cadastrou = true;
          return json(clienteCadastrado, 201);
        },
      },
    });
    fireEvent.click(await principal().findByRole('button', { name: 'Cadastrar cliente' }));
    const d = dialogo('Cadastrar cliente');
    fireEvent.click(d.getByRole('button', { name: 'Cadastrar o cliente' }));
    expect(d.getByText('Informe o CNPJ.')).toBeTruthy();
    expect(d.getByText('Informe a quantidade por mês de ao menos um item.')).toBeTruthy();
    digitar(d.getByLabelText('CNPJ do cliente'), CNPJ);
    digitar(d.getByLabelText('Razão social'), 'Mercado Exemplo Ltda');
    fireEvent.change(await d.findByLabelText('UF'), { target: { value: 'RS' } });
    await d.findByRole('option', { name: 'Porto Alegre' });
    fireEvent.change(d.getByLabelText('Município'), { target: { value: '4314902' } });
    digitar(d.getByLabelText('Chocolate ao leite 90 g'), '300');
    fireEvent.click(d.getByRole('button', { name: 'Cadastrar o cliente' }));
    expect(d.getByText('O cliente não pode ser a própria empresa.')).toBeTruthy();
    digitar(d.getByLabelText('CNPJ do cliente'), '11.222.333/0001-81');
    fireEvent.click(d.getByRole('button', { name: 'Cadastrar o cliente' }));
    await principal().findByText(`Cliente cadastrado: ${clienteCadastrado.cliente.nome}.`);
    expect(deRota(pedidos, 'POST /clientes')[0]?.corpo).toEqual({
      cnpj: CNPJ,
      cnpjCliente: '11222333000181',
      razaoSocial: 'Mercado Exemplo Ltda',
      regime: 'regime_regular',
      uf: 'RS',
      municipio: 4314902,
      compraMensal: [{ itemId: catalogoComItens.itens[0]?.id, quantidade: '300' }],
    });
    await principal().findByText('Mercado Exemplo Ltda');
  });

  it('a recusa da API (cliente repetido) aparece no diálogo', async () => {
    await montar(ROTA_DOS_CLIENTES.caminho, {
      catalogo: () => catalogoComItens,
      rotas: { 'POST /clientes': () => json(erroClienteRepetido, 409) },
    });
    fireEvent.click(await principal().findByRole('button', { name: 'Cadastrar cliente' }));
    const d = dialogo('Cadastrar cliente');
    digitar(d.getByLabelText('CNPJ do cliente'), '11222333000181');
    digitar(d.getByLabelText('Razão social'), 'Mercado Exemplo Ltda');
    fireEvent.change(await d.findByLabelText('UF'), { target: { value: 'RS' } });
    await d.findByRole('option', { name: 'Porto Alegre' });
    fireEvent.change(d.getByLabelText('Município'), { target: { value: '4314902' } });
    digitar(d.getByLabelText('Arroz tipo 1, pacote 5 kg'), '10');
    fireEvent.click(d.getByRole('button', { name: 'Cadastrar o cliente' }));
    expect(await d.findByRole('alert')).toHaveProperty('textContent', erroClienteRepetido.detail);
  });

  it('alterar manda só a compra que mudou; sem mudança, nada vai', async () => {
    const { pedidos } = await montar(ROTA_DOS_CLIENTES.caminho, {
      catalogo: () => catalogoComCliente,
      rotas: { 'PATCH /clientes/11222333000181': () => json(clienteAlterado) },
    });
    fireEvent.click(await principal().findByRole('button', { name: 'Alterar Mercado Exemplo Ltda' }));
    const d = dialogo('Alterar o cliente');
    await d.findByRole('option', { name: 'Porto Alegre' });
    expect(d.getByLabelText('Chocolate ao leite 90 g')).toHaveProperty('value', '300');
    fireEvent.click(d.getByRole('button', { name: 'Salvar o cliente' }));
    expect(d.getByText(FRASE_CLIENTE_SEM_MUDANCA)).toBeTruthy();
    expect(deRota(pedidos, 'PATCH /clientes/11222333000181')).toHaveLength(0);
    digitar(d.getByLabelText('Chocolate ao leite 90 g'), '250');
    digitar(d.getByLabelText('Arroz tipo 1, pacote 5 kg'), '40');
    fireEvent.click(d.getByRole('button', { name: 'Salvar o cliente' }));
    await principal().findByText(`Cliente salvo: ${clienteAlterado.cliente.nome}.`);
    expect(deRota(pedidos, 'PATCH /clientes/11222333000181')[0]?.corpo).toEqual({
      cnpj: CNPJ,
      compraMensal: [
        { itemId: catalogoComItens.itens[0]?.id, quantidade: '250' },
        { itemId: catalogoComItens.itens[1]?.id, quantidade: '40' },
      ],
    });
  });

  it('excluir confirma com o nome e manda o CNPJ da empresa', async () => {
    let excluiu = false;
    const { pedidos } = await montar(ROTA_DOS_CLIENTES.caminho, {
      catalogo: () => (excluiu ? catalogoComItens : catalogoComCliente),
      rotas: {
        'POST /clientes/11222333000181/excluir': () => {
          excluiu = true;
          return json(clienteExcluido);
        },
      },
    });
    fireEvent.click(await principal().findByRole('button', { name: 'Excluir Mercado Exemplo Ltda' }));
    const d = dialogo('Excluir o cliente');
    expect(d.getByText(/não guarda histórico de clientes/u)).toBeTruthy();
    fireEvent.click(d.getByRole('button', { name: 'Excluir Mercado Exemplo Ltda' }));
    await principal().findByText('Cliente excluído: Mercado Exemplo Ltda.');
    expect(deRota(pedidos, 'POST /clientes/11222333000181/excluir')[0]?.corpo).toEqual({ cnpj: CNPJ });
    await principal().findByText('Nenhum cliente empresa cadastrado.');
  });

  it('a conta sem empresa vê a primeira vez, como nas páginas da barra', async () => {
    await montar(ROTA_DOS_CLIENTES.caminho, { conta: CONTA_DE_TESTE });
    expect(await principal().findByRole('heading', { name: 'Cadastre a empresa para começar' })).toBeTruthy();
    expect(screen.getByRole('heading', { level: 1, name: ROTA_DOS_CLIENTES.nome })).toBeTruthy();
  });

  it('o Regime sem clientes leva ao cadastro deles', async () => {
    await montar('/regime', { catalogo: () => catalogoComItens });
    const link = await principal().findByRole('link', { name: 'Cadastrar um cliente' });
    expect(link.getAttribute('href')).toBe(ROTA_DOS_CLIENTES.caminho);
  });
});
