// C3b, etapas 3 a 5 (ADR 0018, seção da C3b): as configurações da empresa, a exclusão da empresa e o arquivo dos
// dados da conta, com respostas reais gravadas da API (src/teste/fixtures: modo real, motores RR 1.7.2 e SN 1.0.2,
// banco temporário, conta fictícia do domínio .test e o CNPJ do exemplo do Serpro). O fetch é falso.

import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from '../App.tsx';
import { carregarSessao } from '../sessao/acoes.ts';
import { NOME_DO_ARQUIVO_PADRAO, nomeDoArquivo, type Conta } from '../sessao/conta.ts';
import { reiniciarFocoDePagina } from '../shell/Pagina.tsx';
import { ROTA_DA_EMPRESA, ROTA_DO_CADASTRO } from '../shell/rotas.ts';
import catalogoDaDemo from '../teste/fixtures/catalogo.json';
import catalogoDaEmpresaNova from '../teste/fixtures/catalogo-empresa-nova.json';
import contaDados from '../teste/fixtures/conta-dados.json';
import empresaCadastrada from '../teste/fixtures/empresa-cadastrada.json';
import empresaConfigurada from '../teste/fixtures/empresa-configurada.json';
import empresaDasInformado from '../teste/fixtures/empresa-das-informado.json';
import empresaDasSimulacao from '../teste/fixtures/empresa-das-simulacao.json';
import erroExcluirCnpj from '../teste/fixtures/erro-empresa-excluir-cnpj.json';
import erroMunicipio from '../teste/fixtures/erro-empresa-municipio.json';
import erroSenha from '../teste/fixtures/erro-senha-errada.json';
import notasDaEmpresaNova from '../teste/fixtures/notas-empresa-nova.json';
import alertasDaEmpresaNova from '../teste/fixtures/alertas-empresa-nova.json';
import atividades from '../teste/fixtures/referencias-atividades.json';
import municipiosRs from '../teste/fixtures/referencias-municipios-rs.json';
import ufs from '../teste/fixtures/referencias-ufs.json';
import { CONTA_DE_TESTE, SAUDE_REAL, json, sessaoDeTeste } from '../teste/sessaoDeTeste.ts';
import { FRASE_ARQUIVO_BAIXADO } from './Conta.tsx';
import { FRASE_GUARDE_AS_NOTAS, FRASE_NADA_MUDOU, FRASE_SALVO, mudancasDosDados } from './ConfiguracoesDaEmpresa.tsx';
import { FRASE_DA_ALIQUOTA } from './regrasDeEntrada.ts';

const CNPJ = empresaCadastrada.empresa.cnpj;
const COM_EMPRESA: Conta = { ...CONTA_DE_TESTE, empresas: [CNPJ] };
const MEMBRO: Conta = { ...COM_EMPRESA, organizacao: { ...COM_EMPRESA.organizacao, papel: 'membro' } };
const DISPOSICAO = 'attachment; filename="contaai-dados-2026-11-28.json"';

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

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

interface Pedido {
  rota: string;
  corpo: unknown;
  comCookie: boolean;
}

type Extra = (pedido: Request) => Response | undefined;

async function montar(caminho: string, { conta = COM_EMPRESA, extra }: { conta?: Conta | null; extra?: Extra } = {}) {
  history.replaceState(null, '', caminho);
  const pedidos: Pedido[] = [];
  const sessao = sessaoDeTeste(async (pedido) => {
    const url = new URL(pedido.url);
    const rota = `${pedido.method} ${url.pathname}`;
    const texto = pedido.method === 'GET' ? '' : await pedido.clone().text();
    pedidos.push({ rota, corpo: texto === '' ? null : (JSON.parse(texto) as unknown), comCookie: pedido.credentials !== 'omit' });
    const especial = extra?.(pedido);
    if (especial) {
      return especial;
    }
    switch (rota) {
      case 'GET /saude':
        return json(SAUDE_REAL);
      case 'GET /conta':
        return conta === null ? json({ title: 'Unauthorized', status: 401, detail: 'Entre com a sua conta.' }, 401) : json(conta);
      case `GET /empresas/${CNPJ}`:
        return json(empresaCadastrada);
      case 'GET /referencias/ufs':
        return json(ufs);
      case 'GET /referencias/municipios':
        return json(municipiosRs);
      case 'GET /referencias/atividades':
        return json(atividades);
      case 'GET /catalogo':
        return json(pedido.credentials === 'omit' ? catalogoDaDemo : catalogoDaEmpresaNova);
      case 'GET /notas':
        return json(notasDaEmpresaNova);
      case 'GET /alertas':
        return json(alertasDaEmpresaNova);
      default:
        return json({ type: 'about:blank', title: 'Not Found', status: 404 }, 404);
    }
  });
  render(<App sessao={sessao} />);
  await act(() => carregarSessao(sessao));
  return { sessao, pedidos };
}

