// Decisão de regime (inventário §2): "para vender a este cliente, tradicional ou híbrido?".
//
// A venda é a compra mensal do cliente empresa que o GET /catalogo descreve (`clientesB2B`), ao preço de
// venda atual (decisão 7 do plano v2.1). A tela não guarda cópia de preço nem de quantidade, e nenhum
// número é refeito aqui: todos vêm do POST /regime/comparar (ADR 0007).
//
// Blocos, na ordem das perguntas:
// 1. a régua do crédito (elemento-assinatura, inventário §3), com o achado em frase;
// 2. ao lado, o caixa da empresa em cada regime;
// 3. a venda por item, com a origem do crédito das compras, e o preço de empate com um concorrente do
//    regime regular;
// 4. premissas e simplificações, sempre visíveis.
//
// A tela nunca diz "opte pelo híbrido" (plano, seção 10): ela mostra o crédito e o caixa, e a decisão é da
// empresa com o contador.

import { useId, useState } from 'react';
import { useCatalogo, useComparacao } from '../dados/empresa.ts';
import type { EstadoRecurso } from '../dados/recurso.ts';
import { dataDoDocumento, inteiro, reais, reaisComSinal } from '../dados/formatar.ts';
import {
  antesDaComparacao,
  NOME_REGIME,
  pedidoDeRegime,
  type Catalogo,
  type ClienteB2B,
  type Comparacao,
} from '../dados/pedidos.ts';
import { Link } from '../shell/navegacao.tsx';
import { Pagina } from '../shell/Pagina.tsx';
import { ROTA_DOS_CLIENTES } from '../shell/rotas.ts';
import { Bloco, Carregando, FalhaNoBloco, ListaDePremissas } from './comum.tsx';
import './telas.css';

type ItemComparado = Comparacao['itens'][number];

const FONTE_DO_CREDITO: Record<ItemComparado['fonteCredito'], string> = {
  nfe: 'da nota',
  motor: 'estimado',
  custo_zero: 'custo zero',
};

/** O achado da tela: o crédito que o cliente leva em cada regime e o que isso custa no caixa da empresa. */
export function achadoDoRegime(c: Comparacao): string {
  // A frase de simulação (P6) já está no subtítulo da página, e o valor da venda, na régua logo abaixo.
  const frases = [
    `No híbrido, o cliente leva ${reais(c.hibrido.creditoCliente)} de crédito por mês; no tradicional, ${reais(
      c.tradicional.creditoCliente,
    )}.`,
  ];
  const diferenca = Number(c.diferencaCaixa);
  if (diferenca < 0) {
    frases.push(`Em troca, a empresa paga ${reais(Math.abs(diferenca))} a mais de imposto.`);
  } else if (diferenca > 0) {
    frases.push(`E a empresa fica com ${reais(diferenca)} a mais de caixa.`);
  } else {
    frases.push('O caixa da empresa fica igual.');
  }
  return frases.join(' ');
}

// ---------------------------------------------------------------------------
// A régua do crédito

const LARGURA_REGUA = 1000;
const ALTURA_REGUA = 28;

interface PropsLado {
  nome: string;
  precoCliente: string;
  custoLiquido: string;
  credito: string;
  /** O fim da escala, o mesmo nas duas barras: o maior preço total ao cliente. */
  escala: number;
  nota?: string | undefined;
}

/**
 * Uma barra da régua: o preço total ao cliente, com o custo líquido dele em tinta e o crédito que ele leva no
 * matiz. As duas barras usam a mesma escala, para o comprimento comparar.
 */
