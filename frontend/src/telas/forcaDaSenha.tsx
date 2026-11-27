// O medidor de força da senha do cadastro: fraca (vermelho), média (amarelo) e forte (verde).
//
// - NIST SP 800-63B-4, §3.1.1.2 (lido em 2026-11-26): "Verifiers SHALL offer guidance to the subscriber to help the
//   subscriber choose a strong password." A mesma seção proíbe regra de composição: o medidor só orienta, não
//   exige mistura de letras, números ou símbolos, e não impede o envio. Quem decide é o backend (senha.py).
// - A estimativa é a do zxcvbn-ts (@zxcvbn-ts/core 4.2.0 e @zxcvbn-ts/language-common 4.1.3, MIT): conta quantas
//   tentativas um atacante precisaria, com a lista de senhas comuns, sequências, teclado e repetições. Fica fora o
//   pacote em português (@zxcvbn-ts/language-pt-br): o dicionário dele vem do OpenSubtitles (ODC-BY, que pede
//   manter um aviso de atribuição) e de uma lista da Wikipédia sem licença declarada.
// - A nota vai de 0 a 4 (TimeEstimates.mjs do zxcvbn-ts): a 3 é "proteção moderada contra ataque offline,
//   assumindo um hash lento como bcrypt, scrypt, PBKDF2 ou argon", e a 4, "proteção forte" no mesmo cenário. Sem o
//   dicionário em português, a estimativa é generosa com palavras da nossa língua ("minhacasa" leva 3, medido em
//   2026-11-26). Por isso só a 4 é forte: 0 a 2 = fraca; 3 = média; 4 = forte. Abaixo do mínimo do backend (8), é
//   fraca sempre.
// - O e-mail, a parte antes do @, a organização e as palavras do produto (senha.py, PALAVRAS_DO_PRODUTO) entram
//   como palavras de quem cadastra: uma senha feita delas vale menos.
// - A biblioteca é carregada só quando a pessoa começa a digitar a senha (import dinâmico, um arquivo à parte no
//   build), para não pesar nas outras páginas. A senha não sai do navegador.

import { useEffect, useState } from 'react';
import { REGRAS_DA_CONTA } from './legal.ts';
import { tamanhoDaSenha } from './regrasDeEntrada.ts';

export type Forca = 'fraca' | 'media' | 'forte';

export const NOME_DA_FORCA: Readonly<Record<Forca, string>> = { fraca: 'fraca', media: 'média', forte: 'forte' };

/** As palavras do produto que o backend recusa como senha (backend/app/contas/senha.py, PALAVRAS_DO_PRODUTO). */
export const PALAVRAS_DO_PRODUTO = ['contaai', 'conta ai', 'serraazul', 'serra azul'] as const;

/** A nota do zxcvbn (0 a 4) e o tamanho, na força que a tela mostra. */
export function forcaPelaNota(nota: number, tamanho: number): Forca {
  if (tamanho < REGRAS_DA_CONTA.senhaMinima || nota <= 2) {
    return 'fraca';
  }
  return nota === 3 ? 'media' : 'forte';
}

/** As palavras que valem menos numa senha desta pessoa. */
export function palavrasDaPessoa(email: string, organizacao: string): string[] {
  const limpo = email.trim().toLowerCase();
  const local = limpo.split('@', 1)[0] ?? '';
  return [limpo, local, organizacao.trim().toLowerCase(), ...PALAVRAS_DO_PRODUTO].filter((p) => p !== '');
}

type Avaliar = (senha: string, palavras: string[]) => number;

let carregando: Promise<Avaliar> | null = null;

/** Carrega o zxcvbn-ts uma vez só (import dinâmico) e devolve a função que dá a nota. */
export function carregarAvaliador(): Promise<Avaliar> {
  carregando ??= Promise.all([import('@zxcvbn-ts/core'), import('@zxcvbn-ts/language-common')]).then(
    ([{ ZxcvbnFactory }, comum]) => {
      const zxcvbn = new ZxcvbnFactory({ dictionary: comum.dictionary, graphs: comum.adjacencyGraphs });
      return (senha, palavras) => zxcvbn.check(senha, palavras).score;
    },
  );
  return carregando;
}

/**
 * A força da senha enquanto ela é digitada, ou null com o campo vazio. Antes de a biblioteca carregar (uma fração
 * de segundo), a senha curta já aparece como fraca; a longa espera a nota.
 */
export function useForcaDaSenha(senha: string, palavras: readonly string[]): Forca | null {
  const [avaliar, setAvaliar] = useState<Avaliar | null>(null);
  const vazia = senha === '';

  useEffect(() => {
    if (vazia || avaliar !== null) {
      return undefined;
    }
    let ativo = true;
    carregarAvaliador().then(
      (funcao) => {
        if (ativo) {
          setAvaliar(() => funcao);
        }
      },
      // Sem a biblioteca (falha de rede ao baixar o arquivo), a tela segue sem o medidor da senha longa.
      () => undefined,
    );
    return () => {
      ativo = false;
    };
  }, [vazia, avaliar]);

  if (vazia) {
    return null;
  }
  const tamanho = tamanhoDaSenha(senha);
  if (tamanho < REGRAS_DA_CONTA.senhaMinima) {
    return 'fraca';
  }
  return avaliar === null ? null : forcaPelaNota(avaliar(senha, [...palavras]), tamanho);
}

/**
 * A barra e a palavra. A barra é só desenho (aria-hidden); a palavra é lida junto do campo (aria-describedby, em
 * Campo), quando o foco chega nele, e não a cada tecla.
 */
export function MedidorDeForca({ forca, id }: { forca: Forca; id?: string }) {
  return (
    <p className="forca" data-forca={forca}>
      <span className="forca__trilho" aria-hidden="true">
        <span className="forca__barra" />
      </span>
      <span id={id} className="forca__rotulo">
        Senha {NOME_DA_FORCA[forca]}
      </span>
    </p>
  );
}