const principal = () => within(screen.getByRole('main'));
const barra = () => within(screen.getByRole('banner'));
const deRota = (pedidos: Pedido[], rota: string) => pedidos.filter((p) => p.rota === rota);
const PATCH = `PATCH /empresas/${CNPJ}`;
const EXCLUIR = `POST /empresas/${CNPJ}/excluir`;

/** Espera o formulário dos dados com os valores do GET /empresas (as listas dos motores já carregadas). */
async function formularioPronto() {
  await principal().findByRole('heading', { name: 'Dados da empresa' });
  await principal().findByRole('option', { name: 'Porto Alegre' });
  await principal().findByRole('radio', { name: /^Revenda de mercadorias/u });
}

describe('o caminho às configurações', () => {
  it('o menu da conta mostra as configurações só com a empresa cadastrada', async () => {
    await montar('/conta');
    fireEvent.click(barra().getByRole('button', { name: `Conta: ${CONTA_DE_TESTE.email}` }));
    const link = barra().getByRole('link', { name: ROTA_DA_EMPRESA.nome });
    expect(link.getAttribute('href')).toBe(ROTA_DA_EMPRESA.caminho);
    cleanup();
    await montar('/conta', { conta: CONTA_DE_TESTE });
    fireEvent.click(barra().getByRole('button', { name: `Conta: ${CONTA_DE_TESTE.email}` }));
    expect(barra().queryByRole('link', { name: ROTA_DA_EMPRESA.nome })).toBeNull();
  });

  it('o Painel da empresa da conta leva às configurações; o da demonstração, não', async () => {
    const { sessao } = await montar('/painel');
    expect((await principal().findByRole('link', { name: ROTA_DA_EMPRESA.nome })).getAttribute('href')).toBe('/empresa');
    act(() => {
      sessao.conta.verDemonstracao();
    });
    await principal().findByText(/Distribuidora Serra Azul/u);
    expect(principal().queryByRole('link', { name: ROTA_DA_EMPRESA.nome })).toBeNull();
  });
});

