// Painel do negócio (inventário §2): "qual item está perdendo margem e o que eu faço?".
//
// Blocos, na ordem das perguntas:
// 1. o alerta de margem, o maior bloco, com "Aplicar" (a tarefa mais frequente, a um clique);
// 2. a última nota de compra e as pendências de cadastro (a carne com a NCM que não combina);
// 3. a margem de cada item contra o alvo, e as premissas da simulação.
//
// Um fato, uma variável: a margem do alerta e a da linha do item saem do mesmo cálculo do backend
// (test_tela.py::test_a_tela_refaz_a_margem_do_alerta_so_com_o_catalogo).

import { useId, useState } from 'react';
import { chamar } from '../api/cliente.ts';
import { ErroApi } from '../api/problema.ts';
import { useAlertasAbertos, useCalculo, useCatalogo, useGravacao } from '../dados/empresa.ts';
import { dataDoDocumento, inteiro, noMeioDaFrase, porcentagem, reais } from '../dados/formatar.ts';
import {
  abaixoDoAlvo,
  estadoEmPalavras,
  NOME_REGIME,
  precisaCorrigirClassificacao,
  ultimaNota,
  type Alerta,
  type Carrinho,
  type Catalogo,
} from '../dados/pedidos.ts';
import { useSessao } from '../sessao/contexto.tsx';
import { Link } from '../shell/navegacao.tsx';
import { Pagina } from '../shell/Pagina.tsx';
import { Bloco, BotaoGravar, Carregando, escalaDeMargens, FalhaNoBloco, ListaDePremissas, MargemContraAlvo } from './comum.tsx';
import { CorrigirClassificacao, type PedidoDeCorrecao } from './Dialogos.tsx';
import { Explicacao, type PedidoDeExplicacao } from './Explicacao.tsx';
import './telas.css';

function frasePrincipal(a: Alerta): string {
  const nota = a.origem.numero ? `da nota ${a.origem.numero}` : 'da nota de compra';
  return `A margem de ${noMeioDaFrase(a.descricaoItem)} caiu de ${porcentagem(a.margemAntesPct)} para ${porcentagem(
    a.margemDepoisPct,
  )} depois ${nota}, de ${dataDoDocumento(a.origem.dataEmissao)}.`;
}

interface PropsAlerta {
  alerta: Alerta;
  outros: Alerta[];
  aoAplicado: () => void;
  aoExplicar: (pedido: PedidoDeExplicacao) => void;
}

