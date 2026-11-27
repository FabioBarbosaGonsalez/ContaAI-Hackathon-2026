// C3a (ADR 0018): a primeira vez, o cadastro da empresa e as telas com a empresa nova, com respostas reais gravadas
// da API (src/teste/fixtures: modo real, motores RR 1.7.2 e SN 1.0.2, banco temporário, CNPJ do exemplo do Serpro).
// O fetch é falso: os testes conferem o que a tela pede e o que ela mostra.

import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from '../App.tsx';
import { CABECALHO_ESPACO } from '../api/cliente.ts';
import { carregarSessao } from '../sessao/acoes.ts';
import type { Conta } from '../sessao/conta.ts';
import { reiniciarFocoDePagina } from '../shell/Pagina.tsx';
import { ROTAS, ROTAS_PUBLICAS, ROTA_DA_CONTA, ROTA_DO_CADASTRO } from '../shell/rotas.ts';
import alertasDaEmpresaNova from '../teste/fixtures/alertas-empresa-nova.json';
import catalogoDaDemo from '../teste/fixtures/catalogo.json';
import catalogoDaEmpresaNova from '../teste/fixtures/catalogo-empresa-nova.json';
import empresaCadastrada from '../teste/fixtures/empresa-cadastrada.json';
import erroEmpresaDigito from '../teste/fixtures/erro-empresa-digito.json';
import erroEmpresaRepetida from '../teste/fixtures/erro-empresa-repetida.json';
import reciboDaEmpresaNova from '../teste/fixtures/nfe-importar-empresa-nova.json';
import notasDaEmpresaNova from '../teste/fixtures/notas-empresa-nova.json';
import notasSemPar from '../teste/fixtures/notas-empresa-nova-sem-par.json';
import atividades from '../teste/fixtures/referencias-atividades.json';
import municipiosRs from '../teste/fixtures/referencias-municipios-rs.json';
import ufs from '../teste/fixtures/referencias-ufs.json';
import { CONTA_DE_TESTE, SAUDE_MOCK, SAUDE_REAL, json, sessaoDeTeste } from '../teste/sessaoDeTeste.ts';

const CNPJ = empresaCadastrada.empresa.cnpj;
const COM_EMPRESA: Conta = { ...CONTA_DE_TESTE, empresas: [CNPJ] };
const MEMBRO: Conta = { ...CONTA_DE_TESTE, organizacao: { ...CONTA_DE_TESTE.organizacao, papel: 'membro' } };

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
});

afterEach(cleanup);

type Extra = (pedido: Request) => Response | undefined;

interface Opcoes {
  saude?: object;
  conta?: Conta | null;
  naDemo?: boolean;
  extra?: Extra;
}

/** Abre a tela como o main.tsx (/saude, depois /conta), com a API falsa das fixtures. */
async function montar(caminho: string, { saude = SAUDE_REAL, conta = CONTA_DE_TESTE, naDemo = false, extra }: Opcoes = {}) {
  history.replaceState(null, '', caminho);
  const sessao = sessaoDeTeste((pedido) => {
    const especial = extra?.(pedido);
    if (especial) {
      return especial;
    }
    const url = new URL(pedido.url);
    const naConta = pedido.credentials !== 'omit';
    switch (`${pedido.method} ${url.pathname}`) {
      case 'GET /saude':
        return json(saude);
      case 'GET /conta':
        return conta === null ? json({ title: 'Unauthorized', status: 401, detail: 'Entre com a sua conta.' }, 401) : json(conta);
      case 'GET /referencias/ufs':
        return json(ufs);
      case 'GET /referencias/municipios':
        return url.searchParams.get('uf') === 'RS'
          ? json(municipiosRs)
          : json({ uf: url.searchParams.get('uf'), municipios: [], fonte: municipiosRs.fonte });
      case 'GET /referencias/atividades':
        return json(atividades);
      case 'POST /empresas':
        return json(empresaCadastrada, 201);
      case 'GET /catalogo':
        return json(naConta ? catalogoDaEmpresaNova : catalogoDaDemo);
      case 'GET /notas':
        return json(notasDaEmpresaNova);
      case 'GET /alertas':
        return json(alertasDaEmpresaNova);
      case 'POST /nfe/importar':
        return json(reciboDaEmpresaNova);
      default:
        return json({ type: 'about:blank', title: 'Not Found', status: 404 }, 404);
    }
  });
  render(<App sessao={sessao} />);
  await act(() => carregarSessao(sessao));
  if (naDemo) {
    act(() => {
      sessao.conta.verDemonstracao();
    });
  }
  return sessao;
}