describe('a página "Configurações da empresa"', () => {
  it('sem conta: pede para entrar, sem pedir a empresa', async () => {
    const { pedidos } = await montar('/empresa', { conta: null });
    expect(await principal().findByText(/Entre para ver as configurações da empresa/u)).toBeTruthy();
    expect(pedidos.some((p) => p.rota.startsWith('GET /empresas'))).toBe(false);
  });

  it('a conta sem empresa leva ao cadastro', async () => {
    await montar('/empresa', { conta: CONTA_DE_TESTE });
    const link = await principal().findByRole('link', { name: ROTA_DO_CADASTRO.nome });
    expect(link.getAttribute('href')).toBe(ROTA_DO_CADASTRO.caminho);
  });

  it('o formulário vem com os dados gravados, e o GET leva o cookie', async () => {
    const { pedidos } = await montar('/empresa');
    await formularioPronto();
    expect(document.title).toBe('Configurações da empresa · ContaAI');
    expect(principal().getByText('12.ABC.345/01DE-35')).toBeTruthy();
    expect(principal().getByLabelText<HTMLInputElement>('Razão social').value).toBe('Mercearia Exemplo Ltda');
    expect(principal().getByRole<HTMLInputElement>('radio', { name: /^Simples tradicional/u }).checked).toBe(true);
    expect(principal().getByLabelText<HTMLSelectElement>('UF').value).toBe('RS');
    expect(principal().getByLabelText<HTMLSelectElement>('Município').value).toBe('4314902');
    expect(principal().getByRole<HTMLInputElement>('radio', { name: /^Revenda de mercadorias/u }).checked).toBe(true);
    const [lida] = deRota(pedidos, `GET /empresas/${CNPJ}`);
    expect(lida?.comCookie).toBe(true);
  });

  it('salvar sem mudar nada não chama a API', async () => {
    const { pedidos } = await montar('/empresa');
    await formularioPronto();
    fireEvent.click(principal().getByRole('button', { name: 'Salvar os dados' }));
    expect(await principal().findByText(FRASE_NADA_MUDOU)).toBeTruthy();
    expect(deRota(pedidos, PATCH)).toHaveLength(0);
  });

  it('salva só o que mudou, com o cookie, e mostra a empresa da resposta', async () => {
    const { pedidos } = await montar('/empresa', {
      extra: (p) => (p.method === 'PATCH' ? json(empresaConfigurada) : undefined),
    });
    await formularioPronto();
    fireEvent.change(principal().getByLabelText('Razão social'), { target: { value: ' Mercearia Exemplo Comércio Ltda ' } });
    fireEvent.click(principal().getByRole('radio', { name: /^Simples híbrido/u }));
    fireEvent.click(principal().getByRole('button', { name: 'Salvar os dados' }));
    expect(await principal().findByText(FRASE_SALVO)).toBeTruthy();
    const [patch] = deRota(pedidos, PATCH);
    expect(patch?.corpo).toEqual({ razaoSocial: 'Mercearia Exemplo Comércio Ltda', regimeAtual: 'simples_hibrido' });
    expect(patch?.comCookie).toBe(true);
    expect(principal().getByLabelText<HTMLInputElement>('Razão social').value).toBe('Mercearia Exemplo Comércio Ltda');
    expect(principal().getByRole<HTMLInputElement>('radio', { name: /^Simples híbrido/u }).checked).toBe(true);
  });

  it('a razão social vazia é recusada na tela, com o foco no campo', async () => {
    const { pedidos } = await montar('/empresa');
    await formularioPronto();
    fireEvent.change(principal().getByLabelText('Razão social'), { target: { value: '   ' } });
    fireEvent.click(principal().getByRole('button', { name: 'Salvar os dados' }));
    expect(await principal().findByText('Informe a razão social.')).toBeTruthy();
    expect(document.activeElement).toBe(principal().getByLabelText('Razão social'));
    expect(deRota(pedidos, PATCH)).toHaveLength(0);
  });

  it('trocar a UF limpa o município; a recusa do município pela API aparece no aviso', async () => {
    const { pedidos } = await montar('/empresa', {
      extra: (p) => (p.method === 'PATCH' ? json(erroMunicipio, 422) : undefined),
    });
    await formularioPronto();
    fireEvent.change(principal().getByLabelText('UF'), { target: { value: 'SP' } });
    expect(principal().getByLabelText<HTMLSelectElement>('Município').value).toBe('');
    fireEvent.click(principal().getByRole('button', { name: 'Salvar os dados' }));
    expect(await principal().findByText('Escolha o município.')).toBeTruthy();
    expect(deRota(pedidos, PATCH)).toHaveLength(0);
    // Volta ao RS e escolhe Porto Alegre de novo: o município vai com a UF, como o contrato pede.
    fireEvent.change(principal().getByLabelText('UF'), { target: { value: 'RS' } });
    await principal().findByRole('option', { name: 'Porto Alegre' });
    fireEvent.change(principal().getByLabelText('Município'), { target: { value: '4314902' } });
    fireEvent.change(principal().getByLabelText('Razão social'), { target: { value: 'Outra Ltda' } });
    fireEvent.click(principal().getByRole('button', { name: 'Salvar os dados' }));
    expect(await principal().findByText(erroMunicipio.detail)).toBeTruthy();
    expect(deRota(pedidos, PATCH)[0]?.corpo).toEqual({ razaoSocial: 'Outra Ltda' });
  });

  it('as alíquotas do DAS: a simulação é rotulada; um valor fora do formato não vai à API', async () => {
    const { pedidos } = await montar('/empresa');
    await formularioPronto();
    expect(principal().getByText(/valores de exemplo da simulação, rotulados em todo cálculo/u).textContent).not.toMatch(/\.\.$/u);
    expect(principal().getByLabelText<HTMLInputElement>('CBS no DAS (%)').value).toBe('1,1612');
    fireEvent.change(principal().getByLabelText('CBS no DAS (%)'), { target: { value: '100' } });
    fireEvent.click(principal().getByRole('button', { name: 'Salvar as alíquotas' }));
    expect(await principal().findByText(FRASE_DA_ALIQUOTA)).toBeTruthy();
    expect(deRota(pedidos, PATCH)).toHaveLength(0);
    expect(principal().queryByRole('button', { name: 'Voltar aos valores da simulação' })).toBeNull();
  });

  it('informar as alíquotas e voltar aos valores da simulação', async () => {
    let resposta: object = empresaDasInformado;
    const { pedidos } = await montar('/empresa', {
      extra: (p) => (p.method === 'PATCH' ? json(resposta) : undefined),
    });
    await formularioPronto();
    fireEvent.change(principal().getByLabelText('CBS no DAS (%)'), { target: { value: '1,2' } });
    fireEvent.change(principal().getByLabelText('IBS no DAS (%)'), { target: { value: '0,1%' } });
    fireEvent.click(principal().getByRole('button', { name: 'Salvar as alíquotas' }));
    expect(await principal().findByText('Hoje: as alíquotas informadas aqui. Fonte: Configurações da empresa.')).toBeTruthy();
    expect(deRota(pedidos, PATCH)[0]?.corpo).toEqual({ premissasDas: { pCBSSN: '1.2', pIBSSN: '0.1' } });
    resposta = empresaDasSimulacao;
    fireEvent.click(principal().getByRole('button', { name: 'Voltar aos valores da simulação' }));
    expect(await principal().findByText('As alíquotas voltaram aos valores da simulação.')).toBeTruthy();
    expect(deRota(pedidos, PATCH)[1]?.corpo).toEqual({ premissasDas: null });
    expect(principal().getByLabelText<HTMLInputElement>('CBS no DAS (%)').value).toBe('1,1612');
  });

  it('com as alíquotas do DAS informadas, trocar para uma atividade de outro anexo avisa; do mesmo anexo, não', async () => {
    await montar('/empresa', { extra: (p) => (p.url.endsWith(`/empresas/${CNPJ}`) && p.method === 'GET' ? json(empresaDasInformado) : undefined) });
    await formularioPronto();
    fireEvent.click(principal().getByRole('radio', { name: /^Operações com os demais bens materiais, sem incidência/u }));
    expect(principal().queryByText(/são do anexo I\./u)).toBeNull();
    fireEvent.click(principal().getByRole('radio', { name: /^Venda de mercadorias industrializadas pelo contribuinte, com/u }));
    expect(principal().getByText(/Esta atividade é do anexo II, e as alíquotas do DAS informadas são do anexo I\./u)).toBeTruthy();
  });

  it('com as alíquotas da simulação, trocar de anexo não avisa', async () => {
    await montar('/empresa');
    await formularioPronto();
    fireEvent.click(principal().getByRole('radio', { name: /^Venda de mercadorias industrializadas pelo contribuinte, com/u }));
    expect(principal().queryByText(/Esta atividade é do anexo/u)).toBeNull();
  });

  it('o membro vê os dados, sem formulários e sem a exclusão', async () => {
    const { pedidos } = await montar('/empresa', { conta: MEMBRO });
    expect(await principal().findByText('Só o dono da organização muda as configurações e exclui a empresa.')).toBeTruthy();
    expect(principal().getByText('Mercearia Exemplo Ltda')).toBeTruthy();
    expect(principal().getByText(/CBS 1,1612% · IBS 0,0129%/u)).toBeTruthy(); // sem arredondar
    expect(principal().queryByRole('button', { name: /Salvar/u })).toBeNull();
    expect(principal().queryByRole('button', { name: 'Excluir a empresa…' })).toBeNull();
    expect(pedidos.some((p) => p.rota === 'GET /referencias/atividades')).toBe(false);
  });

  it('quem estava vendo a demonstração volta aos dados da conta ao abrir a página', async () => {
    history.replaceState(null, '', '/painel');
    const { sessao } = await montar('/painel');
    act(() => {
      sessao.conta.verDemonstracao();
    });
    act(() => {
      history.pushState(null, '', '/empresa');
      dispatchEvent(new PopStateEvent('popstate'));
    });
    await formularioPronto();
    const estado = sessao.conta.obter();
    expect(estado.tipo === 'conectada' && estado.naDemo).toBe(false);
  });
});

