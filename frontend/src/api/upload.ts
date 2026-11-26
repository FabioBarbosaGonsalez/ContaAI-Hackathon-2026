// Envio do XML da NF-e (docs/seguranca.md, regras da interface, item 7).
//
// A tela confere antes de enviar, para responder na hora sem gastar a requisição. Quem decide continua
// sendo o backend: ele recusa por conta própria com 411, 413 e 415 (backend/app/api/rotas/notas.py).

/** O que o campo de arquivo oferece: só XML. */
export const ACEITA_NOTA = '.xml,application/xml,text/xml';

/**
 * O padrão de CONTAAI_TAMANHO_MAX_NFE_BYTES em backend/app/config.py (o teste do backend confere que os
 * dois são iguais). Se o servidor for configurado com outro valor, a resposta 413 dele vale.
 */
export const TAMANHO_MAX_NOTA_BYTES = 1_000_000;

/** Os tipos que POST /nfe/importar aceita (TIPOS_XML no backend); o vazio é o arquivo sem tipo informado. */
const TIPOS_ACEITOS = new Set(['application/xml', 'text/xml', 'application/octet-stream', '']);

export type ConferenciaNota = { ok: true } | { ok: false; motivo: string };

export function conferirArquivoDaNota(arquivo: Pick<File, 'name' | 'size' | 'type'>): ConferenciaNota {
  if (!arquivo.name.toLowerCase().endsWith('.xml')) {
    return { ok: false, motivo: 'Escolha o arquivo XML da nota (termina em .xml).' };
  }
  if (!TIPOS_ACEITOS.has(arquivo.type.toLowerCase())) {
    return { ok: false, motivo: 'O arquivo não é um XML.' };
  }
  if (arquivo.size === 0) {
    return { ok: false, motivo: 'O arquivo está vazio.' };
  }
  if (arquivo.size > TAMANHO_MAX_NOTA_BYTES) {
    return { ok: false, motivo: 'O arquivo passa de 1 MB, maior que qualquer XML de NF-e de compra comum.' };
  }
  return { ok: true };
}
