// Catálogo e impacto (inventário §2): "quanto de CBS/IBS cada item carrega e quanto sobra?".
//
// A tabela é o catálogo calculado num regime, um lote de referência por item. A troca de regime refaz o
// cálculo nos motores; nenhum número é refeito na tela. As ações de cada linha: explicar, alterar o preço
// e, na linha que precisa, corrigir a classificação.

import { useState } from 'react';
import { catalogoVazio, useCalculo, useCatalogo, useGravacao } from '../dados/empresa.ts';
import { inteiro, ncm, noMeioDaFrase, porcentagem, reais } from '../dados/formatar.ts';
import {
  abaixoDoAlvo,
  calculado,
  estadoEmPalavras,
  NOME_REGIME,
  precisaCorrigirClassificacao,
  type Carrinho,
  type Catalogo as DadosCatalogo,
  type ItemCalculado,
  type ItemCatalogo,
  type Regime,
} from '../dados/pedidos.ts';
import { Pagina } from '../shell/Pagina.tsx';
import { Bloco, Carregando, FalhaNoBloco, ListaDePremissas } from './comum.tsx';
import { AlterarPreco, CorrigirClassificacao, type PedidoDeCorrecao } from './Dialogos.tsx';
import { Explicacao, type PedidoDeExplicacao } from './Explicacao.tsx';
import './telas.css';

const REGIMES: Regime[] = ['simples_tradicional', 'simples_hibrido'];

/** Soma em centavos dos valores como a tela os mostra (app-screens §2.1: totais das partes exibidas). */
function centavos(valor: string | null | undefined): number {
  return valor ? Math.round(Number(valor) * 100) : 0;
}

/** A carga de CBS e IBS de uma linha, somada dos dois valores exibidos. */
export function cargaDaLinha(linha: Pick<ItemCalculado, 'tributos'>): number | null {
  const { cbs, ibs } = linha.tributos;
  return cbs === null && ibs === null ? null : centavos(cbs) + centavos(ibs);
}

/** O achado da tela: o item que mais carrega CBS e IBS, e os itens com redução aplicada. */
export function achadoDoCatalogo(calculo: Carrinho, lote: number): string | null {
  const comCarga = calculo.itens
    .filter(calculado)
    .map((linha) => ({ linha, carga: cargaDaLinha(linha) }))
    .filter((x): x is { linha: ItemCalculado; carga: number } => x.carga !== null);
  if (comCarga.length === 0) {
    return null;
  }
  const maior = comCarga.reduce((a, b) => (b.carga > a.carga ? b : a));
  const frases = [
    `No ${NOME_REGIME[calculo.regime]}, ${noMeioDaFrase(maior.linha.descricao)} é o que mais carrega: ${reais(
      maior.carga / 100,
    )} de CBS e IBS a cada ${inteiro(lote)} unidades.`,
  ];
  const reduzidos = calculo.itens.filter((i) => i.reducaoPct !== null && i.reducaoPct !== undefined && Number(i.reducaoPct) > 0);
  if (reduzidos.length > 0) {
    frases.push(
      `Com redução de alíquota: ${reduzidos.map((i) => `${noMeioDaFrase(i.descricao)} (${porcentagem(i.reducaoPct)})`).join(', ')}.`,
    );
  }
  return frases.join(' ');
}

function Seletor({ regime, aoTrocar }: { regime: Regime; aoTrocar: (r: Regime) => void }) {
  return (
    <div className="segmentado" role="group" aria-label="Regime do cálculo">
      {REGIMES.map((r) => (
        <button
          key={r}
          type="button"
          className="segmentado__opcao"
          aria-pressed={r === regime}
          onClick={() => {
            aoTrocar(r);
          }}
        >
          {NOME_REGIME[r]}
        </button>
      ))}
    </div>
  );
}

interface PropsLinha {
  item: ItemCatalogo;
  linha: ItemCalculado | undefined;
  aoExplicar: () => void;
  aoAlterarPreco: () => void;
  aoCorrigir: (() => void) | null;
}