describe('excluir a empresa', () => {
  async function abrir(extra?: Extra) {
    const montado = await montar('/empresa', extra ? { extra } : {});
    await formularioPronto();
    expect(principal().getByText(new RegExp(FRASE_GUARDE_AS_NOTAS, 'u'))).toBeTruthy();
    fireEvent.click(principal().getByRole('button', { name: 'Excluir a empresa…' }));
    await waitFor(() => {
      expect(document.activeElement).toBe(principal().getByLabelText('CNPJ da empresa'));
    });
    return montado;
  }

  it('o CNPJ digitado errado e a senha vazia são recusados na tela, sem ir à API', async () => {
    const { pedidos } = await abrir();
    fireEvent.change(principal().getByLabelText('CNPJ da empresa'), { target: { value: '11.222.333/0001-81' } });
    fireEvent.click(principal().getByRole('button', { name: 'Excluir a empresa' }));
    expect(await principal().findByText('O CNPJ digitado não é o desta empresa.')).toBeTruthy();
    expect(principal().getByText('Informe a senha.')).toBeTruthy();
    expect(deRota(pedidos, EXCLUIR)).toHaveLength(0);
  });

  it('certo: vai com a senha e o CNPJ sem a pontuação; a página diz que saiu, e a conta volta à primeira vez', async () => {
    const { pedidos, sessao } = await abrir((p) => (p.url.endsWith('/excluir') ? new Response(null, { status: 204 }) : undefined));
    fireEvent.change(principal().getByLabelText('CNPJ da empresa'), { target: { value: '12.abc.345/01de-35' } });
    fireEvent.change(principal().getByLabelText('Senha'), { target: { value: 'cavalo bateria grampo' } });
    fireEvent.click(principal().getByRole('button', { name: 'Excluir a empresa' }));
    expect(await principal().findByText('A empresa foi excluída')).toBeTruthy();
    const [excluir] = deRota(pedidos, EXCLUIR);
    expect(excluir?.corpo).toEqual({ senha: 'cavalo bateria grampo', cnpjConfirmacao: CNPJ });
    expect(excluir?.comCookie).toBe(true);
    const estado = sessao.conta.obter();
    expect(estado.tipo === 'conectada' && estado.conta.empresas).toEqual([]);
    expect(principal().getByRole('link', { name: ROTA_DO_CADASTRO.nome }).getAttribute('href')).toBe('/empresa/nova');
  });

  it('senha errada (401, a sessão continua): a frase da API, a senha limpa, e a conta é lida de novo', async () => {
    const { pedidos, sessao } = await abrir((p) => (p.url.endsWith('/excluir') ? json(erroSenha, 401) : undefined));
    fireEvent.change(principal().getByLabelText('CNPJ da empresa'), { target: { value: CNPJ } });
    fireEvent.change(principal().getByLabelText('Senha'), { target: { value: 'outra senha qualquer' } });
    fireEvent.click(principal().getByRole('button', { name: 'Excluir a empresa' }));
    expect(await principal().findByText(erroSenha.detail)).toBeTruthy();
    expect(principal().getByLabelText<HTMLInputElement>('Senha').value).toBe('');
    expect(deRota(pedidos, 'GET /conta')).toHaveLength(2);
    expect(sessao.conta.obter().tipo).toBe('conectada');
  });

  it('a recusa do CNPJ pela API aparece no aviso', async () => {
    await abrir((p) => (p.url.endsWith('/excluir') ? json(erroExcluirCnpj, 422) : undefined));
    fireEvent.change(principal().getByLabelText('CNPJ da empresa'), { target: { value: CNPJ } });
    fireEvent.change(principal().getByLabelText('Senha'), { target: { value: 'cavalo bateria grampo' } });
    fireEvent.click(principal().getByRole('button', { name: 'Excluir a empresa' }));
    expect(await principal().findByRole('alert')).toBeTruthy();
    expect(principal().getAllByText(erroExcluirCnpj.detail).length).toBeGreaterThan(0);
  });

  it('Cancelar fecha o formulário e devolve o foco ao botão', async () => {
    await abrir();
    fireEvent.change(principal().getByLabelText('Senha'), { target: { value: 'algo' } });
    fireEvent.click(principal().getByRole('button', { name: 'Cancelar' }));
    await waitFor(() => {
      expect(document.activeElement).toBe(principal().getByRole('button', { name: 'Excluir a empresa…' }));
    });
    expect(principal().queryByLabelText('Senha')).toBeNull();
  });
});

