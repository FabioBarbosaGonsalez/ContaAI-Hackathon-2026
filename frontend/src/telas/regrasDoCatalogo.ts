// As conferências dos formulários do catálogo e dos clientes empresa (C3b, etapas 6 a 9; ADR 0018, seção da C3b2).
//
// - Como em regrasDeEntrada.ts, elas só poupam uma ida à API com um erro óbvio: o backend confere tudo de novo e
//   tem a palavra final (a NCM nos dados abertos, a classificação válida, o município da UF, o cliente do Simples).
// - Os limites são os do contrato (docs/contrato/openapi.json), conferidos por teste em regrasDoCatalogo.test.ts.
// - O dígito do CNPJ do fornecedor e do cliente só é exigido na empresa da conta, como no backend
//   (`exigir_digito = estado.na_empresa_propria`): os CNPJs da demonstração são fictícios e têm o dígito errado de
//   propósito (ADR 0008).

import type { components } from '../api/esquema.gen.ts';
import { conferirCnpj, normalizarCnpj, PADRAO_CNPJ, tamanhoEmPontos } from './regrasDeEntrada.ts';

type LinhaSemPar = components['schemas']['ItemNotaSemPar'];

/** DescricaoDoItem e CodigoDoFornecedor no contrato. */
export const DESCRICAO_MAXIMA = 200;
export const CODIGO_MAXIMO = 60;
/** TETO_ENTRADA do backend: a quantidade da compra mensal vai até um bilhão. */
export const QUANTIDADE_MAXIMA = 1_000_000_000;
/** As unidades que o cadastro do item aceita (ItemNovoRequisicao.unidade). */
export const UNIDADES = ['UN', 'KG'] as const;
export type Unidade = (typeof UNIDADES)[number];

// eslint-disable-next-line no-control-regex -- é justamente o que a regra procura
const CONTROLE = /[\u0000-\u001f\u007f-\u009f]/u;

/** "2203.00.00", "2203 00 00" ou "22030000" → "22030000". Fora de 8 dígitos, null. */
export function lerNcm(texto: string): string | null {
  const limpo = texto.replace(/[.\s]/gu, '');
  return /^[0-9]{8}$/u.test(limpo) ? limpo : null;
}

/** Um texto do cadastro (a descrição do item, o código do fornecedor): sem as pontas, com tamanho e sem controle. */
export function conferirTexto(texto: string, maximo: number, nome: string): string | null {
  const valor = texto.trim();
  if (valor === '') {
    return `Informe ${nome}.`;
  }
  if (tamanhoEmPontos(valor) > maximo) {
    return `Use no máximo ${String(maximo)} caracteres.`;
  }
  if (CONTROLE.test(valor)) {
    return 'Use só texto, sem caracteres de controle.';
  }
  return null;
}

/**
 * A margem-alvo em %: maior que 0 e menor que 100, com até 4 casas (MargemAlvo no contrato). Aceita a vírgula e o
 * "%" no fim. Fora disso, null.
 */
export function lerMargem(texto: string): string | null {
  const limpo = texto.trim().replace(/\s*%$/u, '').replace(',', '.');
  return /^\d{1,2}(\.\d{1,4})?$/u.test(limpo) && Number(limpo) > 0 ? limpo : null;
}

export const FRASE_DA_MARGEM = 'Use um percentual maior que 0 e menor que 100, com até 4 casas depois da vírgula.';

/** A quantidade por mês da compra mensal: maior que 0, até um bilhão, com até 4 casas (QuantidadeDaCompra). */
export function lerQuantidade(texto: string): string | null {
  const limpo = texto.trim().replace(',', '.');
  if (!/^\d{1,10}(\.\d{1,4})?$/u.test(limpo)) {
    return null;
  }
  const valor = Number(limpo);
  return valor > 0 && valor <= QUANTIDADE_MAXIMA ? limpo : null;
}

export const FRASE_DA_QUANTIDADE = 'Use uma quantidade maior que 0, com até 4 casas depois da vírgula.';

/**
 * O CNPJ de um fornecedor ou de um cliente. Na empresa da conta, com os dígitos verificadores (o backend recusa o
 * dígito errado); na demonstração, só o formato.
 */
export function conferirCnpjDeTerceiro(texto: string, exigirDigito: boolean): string | null {
  if (exigirDigito) {
    return conferirCnpj(texto);
  }
  const valor = normalizarCnpj(texto);
  if (valor === '') {
    return 'Informe o CNPJ.';
  }
  return PADRAO_CNPJ.test(valor)
    ? null
    : 'Confira o CNPJ: são 14 caracteres, os 12 primeiros com números ou letras e os 2 últimos com números.';
}

/** Os dados da nota de onde o item nasce (POST /catalogo/itens com `daNota`). */
export interface OrigemDaNota {
  cnpjFornecedor: string;
  serie: string;
  numero: string;
  linha: LinhaSemPar & { nItem: number; unidade: Unidade; custoUnitario: string; quantidade: string };
}

export type Cadastravel = { pode: true; origem: OrigemDaNota } | { pode: false; motivo: string | null };

/**
 * A linha sem par vira item a partir da nota? As mesmas recusas do backend (`_linha_da_nota`), para a tela não
 * oferecer um botão que daria 422. `motivo` null: a linha já diz por que não casou (`motivo` da API), e cadastrar
 * não mudaria isso.
 */
export function cadastravelDaNota(
  linha: LinhaSemPar,
  nota: { serie?: string | null; numero: string; emitente: { cnpj: string } },
  linhas: readonly LinhaSemPar[],
): Cadastravel {
  if (
    linha.causa === null ||
    linha.causa === undefined ||
    linha.quantidade === null ||
    linha.quantidade === undefined ||
    linha.custoUnitario === null ||
    linha.custoUnitario === undefined ||
    linha.valorTotal === null ||
    linha.valorTotal === undefined
  ) {
    return {
      pode: false,
      motivo:
        'Esta nota foi importada antes de o ContaAI guardar o custo dos itens sem par. Cadastre o item pelo Catálogo: o custo entra com a próxima nota do fornecedor.',
    };
  }
  if (linha.causa !== 'semCadastro') {
    return { pode: false, motivo: null };
  }
  if (linhas.filter((i) => i.codigoFornecedor === linha.codigoFornecedor).length > 1) {
    return {
      pode: false,
      motivo: 'O mesmo produto aparece mais de uma vez na nota: confira com o fornecedor e cadastre o item pelo Catálogo.',
    };
  }
  const unidade = linha.unidade ?? '';
  if (!(UNIDADES as readonly string[]).includes(unidade)) {
    return {
      pode: false,
      motivo: `A unidade da nota (${unidade === '' ? 'vazia' : unidade}) não é UN nem KG, as que o cadastro aceita, e o ContaAI não converte unidades.`,
    };
  }
  if (linha.nItem === null || linha.nItem === undefined || !nota.serie) {
    return { pode: false, motivo: 'A nota não traz a série ou o número desta linha: cadastre o item pelo Catálogo.' };
  }
  return {
    pode: true,
    origem: {
      cnpjFornecedor: nota.emitente.cnpj,
      serie: nota.serie,
      numero: nota.numero,
      linha: {
        ...linha,
        nItem: linha.nItem,
        unidade: unidade as Unidade,
        custoUnitario: linha.custoUnitario,
        quantidade: linha.quantidade,
      },
    },
  };
}
