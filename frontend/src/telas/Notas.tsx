// Notas de compra (inventário §2, "Importar nota"): "o que mudou no custo com esta nota?".
//
// Blocos, na ordem das perguntas:
// 1. o recibo da última importação, o maior bloco, que só aparece depois de importar: o achado (o custo que
//    mudou e a margem que caiu), os alertas com "Aplicar", os itens casados, os itens sem par e as premissas;
// 2. o envio do XML, com as notas de exemplo para baixar (C2c);
// 3. as notas já importadas (GET /notas). "Ver o recibo" abre o recibo gravado de uma delas (GET
//    /notas/{cnpj_emitente}/{serie}/{numero}, C3b2), sem enviar o XML de novo.
//
// Uma linha sem par de código sem cadastro vira item ali mesmo ("Cadastrar este item", C3b2): o cadastro vem com o
// código, a NCM, a unidade e o fornecedor da linha, e o item nasce com o custo da nota. As linhas que a API recusaria
// não têm o botão e dizem por quê (regrasDoCatalogo.ts, cadastravelDaNota).
//
// Todo texto da nota (nome do emitente, descrição do item) é do fornecedor: a tela o mostra como texto, nunca
// como HTML (docs/seguranca.md). Nenhum número é refeito aqui: o recibo vem pronto do backend.

import { useEffect, useId, useRef, useState, type ChangeEvent } from 'react';
import { chamar } from '../api/cliente.ts';
import { ErroApi } from '../api/problema.ts';
import { ACEITA_NOTA, conferirArquivoDaNota } from '../api/upload.ts';
import {
  importarNota,
  useAlertasAbertos,
  useCatalogo,
  useEmpresaDaTela,
  useGravacao,
  useNotas,
  useReciboDaNota,
  type ChaveDaNota,
} from '../dados/empresa.ts';
import {
  cnpj as formatarCnpj,
  dataDoDocumento,
  inteiro,
  ncm,
  noMeioDaFrase,
  porcentagem,
  reais,
  reaisPorUnidade,
  TRACO,
} from '../dados/formatar.ts';
import { notasDeExemplo } from '../dados/notasDeExemplo.ts';
import type { Alerta, Catalogo, ItemCatalogo, LinhaSemPar, NotaImportada, ReciboNota } from '../dados/pedidos.ts';
import { useSessao } from '../sessao/contexto.tsx';
import { ArquivoParaBaixar, Link } from '../shell/navegacao.tsx';
import { Pagina } from '../shell/Pagina.tsx';
import { CadastrarItem } from './CadastroDoItem.tsx';
import { Bloco, BotaoGravar, Carregando, FalhaNoBloco, ListaDePremissas } from './comum.tsx';
import { cadastravelDaNota, type OrigemDaNota } from './regrasDoCatalogo.ts';
import './telas.css';

type ItemCasado = ReciboNota['itensCasados'][number];

/** Quantos itens com o custo mudado o achado cita pelo nome; os outros entram na contagem. */
const CITADOS_NO_ACHADO = 3;

/** O nome do item no catálogo da empresa; sem ele, o texto da nota (do fornecedor). */
function nomeDoItem(catalogo: Catalogo | undefined, itemId: string, descricaoNota: string): string {
  return catalogo?.itens.find((i) => i.id === itemId)?.descricao ?? descricaoNota;
}

function fraseDaMargem(a: Alerta): string {
  return `caiu para ${porcentagem(a.margemDepoisPct)}, abaixo do alvo de ${porcentagem(a.margemAlvoPct)}`;
}

/** O custo que mudou e, se a nota gerou alerta para o mesmo item, a margem na mesma frase. */
function fraseDoCusto(item: ItemCasado, nome: string, alerta: Alerta | undefined): string {
  const variacao = Number(item.variacaoPct);
  const sentido = variacao > 0 ? 'subiu' : 'caiu';
  const custo = `O custo de ${noMeioDaFrase(nome)} ${sentido} ${porcentagem(Math.abs(variacao))} (de ${reais(
    item.custoAnterior,
  )} para ${reais(item.custoNovo)})`;
  return alerta ? `${custo}, e a margem ${fraseDaMargem(alerta)}.` : `${custo}.`;
}