describe('baixar os seus dados (Sua conta)', () => {
  function espiarDownload() {
    const blobs: Blob[] = [];
    const nomes: string[] = [];
    vi.spyOn(URL, 'createObjectURL').mockImplementation((b) => {
      blobs.push(b as Blob);
      return 'blob:teste';
    });
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined);
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function clicar(this: HTMLAnchorElement) {
      nomes.push(this.download);
    });
    return { blobs, nomes };
  }

  async function abrir(extra: Extra) {
    const montado = await montar('/conta', { extra });
    fireEvent.click(await principal().findByRole('button', { name: 'Baixar os seus dados…' }));
    await waitFor(() => {
      expect(document.activeElement).toBe(principal().getByLabelText('Senha'));
    });
    return montado;
  }

  const DADOS = JSON.stringify(contaDados);

  it('com a senha: salva o JSON como a API mandou, com o nome do Content-Disposition', async () => {
    const { blobs, nomes } = espiarDownload();
    const { pedidos } = await abrir((p) =>
      p.url.endsWith('/conta/dados')
        ? new Response(DADOS, { status: 200, headers: { 'Content-Type': 'application/json', 'Content-Disposition': DISPOSICAO } })
        : undefined,
    );
    fireEvent.change(principal().getByLabelText('Senha'), { target: { value: 'cavalo bateria grampo' } });
    fireEvent.click(principal().getByRole('button', { name: 'Baixar o arquivo' }));
    expect(await principal().findByText(FRASE_ARQUIVO_BAIXADO)).toBeTruthy();
    expect(deRota(pedidos, 'POST /conta/dados')[0]?.corpo).toEqual({ senha: 'cavalo bateria grampo' });
    expect(nomes).toEqual(['contaai-dados-2026-11-28.json']);
    expect(blobs[0]?.type).toBe('application/json;charset=utf-8');
    expect(await blobs[0]?.text()).toBe(DADOS);
    expect(principal().queryByLabelText('Senha')).toBeNull();
  });

  it('senha vazia não vai à API; a senha errada mostra a frase e limpa o campo', async () => {
    espiarDownload();
    const { pedidos } = await abrir((p) => (p.url.endsWith('/conta/dados') ? json(erroSenha, 401) : undefined));
    fireEvent.click(principal().getByRole('button', { name: 'Baixar o arquivo' }));
    expect(await principal().findByText('Informe a senha.')).toBeTruthy();
    expect(deRota(pedidos, 'POST /conta/dados')).toHaveLength(0);
    fireEvent.change(principal().getByLabelText('Senha'), { target: { value: 'outra senha qualquer' } });
    fireEvent.click(principal().getByRole('button', { name: 'Baixar o arquivo' }));
    expect(await principal().findByText(erroSenha.detail)).toBeTruthy();
    expect(principal().getByLabelText<HTMLInputElement>('Senha').value).toBe('');
  });
});

