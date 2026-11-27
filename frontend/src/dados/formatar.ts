// Números e datas da tela, no padrão brasileiro (app-screens §7.4 da skill).
//
// A API manda dinheiro e percentuais como texto ("27.90", "11.19"). A tela só formata: não arredonda de
// novo nem soma valores por conta própria. Um valor ausente vira traço; um zero é impresso como zero (§11).

export const TRACO = '—';

const REAIS = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL', minimumFractionDigits: 2 });
const PORCENTAGEM = new Intl.NumberFormat('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const INTEIRO = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 0 });

type Valor = string | number | null | undefined;

function numero(valor: Valor): number | null {
  if (valor === null || valor === undefined || valor === '') {
    return null;
  }
  const n = typeof valor === 'number' ? valor : Number(valor);
  return Number.isFinite(n) ? n : null;
}

/** "3.97" → "R$ 3,97" (com espaço comum, para o texto copiado não trazer o espaço especial do Intl). */
export function reais(valor: Valor): string {
  const n = numero(valor);
  return n === null ? TRACO : REAIS.format(n).replace(/\s/u, ' ');
}

const REAIS_POR_UNIDADE = new Intl.NumberFormat('pt-BR', {
  style: 'currency',
  currency: 'BRL',
  minimumFractionDigits: 2,
  maximumFractionDigits: 4,
});

/**
 * Valor por unidade com até 4 casas, como a API manda: "0.2715" → "R$ 0,2715". O crédito da compra por
 * unidade sai de vCBS + vIBS ÷ qCom (ADR 0003) e não é arredondado de novo na tela.
 */
export function reaisPorUnidade(valor: Valor): string {
  const n = numero(valor);
  return n === null ? TRACO : REAIS_POR_UNIDADE.format(n).replace(/\s/u, ' ');
}

/** Valor com sinal (−R$ 125,79 e +R$ 10,00), com o sinal de menos tipográfico. Zero fica sem sinal. */
export function reaisComSinal(valor: Valor): string {
  const n = numero(valor);
  if (n === null) {
    return TRACO;
  }
  const sinal = n > 0 ? '+' : n < 0 ? '−' : '';
  return `${sinal}${reais(Math.abs(n))}`;
}

/** "11.19" → "11,19%". */
export function porcentagem(valor: Valor): string {
  const n = numero(valor);
  return n === null ? TRACO : `${PORCENTAGEM.format(n)}%`;
}

/** Diferença de pontos percentuais com sinal: −12,93 p.p. */
export function pontos(valor: Valor): string {
  const n = numero(valor);
  if (n === null) {
    return TRACO;
  }
  const sinal = n > 0 ? '+' : n < 0 ? '−' : '';
  return `${sinal}${PORCENTAGEM.format(Math.abs(n))} p.p.`;
}

/** "Cerveja de malte" → "cerveja de malte", para caber no meio da frase (siglas ficam como estão). */
export function noMeioDaFrase(texto: string): string {
  return /^[A-ZÀ-Ý][a-zà-ÿ]/u.test(texto) ? texto.charAt(0).toLowerCase() + texto.slice(1) : texto;
}

export function inteiro(valor: Valor): string {
  const n = numero(valor);
  return n === null ? TRACO : INTEIRO.format(n);
}

/**
 * Data de um documento como foi escrita, sem trocar de fuso: "2027-03-16T09:00:00-03:00" → "16/03/2027".
 * A nota é de 16/03 no fuso dela; convertida para o fuso do navegador, poderia virar outro dia (ADR 0003).
 */
export function dataDoDocumento(iso: string | null | undefined): string {
  const achado = iso ? /^(\d{4})-(\d{2})-(\d{2})/u.exec(iso) : null;
  if (!achado) {
    return TRACO;
  }
  const [, ano = '', mes = '', dia = ''] = achado;
  return `${dia}/${mes}/${ano}`;
}

const INSTANTE = new Intl.DateTimeFormat('pt-BR', { dateStyle: 'short', timeStyle: 'short' });

/**
 * Um instante da API (UTC), no fuso do navegador: "2026-11-26T12:00:00Z" → "26/11/2026, 09:00" em Brasília.
 * Para a conta (criada em, sessão, avisos), que são momentos e não datas de documento (ver dataDoDocumento).
 */
export function instante(iso: string | null | undefined): string {
  const data = iso ? new Date(iso) : null;
  return data === null || Number.isNaN(data.getTime()) ? TRACO : INSTANTE.format(data);
}

/**
 * CNPJ com a máscara oficial: 36817420000113 → 36.817.420/0001-13. O alfanumérico (IN RFB 2.229/2024) usa a mesma
 * máscara, segundo as perguntas e respostas da Receita: 12ABC34501DE35 → 12.ABC.345/01DE-35.
 */
export function cnpj(valor: string): string {
  return /^[0-9A-Z]{12}\d{2}$/u.test(valor)
    ? valor.replace(/^([0-9A-Z]{2})([0-9A-Z]{3})([0-9A-Z]{3})([0-9A-Z]{4})(\d{2})$/u, '$1.$2.$3/$4-$5')
    : valor;
}

/** NCM com os pontos da tabela: 22030000 → 2203.00.00. */
export function ncm(valor: string | null | undefined): string {
  return valor && /^\d{8}$/u.test(valor) ? valor.replace(/^(\d{4})(\d{2})(\d{2})$/u, '$1.$2.$3') : (valor ?? TRACO);
}
