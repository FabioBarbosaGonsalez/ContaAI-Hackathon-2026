/// <reference types="node" />
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import {
  EMAIL_MAXIMO,
  ORGANIZACAO_MAXIMA,
  PADRAO_CODIGO,
  PADRAO_EMAIL,
  PADRAO_RECUPERACAO,
  conferirCodigo,
  conferirEmail,
  conferirOrganizacao,
  conferirRecuperacao,
  conferirSenhaAtual,
  conferirSenhaNova,
  normalizarCodigo,
  normalizarRecuperacao,
  tamanhoDaSenha,
  tamanhoEmPontos,
} from './regrasDeEntrada.ts';

// A fonte dos padrões: o contrato publicado pelo backend (docs/contrato/openapi.json).
const CONTRATO = JSON.parse(
  readFileSync(join(import.meta.dirname, '..', '..', '..', 'docs', 'contrato', 'openapi.json'), 'utf8'),
) as { components: { schemas: Record<string, { properties: Record<string, Record<string, unknown>> }> } };

function propriedade(esquema: string, campo: string): Record<string, unknown> {
  const p = CONTRATO.components.schemas[esquema]?.properties[campo];
  if (p === undefined) {
    throw new Error(`${esquema}.${campo} não está no contrato`);
  }
  return p;
}

function padraoAnulavel(esquema: string, campo: string): unknown {
  const opcoes = propriedade(esquema, campo).anyOf as Record<string, unknown>[];
  return opcoes.find((o) => o.type === 'string')?.pattern;
}

describe('os padrões são os do contrato', () => {
  it('e-mail, código, código de recuperação e organização', () => {
    for (const esquema of ['CadastroRequisicao', 'EntrarRequisicao']) {
      expect(propriedade(esquema, 'email').pattern).toBe(PADRAO_EMAIL.source);
      expect(propriedade(esquema, 'email').maxLength).toBe(EMAIL_MAXIMO);
    }
    expect(propriedade('CodigoRequisicao', 'codigo').pattern).toBe(PADRAO_CODIGO.source);
    expect(padraoAnulavel('SegundaEtapaRequisicao', 'codigo')).toBe(PADRAO_CODIGO.source);
    expect(padraoAnulavel('SegundaEtapaRequisicao', 'codigoRecuperacao')).toBe(PADRAO_RECUPERACAO.source);
    expect(propriedade('CadastroRequisicao', 'organizacao').maxLength).toBe(ORGANIZACAO_MAXIMA);
  });
});

describe('senha', () => {
  it('conta como o backend: NFKC e um caractere por ponto de código', () => {
    expect(tamanhoDaSenha('abcdefgh')).toBe(8);
    // Um emoji fora do plano básico tem .length 2, mas é um ponto de código (len() do Python dá 1).
    expect('😀'.length).toBe(2); // taste-skill-ignore: dado de teste (pontos de código)
    expect(tamanhoDaSenha('😀')).toBe(1); // taste-skill-ignore: dado de teste (pontos de código)
    // NFKC: a ligadura "ﬁ" vira "fi" (2 caracteres).
    expect(tamanhoDaSenha('ﬁ')).toBe(2);
  });

  it('a nova: só o tamanho, sem regra de composição', () => {
    expect(conferirSenhaNova('')).toBe('Crie uma senha.');
    expect(conferirSenhaNova('1234567')).toBe('A senha precisa ter pelo menos 8 caracteres.');
    expect(conferirSenhaNova('aaaaaaaa')).toBeNull(); // a lista e as repetições ficam com o backend
    expect(conferirSenhaNova('só letras minúsculas')).toBeNull();
    expect(conferirSenhaNova('x'.repeat(128))).toBeNull();
    expect(conferirSenhaNova('x'.repeat(129))).toBe('A senha pode ter no máximo 128 caracteres.');
  });

  it('a atual: só não pode faltar (uma senha antiga curta ainda entra)', () => {
    expect(conferirSenhaAtual('')).toBe('Informe a senha.');
    expect(conferirSenhaAtual('curta')).toBeNull();
    expect(conferirSenhaAtual(' ')).toBeNull(); // espaço é caractere da senha: nada de trim
  });
});