function LadoDaRegua({ nome, precoCliente, custoLiquido, credito, escala, nota }: PropsLado) {
  const idValores = useId();
  const x = (valor: string) => (escala > 0 ? (Number(valor) / escala) * LARGURA_REGUA : 0);
  const larguraCusto = x(custoLiquido);
  // Um crédito pequeno ainda aparece: no mínimo 3 unidades da escala de 1000.
  const larguraCredito = Number(credito) > 0 ? Math.max(3, x(credito)) : 0;
  return (
    <div className="regua__lado">
      <div className="regua__topo">
        <span className="regua__nome">{nome}</span>
        <span>
          <span className="num dinheiro">{reais(precoCliente)}</span> <span className="texto-suave">ao cliente</span>
        </span>
      </div>
      <svg
        className="regua__barra"
        viewBox={`0 0 ${String(LARGURA_REGUA)} ${String(ALTURA_REGUA)}`}
        preserveAspectRatio="none"
        role="img"
        aria-label={`${nome}: preço de ${reais(precoCliente)}, com ${reais(custoLiquido)} de custo líquido e ${reais(
          credito,
        )} de crédito para o cliente`}
        aria-describedby={idValores}
      >
        <rect x="0" y="0" width={LARGURA_REGUA} height={ALTURA_REGUA} className="regua__trilho" />
        <rect x="0" y="0" width={larguraCusto} height={ALTURA_REGUA} className="regua__custo" />
        <rect
          x={Math.min(larguraCusto, LARGURA_REGUA - larguraCredito)}
          y="0"
          width={larguraCredito}
          height={ALTURA_REGUA}
          className="regua__credito"
        />
      </svg>
      <dl id={idValores} className="regua__valores">
        <div>
          <dt>Custo líquido do cliente</dt>
          <dd className="num">{reais(custoLiquido)}</dd>
        </div>
        <div>
          <dt>
            <span className="regua__marca" aria-hidden="true" />
            Crédito que o cliente leva
          </dt>
          <dd className="num regua__valor-credito">{reais(credito)}</dd>
        </div>
      </dl>
      {nota !== undefined && <p className="texto-suave regua__nota">{nota}</p>}
    </div>
  );
}

