// A versão dos termos de uso e a data da política de privacidade (C2, T8; ADR 0015, revisão do B0).
//
// A versão dos termos é a data em que o texto de src/telas/Termos.tsx passou a valer. A fonte é
// backend/app/contas/termos.py: o contrato a declara como o único valor de `termosAceitos`, e o tipo gerado
// (esquema.gen.ts) só compila com ela. Mudar o texto dos termos pede uma versão nova, aqui e no backend, no
// mesmo PR.

import type { components } from '../api/esquema.gen.ts';

export type VersaoTermos = components['schemas']['CadastroRequisicao']['termosAceitos'];

export const VERSAO_TERMOS: VersaoTermos = '2026-11-26';

/** A data da última mudança no texto de src/telas/Privacidade.tsx. */
export const ATUALIZACAO_PRIVACIDADE = '2026-11-26';

/** "2026-11-26" → "26/11/2026", sem passar por Date (sem fuso). */
export function dataDaVersao(iso: string): string {
  const [ano, mes, dia] = iso.split('-');
  return `${dia ?? ''}/${mes ?? ''}/${ano ?? ''}`;
}

export const AVISO_RASCUNHO =
  'Rascunho sem revisão jurídica. Este texto precisa ser revisado por um profissional do direito antes da publicação do ContaAI.';

/**
 * As regras da conta que os termos e a privacidade citam. A fonte é o backend (C1, ADR 0015); o teste legal.test.ts
 * lê os arquivos de backend/app/contas e falha se um valor daqui divergir de lá.
 */
export const REGRAS_DA_CONTA = {
  /** senha.py, MINIMO */
  senhaMinima: 8,
  /** senha.py, MAXIMO */
  senhaMaxima: 128,
  /** totp.py, DIGITOS */
  digitosDoCodigo: 6,
  /** servico.py, CODIGOS_RECUPERACAO */
  codigosDeRecuperacao: 10,
  /** servico.py, FALHAS_PARA_ESPERAR */
  falhasParaEsperar: 5,
  /** servico.py, ESPERA_INICIAL_S */
  esperaInicialS: 30,
  /** servico.py, ESPERA_MAXIMA_S */
  esperaMaximaS: 3600,
  /** servico.py, FALHAS_PARA_BLOQUEAR */
  falhasParaBloquear: 100,
  /** servico.py, SESSAO_OCIOSA (minutos) */
  sessaoOciosaMin: 30,
  /** servico.py, SESSAO_TOTAL (horas) */
  sessaoTotalH: 8,
  /** servico.py, PASSE (minutos) */
  passeMin: 5,
  /** servico.py, PENDENTE (minutos) */
  pendenteMin: 30,
} as const;

/** Os cookies da API (backend/app/api/dependencias.py, COOKIE_SESSAO e COOKIE_PASSE; conferido em legal.test.ts). */
export const COOKIES = { sessao: '__Host-contaai_sessao', passe: '__Host-contaai_passe' } as const;
