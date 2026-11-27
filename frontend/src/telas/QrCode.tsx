// O QR code do segundo fator (C2b, etapa 5; ADR 0016) e o segredo para digitar à mão.
//
// - O QR é desenhado aqui, como SVG de elementos React, a partir da matriz do `encode()` da `uqr` 0.1.3 (MIT).
//   Fica fora o `renderSVG()`, que devolve texto e pediria dangerouslySetInnerHTML (proibido: docs/seguranca.md,
//   regras, item 1); fica fora também `<img src="data:...">`, que a CSP barra (img-src 'self'), e qualquer
//   serviço externo de QR, que receberia o segredo do TOTP.
// - O desenho é um único <path>: cada trecho de módulos escuros seguidos numa linha vira um retângulo. O `d` é
//   um atributo montado com números; não passa por HTML.
// - Fundo branco e módulos pretos em qualquer tema: o leitor de QR do celular espera o escuro sobre o claro.
// - A borda (zona de silêncio) tem 4 módulos, o valor dos exemplos do Project Nayuki (`toSvgString(qr0, 4)`,
//   nayuki.io/page/qr-code-generator-library, lido em 2026-11-26). A página não diz que a norma exige 4; a
//   norma ISO/IEC 18004 não foi lida.
// - A correção de erro é a M (até 15% de perda, pela documentação da `uqr`), contra a L padrão da biblioteca:
//   a câmera lê a tela com reflexo. O endereço otpauth:// de um e-mail comum dá a versão 8 (49 módulos).
// - Cada módulo tem 4 px inteiros, e o QR cresce com o endereço: o e-mail aceito vai até 254 caracteres, e o
//   acentuado triplica no endereço (ã vira %C3%A3), o que leva a até 157 módulos com a borda. Com um tamanho
//   fixo de 224 px, um e-mail longo dava 2,64 px por módulo, e o QR fotografado no Chrome não foi lido. Em tela
//   estreita, o max-width do CSS encolhe o desenho (quem está no celular digita o segredo).
// - O segredo e o endereço só vivem nas props: nada vai ao endereço da página, ao armazenamento ou ao log.

import { Fragment, useMemo } from 'react';
import { encode } from 'uqr';

/** Os módulos de borda em volta do desenho. */
export const BORDA_DO_QR = 4;

/** Pixels (CSS) por módulo: inteiro, para o desenho não borrar em tela de densidade 1. */
export const PX_POR_MODULO = 4;

/**
 * O `d` do <path> com os módulos escuros, um retângulo por trecho seguido de cada linha, deslocado pela borda.
 * Ex.: a linha [true, true, false, true] dá "M4 4h2v1h-2z M7 4h1v1h-1z" (com a borda de 4).
 */
export function caminhoDoQr(matriz: readonly (readonly boolean[])[], borda = BORDA_DO_QR): string {
  const trechos: string[] = [];
  matriz.forEach((linha, y) => {
    let x = 0;
    while (x < linha.length) {
      if (!linha[x]) {
        x += 1;
        continue;
      }
      const inicio = x;
      while (x < linha.length && linha[x]) {
        x += 1;
      }
      const largura = x - inicio;
      trechos.push(
        `M${String(inicio + borda)} ${String(y + borda)}h${String(largura)}v1h-${String(largura)}z`,
      );
    }
  });
  return trechos.join(' ');
}

interface PropsQr {
  /** O endereço otpauth:// que a API devolve no cadastro. */
  endereco: string;
  /** O nome que o leitor de tela anuncia. */
  rotulo?: string;
}

export function QrCode({ endereco, rotulo = 'QR code para o aplicativo autenticador' }: PropsQr) {
  const { tamanho, caminho } = useMemo(() => {
    const qr = encode(endereco, { ecc: 'M', border: 0 });
    return { tamanho: qr.size + 2 * BORDA_DO_QR, caminho: caminhoDoQr(qr.data) };
  }, [endereco]);
  const lado = String(tamanho);
  return (
    <svg
      className="qr"
      viewBox={`0 0 ${lado} ${lado}`}
      width={tamanho * PX_POR_MODULO}
      height={tamanho * PX_POR_MODULO}
      role="img"
      aria-label={rotulo}
      shapeRendering="crispEdges"
      focusable="false"
    >
      <rect width={lado} height={lado} fill="#ffffff" />
      <path d={caminho} fill="#000000" />
    </svg>
  );
}

/** O segredo em grupos de 4 caracteres, para ler e digitar. Os espaços não fazem parte do segredo. */
export function gruposDoSegredo(segredo: string): string[] {
  return segredo.match(/.{1,4}/gu) ?? [];
}

interface PropsSegredo {
  segredo: string;
}

/**
 * O segredo para digitar à mão, quando a câmera não lê o QR (ou o QR está no próprio celular). Cada grupo é um
 * elemento em linha, e o espaço entre eles é uma margem do CSS: copiar e colar leva o segredo sem espaços. O
 * <wbr> deixa a linha quebrar entre os grupos sem pôr nada no texto copiado. Conferido no Chrome: com os grupos
 * em flex (blocos), a cópia levava uma quebra de linha entre cada grupo.
 */
export function SegredoParaDigitar({ segredo }: PropsSegredo) {
  const grupos = gruposDoSegredo(segredo);
  return (
    <code className="segredo" translate="no">
      {grupos.map((grupo, i) => (
        // Os grupos são fatias fixas de um texto que não muda dentro do passo: a posição é a identidade.
        <Fragment key={i}>
          <span className="segredo__grupo">{grupo}</span>
          {i < grupos.length - 1 && <wbr />}
        </Fragment>
      ))}
    </code>
  );
}
