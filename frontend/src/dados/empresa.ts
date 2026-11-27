// Os dados de uma empresa na tela: catálogo, cálculo por regime e alertas, e se a tela pode gravar.
//
// De quem são os dados (C3a, ADR 0018):
// - na demonstração (compartilhada, num espaço, ou quem tem conta e escolheu vê-la): a Distribuidora Serra Azul ME
//   (fictícia, data/demo);
// - na conta: a empresa que a organização cadastrou. Até o seletor do 3c, a primeira do GET /conta (em ordem de
//   CNPJ). Sem empresa, nenhuma tela pede dados: a primeira vez leva ao cadastro.

import { chamar, type ClienteApi, type Resposta } from '../api/cliente.ts';
import type { Conta } from '../sessao/conta.ts';
import { useSessao } from '../sessao/contexto.tsx';
import { useConta, useEspaco, useModo, useTemToken } from '../sessao/ganchos.ts';
import {
  pedidoDeRegime,
  pedidoDoCatalogo,
  type Alerta,
  type Carrinho,
  type Catalogo,
  type ClienteB2B,
  type Comparacao,
  type Notas,
  type ReciboNota,
  type Regime,
} from './pedidos.ts';
import { useRecurso, type EstadoRecurso } from './recurso.ts';

/** CNPJ fictício da distribuidora da demonstração (data/demo/distribuidora.json). */
export const CNPJ_DEMONSTRACAO = '36817420000113';

export type EmpresaDaTela =
  /** A API ainda não respondeu ao /saude ou, no modo real, a tela ainda não sabe se há conta. */
  | { tipo: 'esperando' }
  | { tipo: 'demonstracao'; cnpj: string }
  | { tipo: 'conta'; cnpj: string; organizacao: string }
  /** A conta ainda não cadastrou a empresa. Só o dono cadastra (ADR 0017, etapa 8). */
  | { tipo: 'sem-empresa'; papel: Conta['organizacao']['papel'] };

/** A empresa cujos dados a tela mostra: a fonte única do CNPJ de todo pedido de dados. */
export function useEmpresaDaTela(): EmpresaDaTela {
  const modo = useModo();
  const conta = useConta();
  if (modo.tipo !== 'pronto' || conta.tipo === 'carregando') {
    return { tipo: 'esperando' };
  }
  if (conta.tipo === 'conectada' && !conta.naDemo) {
    const [cnpj] = conta.conta.empresas;
    const { organizacao } = conta.conta;
    return cnpj === undefined
      ? { tipo: 'sem-empresa', papel: organizacao.papel }
      : { tipo: 'conta', cnpj, organizacao: organizacao.id };
  }
  return { tipo: 'demonstracao', cnpj: CNPJ_DEMONSTRACAO };
}

/** O CNPJ da empresa da tela, ou null quando nenhum dado deve ser pedido. */
export function useCnpjDaTela(): string | null {
  const empresa = useEmpresaDaTela();
  return empresa.tipo === 'demonstracao' || empresa.tipo === 'conta' ? empresa.cnpj : null;
}

/**
 * De onde vêm os dados: o espaço próprio, a demonstração compartilhada ou a organização da conta. Entra na chave
 * de todo dado, junto do CNPJ: trocar de espaço, de conta ou de empresa nunca mostra o dado da anterior.
 *
 * Devolve null (nenhum pedido sai) enquanto a API não responde, enquanto a tela não sabe se há conta e na conta sem
 * empresa (ADR 0016 e ADR 0018).
 */
export function useOrigemDosDados(): string | null {
  const modo = useModo();
  const espaco = useEspaco();
  const empresa = useEmpresaDaTela();
  if (modo.tipo !== 'pronto' || empresa.tipo === 'esperando' || empresa.tipo === 'sem-empresa') {
    return null;
  }
  if (empresa.tipo === 'conta') {
    return `conta:${empresa.organizacao}`;
  }
  return espaco.tipo === 'ativo' ? `espaco:${espaco.espaco.id}` : `compartilhada:${modo.saude.modo}`;
}

/** A chave de um dado da empresa da tela (a rota, o CNPJ e a origem), ou null quando ele não deve ser pedido. */
function useChaveDaEmpresa(rota: string): { chave: string | null; cnpj: string } {
  const cnpj = useCnpjDaTela();
  const origem = useOrigemDosDados();
  return { chave: cnpj !== null && origem !== null ? `${rota}:${cnpj}:${origem}` : null, cnpj: cnpj ?? '' };
}

export function useCatalogo(): EstadoRecurso<Catalogo> {
  const { api } = useSessao();
  const { chave, cnpj } = useChaveDaEmpresa('catalogo');
  return useRecurso(chave, (sinal) =>
    chamar(api.GET('/catalogo', { params: { query: { cnpj } }, signal: sinal })),
  );
}

/** O catálogo não tem item: não há o que calcular (o carrinho pede pelo menos um, `minItems` do contrato). */
export function catalogoVazio(catalogo: Catalogo | undefined): boolean {
  return catalogo !== undefined && catalogo.itens.length === 0;
}

