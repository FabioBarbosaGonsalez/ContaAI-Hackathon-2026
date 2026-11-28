import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from '../App.tsx';
import { carregarSessao } from '../sessao/acoes.ts';
import { Ancora } from '../shell/navegacao.tsx';
import { reiniciarFocoDePagina } from '../shell/Pagina.tsx';
import { TEXTO_DEMONSTRACAO } from '../shell/demonstracao.tsx';
import { CONTA_DE_TESTE, SAUDE_MOCK, SAUDE_REAL, json, sessaoDeTeste } from '../teste/sessaoDeTeste.ts';
import { AVISO_RASCUNHO, VERSAO_TERMOS, dataDaVersao } from './legal.ts';

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

afterEach(cleanup);

type Conta = typeof CONTA_DE_TESTE | null;

/** Abre a tela como o main.tsx: /saude, depois /conta. As outras rotas respondem 404 (não importam aqui). */
async function montar(caminho: string, { saude = SAUDE_REAL, conta = null as Conta } = {}) {
  history.replaceState(null, '', caminho);
  const sessao = sessaoDeTeste((pedido) => {
    const rota = new URL(pedido.url).pathname;
    if (rota === '/saude') {
      return json(saude);
    }
    if (rota === '/conta') {
      return conta === null ? json({ title: 'Unauthorized', status: 401, detail: 'Entre com a sua conta.' }, 401) : json(conta);
    }
    return json({ type: 'about:blank', title: 'Not Found', status: 404 }, 404);
  });
  render(<App sessao={sessao} />);
  await act(() => carregarSessao(sessao));
  return sessao;
}

const principal = () => within(screen.getByRole('main'));
const rotasPedidas = (pedidos: Request[]) => pedidos.map((p) => new URL(p.url).pathname);

describe('página inicial', () => {
  it('diz o que é o ContaAI, a frase de simulação e tem "Explorar a demonstração" como primeiro botão', async () => {
    await montar('/');
    expect(screen.getByRole('heading', { level: 1, name: 'Preço e margem na reforma tributária' })).toBeDefined();
    expect(document.title).toBe('Preço e margem na reforma tributária · ContaAI');
    expect(screen.getByText(/as alíquotas são premissas, e cada resultado mostra que é simulação/u)).toBeDefined();
    const acoes = principal().getAllByRole('link');
    expect(acoes[0]?.textContent).toBe('Explorar a demonstração');
    expect(acoes[0]?.getAttribute('href')).toBe('/painel');
    expect(screen.getByText('A demonstração não pede cadastro e usa uma distribuidora fictícia.')).toBeDefined();
  });

  it('a barra pública não tem os destinos do app nem a faixa da demonstração', async () => {
    await montar('/');
    expect(screen.queryByRole('navigation', { name: 'Principal' })).toBeNull();
    expect(screen.queryByText(TEXTO_DEMONSTRACAO)).toBeNull();
    expect(within(screen.getByRole('banner')).getByRole('link', { name: 'Explorar a demonstração' })).toBeDefined();
  });

  it('não pede dados da empresa', async () => {
    const sessao = await montar('/');
    expect(rotasPedidas(sessao.pedidos)).toEqual(['/saude', '/conta']);
  });

  it('explorar a demonstração abre o Painel, com a faixa de dados fictícios', async () => {
    await montar('/');
    fireEvent.click(principal().getByRole('link', { name: 'Explorar a demonstração' }));
    expect(location.pathname).toBe('/painel');
    expect(screen.getByRole('heading', { level: 1, name: 'Painel' })).toBeDefined();
    expect(screen.getByText(TEXTO_DEMONSTRACAO)).toBeDefined();
  });

  it('no modo mock, diz que a demonstração é só leitura', async () => {
    const sessao = await montar('/', { saude: SAUDE_MOCK });
    expect(screen.getByText('Nesta instalação, a demonstração é só leitura: nada é gravado.')).toBeDefined();
    // No mock, as rotas de conta dão 501: a tela nem pergunta.
    expect(rotasPedidas(sessao.pedidos)).toEqual(['/saude']);
  });

  it('o rodapé leva aos termos e à privacidade', async () => {
    await montar('/');
    const rodape = within(screen.getByRole('contentinfo'));
    expect(rodape.getByRole('link', { name: 'Termos de uso' }).getAttribute('href')).toBe('/termos');
    expect(rodape.getByRole('link', { name: 'Privacidade' }).getAttribute('href')).toBe('/privacidade');
  });
});