function Linha({ item, linha, aoExplicar, aoAlterarPreco, aoCorrigir }: PropsLinha) {
  const margem = linha?.margemPct ?? null;
  const quebra = abaixoDoAlvo(margem, item.margemAlvoPct);
  const ok = linha !== undefined && calculado(linha);
  return (
    <tr className={ok ? undefined : 'tabela__linha--pendente'}>
      <th scope="row" className="tabela__item">
        <span className="tabela__nome">{item.descricao}</span>
        <span className="tabela__sub">
          NCM <span className="num">{ncm(item.ncm)}</span> · <span className="num">{item.cClassTrib}</span>
        </span>
      </th>
      <td data-rotulo="Estado" className="tabela__estado">
        <span className={ok ? undefined : 'negativo'}>{linha ? estadoEmPalavras(linha) : '—'}</span>
        {aoCorrigir && (
          <button type="button" className="botao-secundario tabela__corrigir" onClick={aoCorrigir}>
            Corrigir
          </button>
        )}
      </td>
      <td data-rotulo="CBS" className="num">
        {reais(linha?.tributos.cbs)}
      </td>
      <td data-rotulo="IBS" className="num">
        {reais(linha?.tributos.ibs)}
      </td>
      <td data-rotulo="Redução" className="num">
        {porcentagem(linha?.reducaoPct)}
      </td>
      <td data-rotulo="Preço de venda" className="num">
        {reais(item.precoVenda)}
        <span className="tabela__sub">por {item.unidade}</span>
      </td>
      <td data-rotulo="Preço ao cliente" className="num dinheiro">
        {reais(linha?.precoCliente)}
      </td>
      <td data-rotulo="Margem" className={`num${quebra ? ' negativo' : ''}`}>
        {porcentagem(margem)}
        <span className="tabela__sub num">alvo {porcentagem(item.margemAlvoPct)}</span>
      </td>
      <td className="tabela__acoes">
        <button type="button" className="botao-texto" onClick={aoExplicar}>
          Explicar
        </button>
        <button type="button" className="botao-texto" onClick={aoAlterarPreco}>
          Preço
        </button>
      </td>
    </tr>
  );
}

function Tabela(props: {
  catalogo: DadosCatalogo;
  calculo: Carrinho;
  aoExplicar: (p: PedidoDeExplicacao) => void;
  aoAlterarPreco: (i: ItemCatalogo) => void;
  aoCorrigir: (p: PedidoDeCorrecao) => void;
}) {
  const { catalogo, calculo } = props;
  const { totais } = calculo;
  return (
    <div className="tabela__moldura">
      <table className="tabela tabela--catalogo">
        <caption className="so-leitor">
          Catálogo no {NOME_REGIME[calculo.regime]}, a cada {inteiro(catalogo.loteReferencia)} unidades
        </caption>
        <thead>
          <tr>
            <th scope="col">Item</th>
            <th scope="col">Estado</th>
            <th scope="col" className="num">
              CBS
            </th>
            <th scope="col" className="num">
              IBS
            </th>
            <th scope="col" className="num">
              Redução
            </th>
            <th scope="col" className="num">
              Preço de venda
            </th>
            <th scope="col" className="num">
              Preço ao cliente
            </th>
            <th scope="col" className="num">
              Margem
            </th>
            <th scope="col">
              <span className="so-leitor">Ações</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {catalogo.itens.map((item) => {
            const linha = calculo.itens.find((c) => c.id === item.id);
            const erro = linha?.erros[0];
            return (
              <Linha
                key={item.id}
                item={item}
                linha={linha}
                aoExplicar={() => {
                  props.aoExplicar({ itemId: item.id, descricao: item.descricao, regime: calculo.regime });
                }}
                aoAlterarPreco={() => {
                  props.aoAlterarPreco(item);
                }}
                aoCorrigir={
                  linha && erro && precisaCorrigirClassificacao(linha)
                    ? () => {
                        props.aoCorrigir({ item, erro });
                      }
                    : null
                }
              />
            );
          })}
        </tbody>
        <tfoot>
          <tr>
            <th scope="row" className="tabela__item">
              <span className="tabela__nome">Total dos itens calculados</span>
              <span className="tabela__sub">
                <span className="num">{inteiro(totais.itensCalculados)}</span> de{' '}
                <span className="num">{inteiro(totais.itensCalculados + totais.itensComErro)}</span> itens
              </span>
            </th>
            <td />
            <td data-rotulo="CBS" className="num">
              {reais(totais.tributos.cbs)}
            </td>
            <td data-rotulo="IBS" className="num">
              {reais(totais.tributos.ibs)}
            </td>
            <td />
            <td />
            <td data-rotulo="Preço ao cliente" className="num dinheiro">
              {reais(totais.precoCliente)}
            </td>
            <td />
            <td />
          </tr>
        </tfoot>
      </table>
    </div>
  );
}

