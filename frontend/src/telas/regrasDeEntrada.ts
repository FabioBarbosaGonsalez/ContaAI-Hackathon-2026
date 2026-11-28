// As conferências que a tela faz antes de enviar os formulários da conta (C2b, ADR 0016) e o cadastro da empresa
// (C3a, ADR 0018).
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
/** Contrato: EmpresaCadastroRequisicao.cnpj (o padrão do backend, app/cnpj.py). */
export const PADRAO_CNPJ = /^[0-9A-Z]{12}[0-9]{2}$/u;
/** Contrato: EmpresaCadastroRequisicao.razaoSocial (maxLength). */
export const RAZAO_SOCIAL_MAXIMA = 150;
/** O backend recusa caractere de controle nos textos do cadastro (contrato.py, _texto_de_cadastro). */
// eslint-disable-next-line no-control-regex -- é justamente o que a regra procura
const CONTROLE = /[\x00-\x1f\x7f]/u;

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

/**
 * O CNPJ como a API o recebe: sem os pontos, a barra, o traço e os espaços, e com as letras em maiúsculas (a
 * Receita só fala em maiúsculas; ADR 0017). O que sobrar fora do formato fica, para a conferência recusar.
 */
export function normalizarCnpj(texto: string): string {
  return texto.replace(/[.\-/\s]/gu, '').toUpperCase();
}

/**
 * Um dígito verificador, pelo cálculo do Serpro ("Cálculo dos dígitos verificadores de CNPJ alfanumérico"): o valor
 * de cada caractere é o código ASCII menos 48; os pesos vão de 2 a 9, da direita para a esquerda, recomeçando
 * depois do oitavo; resto 0 ou 1 dá 0, senão 11 menos o resto. Para os dígitos, é o cálculo do CNPJ numérico. É o
 * mesmo de backend/app/cnpj.py, e o backend confere de novo.
 */
function digito(base: string): string {
  let soma = 0;
  Array.from(base)
    .reverse()
    .forEach((caractere, i) => {
      soma += (caractere.charCodeAt(0) - 48) * (2 + (i % 8));
    });
  const resto = soma % 11;
  return resto < 2 ? '0' : String(11 - resto);
}

/** Os dois dígitos verificadores dos 12 primeiros caracteres (já no formato: dígitos ou letras maiúsculas). */
export function digitosVerificadoresDoCnpj(base: string): string {
  const primeiro = digito(base);
  return primeiro + digito(base + primeiro);
}

export function conferirCnpj(texto: string): string | null {
  const valor = normalizarCnpj(texto);
  if (valor === '') {
    return 'Informe o CNPJ.';
  }
  if (!PADRAO_CNPJ.test(valor)) {
    return 'Confira o CNPJ: são 14 caracteres, os 12 primeiros com números ou letras e os 2 últimos com números.';
  }
  if (digitosVerificadoresDoCnpj(valor.slice(0, 12)) !== valor.slice(12)) {
    return 'CNPJ inválido: confira os dígitos verificadores.';
  }
  return null;
}

export function conferirRazaoSocial(texto: string): string | null {
  const valor = texto.trim();
  if (valor === '') {
    return 'Informe a razão social.';
  }
  if (tamanhoEmPontos(valor) > RAZAO_SOCIAL_MAXIMA) {
    return `A razão social pode ter no máximo ${String(RAZAO_SOCIAL_MAXIMA)} caracteres.`;
  }
  if (CONTROLE.test(valor)) {
    return 'Use só texto, sem caracteres de controle.';
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

/**
 * Uma alíquota efetiva do DAS (pCBSSN ou pIBSSN), em %: de 0 a menos de 100, com até 4 casas (o contrato:
 * `PorcentagemEntrada`, ge=0, lt=100, decimal_places=4). Aceita a vírgula e o "%" no fim. Fora disso, null.
 */
export function lerAliquotaDoDas(texto: string): string | null {
  const limpo = texto.trim().replace(/\s*%$/u, '').replace(',', '.');
  return /^\d{1,2}(\.\d{1,4})?$/u.test(limpo) ? limpo : null;
}

export const FRASE_DA_ALIQUOTA = 'Use um percentual de 0 a 99,9999, com até 4 casas depois da vírgula.';

/** O CNPJ digitado para confirmar a exclusão é o da empresa (sem a pontuação e em maiúsculas)? */
export function conferirCnpjDaConfirmacao(texto: string, cnpj: string): string | null {
  const valor = normalizarCnpj(texto);
  if (valor === '') {
    return 'Digite o CNPJ da empresa para confirmar.';
  }
  return valor === cnpj ? null : 'O CNPJ digitado não é o desta empresa.';
}