const principal = () => within(screen.getByRole('main'));
const rota = (p: Request) => `${p.method} ${new URL(p.url).pathname}`;
const CAMINHOS = new Set<string>([...ROTAS, ...ROTAS_PUBLICAS, ROTA_DA_CONTA, ROTA_DO_CADASTRO].map((r) => r.caminho));

function conferirLinks() {
  for (const link of screen.getAllByRole('link', { hidden: true })) {
    const href = link.getAttribute('href') ?? '';
    expect(CAMINHOS.has(href) || href === '#conteudo', href).toBe(true);
  }
}

/** Preenche o formulário inteiro com os dados da empresa gravada (Porto Alegre, atividade 01). */
async function preencher({ cnpj = '12.abc.345/01de-35' } = {}) {
  fireEvent.change(principal().getByLabelText('CNPJ'), { target: { value: cnpj } });
  fireEvent.change(principal().getByLabelText('Razão social'), { target: { value: '  Mercearia Exemplo Ltda ' } });
  fireEvent.click(principal().getByRole('radio', { name: /^Simples tradicional/u }));
  const uf = await principal().findByRole('option', { name: 'RS · RIO GRANDE DO SUL' });
  fireEvent.change(principal().getByLabelText('UF'), { target: { value: uf.getAttribute('value') } });
  await principal().findByRole('option', { name: 'Porto Alegre' });
  fireEvent.change(principal().getByLabelText('Município'), { target: { value: '4314902' } });
  fireEvent.click(principal().getByRole('radio', { name: /^Revenda de mercadorias/u }));
}

describe('a primeira vez (C3a)', () => {
  it.each(ROTAS.filter((r) => r.caminho !== '/contador'))(
    '$caminho: o dono vê o caminho para o cadastro, e nenhum dado da empresa é pedido',
    async ({ caminho, nome }) => {
      const sessao = await montar(caminho);
      expect(screen.getByRole('heading', { level: 1, name: nome })).toBeDefined();
      expect(principal().getByRole('heading', { level: 2, name: 'Cadastre a empresa para começar' })).toBeDefined();
      expect(principal().getByRole('link', { name: 'Cadastrar a empresa' }).getAttribute('href')).toBe('/empresa/nova');
      expect(principal().getByRole('link', { name: 'Explorar a demonstração' })).toBeDefined();
      expect(sessao.pedidos.map(rota)).toEqual(['GET /saude', 'GET /conta']);
      conferirLinks();
    },
  );

  it('o membro fica sabendo que só o dono cadastra, sem o caminho do cadastro', async () => {
    await montar('/painel', { conta: MEMBRO });
    expect(principal().getByText(/Só o dono da organização cadastra a empresa/u)).toBeDefined();
    expect(principal().queryByRole('link', { name: 'Cadastrar a empresa' })).toBeNull();
  });
});