describe('e-mail e organização', () => {
  it('e-mail', () => {
    expect(conferirEmail('')).toBe('Informe o e-mail.');
    expect(conferirEmail('   ')).toBe('Informe o e-mail.');
    expect(conferirEmail('pessoa@exemplo.test')).toBeNull();
    expect(conferirEmail('  pessoa@exemplo.test  ')).toBeNull();
    for (const ruim of ['pessoa', 'pessoa@', 'pessoa@exemplo', 'a b@exemplo.test', 'a:b@exemplo.test', 'a@exem:plo.test', `${'a'.repeat(65)}@x.test`]) {
      expect(conferirEmail(ruim), ruim).toMatch(/^Confira o e-mail/u);
    }
    expect(conferirEmail(`a@${'b'.repeat(250)}.test`)).toMatch(/^Confira o e-mail/u);
  });

  it('organização', () => {
    expect(conferirOrganizacao(' ')).toBe('Informe o nome da organização.');
    expect(conferirOrganizacao('Escritório Modelo')).toBeNull();
    expect(conferirOrganizacao('x'.repeat(120))).toBeNull();
    expect(conferirOrganizacao('x'.repeat(121))).toBe('O nome pode ter no máximo 120 caracteres.');
    // Conta pontos de código, como o maxLength do Pydantic: 120 emojis cabem (240 unidades UTF-16), 121 não.
    expect(conferirOrganizacao('😀'.repeat(120))).toBeNull(); // taste-skill-ignore: dado de teste (pontos de código)
    expect(conferirOrganizacao('😀'.repeat(121))).toBe('O nome pode ter no máximo 120 caracteres.'); // taste-skill-ignore: dado de teste (pontos de código)
    // Os espaços das pontas não contam: a tela envia o nome sem eles.
    expect(conferirOrganizacao(` ${'x'.repeat(120)} `)).toBeNull();
  });

  it('tamanhoEmPontos conta pontos de código, e não unidades UTF-16', () => {
    expect(tamanhoEmPontos('ação')).toBe(4);
    expect(tamanhoEmPontos('😀')).toBe(1); // taste-skill-ignore: dado de teste (pontos de código)
    expect('😀'.length).toBe(2); // taste-skill-ignore: dado de teste (pontos de código)
  });
});

describe('códigos', () => {
  it('do aplicativo: 6 dígitos, aceitando espaços', () => {
    expect(normalizarCodigo(' 123 456 ')).toBe('123456');
    expect(conferirCodigo('123 456')).toBeNull();
    expect(conferirCodigo('')).toBe('Informe o código do aplicativo.');
    for (const ruim of ['12345', '1234567', '12a456', '１２３４５６']) {
      expect(conferirCodigo(ruim), ruim).toBe('O código tem 6 números, como aparece no aplicativo.');
    }
  });

  it('de recuperação: base32 em três grupos, com ou sem hífens, maiúsculas ou não', () => {
    expect(normalizarRecuperacao(' abcd-efgh-ijk23 ')).toBe('ABCD-EFGH-IJK23');
    expect(conferirRecuperacao('abcd-efgh-ijk23')).toBeNull();
    expect(conferirRecuperacao('ABCDEFGHIJK23')).toBeNull();
    expect(conferirRecuperacao('')).toBe('Informe um código de recuperação.');
    for (const ruim of ['ABCD-EFGH-IJK2', 'ABCD-EFGH-IJK18', 'ABCD_EFGH_IJK23']) {
      expect(conferirRecuperacao(ruim), ruim).toMatch(/^O código de recuperação tem 13/u);
    }
  });
});
