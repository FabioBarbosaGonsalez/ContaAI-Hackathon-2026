// Peças comuns das telas (app-screens §4, §7 e §11 da skill).
//
// Todo texto vindo da API é exibido como texto do React, nunca como HTML (docs/seguranca.md).

import type { ReactNode } from 'react';
import { ErroApi } from '../api/problema.ts';
import type { Gravacao } from '../dados/empresa.ts';
import { porcentagem } from '../dados/formatar.ts';
import type { Premissa } from '../dados/pedidos.ts';

interface PropsBloco {
  titulo: string;
  /** À direita do título: o período, a ação do bloco ou um link. */
  extra?: ReactNode;
  className?: string;
  children: ReactNode;
}

/** Um bloco da tela: cartão branco com borda de 1px, título em frase e conteúdo. */
export function Bloco({ titulo, extra, className, children }: PropsBloco) {
  return (
    <section className={`bloco${className ? ` ${className}` : ''}`} aria-label={titulo}>
      <div className="bloco__cabecalho">
        <h2>{titulo}</h2>
        {extra}
      </div>
      {children}
    </section>
  );
}

function mensagemDeErro(erro: unknown): string {
  return erro instanceof ErroApi ? erro.message : 'Não foi possível carregar.';
}

/** Falha dentro do bloco que falhou, com "Tentar de novo" (app-screens §11), nunca uma faixa na tela toda. */
export function FalhaNoBloco({ erro, aoTentar }: { erro: unknown; aoTentar: () => void }) {
  return (
    <div className="falha" role="alert">
      <p>{mensagemDeErro(erro)}</p>
      <button type="button" className="botao-texto" onClick={aoTentar}>
        Tentar de novo
      </button>
    </div>
  );
}

/** Carregando: o lugar final, com barras cinza do tamanho do dado, sem brilho nem mudança de layout. */
export function Carregando({ linhas = 3 }: { linhas?: number }) {
  return (
    <div className="carregando" aria-busy="true" aria-label="Carregando">
      {Array.from({ length: linhas }, (_, i) => (
        <span key={i} className="carregando__barra" />
      ))}
    </div>
  );
}

/** As premissas de todo resultado simulado, sempre visíveis junto dele (P6, P7, P8). */
export function ListaDePremissas({ premissas, compacta = false }: { premissas: readonly Premissa[]; compacta?: boolean }) {
  if (premissas.length === 0) {
    return <p className="texto-suave">Sem premissas: o resultado não é simulado.</p>;
  }
  return (
    <dl className={compacta ? 'premissas premissas--compacta' : 'premissas'}>
      {premissas.map((p) => (
        <div key={p.nome} className="premissas__linha">
          <dt>{p.nome}</dt>
          <dd>
            <span className="premissas__valor">{p.valor}</span>
            {compacta ? (
              // Na versão compacta o nome e o valor ficam sempre à vista; a fonte abre com um clique.
              <details className="premissas__detalhe">
                <summary>Fonte</summary>
                <span className="premissas__fonte">{p.fonte}</span>
              </details>
            ) : (
              <span className="premissas__fonte">{p.fonte}</span>
            )}
          </dd>
        </div>
      ))}
    </dl>
  );
}

interface PropsMargem {
  margemPct: string | null | undefined;
  alvoPct: string;
  /** O fim da escala, igual para todas as linhas do bloco (as barras se comparam). */
  escalaPct: number;
}

/**
 * A margem contra o alvo (app-screens §6.1, "drifted from its target"): a barra é a margem, o traço é o
 * alvo. Só a que fica abaixo do alvo leva cor. Sem margem (item não calculado), não há barra.
 */
export function MargemContraAlvo({ margemPct, alvoPct, escalaPct }: PropsMargem) {
  const largura = 240;
  const altura = 12;
  const x = (pct: number) => Math.max(0, Math.min(largura, (pct / escalaPct) * largura));
  const margem = margemPct === null || margemPct === undefined ? null : Number(margemPct);
  const alvo = Number(alvoPct);
  const quebra = margem !== null && margem < alvo;
  return (
    <svg
      className="margem-alvo"
      viewBox={`0 0 ${String(largura)} ${String(altura)}`}
      width={largura}
      height={altura}
      role="img"
      aria-label={
        margem === null
          ? `Sem margem calculada; alvo de ${porcentagem(alvoPct)}`
          : `Margem de ${porcentagem(margemPct)} contra o alvo de ${porcentagem(alvoPct)}`
      }
    >
      <rect x="0" y="5" width={largura} height="2" className="margem-alvo__trilho" />
      {margem !== null && (
        <rect
          x="0"
          y="2"
          width={x(margem)}
          height="8"
          className={quebra ? 'margem-alvo__barra margem-alvo__barra--quebra' : 'margem-alvo__barra'}
        />
      )}
      <rect x={x(alvo) - 1} y="0" width="2" height={altura} className="margem-alvo__alvo" />
    </svg>
  );
}

/** O fim da escala: o maior valor do bloco arredondado para cima, de 10 em 10 pontos. */
export function escalaDeMargens(valores: readonly (string | null | undefined)[]): number {
  const maior = Math.max(10, ...valores.filter((v): v is string => typeof v === 'string').map(Number));
  return Math.ceil(maior / 10) * 10;
}

interface PropsBotaoGravar {
  gravacao: Gravacao;
  ocupado?: boolean;
  principal?: boolean;
  onClick: () => void;
  children: ReactNode;
  idMotivo: string;
}

/** Botão que grava. Desligado, ele continua legível e diz por quê, logo abaixo (app-screens §8.1). */
export function BotaoGravar({ gravacao, ocupado = false, principal = false, onClick, children, idMotivo }: PropsBotaoGravar) {
  return (
    <div className="gravar">
      <button
        type="button"
        className={principal ? 'botao-principal' : 'botao-secundario'}
        disabled={!gravacao.pode || ocupado}
        aria-describedby={gravacao.pode ? undefined : idMotivo}
        onClick={onClick}
      >
        {children}
      </button>
      {!gravacao.pode && (
        <p id={idMotivo} className="gravar__motivo">
          {gravacao.motivo}
        </p>
      )}
    </div>
  );
}