describe('a página "Cadastrar a empresa" (C3a)', () => {
  it('sem conta: pede para entrar, sem o formulário e sem pedir as referências', async () => {
    const sessao = await montar('/empresa/nova', { conta: null });
    expect(screen.getByRole('heading', { level: 1, name: 'Cadastrar a empresa' })).toBeDefined();
    expect(principal().getByText('Entre para cadastrar a sua empresa.')).toBeDefined();
    expect(principal().getByRole('link', { name: 'Entrar' })).toBeDefined();
    expect(principal().queryByLabelText('CNPJ')).toBeNull();
    expect(sessao.pedidos.map(rota)).toEqual(['GET /saude', 'GET /conta']);
  });

  it('no modo mock: as contas não existem nesta instalação', async () => {
    await montar('/empresa/nova', { saude: SAUDE_MOCK });
    expect(principal().getByText(/as contas não existem/u)).toBeDefined();
    expect(principal().queryByLabelText('CNPJ')).toBeNull();
  });

  it('o formulário: as listas vêm dos motores, com a fonte, e o município espera a UF', async () => {
    await montar('/empresa/nova');
    expect(await principal().findByRole('option', { name: 'RS · RIO GRANDE DO SUL' })).toBeDefined();
    expect(principal().getAllByRole('option').filter((o) => o.closest('select')?.name === 'uf')).toHaveLength(ufs.ufs.length + 1);
    expect(principal().getByText(`Fonte: ${ufs.fonte}`)).toBeDefined();
    const municipio = principal().getByLabelText<HTMLSelectElement>('Município');
    expect(municipio.disabled).toBe(true);
    expect(principal().getByText('Escolha a UF primeiro.')).toBeDefined();
    for (const a of atividades.atividades) {
      expect(principal().getByRole('radio', { name: new RegExp(`^${a.descricao}`, 'u') })).toBeDefined();
    }
    expect(principal().getByText(new RegExp(atividades.fonte.replace(/[.*+?^${}()|[\]\\]/gu, '\\$&'), 'u'))).toBeDefined();
    expect(principal().getByRole('radio', { name: /^Simples híbrido.+LC 214\/2025, art\. 41, §3º/u })).toBeDefined();
    // O quadro ao lado diz a data do cenário, da resposta das atividades.
    expect(principal().getByRole('complementary', { name: 'O que o ContaAI faz com estes dados' }).textContent).toContain(
      '16/03/2027',
    );
    conferirLinks();
  });

  it('enviar vazio: cada campo diz o que falta, o foco vai ao CNPJ, e nada vai à API', async () => {
    const sessao = await montar('/empresa/nova');
    await principal().findByRole('option', { name: 'RS · RIO GRANDE DO SUL' });
    fireEvent.click(principal().getByRole('button', { name: 'Cadastrar a empresa' }));
    expect(principal().getByText('Informe o CNPJ.')).toBeDefined();
    expect(principal().getByText('Informe a razão social.')).toBeDefined();
    expect(principal().getByText('Escolha o regime da empresa no Simples Nacional.')).toBeDefined();
    expect(principal().getByText('Escolha a UF.')).toBeDefined();
    expect(principal().getByText('Escolha o município.')).toBeDefined();
    expect(principal().getByText('Escolha a atividade da empresa.')).toBeDefined();
    expect(document.activeElement).toBe(principal().getByLabelText('CNPJ'));
    expect(principal().getByLabelText('CNPJ').getAttribute('aria-invalid')).toBe('true');
    expect(sessao.pedidos.filter((p) => rota(p) === 'POST /empresas')).toHaveLength(0);

    // Corrigido o campo, o erro dele some (os outros ficam até o próximo envio).
    fireEvent.change(principal().getByLabelText('CNPJ'), { target: { value: '1' } });
    expect(principal().queryByText('Informe o CNPJ.')).toBeNull();
    expect(principal().getByLabelText('CNPJ').getAttribute('aria-invalid')).toBeNull();
    expect(principal().getByText('Informe a razão social.')).toBeDefined();
  });

  it('o dígito errado é recusado na tela, com a mesma frase da API, sem ir à API', async () => {
    const sessao = await montar('/empresa/nova');
    await preencher({ cnpj: '12ABC34501DE36' });
    fireEvent.click(principal().getByRole('button', { name: 'Cadastrar a empresa' }));
    expect(principal().getByText(erroEmpresaDigito.detail)).toBeDefined();
    expect(document.activeElement).toBe(principal().getByLabelText('CNPJ'));
    expect(sessao.pedidos.filter((p) => rota(p) === 'POST /empresas')).toHaveLength(0);
  });

  it('cadastra: o CNPJ vai sem a pontuação e em maiúsculas, com o cookie, e a tela abre o Painel da empresa nova', async () => {
    const sessao = await montar('/empresa/nova');
    await preencher();
    fireEvent.click(principal().getByRole('button', { name: 'Cadastrar a empresa' }));
    await waitFor(() => {
      expect(location.pathname).toBe('/painel');
    });
    const envio = sessao.pedidos.find((p) => rota(p) === 'POST /empresas');
    expect(envio?.credentials).toBe('same-origin');
    expect(JSON.parse((await envio?.clone().text()) ?? '{}')).toEqual({
      cnpj: CNPJ,
      razaoSocial: 'Mercearia Exemplo Ltda',
      regimeAtual: 'simples_tradicional',
      uf: 'RS',
      municipio: 4314902,
      cAtivSN: '01', // taste-skill-ignore: código oficial da atividade do Simples (cAtivSN), não é numeração
    });
    expect(sessao.conta.obter()).toMatchObject({ conta: { empresas: [CNPJ] } });

    // O Painel da empresa nova: os dados do cadastro e o catálogo vazio, sem pedir cálculo.
    expect(await principal().findByText('Nenhum item no catálogo ainda.')).toBeDefined();
    const empresa = principal().getByRole('region', { name: 'A empresa' });
    expect(within(empresa).getByText('12.ABC.345/01DE-35')).toBeDefined();
    expect(within(empresa).getByText('Porto Alegre · RS')).toBeDefined();
    expect(within(empresa).getByText('Simples tradicional')).toBeDefined();
    expect(screen.getByText(`Mercearia Exemplo Ltda · ${catalogoDaEmpresaNova.cenario.descricao}`)).toBeDefined();
    const dados = sessao.pedidos.filter((p) => ['GET /catalogo', 'GET /alertas'].includes(rota(p)));
    expect(dados.length).toBeGreaterThan(0);
    for (const p of dados) {
      expect(new URL(p.url).searchParams.get('cnpj')).toBe(CNPJ);
      expect(p.credentials).toBe('same-origin');
      expect(p.headers.get(CABECALHO_ESPACO)).toBeNull();
    }
    expect(sessao.pedidos.filter((p) => rota(p) === 'POST /carrinho/calcular')).toHaveLength(0);
  });

  it('a recusa da API aparece no aviso; o 409 lê a conta de novo e leva ao Painel', async () => {
    const sessao = await montar('/empresa/nova', {
      extra: (p) => (rota(p) === 'POST /empresas' ? json(erroEmpresaRepetida, 409) : undefined),
    });
    await preencher();
    fireEvent.click(principal().getByRole('button', { name: 'Cadastrar a empresa' }));
    const aviso = await principal().findByRole('alert');
    expect(aviso.textContent).toBe(erroEmpresaRepetida.detail);
    await waitFor(() => {
      expect(document.activeElement).toBe(aviso);
    });
    expect(principal().getByRole('link', { name: 'Ir ao Painel' })).toBeDefined();
    await waitFor(() => {
      expect(sessao.pedidos.filter((p) => rota(p) === 'GET /conta')).toHaveLength(2);
    });
  });

  it('com a empresa já cadastrada, a página leva ao Painel (uma por conta até o seletor do 3c)', async () => {
    const sessao = await montar('/empresa/nova', { conta: COM_EMPRESA });
    expect(principal().getByText('A empresa da sua conta já está cadastrada.')).toBeDefined();
    expect(principal().getByRole('link', { name: 'Ir ao Painel' }).getAttribute('href')).toBe('/painel');
    expect(principal().queryByLabelText('CNPJ')).toBeNull();
    expect(sessao.pedidos.some((p) => rota(p).includes('/referencias/'))).toBe(false);
  });

  it('o membro não vê o formulário', async () => {
    await montar('/empresa/nova', { conta: MEMBRO });
    expect(principal().getByText('Só o dono da organização cadastra a empresa.')).toBeDefined();
    expect(principal().queryByLabelText('CNPJ')).toBeNull();
  });

  it('quem estava vendo a demonstração volta aos dados da conta ao abrir a página', async () => {
    const sessao = await montar('/empresa/nova', { naDemo: true });
    await waitFor(() => {
      expect(sessao.conta.naConta()).toBe(true);
    });
    expect(screen.queryByText(/Demonstração: a empresa, as notas e o cliente são fictícios/u)).toBeNull();
  });
});