/** O achado do recibo: o custo que mudou, a margem que caiu abaixo do alvo e o que ficou igual. */
export function achadoDoRecibo(recibo: ReciboNota, catalogo: Catalogo | undefined): string {
  const { itensCasados, alertas, nota } = recibo;
  // Itens cadastrados depois, a partir desta nota (C3b2): o custo dela entrou com eles.
  const cadastrados = recibo.itensSemPar.filter((i) => i.itemCadastrado).length;
  const depois =
    cadastrados === 0
      ? null
      : cadastrados === 1
        ? 'Depois, um item foi cadastrado a partir desta nota, com o custo dela.'
        : `Depois, ${inteiro(cadastrados)} itens foram cadastrados a partir desta nota, com o custo dela.`;
  if (itensCasados.length === 0) {
    const frase = `Nenhum item da nota ${nota.numero} casou com o catálogo: nenhum custo mudou.`;
    return depois === null ? frase : `${frase} ${depois}`;
  }
  const mudaram = itensCasados.filter((i) => i.atualizaCusto && i.variacaoPct !== null && Number(i.variacaoPct) !== 0);
  const historico = itensCasados.filter((i) => !i.atualizaCusto);
  const citados = mudaram.slice(0, CITADOS_NO_ACHADO);
  const frases: string[] = citados.map((i) =>
    fraseDoCusto(
      i,
      nomeDoItem(catalogo, i.itemId, i.descricaoNota),
      alertas.find((a) => a.itemId === i.itemId),
    ),
  );
  if (mudaram.length > CITADOS_NO_ACHADO) {
    frases.push(`Mais ${inteiro(mudaram.length - CITADOS_NO_ACHADO)} itens mudaram de custo.`);
  }
  // Os alertas de itens que não foram citados acima ganham a própria frase.
  for (const a of alertas.filter((x) => !citados.some((i) => i.itemId === x.itemId))) {
    frases.push(`A margem de ${noMeioDaFrase(a.descricaoItem)} ${fraseDaMargem(a)}.`);
  }
  const iguais = itensCasados.length - mudaram.length - historico.length;
  if (mudaram.length === 0 && historico.length === 0) {
    frases.push(`Nenhum custo mudou com a nota ${nota.numero}.`);
  } else if (iguais > 0) {
    frases.push(iguais === 1 ? 'O outro item ficou com o mesmo custo.' : `Os outros ${inteiro(iguais)} itens ficaram com o mesmo custo.`);
  }
  if (depois !== null) {
    frases.push(depois);
  }
  if (historico.length > 0) {
    frases.push(
      historico.length === 1
        ? 'Um item entrou só no histórico: a nota é mais antiga que o custo atual dele, que foi mantido.'
        : `${inteiro(historico.length)} itens entraram só no histórico: a nota é mais antiga que o custo atual deles, que foi mantido.`,
    );
  }
  return frases.join(' ');
}

const FONTE_DO_CREDITO: Record<NonNullable<ItemCasado['fonteCredito']>, string> = {
  nfe: 'da nota',
  motor: 'estimado',
};

// ---------------------------------------------------------------------------
// Recibo