function Regua({ c }: { c: Comparacao }) {
  const escala = Math.max(Number(c.tradicional.precoCliente), Number(c.hibrido.precoCliente));
  const sobra = Number(c.diferencaPrecoCliente);
  return (
    <div className="regua">
      <LadoDaRegua
        nome={NOME_REGIME.simples_tradicional}
        precoCliente={c.tradicional.precoCliente}
        custoLiquido={c.tradicional.custoLiquidoCliente}
        credito={c.tradicional.creditoCliente}
        escala={escala}
      />
      <LadoDaRegua
        nome={NOME_REGIME.simples_hibrido}
        precoCliente={c.hibrido.precoCliente}
        custoLiquido={c.hibrido.custoLiquidoCliente}
        credito={c.hibrido.creditoCliente}
        escala={escala}
        nota={
          sobra !== 0
            ? `${reaisComSinal(c.diferencaPrecoCliente)} de arredondamento.`
            : undefined
        }
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// O caixa da empresa

/** O tributo do mês em cada regime, na mesma escala: o que a empresa paga ao fisco (valores da API). */
function BarrasDoTributo({ c }: { c: Comparacao }) {
  const linhas = [
    { nome: 'Tradicional', valor: c.tradicional.tributo, detalhe: 'no DAS' },
    { nome: 'Híbrido', valor: c.hibrido.tributoLiquido, detalhe: 'líquido' },
  ];
  const escala = Math.max(...linhas.map((l) => Number(l.valor)));
  return (
    <div
      className="tributo"
      role="img"
      aria-label={`Tributo por mês: ${reais(c.tradicional.tributo)} no DAS do tradicional e ${reais(
        c.hibrido.tributoLiquido,
      )} líquidos no híbrido, depois do crédito das compras`}
    >
      {linhas.map((l) => (
        <div key={l.nome} className="tributo__linha" aria-hidden="true">
          <span className="tributo__nome">{l.nome}</span>
          <svg className="tributo__barra" viewBox="0 0 1000 12" preserveAspectRatio="none">
            <rect x="0" y="0" width="1000" height="12" className="regua__trilho" />
            <rect x="0" y="0" width={escala > 0 ? (Number(l.valor) / escala) * 1000 : 0} height="12" className="tributo__valor" />
          </svg>
          <span className="num tributo__numero">{reais(l.valor)}</span>
        </div>
      ))}
    </div>
  );
}

function Caixa({ c }: { c: Comparacao }) {
  return (
    <dl className="caixa">
      <div className="caixa__grafico">
        <dt>Tributo por mês</dt>
        <dd>
          <BarrasDoTributo c={c} />
        </dd>
      </div>
      <div className="caixa__regime">
        <dt>{NOME_REGIME.simples_tradicional}</dt>
        <dd>
          <dl className="caixa__contas">
            <div>
              <dt>CBS e IBS dentro do DAS</dt>
              <dd className="num">{reais(c.tradicional.tributo)}</dd>
            </div>
          </dl>
        </dd>
      </div>
      <div className="caixa__regime">
        <dt>{NOME_REGIME.simples_hibrido}</dt>
        <dd>
          <dl className="caixa__contas">
            <div>
              <dt>CBS e IBS destacados na venda</dt>
              <dd className="num">{reais(c.hibrido.debito)}</dd>
            </div>
            <div>
              <dt>Crédito das compras</dt>
              <dd className="num">−{reais(c.hibrido.creditoCompras)}</dd>
            </div>
            <div className="caixa__total">
              <dt>Tributo líquido</dt>
              <dd className="num">{reais(c.hibrido.tributoLiquido)}</dd>
            </div>
          </dl>
        </dd>
      </div>
      <div className="caixa__diferenca">
        <dt>Diferença de caixa por mês</dt>
        <dd>
          <span className="num faixa__lider">{reaisComSinal(c.diferencaCaixa)}</span>
          <span className="texto-suave caixa__explica">híbrido menos tradicional, ao mesmo preço</span>
        </dd>
      </div>
    </dl>
  );
}

// ---------------------------------------------------------------------------
// A venda por item e o empate

function TabelaDaVenda({ c }: { c: Comparacao }) {
  // A origem do crédito (da nota ou estimado) vai uma vez no cabeçalho quando é a mesma em todos os itens, e em cada
  // linha só quando muda de um item para outro: repetir a mesma palavra em toda linha é ruído.
  const fontes = new Set(c.itens.map((i) => i.fonteCredito));
  const fonteUnica = fontes.size === 1 ? c.itens[0]?.fonteCredito : undefined;
  return (
    <div className="tabela__moldura">
      <table className="tabela tabela--lista">
        <caption className="so-leitor">A venda mensal a {c.cliente.nome}, item por item, nos dois regimes</caption>
        <thead>
          <tr>
            <th scope="col">Item</th>
            <th scope="col" className="num">
              Quantidade
            </th>
            <th scope="col" className="num">
              Venda
            </th>
            <th scope="col" className="num">
              No DAS
            </th>
            <th scope="col" className="num">
              Destacado no híbrido
            </th>
            <th scope="col" className="num">
              Crédito das compras
              {fonteUnica !== undefined && (
                <span className="tabela__sub tabela__sub--texto">{FONTE_DO_CREDITO[fonteUnica]}</span>
              )}
            </th>
          </tr>
        </thead>
        <tbody>
          {c.itens.map((i) => (
            <tr key={i.id}>
              <th scope="row" className="tabela__item">
                <span className="tabela__nome">{i.descricao}</span>
              </th>
              <td data-rotulo="Quantidade" className="num">
                {inteiro(i.quantidade)}
              </td>
              <td data-rotulo="Venda" className="num dinheiro">
                {reais(i.valorVenda)}
              </td>
              <td data-rotulo="No DAS" className="num">
                {reais(i.tributoTradicional)}
              </td>
              <td data-rotulo="Destacado no híbrido" className="num">
                {reais(i.debitoHibrido)}
              </td>
              <td data-rotulo="Crédito das compras" className="num">
                {reais(i.creditoCompras)}
                {fonteUnica === undefined && (
                  <span className="tabela__sub tabela__sub--texto">{FONTE_DO_CREDITO[i.fonteCredito]}</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr>
            <th scope="row" className="tabela__item">
              <span className="tabela__nome">Total da venda</span>
            </th>
            <td />
            <td data-rotulo="Venda" className="num dinheiro">
              {reais(c.valorVenda)}
            </td>
            <td data-rotulo="No DAS" className="num">
              {reais(c.tradicional.tributo)}
            </td>
            <td data-rotulo="Destacado no híbrido" className="num">
              {reais(c.hibrido.debito)}
            </td>
            <td data-rotulo="Crédito das compras" className="num">
              {reais(c.hibrido.creditoCompras)}
            </td>
          </tr>
        </tfoot>
      </table>
    </div>
  );
}

function Empate({ c }: { c: Comparacao }) {
  const e = c.empateTradicional;
  if (!e) {
    return (
      <p className="texto-suave">O preço de empate não fechou no motor do Simples. A comparação acima vale.</p>
    );
  }
  const desconto = Number(e.descontoNecessario);
  const quanto =
    desconto > 0 ? `${reais(desconto)} a menos` : desconto < 0 ? `${reais(Math.abs(desconto))} a mais` : 'o mesmo preço';
  return (
    <>
      <p>
        Para empatar com um concorrente do regime regular, o preço no tradicional teria de ser{' '}
        <span className="num dinheiro">{reais(e.precoCliente)}</span> ({quanto}).
      </p>
      <dl className="caixa__contas">
        <div>
          <dt>CBS e IBS no DAS, a esse preço</dt>
          <dd className="num">{reais(e.tributo)}</dd>
        </div>
        <div>
          <dt>Custo líquido do cliente</dt>
          <dd className="num">{reais(e.custoLiquidoCliente)}</dd>
        </div>
        <div>
          <dt>No concorrente</dt>
          <dd className="num">{reais(e.custoLiquidoAlvo)}</dd>
        </div>
      </dl>
      {/* A definição que o número precisa; o detalhe do cálculo fica nas simplificações (hipotese da API). */}
      <p className="texto-suave origem">
        O concorrente vende os mesmos itens pelo mesmo preço total, e o custo do cliente nele é o do híbrido.
      </p>
    </>
  );
}

// ---------------------------------------------------------------------------
// A tela

function SeletorDeCliente({
  clientes,
  escolhido,
  aoEscolher,
}: {
  clientes: ClienteB2B[];
  escolhido: ClienteB2B;
  aoEscolher: (cnpj: string) => void;
}) {
  const id = useId();
  if (clientes.length < 2) {
    return null;
  }
  return (
    <div className="campo campo--linha">
      <label htmlFor={id}>Cliente</label>
      <select
        id={id}
        value={escolhido.cnpj}
        onChange={(e) => {
          aoEscolher(e.target.value);
        }}
      >
        {clientes.map((c) => (
          <option key={c.cnpj} value={c.cnpj}>
            {c.nome}
          </option>
        ))}
      </select>
    </div>
  );
}

interface PropsBlocos {
  catalogo: Catalogo;
  cliente: ClienteB2B;
  comparacao: EstadoRecurso<Comparacao>;
}

function BlocosDaComparacao({ catalogo, cliente, comparacao }: PropsBlocos) {
  const c = comparacao.dados;

  if (pedidoDeRegime(catalogo, cliente) === null) {
    return (
      <Bloco titulo="A venda a este cliente" className="regime__regua">
        <p>Um item da compra mensal deste cliente não está no catálogo: não há venda para comparar.</p>
      </Bloco>
    );
  }
  if (comparacao.erro !== undefined && c === undefined) {
    return (
      <Bloco titulo={`A venda a ${cliente.nome}`} className="regime__regua">
        <FalhaNoBloco erro={comparacao.erro} aoTentar={comparacao.recarregar} />
      </Bloco>
    );
  }
  if (c === undefined) {
    return (
      <>
        <Bloco titulo={`A venda a ${cliente.nome}`} className="regime__regua">
          <Carregando linhas={5} />
        </Bloco>
        <Bloco titulo="O caixa da empresa" className="regime__caixa">
          <Carregando linhas={4} />
        </Bloco>
      </>
    );
  }
  return (
    <>
      <Bloco
        titulo={`A venda a ${c.cliente.nome}`}
        className="regime__regua"
        extra={
          <span className="bloco__meta">
            {cliente.compraMensalDescricao}
            {comparacao.carregando ? ' · recalculando…' : ''}
          </span>
        }
      >
        <p className="achado">{achadoDoRegime(c)}</p>
        <Regua c={c} />
      </Bloco>
      <Bloco titulo="O caixa da empresa" className="regime__caixa">
        <Caixa c={c} />
      </Bloco>
      <Bloco titulo="A venda por item" className="regime__itens">
        <TabelaDaVenda c={c} />
      </Bloco>
      <Bloco titulo="Preço de empate no tradicional" className="regime__empate">
        <Empate c={c} />
      </Bloco>
      <Bloco titulo="Premissas da comparação" className="regime__premissas">
        <ListaDePremissas premissas={c.premissas} compacta />
        {/* As simplificações e a hipótese do empate valem para ler os números, mas não precisam estar abertas: o
            nome e o valor das premissas ficam à vista (P6 a P8), e o resto abre com um clique. */}
        <details className="simplificacoes__detalhe">
          <summary>Simplificações do cálculo</summary>
          <ul className="simplificacoes">
            {[...c.simplificacoes, ...(c.empateTradicional ? [c.empateTradicional.hipotese] : [])].map((s) => (
              <li key={s}>{s}</li>
            ))}
          </ul>
        </details>
      </Bloco>
    </>
  );
}

export function Regime() {
  const catalogo = useCatalogo();
  const [cnpjEscolhido, setCnpjEscolhido] = useState<string | null>(null);
  const dados = catalogo.dados;
  const clientes = dados?.clientesB2B ?? [];
  const cliente = clientes.find((c) => c.cnpj === cnpjEscolhido) ?? clientes[0];
  const comparavel = dados !== undefined && !antesDaComparacao(dados);
  // Antes de 2027 não há pedido: a tela explica por quê e não chama a API.
  const comparacao = useComparacao(comparavel ? dados : undefined, cliente);

  let corpo;
  if (catalogo.erro !== undefined && dados === undefined) {
    corpo = <FalhaNoBloco erro={catalogo.erro} aoTentar={catalogo.recarregar} />;
  } else if (dados === undefined) {
    corpo = (
      <div className="grade">
        <Bloco titulo="A venda ao cliente" className="regime__regua">
          <Carregando linhas={5} />
        </Bloco>
        <Bloco titulo="O caixa da empresa" className="regime__caixa">
          <Carregando linhas={4} />
        </Bloco>
      </div>
    );
  } else if (antesDaComparacao(dados)) {
    corpo = (
      <Bloco titulo="Comparação de regimes">
        <p>
          A comparação começa em 2027: antes disso, o motor do Simples não calcula a NF-e (VSN-015). O cenário desta
          empresa é de{' '}
          <span className="num">{dataDoDocumento(dados.cenario.operacao.data)}</span>.
        </p>
      </Bloco>
    );
  } else if (cliente === undefined) {
    corpo = (
      <Bloco titulo="Comparação de regimes">
        <div className="vazio">
          <p>Nenhum cliente empresa cadastrado.</p>
          <p className="texto-suave">
            A comparação usa a venda mensal a um cliente do regime regular.{' '}
            <Link para={ROTA_DOS_CLIENTES.caminho}>Cadastrar um cliente</Link>
          </p>
        </div>
      </Bloco>
    );
  } else {
    corpo = (
      <>
        <SeletorDeCliente clientes={clientes} escolhido={cliente} aoEscolher={setCnpjEscolhido} />
        <div className="grade">
          <BlocosDaComparacao catalogo={dados} cliente={cliente} comparacao={comparacao} />
        </div>
      </>
    );
  }

  // A frase de simulação vem da resposta; antes dela, a descrição do cenário da empresa.
  const aviso = comparacao.dados?.avisoSimulacao ?? dados?.cenario.descricao;
  const subtitulo = [dados?.empresa.razaoSocial, aviso].filter(Boolean).join(' · ');
  return (
    <Pagina
      titulo="Regime"
      {...(subtitulo ? { subtitulo } : {})}
      {...(dados ? { acao: <Link para={ROTA_DOS_CLIENTES.caminho}>{ROTA_DOS_CLIENTES.nome}</Link> } : {})}
    >
      {corpo}
    </Pagina>
  );
}