function AlertaPrincipal({ alerta, outros, aoAplicado, aoExplicar }: PropsAlerta) {
  const { api } = useSessao();
  const gravacao = useGravacao();
  const idMotivo = useId();
  const [aplicando, setAplicando] = useState(false);
  const [falha, setFalha] = useState<string | null>(null);

  const aplicar = async () => {
    setAplicando(true);
    setFalha(null);
    try {
      await chamar(api.POST('/alertas/{alerta_id}/aplicar', { params: { path: { alerta_id: alerta.id } } }));
      aoAplicado();
    } catch (erro) {
      setFalha(erro instanceof ErroApi ? erro.message : 'Não foi possível aplicar o preço.');
    } finally {
      setAplicando(false);
    }
  };

  return (
    <>
      <p className="achado">{frasePrincipal(alerta)}</p>
      <dl className="faixa">
        <div className="faixa__celula">
          <dt>Preço sugerido</dt>
          <dd className="num dinheiro faixa__lider">{reais(alerta.precoSugerido)}</dd>
          <dd className="faixa__nota">
            hoje <span className="num">{reais(alerta.precoAtual)}</span>
          </dd>
        </div>
        <div className="faixa__celula">
          <dt>Margem agora</dt>
          <dd className="num faixa__valor negativo">{porcentagem(alerta.margemDepoisPct)}</dd>
          <dd className="faixa__nota">
            alvo <span className="num">{porcentagem(alerta.margemAlvoPct)}</span>
          </dd>
        </div>
        <div className="faixa__celula">
          <dt>Custo por unidade</dt>
          <dd className="num faixa__valor">{reais(alerta.custoNovo)}</dd>
          <dd className="faixa__nota">
            antes <span className="num">{reais(alerta.custoAnterior)}</span>
          </dd>
        </div>
      </dl>
      {alerta.precoSugerido === null ? (
        <p>{alerta.motivoSemPreco ?? 'Não há preço que alcance a margem-alvo.'}</p>
      ) : (
        <div className="acoes">
          <BotaoGravar
            gravacao={gravacao}
            ocupado={aplicando}
            principal
            idMotivo={idMotivo}
            onClick={() => void aplicar()}
          >
            Aplicar {reais(alerta.precoSugerido)}
          </BotaoGravar>
          <button
            type="button"
            className="botao-texto"
            onClick={() => {
              aoExplicar({ itemId: alerta.itemId, descricao: alerta.descricaoItem, regime: alerta.regime });
            }}
          >
            Por que este preço
          </button>
        </div>
      )}
      {falha !== null && (
        <p className="dialogo__falha" role="alert">
          {falha}
        </p>
      )}
      <p className="texto-suave origem">
        Nota {alerta.origem.numero} de {alerta.origem.emitente}, emitida em {dataDoDocumento(alerta.origem.dataEmissao)}.
        Margem a cada 100 unidades no {NOME_REGIME[alerta.regime]}, com o preço atual.
      </p>
      {outros.length > 0 && (
        <div className="outros">
          <h3>Outros alertas abertos</h3>
          <ul className="lista">
            {outros.slice(0, 4).map((a) => (
              <li key={a.id} className="lista__linha">
                <span>{a.descricaoItem}</span>
                <span className="num negativo">{porcentagem(a.margemDepoisPct)}</span>
                <span className="num dinheiro">{reais(a.precoSugerido)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </>
  );
}

function BlocoAlerta(props: {
  alertas: Alerta[] | undefined;
  erro: unknown;
  aoTentar: () => void;
  aoAplicado: () => void;
  aoExplicar: (p: PedidoDeExplicacao) => void;
}) {
  const { alertas, erro, aoTentar } = props;
  let corpo;
  if (erro !== undefined) {
    corpo = <FalhaNoBloco erro={erro} aoTentar={aoTentar} />;
  } else if (alertas === undefined) {
    corpo = <Carregando linhas={4} />;
  } else if (alertas.length === 0) {
    corpo = (
      <div className="vazio">
        <p>Nenhum item com a margem abaixo do alvo.</p>
        <p className="texto-suave">
          Quando uma nota de compra baixar a margem de um item, o alerta aparece aqui com o preço que volta ao
          alvo. <Link para="/notas">Importar uma nota</Link>
        </p>
      </div>
    );
  } else {
    const [primeiro, ...outros] = alertas;
    corpo = primeiro && (
      <AlertaPrincipal alerta={primeiro} outros={outros} aoAplicado={props.aoAplicado} aoExplicar={props.aoExplicar} />
    );
  }
  const total = alertas?.length ?? 0;
  return (
    <Bloco
      titulo="Margem abaixo do alvo"
      className="painel__alerta"
      extra={total > 1 ? <span className="bloco__meta">{inteiro(total)} alertas abertos</span> : undefined}
    >
      {corpo}
    </Bloco>
  );
}

function BlocoNota({ catalogo }: { catalogo: Catalogo | undefined }) {
  const nota = catalogo ? ultimaNota(catalogo) : null;
  return (
    <Bloco titulo="Última nota de compra" className="painel__metade" extra={<Link para="/notas">Importar nota</Link>}>
      {catalogo === undefined ? (
        <Carregando linhas={2} />
      ) : nota === null ? (
        <p className="texto-suave">Nenhuma nota importada ainda.</p>
      ) : (
        <p>
          Nota <span className="num">{nota.numero ?? '—'}</span>, de{' '}
          <span className="num">{dataDoDocumento(nota.data)}</span>: atualizou o custo de{' '}
          <span className="num">{inteiro(nota.itens)}</span> {nota.itens === 1 ? 'item' : 'itens'}.
        </p>
      )}
    </Bloco>
  );
}

function BlocoPendencias({
  catalogo,
  calculo,
  aoCorrigir,
}: {
  catalogo: Catalogo | undefined;
  calculo: Carrinho | undefined;
  aoCorrigir: (p: PedidoDeCorrecao) => void;
}) {
  const pendentes = calculo?.itens.filter(precisaCorrigirClassificacao) ?? [];
  return (
    <Bloco titulo="Cadastro a corrigir" className="painel__metade">
      {catalogo === undefined || calculo === undefined ? (
        <Carregando linhas={2} />
      ) : pendentes.length === 0 ? (
        <p className="texto-suave">Nenhum item com a classificação recusada pelo motor.</p>
      ) : (
        <ul className="lista">
          {pendentes.map((p) => {
            const item = catalogo.itens.find((i) => i.id === p.id);
            const erro = p.erros[0];
            return (
              <li key={p.id} className="pendencia">
                <span className="pendencia__texto">
                  <span>{p.descricao}</span>
                  <span className="pendencia__motivo">
                    {estadoEmPalavras(p)} <span className="num">({erro?.codigo})</span>
                  </span>
                </span>
                {item && erro && (
                  <button
                    type="button"
                    className="botao-secundario"
                    onClick={() => {
                      aoCorrigir({ item, erro });
                    }}
                  >
                    Corrigir
                  </button>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </Bloco>
  );
}

function BlocoMargens({ catalogo, calculo }: { catalogo: Catalogo | undefined; calculo: Carrinho | undefined }) {
  if (catalogo === undefined || calculo === undefined) {
    return (
      <Bloco titulo="Margem de cada item contra o alvo" className="painel__margens">
        <Carregando linhas={5} />
      </Bloco>
    );
  }
  const escala = escalaDeMargens(calculo.itens.flatMap((i) => [i.margemPct ?? null]).concat(catalogo.itens.map((i) => i.margemAlvoPct)));
  return (
    <Bloco
      titulo="Margem de cada item contra o alvo"
      className="painel__margens"
      extra={
        <span className="bloco__meta">
          {NOME_REGIME[calculo.regime]}, a cada {inteiro(catalogo.loteReferencia)} unidades
        </span>
      }
    >
      <table className="tabela tabela--margens">
        <thead>
          <tr>
            <th scope="col">Item</th>
            <th scope="col" className="tabela__grafico">
              <span className="so-leitor">Margem contra o alvo</span>
            </th>
            <th scope="col" className="num">
              Margem e alvo
            </th>
          </tr>
        </thead>
        <tbody>
          {catalogo.itens.map((item) => {
            const linha = calculo.itens.find((c) => c.id === item.id);
            const margem = linha?.margemPct ?? null;
            const quebra = abaixoDoAlvo(margem, item.margemAlvoPct);
            return (
              <tr key={item.id}>
                <th scope="row" className="tabela__item">
                  <span className="tabela__nome">{item.descricao}</span>
                  {linha && margem === null && <span className="tabela__sub">{estadoEmPalavras(linha)}</span>}
                </th>
                <td className="tabela__grafico">
                  <MargemContraAlvo margemPct={margem} alvoPct={item.margemAlvoPct} escalaPct={escala} />
                </td>
                <td className="num">
                  <span className={quebra ? 'negativo' : undefined}>{porcentagem(margem)}</span>
                  <span className="tabela__sub">alvo {porcentagem(item.margemAlvoPct)}</span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </Bloco>
  );
}

export function Painel() {
  const catalogo = useCatalogo();
  const calculo = useCalculo(catalogo.dados, catalogo.dados?.empresa.regimeAtual ?? null);
  const alertas = useAlertasAbertos();
  const [correcao, setCorrecao] = useState<PedidoDeCorrecao | null>(null);
  const [explicacao, setExplicacao] = useState<PedidoDeExplicacao | null>(null);

  const recarregarTudo = () => {
    catalogo.recarregar();
    alertas.recarregar();
  };

  const empresa = catalogo.dados?.empresa;
  const subtitulo = [empresa?.razaoSocial, calculo.dados?.avisoSimulacao].filter(Boolean).join(' · ');

  if (catalogo.erro !== undefined && catalogo.dados === undefined) {
    return (
      <Pagina titulo="Painel">
        <FalhaNoBloco erro={catalogo.erro} aoTentar={catalogo.recarregar} />
      </Pagina>
    );
  }

  return (
    <Pagina titulo="Painel" {...(subtitulo ? { subtitulo } : {})}>
      <div className="grade">
        <BlocoAlerta
          alertas={alertas.dados?.alertas}
          erro={alertas.erro}
          aoTentar={alertas.recarregar}
          aoAplicado={recarregarTudo}
          aoExplicar={setExplicacao}
        />
        {calculo.erro !== undefined ? (
          <Bloco titulo="Margem de cada item contra o alvo" className="painel__margens">
            <FalhaNoBloco erro={calculo.erro} aoTentar={calculo.recarregar} />
          </Bloco>
        ) : (
          <BlocoMargens catalogo={catalogo.dados} calculo={calculo.dados} />
        )}
        <BlocoNota catalogo={catalogo.dados} />
        <BlocoPendencias catalogo={catalogo.dados} calculo={calculo.dados} aoCorrigir={setCorrecao} />
        <Bloco titulo="Premissas da simulação" className="painel__premissas">
          {calculo.dados === undefined ? <Carregando /> : <ListaDePremissas premissas={calculo.dados.premissas} compacta />}
        </Bloco>
      </div>
      {catalogo.dados && (
        <CorrigirClassificacao
          pedido={correcao}
          catalogo={catalogo.dados}
          aoFechar={() => {
            setCorrecao(null);
          }}
          aoGravar={recarregarTudo}
        />
      )}
      <Explicacao
        pedido={explicacao}
        aoFechar={() => {
          setExplicacao(null);
        }}
      />
    </Pagina>
  );
}