function AlertaDoRecibo({ alerta, aberto, aoAplicado }: { alerta: Alerta; aberto: boolean | null; aoAplicado: () => void }) {
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

  let acao;
  if (alerta.precoSugerido === null) {
    acao = <p className="texto-suave">{alerta.motivoSemPreco ?? 'Não há preço que alcance a margem-alvo.'}</p>;
  } else if (aberto === false) {
    acao = <p className="texto-suave">Preço sugerido já aplicado.</p>;
  } else {
    acao = (
      <BotaoGravar gravacao={gravacao} ocupado={aplicando} idMotivo={idMotivo} onClick={() => void aplicar()}>
        Aplicar {reais(alerta.precoSugerido)}
      </BotaoGravar>
    );
  }

  return (
    <li className="recibo__alerta">
      <div className="recibo__alerta-texto">
        <span>{alerta.descricaoItem}</span>
        <span className="texto-suave">
          margem <span className="num negativo">{porcentagem(alerta.margemDepoisPct)}</span>, alvo{' '}
          <span className="num">{porcentagem(alerta.margemAlvoPct)}</span>; hoje{' '}
          <span className="num">{reais(alerta.precoAtual)}</span>, sugerido{' '}
          <span className="num dinheiro">{reais(alerta.precoSugerido)}</span>
        </span>
      </div>
      {acao}
      {falha !== null && (
        <p className="dialogo__falha" role="alert">
          {falha}
        </p>
      )}
    </li>
  );
}