describe('termos de uso e privacidade', () => {
  it.each([
    ['/termos', 'Termos de uso', `Versão de ${dataDaVersao(VERSAO_TERMOS)}`],
    ['/privacidade', 'Privacidade', 'Atualizada em 27/11/2026'],
  ])('%s: título, data, aviso de rascunho e um índice igual às seções', async (caminho, titulo, data) => {
    await montar(caminho);
    expect(screen.getByRole('heading', { level: 1, name: titulo })).toBeDefined();
    expect(screen.getByText(data)).toBeDefined();
    expect(screen.getByText(AVISO_RASCUNHO)).toBeDefined();
    const indice = within(screen.getByRole('navigation', { name: 'Nesta página' }));
    const links = indice.getAllByRole('link');
    const secoes = principal()
      .getAllByRole('heading', { level: 2 })
      .filter((h) => h.id !== '');
    expect(links.map((l) => l.getAttribute('href'))).toEqual(secoes.map((h) => `#${h.id}`));
    expect(links.map((l) => l.textContent)).toEqual(secoes.map((h) => h.textContent));
  });

  it('quem responde é só "Equipe ContaAI", sem e-mail', async () => {
    for (const caminho of ['/termos', '/privacidade']) {
      cleanup();
      await montar(caminho);
      expect(principal().getAllByText('Equipe ContaAI.').length).toBeGreaterThan(0);
      expect(screen.getByRole('main').textContent).not.toMatch(/@|mailto:/u);
    }
  });

  it('a âncora do índice só aceita um id fixo e só monta o fragmento', () => {
    render(<Ancora id="termos-conta">A conta</Ancora>);
    expect(screen.getByRole('link', { name: 'A conta' }).getAttribute('href')).toBe('#termos-conta');
    // Um esquema de script, outra origem, maiúsculas, espaço e vazio.
    for (const id of [['java', 'script:alert(1)'].join(''), '//outro.site', 'Conta', 'a b', '']) {
      expect(() => render(<Ancora id={id}>x</Ancora>)).toThrow('Âncora com id fora do padrão');
    }
  });

  it('a privacidade lista os dois cookies e o id do espaço no localStorage', async () => {
    await montar('/privacidade');
    expect(screen.getByText('__Host-contaai_sessao')).toBeDefined();
    expect(screen.getByText('__Host-contaai_passe')).toBeDefined();
    expect(screen.getByText('contaai.espaco')).toBeDefined();
  });

  it('a privacidade diz que o log técnico não guarda o IP nem o CNPJ da rota (C3-B, etapa 7)', async () => {
    await montar('/privacidade');
    const texto = document.body.textContent;
    expect(texto).toMatch(/O log técnico da API registra.+sem o IP e sem dado pessoal/u);
    expect(screen.getByText('/empresas/{cnpj}')).toBeDefined();
    expect(texto).not.toMatch(/registrar, em log técnico, o IP/u);
  });
});

describe('a privacidade com a empresa da conta (C3a)', () => {
  it('diz o que fica guardado da empresa, que o XML não é guardado e o que vai às calculadoras', async () => {
    await montar('/privacidade');
    const texto = document.body.textContent;
    expect(texto).toMatch(/Quando você cadastra a empresa, ficam guardados também/u);
    expect(texto).toMatch(/o CNPJ, a razão social, o regime no Simples, a UF, o município, a atividade e as alíquotas do DAS/u);
    expect(texto).toMatch(/O arquivo XML não é guardado/u);
    expect(texto).toMatch(/nunca o CNPJ, a razão social ou um dado pessoal/u);
    expect(texto).toMatch(/A empresa e os dados dela: até o dono excluir a empresa, e no máximo enquanto a organização existir/u);
  });
});