describe('as regras', () => {
  it('o nome do arquivo: só o formato esperado, senão o padrão', () => {
    expect(nomeDoArquivo(DISPOSICAO)).toBe('contaai-dados-2026-11-28.json');
    expect(nomeDoArquivo(null)).toBe(NOME_DO_ARQUIVO_PADRAO);
    expect(nomeDoArquivo('attachment; filename="../../etc/passwd.json"')).toBe(NOME_DO_ARQUIVO_PADRAO);
    expect(nomeDoArquivo('attachment; filename="dados.exe"')).toBe(NOME_DO_ARQUIVO_PADRAO);
    expect(nomeDoArquivo('attachment; filename=".json"')).toBe(NOME_DO_ARQUIVO_PADRAO);
  });

  it('o PATCH leva só o que mudou, e a UF vai com o município', () => {
    const antes = { razaoSocial: 'A', regime: 'simples_tradicional' as const, uf: 'RS', municipio: '4314902', atividade: '01' }; // taste-skill-ignore: código oficial da atividade do Simples (cAtivSN), não é numeração
    expect(mudancasDosDados(antes, antes)).toEqual({});
    expect(mudancasDosDados(antes, { ...antes, razaoSocial: ' A ' })).toEqual({});
    expect(mudancasDosDados(antes, { ...antes, municipio: '4305108' })).toEqual({ uf: 'RS', municipio: 4305108 });
    expect(mudancasDosDados(antes, { ...antes, atividade: '03' })).toEqual({ cAtivSN: '03' }); // taste-skill-ignore: código oficial da atividade do Simples (cAtivSN), não é numeração
  });
});
