// As conferências que a tela faz antes de enviar os formulários da conta (C2b, ADR 0016).
//
// - Elas só poupam uma ida à API com um erro óbvio. Quem decide é o backend, que confere tudo de novo e responde
//   com a frase dele (senha comum, e-mail já usado etc.), e a tela mostra essa frase.
// - Os padrões são os do contrato (docs/contrato/openapi.json), conferidos por teste em regrasDeEntrada.test.ts.
// - Nenhuma regra de composição de senha (NIST SP 800-63B-4, §3.1.1.2): só o tamanho, contado como o backend
//   conta (NFKC, um caractere por ponto de código).

import { REGRAS_DA_CONTA } from './legal.ts';

/** Contrato: Email (pattern e maxLength). */
export const PADRAO_EMAIL = /^[^@\s:]{1,64}@[^@\s:]+\.[^@\s:]+$/u;
export const EMAIL_MAXIMO = 254;
/** Contrato: CodigoRequisicao.codigo. */
export const PADRAO_CODIGO = /^[0-9]{6}$/u;
/** Contrato: SegundaEtapaRequisicao.codigoRecuperacao (13 caracteres de base32, hífens opcionais). */
export const PADRAO_RECUPERACAO = /^[A-Za-z2-7]{4}-?[A-Za-z2-7]{4}-?[A-Za-z2-7]{5}$/u;
/** Contrato: CadastroRequisicao.organizacao (maxLength). */
export const ORGANIZACAO_MAXIMA = 120;

/**
 * Quantos caracteres o texto tem para o backend: pontos de código, como o len() do Python e o maxLength do
 * Pydantic (e não unidades UTF-16, como o .length, que conta um emoji como 2).
 */
export function tamanhoEmPontos(texto: string): number {
  return Array.from(texto).length;
}

/** Quantos caracteres a senha tem para o backend (senha.py: NFKC, depois len()). */
export function tamanhoDaSenha(senha: string): number {
  return tamanhoEmPontos(senha.normalize('NFKC'));
}

export function conferirEmail(email: string): string | null {
  const texto = email.trim();
  if (texto === '') {
    return 'Informe o e-mail.';
  }
  if (tamanhoEmPontos(texto) > EMAIL_MAXIMO || !PADRAO_EMAIL.test(texto)) {
    return 'Confira o e-mail: ele precisa ter um @ e um domínio, como nome@example.com.'; // taste-skill-ignore: domínio reservado para exemplos (RFC 2606)
  }
  return null;
}

/** A senha nova do cadastro: só o tamanho. A lista de senhas comuns fica no backend. */
export function conferirSenhaNova(senha: string): string | null {
  const tamanho = tamanhoDaSenha(senha);
  if (tamanho === 0) {
    return 'Crie uma senha.';
  }
  if (tamanho < REGRAS_DA_CONTA.senhaMinima) {
    return `A senha precisa ter pelo menos ${String(REGRAS_DA_CONTA.senhaMinima)} caracteres.`;
  }
  if (tamanho > REGRAS_DA_CONTA.senhaMaxima) {
    return `A senha pode ter no máximo ${String(REGRAS_DA_CONTA.senhaMaxima)} caracteres.`;
  }
  return null;
}

/** A senha de quem entra (ou confirma a exclusão): só não pode faltar. A regra de tamanho vale no cadastro. */
export function conferirSenhaAtual(senha: string): string | null {
  return senha === '' ? 'Informe a senha.' : null;
}

export function conferirOrganizacao(nome: string): string | null {
  const texto = nome.trim();
  if (texto === '') {
    return 'Informe o nome da organização.';
  }
  if (tamanhoEmPontos(texto) > ORGANIZACAO_MAXIMA) {
    return `O nome pode ter no máximo ${String(ORGANIZACAO_MAXIMA)} caracteres.`;
  }
  return null;
}

/** O código do aplicativo sem espaços (alguns aplicativos mostram "123 456"). */
export function normalizarCodigo(codigo: string): string {
  return codigo.replace(/\s+/gu, '');
}

export function conferirCodigo(codigo: string): string | null {
  const texto = normalizarCodigo(codigo);
  if (texto === '') {
    return 'Informe o código do aplicativo.';
  }
  return PADRAO_CODIGO.test(texto)
    ? null
    : `O código tem ${String(REGRAS_DA_CONTA.digitosDoCodigo)} números, como aparece no aplicativo.`;
}

/** O código de recuperação em maiúsculas e sem espaços; os hífens ficam (o backend aceita com ou sem). */
export function normalizarRecuperacao(codigo: string): string {
  return codigo.replace(/\s+/gu, '').toUpperCase();
}

export function conferirRecuperacao(codigo: string): string | null {
  const texto = normalizarRecuperacao(codigo);
  if (texto === '') {
    return 'Informe um código de recuperação.';
  }
  return PADRAO_RECUPERACAO.test(texto)
    ? null
    : 'O código de recuperação tem 13 letras e números, em três grupos, como XXXX-XXXX-XXXXX.';
}