describe('as telas com a empresa nova (C3a)', () => {
  it('o Catálogo vazio diz que não há itens, sem a troca de regime, sem as premissas e sem cálculo', async () => {
    const sessao = await montar('/catalogo', { conta: COM_EMPRESA });
    expect(await principal().findByText('Nenhum item no catálogo ainda.')).toBeDefined();
    expect(principal().queryByRole('group', { name: /regime/iu })).toBeNull();
    expect(principal().queryByRole('region', { name: 'Premissas do cálculo' })).toBeNull();
    expect(screen.getByText(catalogoDaEmpresaNova.cenario.descricao)).toBeDefined();
    expect(sessao.pedidos.filter((p) => rota(p) === 'POST /carrinho/calcular')).toHaveLength(0);
  });

  it('as Notas da empresa nova: sem as notas de exemplo da Serra Azul, e a importação liberada', async () => {
    await montar('/notas', { conta: COM_EMPRESA });
    expect(await principal().findByText('Nenhuma nota importada ainda.')).toBeDefined();
    expect(principal().queryByText(/Notas de exemplo para baixar/u)).toBeNull();
    expect(principal().getByLabelText<HTMLInputElement>('Arquivo XML da NF-e').disabled).toBe(false);
  });

  it('na demonstração, as notas de exemplo continuam', async () => {
    await montar('/notas', { conta: null });
    expect(await principal().findByText(/Notas de exemplo para baixar/u)).toBeDefined();
  });

  it('importar uma nota na empresa nova: vai com o cookie, e o recibo diz que nenhum item casou', async () => {
    const sessao = await montar('/notas', { conta: COM_EMPRESA });
    await principal().findByText('Nenhuma nota importada ainda.');
    const campo = principal().getByLabelText<HTMLInputElement>('Arquivo XML da NF-e');
    fireEvent.change(campo, { target: { files: [new File(['<NFe/>'], 'nota.xml', { type: 'text/xml' })] } });
    fireEvent.click(principal().getByRole('button', { name: 'Importar nota' }));
    expect(await principal().findByText(/Nenhum item da nota 1002 casou com o catálogo/u)).toBeDefined();
    const envio = sessao.pedidos.find((p) => rota(p) === 'POST /nfe/importar');
    expect(envio?.credentials).toBe('same-origin');
    expect(envio?.headers.get(CABECALHO_ESPACO)).toBeNull();
  });

  it('o Painel depois de uma nota toda sem par diz qual foi a nota, e não "nenhuma nota" (achado da C3a)', async () => {
    const sessao = await montar('/painel', {
      conta: COM_EMPRESA,
      extra: (p) => (rota(p) === 'GET /notas' ? json(notasSemPar) : undefined),
    });
    const bloco = await principal().findByRole('region', { name: 'Última nota de compra' });
    await waitFor(() => {
      expect(bloco.textContent).toContain('nenhum item casou com o catálogo (3 sem par)');
    });
    expect(bloco.textContent).toContain('Nota 1002, de 16/03/2027');
    expect(bloco.textContent).not.toContain('Nenhuma nota importada ainda.');
    expect(sessao.pedidos.filter((p) => rota(p) === 'GET /notas')).toHaveLength(1);
  });

  it('o Painel da demonstração, com o custo da nota no catálogo, não pede a lista das notas', async () => {
    const sessao = await montar('/painel', { conta: null });
    const bloco = await principal().findByRole('region', { name: 'Última nota de compra' });
    await waitFor(() => {
      expect(bloco.textContent).toMatch(/atualizou o custo de/u);
    });
    expect(sessao.pedidos.filter((p) => rota(p) === 'GET /notas')).toHaveLength(0);
  });

  it('o Regime da empresa nova: nenhum cliente empresa, sem pedir a comparação', async () => {
    const sessao = await montar('/regime', { conta: COM_EMPRESA });
    expect(await principal().findByText('Nenhum cliente empresa cadastrado.')).toBeDefined();
    expect(sessao.pedidos.filter((p) => rota(p) === 'POST /regime/comparar')).toHaveLength(0);
  });

  it('com a conta vendo a demonstração, os dados são os da Serra Azul, sem o cookie', async () => {
    const sessao = await montar('/painel', { conta: COM_EMPRESA });
    await principal().findByText('Nenhum item no catálogo ainda.');
    const antes = sessao.pedidos.length;
    act(() => {
      sessao.conta.verDemonstracao();
    });
    await waitFor(() => {
      expect(sessao.pedidos.slice(antes).some((p) => rota(p) === 'GET /catalogo')).toBe(true);
    });
    const catalogo = sessao.pedidos.slice(antes).filter((p) => rota(p) === 'GET /catalogo');
    expect(catalogo.map((p) => new URL(p.url).searchParams.get('cnpj'))).toEqual([catalogoDaDemo.empresa.cnpj]);
    expect(catalogo.map((p) => p.credentials)).toEqual(['omit']);
  });
});