describe('a privacidade com as telas da C3b', () => {
  it('os direitos levam a baixar os dados e a excluir a empresa, onde as telas estão', async () => {
    await montar('/privacidade');
    const texto = document.body.textContent;
    expect(texto).toMatch(/baixar os seus dados: em “Sua conta”, com a senha/u);
    expect(texto).toMatch(/excluir a empresa: em “Configurações da empresa”, no mesmo menu, com a senha e o CNPJ digitado/u);
  });
});

describe('conta conectada (C2a)', () => {
  it('nas páginas do app, a conta sem empresa mostra a primeira vez e não pede o CNPJ da demonstração (C3a)', async () => {
    const sessao = await montar('/painel', { conta: CONTA_DE_TESTE });
    expect(screen.getByRole('heading', { level: 1, name: 'Painel' })).toBeDefined();
    expect(screen.getByRole('heading', { level: 2, name: 'Cadastre a empresa para começar' })).toBeDefined();
    expect(principal().getByRole('link', { name: 'Cadastrar a empresa' }).getAttribute('href')).toBe('/empresa/nova');
    expect(screen.queryByText(TEXTO_DEMONSTRACAO)).toBeNull();
    expect(within(screen.getByRole('banner')).getByText(CONTA_DE_TESTE.organizacao.nome)).toBeDefined();
    expect(rotasPedidas(sessao.pedidos)).toEqual(['/saude', '/conta']);
  });

  it('ver a demonstração: os pedidos de dados saem sem o cookie, e a faixa volta à conta', async () => {
    const sessao = await montar('/painel', { conta: CONTA_DE_TESTE });
    fireEvent.click(principal().getByRole('link', { name: 'Explorar a demonstração' }));
    expect(sessao.conta.obter()).toMatchObject({ tipo: 'conectada', naDemo: true });
    await screen.findByText(TEXTO_DEMONSTRACAO);
    const dados = sessao.pedidos.filter((p) => !['/saude', '/conta'].includes(new URL(p.url).pathname));
    expect(dados.length).toBeGreaterThan(0);
    expect(new Set(dados.map((p) => p.credentials))).toEqual(new Set(['omit']));

    fireEvent.click(screen.getByRole('link', { name: 'Voltar à minha conta' }));
    expect(sessao.conta.naConta()).toBe(true);
    expect(screen.getByRole('heading', { level: 2, name: 'Cadastre a empresa para começar' })).toBeDefined();
  });

  it('na página inicial, quem tem conta também vê o caminho ao Painel (e não "Minha conta", que lembra "Sua conta")', async () => {
    await montar('/', { conta: CONTA_DE_TESTE });
    const acoes = principal().getAllByRole('link');
    expect(acoes.map((a) => a.textContent).slice(0, 2)).toEqual(['Explorar a demonstração', 'Ir ao Painel']);
    expect(within(screen.getByRole('banner')).getByRole('link', { name: 'Ir ao Painel' })).toBeDefined();
    expect(screen.queryByText('Minha conta')).toBeNull();
  });

  it('a sessão que acaba avisa na faixa e volta à demonstração', async () => {
    const sessao = await montar('/painel', { conta: CONTA_DE_TESTE });
    act(() => {
      sessao.conta.marcarEncerrada();
    });
    expect(screen.getByText(/Sua sessão terminou, e você voltou à demonstração/u)).toBeDefined();
    fireEvent.click(screen.getByRole('button', { name: 'Entendi' }));
    expect(screen.getByText(TEXTO_DEMONSTRACAO)).toBeDefined();
  });

  it('o nome da organização vem como texto, nunca como HTML', async () => {
    const conta = { ...CONTA_DE_TESTE, organizacao: { ...CONTA_DE_TESTE.organizacao, nome: '<img src=x onerror=alert(1)>' } };
    await montar('/painel', { conta });
    expect(within(screen.getByRole('banner')).getByText('<img src=x onerror=alert(1)>')).toBeDefined();
    expect(document.querySelector('img')).toBeNull();
  });
});