/** O catálogo inteiro calculado num regime, um lote de referência por item. Sem item, não chama a API. */
export function useCalculo(catalogo: Catalogo | undefined, regime: Regime | null): EstadoRecurso<Carrinho> {
  const { api } = useSessao();
  // O catálogo muda depois de uma gravação (preço, classificação): a chave leva o que entra no pedido.
  const chave =
    catalogo && regime && !catalogoVazio(catalogo)
      ? `calculo:${regime}:${JSON.stringify(pedidoDoCatalogo(catalogo, regime))}`
      : null;
  return useRecurso(chave, (sinal) => {
    if (!catalogo || !regime) {
      return Promise.reject(new Error('sem catálogo'));
    }
    return chamar(api.POST('/carrinho/calcular', { body: pedidoDoCatalogo(catalogo, regime), signal: sinal }));
  });
}

export function useAlertasAbertos(): EstadoRecurso<{ alertas: Alerta[] }> {
  const { api } = useSessao();
  const { chave, cnpj } = useChaveDaEmpresa('alertas');
  return useRecurso(chave, (sinal) =>
    chamar(api.GET('/alertas', { params: { query: { cnpj, abertos: true } }, signal: sinal })),
  );
}

/**
 * As NF-e de compra já importadas, da emissão mais recente para a mais antiga (GET /notas). Com `pedir` falso,
 * nenhum pedido sai (o Painel só precisa da lista quando o catálogo não diz qual foi a última nota).
 */
export function useNotas(pedir = true): EstadoRecurso<Notas> {
  const { api } = useSessao();
  const { chave: daEmpresa, cnpj } = useChaveDaEmpresa('notas');
  const chave = pedir ? daEmpresa : null;
  return useRecurso(chave, (sinal) =>
    chamar(api.GET('/notas', { params: { query: { cnpj } }, signal: sinal })),
  );
}

/**
 * A venda mensal ao cliente comparada nos dois regimes (POST /regime/comparar). Sem pedido (antes de 2027,
 * ou com um item da venda fora do catálogo), não chama a API.
 */
export function useComparacao(catalogo: Catalogo | undefined, cliente: ClienteB2B | undefined): EstadoRecurso<Comparacao> {
  const { api } = useSessao();
  const pedido = catalogo && cliente ? pedidoDeRegime(catalogo, cliente) : null;
  // A chave leva o pedido inteiro: um preço aplicado ou uma nota nova muda a venda ou o crédito.
  const chave = pedido ? `regime:${JSON.stringify(pedido)}` : null;
  return useRecurso(chave, (sinal) => {
    if (!pedido) {
      return Promise.reject(new Error('sem pedido'));
    }
    return chamar(api.POST('/regime/comparar', { body: pedido, signal: sinal }));
  });
}

/**
 * Envia o XML da nota (POST /nfe/importar, multipart com o campo `arquivo`). O arquivo já passou por
 * conferirArquivoDaNota; quem decide é o backend (411, 413, 415, 409 e 422).
 */
export function importarNota(api: ClienteApi, arquivo: File): Promise<Resposta<ReciboNota>> {
  const corpo = new FormData();
  corpo.append('arquivo', arquivo, arquivo.name);
  return chamar(
    api.POST('/nfe/importar', {
      // O tipo gerado descreve o campo como texto; o corpo real é o FormData, que o openapi-fetch envia
      // como está, sem Content-Type, para o navegador pôr o boundary do multipart.
      body: corpo as unknown as { arquivo: string },
      bodySerializer: (b) => b as unknown as FormData,
    }),
  );
}

export type Gravacao = { pode: true } | { pode: false; motivo: string };

/**
 * A tela grava (preço, classificação, alerta aplicado, nota importada) só no modo real:
 * - na conta, na empresa dela: o dono e o membro editam (ADR 0017, etapa 8);
 * - na demonstração, no espaço próprio ou com o token da demo (ADR 0010 e ADR 0011).
 * Fora disso, o botão fica desligado e diz por quê (app-screens §8.1).
 */
export function useGravacao(): Gravacao {
  const modo = useModo();
  const espaco = useEspaco();
  const temToken = useTemToken();
  const empresa = useEmpresaDaTela();
  if (modo.tipo !== 'pronto' || empresa.tipo === 'esperando') {
    return { pode: false, motivo: 'A API ainda não respondeu.' };
  }
  if (empresa.tipo === 'sem-empresa') {
    return { pode: false, motivo: 'Cadastre a empresa para gravar.' };
  }
  if (empresa.tipo === 'conta') {
    return { pode: true };
  }
  if (modo.saude.modo === 'mock') {
    return { pode: false, motivo: 'Os dados de demonstração são só leitura: nada é gravado neste modo.' };
  }
  if (espaco.tipo === 'ativo' || temToken) {
    return { pode: true };
  }
  return { pode: false, motivo: 'Para gravar, crie seu espaço no alto da tela.' };
}
