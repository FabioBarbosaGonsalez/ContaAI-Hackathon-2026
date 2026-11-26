// Os dados de uma empresa na tela: catálogo, cálculo por regime e alertas, e se a tela pode gravar.
//
// A empresa da demonstração é a Distribuidora Serra Azul ME (fictícia, data/demo). O seletor de CNPJ do
// painel do contador (D1) entra no PR 3c; até lá, toda tela abre esta empresa.

import { chamar, type ClienteApi, type Resposta } from '../api/cliente.ts';
import { useSessao } from '../sessao/contexto.tsx';
import { useEspaco, useModo, useTemToken } from '../sessao/ganchos.ts';
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

/** De onde vêm os dados: o espaço próprio ou a demonstração compartilhada. Entra na chave de todo dado. */
export function useOrigemDosDados(): string | null {
  const modo = useModo();
  const espaco = useEspaco();
  if (modo.tipo !== 'pronto') {
    return null;
  }
  return espaco.tipo === 'ativo' ? `espaco:${espaco.espaco.id}` : `compartilhada:${modo.saude.modo}`;
}

export function useCatalogo(cnpj: string = CNPJ_DEMONSTRACAO): EstadoRecurso<Catalogo> {
  const { api } = useSessao();
  const origem = useOrigemDosDados();
  return useRecurso(origem && `catalogo:${cnpj}:${origem}`, (sinal) =>
    chamar(api.GET('/catalogo', { params: { query: { cnpj } }, signal: sinal })),
  );
}

/** O catálogo inteiro calculado num regime, um lote de referência por item. */
export function useCalculo(catalogo: Catalogo | undefined, regime: Regime | null): EstadoRecurso<Carrinho> {
  const { api } = useSessao();
  // O catálogo muda depois de uma gravação (preço, classificação): a chave leva o que entra no pedido.
  const chave =
    catalogo && regime ? `calculo:${regime}:${JSON.stringify(pedidoDoCatalogo(catalogo, regime))}` : null;
  return useRecurso(chave, (sinal) => {
    if (!catalogo || !regime) {
      return Promise.reject(new Error('sem catálogo'));
    }
    return chamar(api.POST('/carrinho/calcular', { body: pedidoDoCatalogo(catalogo, regime), signal: sinal }));
  });
}

export function useAlertasAbertos(cnpj: string = CNPJ_DEMONSTRACAO): EstadoRecurso<{ alertas: Alerta[] }> {
  const { api } = useSessao();
  const origem = useOrigemDosDados();
  return useRecurso(origem && `alertas:${cnpj}:${origem}`, (sinal) =>
    chamar(api.GET('/alertas', { params: { query: { cnpj, abertos: true } }, signal: sinal })),
  );
}

/** As NF-e de compra já importadas, da emissão mais recente para a mais antiga (GET /notas). */
export function useNotas(cnpj: string = CNPJ_DEMONSTRACAO): EstadoRecurso<Notas> {
  const { api } = useSessao();
  const origem = useOrigemDosDados();
  return useRecurso(origem && `notas:${cnpj}:${origem}`, (sinal) =>
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
 * A tela grava (preço, classificação, alerta aplicado) só no modo real, no espaço próprio ou com o token
 * da demo (ADR 0010 e ADR 0011). Fora disso, o botão fica desligado e diz por quê (app-screens §8.1).
 */
export function useGravacao(): Gravacao {
  const modo = useModo();
  const espaco = useEspaco();
  const temToken = useTemToken();
  if (modo.tipo !== 'pronto') {
    return { pode: false, motivo: 'A API ainda não respondeu.' };
  }
  if (modo.saude.modo === 'mock') {
    return { pode: false, motivo: 'Os dados de demonstração são só leitura: nada é gravado neste modo.' };
  }
  if (espaco.tipo === 'ativo' || temToken) {
    return { pode: true };
  }
  return { pode: false, motivo: 'Para gravar, crie seu espaço no alto da tela.' };
}