function TabelaCasados({ recibo, catalogo }: { recibo: ReciboNota; catalogo: Catalogo | undefined }) {
  return (
    <div className="tabela__moldura">
      <table className="tabela tabela--lista">
        <caption className="so-leitor">Itens da nota {recibo.nota.numero} que casaram com o catálogo</caption>
        <thead>
          <tr>
            <th scope="col">Item</th>
            <th scope="col" className="num">
              Quantidade
            </th>
            <th scope="col" className="num">
              Custo antes
            </th>
            <th scope="col" className="num">
              Custo da nota
            </th>
            <th scope="col" className="num">
              Variação
            </th>
            <th scope="col" className="num">
              Crédito por unidade
            </th>
          </tr>
        </thead>
        <tbody>
          {recibo.itensCasados.map((i) => (
            <tr key={`${i.itemId}:${String(i.nItem)}`}>
              <th scope="row" className="tabela__item">
                <span className="tabela__nome">{nomeDoItem(catalogo, i.itemId, i.descricaoNota)}</span>
                <span className="tabela__sub">
                  código <span className="num">{i.codigoFornecedor}</span> · NCM <span className="num">{ncm(i.ncm)}</span>
                </span>
              </th>
              <td data-rotulo="Quantidade" className="num">
                {inteiro(i.quantidade)}
              </td>
              <td data-rotulo="Custo antes" className="num">
                {reais(i.custoAnterior)}
              </td>
              <td data-rotulo="Custo da nota" className="num">
                {reais(i.custoNovo)}
                {!i.atualizaCusto && <span className="tabela__sub tabela__sub--texto">entrou no histórico, custo mantido</span>}
              </td>
              <td data-rotulo="Variação" className="num">
                {i.variacaoPct === null ? TRACO : `${Number(i.variacaoPct) > 0 ? '+' : ''}${porcentagem(i.variacaoPct)}`}
              </td>
              <td data-rotulo="Crédito por unidade" className="num">
                {i.creditoCompraUnitario === null ? TRACO : reaisPorUnidade(i.creditoCompraUnitario)}
                {i.fonteCredito !== null && <span className="tabela__sub tabela__sub--texto">{FONTE_DO_CREDITO[i.fonteCredito]}</span>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function LinhaSemParDaNota({
  linha,
  recibo,
  catalogo,
  aoCadastrar,
}: {
  linha: LinhaSemPar;
  recibo: ReciboNota;
  catalogo: Catalogo | undefined;
  aoCadastrar: (origem: OrigemDaNota) => void;
}) {
  const gravacao = useGravacao();
  const idMotivo = useId();
  const cadastravel = cadastravelDaNota(linha, recibo.nota, recibo.itensSemPar);
  let acao = null;
  if (linha.itemCadastrado) {
    const nome = catalogo?.itens.find((i) => i.id === linha.itemCadastrado)?.descricao;
    acao = <span className="pendencia__feito">Cadastrado no catálogo{nome ? `: ${nome}` : ''}.</span>;
  } else if (cadastravel.pode) {
    const { origem } = cadastravel;
    acao = (
      <BotaoGravar
        gravacao={gravacao}
        ocupado={catalogo === undefined}
        idMotivo={idMotivo}
        onClick={() => {
          aoCadastrar(origem);
        }}
      >
        Cadastrar este item
      </BotaoGravar>
    );
  } else if (cadastravel.motivo !== null) {
    acao = <span className="texto-suave tabela__sub">{cadastravel.motivo}</span>;
  }
  return (
    <li className="pendencia pendencia--com-acao">
      <span className="pendencia__texto">
        <span>{linha.descricaoNota}</span>
        <span className="texto-suave tabela__sub">
          código <span className="num">{linha.codigoFornecedor}</span> · NCM <span className="num">{ncm(linha.ncm)}</span>
          {linha.unidade ? (
            <>
              {' '}
              · <span className="num">{linha.unidade}</span>
            </>
          ) : null}
          {linha.custoUnitario !== null && linha.custoUnitario !== undefined ? (
            <>
              {' '}
              · custo <span className="num">{reaisPorUnidade(linha.custoUnitario)}</span>
            </>
          ) : null}
        </span>
        {!linha.itemCadastrado && <span className="pendencia__motivo">{linha.motivo ?? 'Sem par no catálogo.'}</span>}
      </span>
      {acao}
    </li>
  );
}

function SemPar({
  recibo,
  catalogo,
  aoCadastrar,
}: {
  recibo: ReciboNota;
  catalogo: Catalogo | undefined;
  aoCadastrar: (origem: OrigemDaNota) => void;
}) {
  const faltam = recibo.itensSemPar.filter((i) => !i.itemCadastrado).length;
  return (
    <div className="recibo__secao">
      <h3>
        Itens que não casaram com o catálogo (<span className="num">{inteiro(recibo.itensSemPar.length)}</span>)
      </h3>
      <p className="texto-suave">
        Não mudaram custo. Um item casa quando o código do fornecedor, a NCM e a unidade batem com o cadastro.
        {faltam > 0 ? ' Um código sem cadastro vira item daqui, com o custo desta nota.' : ''}
      </p>
      <ul className="lista">
        {recibo.itensSemPar.map((i) => (
          <LinhaSemParDaNota
            key={`${i.codigoFornecedor}:${String(i.nItem)}`}
            linha={i}
            recibo={recibo}
            catalogo={catalogo}
            aoCadastrar={aoCadastrar}
          />
        ))}
      </ul>
    </div>
  );
}

interface PropsRecibo {
  recibo: ReciboNota;
  catalogo: Catalogo | undefined;
  /** Os ids dos alertas abertos agora, ou null sem a lista (aí quem decide é o backend, com 409). */
  abertos: ReadonlySet<string> | null;
  aoAplicado: () => void;
  aoCadastrar: (origem: OrigemDaNota) => void;
}

function Recibo({ recibo, catalogo, abertos, aoAplicado, aoCadastrar }: PropsRecibo) {
  const { nota } = recibo;
  return (
    <Bloco
      titulo={`Recibo da nota ${nota.numero}`}
      className="notas__recibo"
      extra={
        <span className="bloco__meta">
          {nota.serie ? `série ${nota.serie} · ` : ''}emitida em {dataDoDocumento(nota.dataEmissao)}
        </span>
      }
    >
      {recibo.jaImportada && (
        <p className="aviso-neutro" role="status">
          Esta nota já tinha sido importada: nada foi gravado de novo. Este é o recibo da primeira vez.
        </p>
      )}
      <p className="achado">{achadoDoRecibo(recibo, catalogo)}</p>
      <dl className="recibo__dados">
        <div>
          <dt>Emitente</dt>
          <dd>
            {nota.emitente.nome}
            <span className="tabela__sub num">{formatarCnpj(nota.emitente.cnpj)}</span>
          </dd>
        </div>
        <div>
          <dt>Crédito das compras</dt>
          <dd>
            {nota.temGrupoIbsCbs
              ? 'Lido do grupo IBSCBS da nota.'
              : 'A nota não traz o grupo IBSCBS: o crédito foi estimado sobre o custo.'}
          </dd>
        </div>
        {nota.homologacao && (
          <div>
            <dt>Ambiente</dt>
            <dd>Nota de homologação, sem valor fiscal.</dd>
          </div>
        )}
      </dl>
      {recibo.alertas.length > 0 && (
        <div className="recibo__secao">
          <h3>Margem abaixo do alvo depois desta nota</h3>
          <ul className="lista">
            {recibo.alertas.map((a) => (
              <AlertaDoRecibo key={a.id} alerta={a} aberto={abertos === null ? null : abertos.has(a.id)} aoAplicado={aoAplicado} />
            ))}
          </ul>
          <p className="texto-suave origem">
            Os alertas abertos também ficam no <Link para="/painel">Painel</Link>.
          </p>
        </div>
      )}
      {recibo.itensCasados.length > 0 && (
        <div className="recibo__secao">
          <h3>
            Itens que casaram com o catálogo (<span className="num">{inteiro(recibo.itensCasados.length)}</span>)
          </h3>
          <TabelaCasados recibo={recibo} catalogo={catalogo} />
        </div>
      )}
      {recibo.itensSemPar.length > 0 && <SemPar recibo={recibo} catalogo={catalogo} aoCadastrar={aoCadastrar} />}
      {recibo.premissas.length > 0 && (
        <div className="recibo__secao">
          <h3>Premissas</h3>
          {recibo.avisoSimulacao && <p className="texto-suave">{recibo.avisoSimulacao}</p>}
          <ListaDePremissas premissas={recibo.premissas} compacta />
        </div>
      )}
    </Bloco>
  );
}

// ---------------------------------------------------------------------------
// Envio do XML

/**
 * As notas fictícias de data/demo/notas para baixar (C2c). Aparecem também na demonstração compartilhada e no
 * modo mock, onde ninguém importa: a pessoa baixa a nota e cria um espaço para importar. O link é um arquivo da
 * mesma origem com `download` (ArquivoParaBaixar confere o endereço), sem blob: nem script.
 *
 * Na empresa da conta, não aparecem (C3, decisão 3): as notas são da Serra Azul, e a API recusa, com 422, a nota de
 * outro destinatário.
 */
function NotasDeExemplo() {
  const idTitulo = useId();
  const idDescricao = useId();
  const empresa = useEmpresaDaTela();
  const notas = notasDeExemplo();
  if (notas.length === 0 || empresa.tipo !== 'demonstracao') {
    return null;
  }
  return (
    <section className="exemplos" aria-labelledby={idTitulo}>
      <h3 id={idTitulo}>Notas de exemplo para baixar (fictícias)</h3>
      <ul className="exemplos__lista">
        {notas.map((n, i) => (
          <li key={n.arquivo} className="exemplos__linha">
            <ArquivoParaBaixar endereco={n.endereco} nome={n.arquivo} aria-describedby={`${idDescricao}-${String(i)}`}>
              {n.arquivo}
            </ArquivoParaBaixar>
            <span id={`${idDescricao}-${String(i)}`} className="exemplos__descricao">
              {n.descricao}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}

function Envio({ aoImportada }: { aoImportada: (recibo: ReciboNota) => void }) {
  const { api } = useSessao();
  const gravacao = useGravacao();
  const idCampo = useId();
  const idAjuda = useId();
  const idMotivo = useId();
  const refCampo = useRef<HTMLInputElement>(null);
  const [arquivo, setArquivo] = useState<File | null>(null);
  const [recusa, setRecusa] = useState<string | null>(null);
  const [falha, setFalha] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  const escolher = (e: ChangeEvent<HTMLInputElement>) => {
    const escolhido = e.target.files?.[0] ?? null;
    setFalha(null);
    if (escolhido === null) {
      setArquivo(null);
      setRecusa(null);
      return;
    }
    const conferencia = conferirArquivoDaNota(escolhido);
    setArquivo(conferencia.ok ? escolhido : null);
    setRecusa(conferencia.ok ? null : conferencia.motivo);
  };

  const enviar = async () => {
    if (arquivo === null) {
      return;
    }
    setEnviando(true);
    setFalha(null);
    try {
      const { dados } = await importarNota(api, arquivo);
      setArquivo(null);
      if (refCampo.current) {
        refCampo.current.value = '';
      }
      aoImportada(dados);
    } catch (erro) {
      setFalha(erro instanceof ErroApi ? erro.message : 'Não foi possível importar a nota.');
    } finally {
      setEnviando(false);
    }
  };

  return (
    <Bloco titulo="Importar nota de compra" className="notas__envio">
      <div className="envio">
        <div className="campo">
          <label htmlFor={idCampo}>Arquivo XML da NF-e</label>
          <input
            ref={refCampo}
            id={idCampo}
            type="file"
            accept={ACEITA_NOTA}
            className="campo__arquivo"
            aria-describedby={idAjuda}
            aria-invalid={recusa !== null}
            disabled={!gravacao.pode || enviando}
            onChange={escolher}
          />
          <p id={idAjuda} className="campo__ajuda">
            XML da NF-e de compra (modelo 55), até 1 MB.
          </p>
        </div>
        <BotaoGravar
          gravacao={gravacao}
          principal
          ocupado={enviando || arquivo === null}
          idMotivo={idMotivo}
          onClick={() => void enviar()}
        >
          {enviando ? 'Importando…' : 'Importar nota'}
        </BotaoGravar>
      </div>
      {recusa !== null && (
        <p className="dialogo__falha" role="alert">
          {recusa}
        </p>
      )}
      <p className="so-leitor" role="status">
        {enviando ? 'Importando a nota: os motores calculam o crédito e a margem.' : ''}
      </p>
      {falha !== null && (
        <p className="dialogo__falha" role="alert">
          {falha}
        </p>
      )}
      <NotasDeExemplo />
    </Bloco>
  );
}

// ---------------------------------------------------------------------------
// Notas importadas

/** A chave da nota no GET do recibo; sem série (só em recibos muito antigos), não há como pedi-lo. */
export function chaveDaNota(nota: ReciboNota['nota']): ChaveDaNota | null {
  return nota.serie ? { cnpjEmitente: nota.emitente.cnpj, serie: nota.serie, numero: nota.numero } : null;
}

function mesmaNota(a: ChaveDaNota | null, b: ChaveDaNota | null): boolean {
  return a !== null && b !== null && a.cnpjEmitente === b.cnpjEmitente && a.serie === b.serie && a.numero === b.numero;
}

function LinhaDaNota({ n, aberta, aoAbrir }: { n: NotaImportada; aberta: boolean; aoAbrir: (chave: ChaveDaNota) => void }) {
  const chave = chaveDaNota(n.nota);
  return (
    <tr>
      <th scope="row" className="tabela__item">
        <span className="tabela__nome">
          Nota <span className="num">{n.nota.numero}</span>
        </span>
        <span className="tabela__sub">
          {n.nota.serie ? `série ${n.nota.serie}` : 'sem série'}
          {n.nota.homologacao ? ' · homologação' : ''}
        </span>
      </th>
      <td data-rotulo="Emissão" className="num">
        {dataDoDocumento(n.nota.dataEmissao)}
      </td>
      <td data-rotulo="Emitente">
        {n.nota.emitente.nome}
        <span className="tabela__sub">
          <span className="num">{formatarCnpj(n.nota.emitente.cnpj)}</span>
        </span>
      </td>
      <td data-rotulo="Itens casados" className="num">
        {inteiro(n.itensCasados)}
      </td>
      <td data-rotulo="Sem par" className="num">
        {inteiro(n.itensSemPar)}
      </td>
      <td data-rotulo="Alertas" className="num">
        {inteiro(n.alertasGerados)}
        {n.alertasGerados > 0 && (
          <span className="tabela__sub tabela__sub--texto">
            {n.alertasAbertos === 0 ? 'todos aplicados' : `${inteiro(n.alertasAbertos)} ${n.alertasAbertos === 1 ? 'aberto' : 'abertos'}`}
          </span>
        )}
      </td>
      <td className="tabela__acoes">
        {aberta ? (
          <span className="texto-suave">Recibo aberto</span>
        ) : (
          chave && (
            <button
              type="button"
              className="botao-texto"
              aria-label={`Ver o recibo da nota ${n.nota.numero}`}
              onClick={() => {
                aoAbrir(chave);
              }}
            >
              Ver o recibo
            </button>
          )
        )}
      </td>
    </tr>
  );
}

interface PropsImportadas {
  notas: NotaImportada[] | undefined;
  erro: unknown;
  aoTentar: () => void;
  aberta: ChaveDaNota | null;
  aoAbrir: (chave: ChaveDaNota) => void;
}

function Importadas({ notas, erro, aoTentar, aberta, aoAbrir }: PropsImportadas) {
  let corpo;
  if (erro !== undefined && notas === undefined) {
    corpo = <FalhaNoBloco erro={erro} aoTentar={aoTentar} />;
  } else if (notas === undefined) {
    corpo = <Carregando linhas={3} />;
  } else if (notas.length === 0) {
    corpo = <p className="texto-suave">Nenhuma nota importada ainda.</p>;
  } else {
    corpo = (
      <div className="tabela__moldura">
        <table className="tabela tabela--lista">
          <caption className="so-leitor">Notas de compra importadas, da emissão mais recente para a mais antiga</caption>
          <thead>
            <tr>
              <th scope="col">Nota</th>
              <th scope="col" className="num">
                Emissão
              </th>
              <th scope="col">Emitente</th>
              <th scope="col" className="num">
                Itens casados
              </th>
              <th scope="col" className="num">
                Sem par
              </th>
              <th scope="col" className="num">
                Alertas
              </th>
              <th scope="col">
                <span className="so-leitor">Recibo</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {notas.map((n) => (
              <LinhaDaNota
                key={`${n.nota.emitente.cnpj}:${n.nota.serie ?? ''}:${n.nota.numero}`}
                n={n}
                aberta={mesmaNota(aberta, chaveDaNota(n.nota))}
                aoAbrir={aoAbrir}
              />
            ))}
          </tbody>
        </table>
      </div>
    );
  }
  return (
    <Bloco
      titulo="Notas importadas"
      className="notas__lista"
      extra={notas && notas.length > 0 ? <span className="bloco__meta">mais recentes primeiro</span> : undefined}
    >
      {corpo}
    </Bloco>
  );
}

/**
 * O recibo na tela: o da importação que acabou de acontecer (com o aviso de nota repetida, se veio), ou o gravado,
 * lido da API, quando a pessoa abre uma nota da lista ou cadastra um item a partir dela.
 */
function ReciboAberto(props: {
  chave: ChaveDaNota;
  doEnvio: ReciboNota | null;
  catalogo: Catalogo | undefined;
  abertos: ReadonlySet<string> | null;
  aoAplicado: () => void;
  aoCadastrar: (origem: OrigemDaNota) => void;
}) {
  const { chave, doEnvio } = props;
  const lido = useReciboDaNota(doEnvio === null ? chave : null);
  const recibo = doEnvio ?? lido.dados?.recibo;
  if (recibo === undefined) {
    return (
      <Bloco titulo={`Recibo da nota ${chave.numero}`} className="notas__recibo">
        {lido.erro !== undefined ? <FalhaNoBloco erro={lido.erro} aoTentar={lido.recarregar} /> : <Carregando linhas={4} />}
      </Bloco>
    );
  }
  return (
    <Recibo
      recibo={recibo}
      catalogo={props.catalogo}
      abertos={props.abertos}
      aoAplicado={props.aoAplicado}
      aoCadastrar={props.aoCadastrar}
    />
  );
}

interface NotaAberta {
  chave: ChaveDaNota;
  /** O recibo da importação que acabou de acontecer; null, o gravado (lido da API). */
  doEnvio: ReciboNota | null;
  /** Muda a cada cadastro a partir do recibo: o recibo gravado é lido de novo. */
  leitura: number;
}

export function Notas() {
  const catalogo = useCatalogo();
  const notas = useNotas();
  const alertas = useAlertasAbertos();
  const [aberta, setAberta] = useState<NotaAberta | null>(null);
  const [origem, setOrigem] = useState<OrigemDaNota | null>(null);
  const [salvo, setSalvo] = useState<string | null>(null);
  const [irAoRecibo, setIrAoRecibo] = useState(0);
  const refRecibo = useRef<HTMLDivElement>(null);

  // Quem abre um recibo pela lista vai até ele (o recibo fica no alto da página).
  useEffect(() => {
    if (irAoRecibo > 0) {
      refRecibo.current?.focus({ preventScroll: true });
      // O jsdom dos testes não tem scrollIntoView; os navegadores têm.
      // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition
      refRecibo.current?.scrollIntoView?.({ block: 'start' });
    }
  }, [irAoRecibo]);

  const recarregar = () => {
    notas.recarregar();
    alertas.recarregar();
    catalogo.recarregar();
  };

  const abrir = (chave: ChaveDaNota, doEnvio: ReciboNota | null) => {
    setSalvo(null);
    setAberta((a) => ({ chave, doEnvio, leitura: (a?.leitura ?? 0) + 1 }));
    setIrAoRecibo((n) => n + 1);
  };

  const cadastrado = (item: ItemCatalogo) => {
    setOrigem(null);
    setSalvo(`Item cadastrado: ${item.descricao}, com o custo desta nota.`);
    // Depois do cadastro, o recibo é o gravado: a linha passa a citar o item.
    setAberta((a) => (a === null ? a : { ...a, doEnvio: null, leitura: a.leitura + 1 }));
    recarregar();
  };

  // Enquanto a lista recarrega, a anterior serve: um alerta só sai dela quando o preço é aplicado.
  const abertos = alertas.dados ? new Set(alertas.dados.alertas.map((a) => a.id)) : null;
  const empresa = notas.dados?.empresa ?? catalogo.dados?.empresa;

  return (
    <Pagina titulo="Notas" {...(empresa ? { subtitulo: empresa.razaoSocial } : {})}>
      <div className="grade">
        {aberta !== null && (
          <div ref={refRecibo} tabIndex={-1} className="notas__aberta">
            {salvo !== null && (
              <p className="conta__salvo" role="status">
                {salvo}
              </p>
            )}
            <ReciboAberto
              key={`${aberta.chave.cnpjEmitente}:${aberta.chave.serie}:${aberta.chave.numero}:${String(aberta.leitura)}`}
              chave={aberta.chave}
              doEnvio={aberta.doEnvio}
              catalogo={catalogo.dados}
              abertos={abertos}
              aoAplicado={recarregar}
              aoCadastrar={setOrigem}
            />
          </div>
        )}
        <Envio
          aoImportada={(r) => {
            const chave = chaveDaNota(r.nota);
            if (chave !== null) {
              abrir(chave, r);
            }
            recarregar();
          }}
        />
        <Importadas
          notas={notas.dados?.notas}
          erro={notas.erro}
          aoTentar={notas.recarregar}
          aberta={aberta?.chave ?? null}
          aoAbrir={(chave) => {
            abrir(chave, null);
          }}
        />
      </div>
      <CadastrarItem
        aberto={origem !== null}
        catalogo={catalogo.dados}
        origem={origem}
        aoFechar={() => {
          setOrigem(null);
        }}
        aoCadastrado={cadastrado}
      />
    </Pagina>
  );
}