export function Catalogo() {
  const catalogo = useCatalogo();
  const [escolhido, setEscolhido] = useState<Regime | null>(null);
  const regime = escolhido ?? catalogo.dados?.empresa.regimeAtual ?? null;
  const calculo = useCalculo(catalogo.dados, regime);
  const gravacao = useGravacao();
  const [explicacao, setExplicacao] = useState<PedidoDeExplicacao | null>(null);
  const [preco, setPreco] = useState<ItemCatalogo | null>(null);
  const [correcao, setCorrecao] = useState<PedidoDeCorrecao | null>(null);

  const achado = calculo.dados && catalogo.dados ? achadoDoCatalogo(calculo.dados, catalogo.dados.loteReferencia) : null;
  // A empresa nova, sem itens (C3a): não há cálculo, e a frase de simulação é a descrição do cenário.
  const vazio = catalogoVazio(catalogo.dados);
  const subtitulo = calculo.dados?.avisoSimulacao ?? (vazio ? catalogo.dados?.cenario.descricao : undefined);

  let corpo;
  if (catalogo.erro !== undefined && catalogo.dados === undefined) {
    corpo = <FalhaNoBloco erro={catalogo.erro} aoTentar={catalogo.recarregar} />;
  } else if (vazio && catalogo.dados) {
    corpo = (
      <div className="vazio">
        <p>Nenhum item no catálogo ainda.</p>
        <p className="texto-suave">
          A tabela mostra a CBS e o IBS de cada item, a cada {inteiro(catalogo.dados.loteReferencia)} unidades, quando o
          catálogo tiver itens.
        </p>
      </div>
    );
  } else if (calculo.erro !== undefined) {
    corpo = <FalhaNoBloco erro={calculo.erro} aoTentar={calculo.recarregar} />;
  } else if (catalogo.dados === undefined || calculo.dados === undefined) {
    corpo = <Carregando linhas={6} />;
  } else {
    corpo = (
      <Tabela
        catalogo={catalogo.dados}
        calculo={calculo.dados}
        aoExplicar={setExplicacao}
        aoAlterarPreco={setPreco}
        aoCorrigir={setCorrecao}
      />
    );
  }

  return (
    <Pagina titulo="Catálogo" {...(subtitulo ? { subtitulo } : {})}>
      <div className="catalogo__topo">
        {achado !== null ? <p className="achado achado--linha">{achado}</p> : <span />}
        {regime && !vazio && <Seletor regime={regime} aoTrocar={setEscolhido} />}
      </div>
      <Bloco
        titulo="CBS e IBS por item"
        extra={
          catalogo.dados &&
          !vazio && (
            <span className="bloco__meta">
              A cada {inteiro(catalogo.dados.loteReferencia)} unidades, ao preço de venda atual
              {calculo.carregando && calculo.dados ? ' · recalculando…' : ''}
            </span>
          )
        }
      >
        {corpo}
        {!gravacao.pode && !vazio && <p className="gravar__motivo catalogo__motivo">{gravacao.motivo}</p>}
      </Bloco>
      {!vazio && (
        <Bloco titulo="Premissas do cálculo" className="catalogo__premissas">
          {calculo.dados === undefined ? <Carregando /> : <ListaDePremissas premissas={calculo.dados.premissas} compacta />}
        </Bloco>
      )}
      <Explicacao
        pedido={explicacao}
        aoFechar={() => {
          setExplicacao(null);
        }}
      />
      <AlterarPreco
        item={preco}
        aoFechar={() => {
          setPreco(null);
        }}
        aoGravar={catalogo.recarregar}
      />
      {catalogo.dados && (
        <CorrigirClassificacao
          pedido={correcao}
          catalogo={catalogo.dados}
          aoFechar={() => {
            setCorrecao(null);
          }}
          aoGravar={catalogo.recarregar}
        />
      )}
    </Pagina>
  );
}
