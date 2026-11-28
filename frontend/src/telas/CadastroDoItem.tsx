// O cadastro do item (C3b, etapas 6 a 8; ADR 0018, seção da C3b2): criar o item pelo Catálogo ou a partir de uma
// linha sem par da nota, e alterar ou arquivar um item do catálogo.
//
// - A NCM vem da busca nos dados abertos (GET /busca/ncm, pela NCM ou pelo nome do produto), e a classificação é
//   escolhida entre as válidas para ela na data do cenário: a escolha é da pessoa (P3), e o backend aceita só uma das
//   válidas e tira o CST da fundamentação oficial. A tela não sugere classificação nem preço.
// - Itens com Imposto Seletivo ainda não entram (ADR 0017): a NCM aparece, mas fora da escolha, com o motivo.
// - A partir da nota, o código, a NCM, a unidade e o fornecedor são os da linha e não mudam; o item nasce com o custo
//   daquela nota (decisão b1 da C3b). A descrição vem do texto do fornecedor (dado não confiável, mostrado como texto)
//   e pode ser trocada.
// - Alterar manda só o que mudou, com o CNPJ e o código do fornecedor juntos (o contrato pede). A NCM e a unidade não
//   mudam: outra NCM é outro item.
// - Arquivar não tem volta (não há rota para desarquivar). A confirmação diz o que acontece antes do clique. Um item
//   na compra mensal de um cliente não sai (409): a tela diz de quais clientes e leva à página deles.

import { useRef, useState, type KeyboardEvent, type ReactNode, type SubmitEvent } from 'react';
import { chamar } from '../api/cliente.ts';
import { ErroApi } from '../api/problema.ts';
import { useEmpresaDaTela, useGravacao } from '../dados/empresa.ts';
import { cnpj as formatarCnpj, ncm as formatarNcm, porcentagem, reais, reaisPorUnidade } from '../dados/formatar.ts';
import type { Catalogo, Esquemas, ItemCatalogo } from '../dados/pedidos.ts';
import { useRecurso } from '../dados/recurso.ts';
import { useSessao } from '../sessao/contexto.tsx';
import { Link } from '../shell/navegacao.tsx';
import { ROTA_DOS_CLIENTES } from '../shell/rotas.ts';
import { Carregando, FalhaNoBloco } from './comum.tsx';
import { lerPreco, Molde } from './Dialogos.tsx';
import { AvisoDeFalha, Campo, GrupoDeOpcoes, falhaDe, rotuloDoEnvio, useEspera, type Opcao } from './formulario.tsx';
import {
  CODIGO_MAXIMO,
  DESCRICAO_MAXIMA,
  FRASE_DA_MARGEM,
  conferirCnpjDeTerceiro,
  conferirTexto,
  lerMargem,
  lerNcm,
  type OrigemDaNota,
  type Unidade,
} from './regrasDoCatalogo.ts';
import { normalizarCnpj } from './regrasDeEntrada.ts';
import './conta.css';
import './empresa.css';
import './telas.css';

type Candidato = Esquemas['CandidatoNcm'];
type ItemNovo = Esquemas['ItemNovoRequisicao'];
type Alteracao = Esquemas['ItemAlteracaoRequisicao'];

export const FRASE_DO_PRECO = 'Informe o preço em reais, com até 2 casas (ex.: 3,99).';
export const FRASE_ITEM_SEM_MUDANCA = 'Nada mudou: o item já tem estes valores.';
export const FRASE_DA_CLASSIFICACAO =
  'As válidas para esta NCM nos dados abertos da calculadora oficial, na data do cenário. A escolha é sua; confira com o contador.';
/** O tipo do 409 do item na compra mensal de clientes (backend, app/api/problemas.py). */
export const TIPO_ITEM_EM_USO = '/problemas/item-em-uso';
/** Itens com Imposto Seletivo ainda não entram no cadastro (backend, `criar_item`; ADR 0017). */
export const FRASE_DO_SELETIVO = 'O cadastro ainda não aceita itens com Imposto Seletivo.';

const OPCOES_DE_UNIDADE: readonly (Opcao & { valor: Unidade })[] = [
  { valor: 'UN', rotulo: 'Unidade (UN)' },
  { valor: 'KG', rotulo: 'Quilo (KG)' },
];

/** O número do contrato ("15.0000") como a pessoa digita ("15"). */
function paraDigitar(valor: string): string {
  return String(Number(valor)).replace('.', ',');
}

/** O CNPJ do fornecedor só tem o dígito exigido na empresa da conta, como no backend. */
function useExigeDigito(): boolean {
  return useEmpresaDaTela().tipo === 'conta';
}

function Dado({ nome, children }: { nome: string; children: ReactNode }) {
  return (
    <div className="lado__item">
      <dt>{nome}</dt>
      <dd>{children}</dd>
    </div>
  );
}

function Acoes({ children }: { children: ReactNode }) {
  return <div className="dialogo__acoes">{children}</div>;
}

// ---------------------------------------------------------------------------
// Cadastrar o item

interface Erros {
  descricao: string | null;
  consulta: string | null;
  ncm: string | null;
  classificacao: string | null;
  unidade: string | null;
  cnpj: string | null;
  codigo: string | null;
  preco: string | null;
  margem: string | null;
}

const SEM_ERROS: Erros = {
  descricao: null,
  consulta: null,
  ncm: null,
  classificacao: null,
  unidade: null,
  cnpj: null,
  codigo: null,
  preco: null,
  margem: null,
};

function opcaoDaNcm(c: Candidato & { ncm: string }): Opcao {
  return { valor: c.ncm, rotulo: <span className="num">{formatarNcm(c.ncm)}</span>, detalhe: c.descricao };
}

function opcaoDaClassificacao(c: Candidato['classificacoes'][number]): Opcao {
  return {
    valor: c.cClassTrib,
    rotulo: (
      <>
        <span className="num">{c.cClassTrib}</span> · {c.descricao}
      </>
    ),
    detalhe: (
      <>
        Redução de <span className="num">{porcentagem(c.reducaoPct)}</span>
        {c.especificaDoProduto ? ' · específica deste produto' : ' · vale para qualquer produto'}
      </>
    ),
  };
}

interface PropsFormulario {
  catalogo: Catalogo;
  origem: OrigemDaNota | null;
  aoFechar: () => void;
  aoCadastrado: (item: ItemCatalogo) => void;
}

function FormularioDoItem({ catalogo, origem, aoFechar, aoCadastrado }: PropsFormulario) {
  const { api } = useSessao();
  const gravacao = useGravacao();
  const exigirDigito = useExigeDigito();
  const espera = useEspera();
  const data = catalogo.cenario.operacao.data;
  const [descricao, setDescricao] = useState(origem?.linha.descricaoNota ?? '');
  const [consulta, setConsulta] = useState('');
  const [buscada, setBuscada] = useState<string | null>(origem ? origem.linha.ncm : null);
  const [ncm, setNcm] = useState<string | null>(null);
  const [cClassTrib, setCClassTrib] = useState<string | null>(null);
  const [unidade, setUnidade] = useState<Unidade | null>(origem?.linha.unidade ?? null);
  const [cnpjFornecedor, setCnpjFornecedor] = useState('');
  const [codigo, setCodigo] = useState('');
  const [preco, setPreco] = useState('');
  const [margem, setMargem] = useState('');
  const [erros, setErros] = useState<Erros>(SEM_ERROS);
  const [falha, setFalha] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  const refDescricao = useRef<HTMLInputElement>(null);
  const refConsulta = useRef<HTMLInputElement>(null);
  const refNcm = useRef<HTMLInputElement>(null);
  const refClassificacao = useRef<HTMLInputElement>(null);
  const refUnidade = useRef<HTMLInputElement>(null);
  const refCnpj = useRef<HTMLInputElement>(null);
  const refCodigo = useRef<HTMLInputElement>(null);
  const refPreco = useRef<HTMLInputElement>(null);
  const refMargem = useRef<HTMLInputElement>(null);

  const busca = useRecurso(buscada === null ? null : `busca:${buscada}:${data}`, (sinal) =>
    chamar(api.GET('/busca/ncm', { params: { query: { q: buscada ?? '', data } }, signal: sinal })),
  );
  const candidatos = (busca.dados?.candidatos ?? []).filter((c): c is Candidato & { ncm: string } => typeof c.ncm === 'string');
  const comSeletivo = candidatos.filter((c) => c.tributadoPeloImpostoSeletivo);
  const elegiveis = candidatos.filter((c) => !c.tributadoPeloImpostoSeletivo);
  // Uma NCM só (a busca pelo código, ou a da nota) já vem escolhida.
  const [unica] = elegiveis;
  const ncmEscolhida = ncm ?? (elegiveis.length === 1 && unica ? unica.ncm : null);
  const candidato = elegiveis.find((c) => c.ncm === ncmEscolhida);
  // A busca voltou e nada pode ser escolhido (só NCMs com Imposto Seletivo, ou nenhuma).
  const semEscolha = buscada !== null && busca.dados !== undefined && elegiveis.length === 0;
  const fraseDaNcm =
    comSeletivo.length > 0 && elegiveis.length === 0
      ? FRASE_DO_SELETIVO
      : 'Busque e escolha a NCM do produto.';

  const limpar = (campo: keyof Erros) => {
    setErros((e) => (e[campo] === null ? e : { ...e, [campo]: null }));
  };

  const buscar = () => {
    const texto = consulta.trim();
    if (texto.length < 2) {
      setErros((e) => ({ ...e, consulta: 'Digite a NCM, com 8 dígitos, ou ao menos 2 letras do nome do produto.' }));
      refConsulta.current?.focus();
      return;
    }
    setErros((e) => ({ ...e, consulta: null, ncm: null, classificacao: null }));
    setBuscada(lerNcm(texto) ?? texto.slice(0, 60));
    setNcm(null);
    setCClassTrib(null);
  };

  const buscarComEnter = (evento: KeyboardEvent<HTMLInputElement>) => {
    if (evento.key === 'Enter') {
      evento.preventDefault();
      buscar();
    }
  };

  const enviar = async (evento: SubmitEvent<HTMLFormElement>) => {
    evento.preventDefault();
    if (enviando || espera.aguardando || !gravacao.pode) {
      return;
    }
    const precoLido = lerPreco(preco);
    const margemLida = lerMargem(margem);
    const novos: Erros = {
      descricao: conferirTexto(descricao, DESCRICAO_MAXIMA, 'a descrição do item'),
      consulta: null,
      ncm: candidato ? null : fraseDaNcm,
      classificacao: candidato && (cClassTrib === null || !candidato.classificacoes.some((c) => c.cClassTrib === cClassTrib)) ? 'Escolha a classificação.' : null,
      unidade: unidade === null ? 'Escolha a unidade.' : null,
      cnpj: origem ? null : conferirCnpjDeTerceiro(cnpjFornecedor, exigirDigito),
      codigo: origem ? null : conferirTexto(codigo, CODIGO_MAXIMO, 'o código do produto no fornecedor'),
      preco: precoLido === null ? FRASE_DO_PRECO : null,
      margem: margemLida === null ? FRASE_DA_MARGEM : null,
    };
    setErros(novos);
    const primeiro = (Object.keys(novos) as (keyof Erros)[]).find((campo) => novos[campo] !== null);
    if (primeiro !== undefined || !candidato || cClassTrib === null || unidade === null || precoLido === null || margemLida === null) {
      setFalha(null);
      if (primeiro !== undefined) {
        const refs = {
          descricao: refDescricao,
          consulta: refConsulta,
          ncm: refNcm,
          classificacao: refClassificacao,
          unidade: refUnidade,
          cnpj: refCnpj,
          codigo: refCodigo,
          preco: refPreco,
          margem: refMargem,
        };
        (primeiro === 'ncm' && buscada === null ? refConsulta : refs[primeiro]).current?.focus();
      }
      return;
    }
    const corpo: ItemNovo = {
      cnpj: catalogo.empresa.cnpj,
      descricao: descricao.trim(),
      ncm: candidato.ncm,
      cClassTrib,
      unidade,
      cnpjFornecedor: origem ? origem.cnpjFornecedor : normalizarCnpj(cnpjFornecedor),
      codigoFornecedor: origem ? origem.linha.codigoFornecedor : codigo.trim(),
      precoVenda: precoLido,
      margemAlvoPct: margemLida,
    };
    if (origem) {
      corpo.daNota = { serie: origem.serie, numero: origem.numero, nItem: origem.linha.nItem };
    }
    setEnviando(true);
    setFalha(null);
    try {
      const { dados } = await chamar(api.POST('/catalogo/itens', { body: corpo }));
      aoCadastrado(dados.item);
    } catch (e) {
      const { texto, esperaS } = falhaDe(e, 'Não foi possível cadastrar o item. Tente de novo.');
      if (esperaS !== null) {
        espera.iniciar(esperaS);
      }
      setFalha(texto);
      setEnviando(false);
    }
  };

  let resultado: ReactNode = null;
  if (buscada !== null) {
    if (busca.erro !== undefined && busca.dados === undefined) {
      resultado = <FalhaNoBloco erro={busca.erro} aoTentar={busca.recarregar} />;
    } else if (busca.dados === undefined) {
      resultado = <Carregando linhas={2} />;
    } else if (candidatos.length === 0) {
      resultado = (
        <p className="campo__ajuda" role="status">
          Nenhuma NCM encontrada para “{buscada}” nos dados abertos. Tente o código de 8 dígitos ou outra palavra.
        </p>
      );
    } else {
      resultado = (
        <>
          {elegiveis.length > 1 && (
            <GrupoDeOpcoes
              ref={refNcm}
              legenda="NCM"
              nome="ncm"
              opcoes={elegiveis.map(opcaoDaNcm)}
              valor={ncmEscolhida}
              aoEscolher={(valor) => {
                setNcm(valor);
                setCClassTrib(null);
                limpar('ncm');
              }}
              erro={erros.ncm}
              ajuda={busca.dados.aviso}
            />
          )}
          {elegiveis.length === 1 && unica && (
            <dl className="lado__lista">
              <Dado nome="NCM">
                <span className="num">{formatarNcm(unica.ncm)}</span> · {unica.descricao}
              </Dado>
            </dl>
          )}
          {comSeletivo.length > 0 && (
            <p className="conta__aviso" role="note">
              {FRASE_DO_SELETIVO.replace(/\.$/u, ':')}{' '}
              {comSeletivo.map((c, i) => (
                <span key={c.ncm}>
                  {i > 0 ? ', ' : ''}NCM <span className="num">{formatarNcm(c.ncm)}</span>
                </span>
              ))}
              .
            </p>
          )}
          {candidato && candidato.classificacoes.length === 0 && (
            <p className="campo__ajuda">Não há classificação válida para esta NCM nos dados abertos.</p>
          )}
          {candidato && candidato.classificacoes.length > 0 && (
            <GrupoDeOpcoes
              ref={refClassificacao}
              legenda="Classificação (cClassTrib)"
              nome="classificacao"
              opcoes={candidato.classificacoes.map(opcaoDaClassificacao)}
              valor={cClassTrib}
              aoEscolher={(valor) => {
                setCClassTrib(valor);
                limpar('classificacao');
              }}
              erro={erros.classificacao}
              ajuda={FRASE_DA_CLASSIFICACAO}
            />
          )}
          {/* Sem a lista de NCMs para escolher, o erro da NCM fica aqui (com a lista, fica no grupo). */}
          {elegiveis.length <= 1 && erros.ncm !== null && <p className="campo__erro">{erros.ncm}</p>}
          {busca.dados.fonte && <p className="campo__ajuda">Fonte: {busca.dados.fonte}</p>}
        </>
      );
    }
  }

  return (
    <form className="dialogo__corpo formulario" noValidate onSubmit={(e) => void enviar(e)}>
      <AvisoDeFalha texto={falha} />
      {origem && (
        <>
          <dl className="lado__lista">
            <Dado nome="Da nota">
              Nota <span className="num">{origem.numero}</span>, série <span className="num">{origem.serie}</span>, linha{' '}
              <span className="num">{origem.linha.nItem}</span>
            </Dado>
            <Dado nome="Fornecedor">
              <span className="num">{formatarCnpj(origem.cnpjFornecedor)}</span> · código{' '}
              <span className="num">{origem.linha.codigoFornecedor}</span>
            </Dado>
            <Dado nome="Unidade">{origem.linha.unidade}</Dado>
            <Dado nome="Custo na nota">
              <span className="num">{reaisPorUnidade(origem.linha.custoUnitario)}</span> por {origem.linha.unidade}
            </Dado>
          </dl>
          <p className="campo__ajuda">
            O item nasce com o custo desta nota. Sem custo anterior, não há alerta agora: ele vem com a próxima nota do
            fornecedor, se a margem cair abaixo da margem-alvo.
          </p>
        </>
      )}
      <Campo
        ref={refDescricao}
        rotulo="Descrição do item"
        name="descricao"
        autoComplete="off"
        value={descricao}
        maxLength={DESCRICAO_MAXIMA + 20}
        erro={erros.descricao}
        ajuda={origem ? 'Veio da nota, como o fornecedor escreveu. Troque pelo nome que a empresa usa.' : 'Como a empresa chama o produto.'}
        onChange={(e) => {
          setDescricao(e.target.value);
          limpar('descricao');
        }}
      />
      {!origem && (
        <Campo
          ref={refConsulta}
          rotulo="NCM ou nome do produto"
          name="consulta"
          autoComplete="off"
          spellCheck={false}
          value={consulta}
          maxLength={60}
          erro={erros.consulta ?? (buscada === null ? erros.ncm : null)}
          ajuda="A NCM com 8 dígitos (com ou sem os pontos), ou palavras do nome. A busca é nos dados abertos da calculadora oficial."
          onKeyDown={buscarComEnter}
          onChange={(e) => {
            setConsulta(e.target.value);
            limpar('consulta');
          }}
          depois={
            <button type="button" className="botao-secundario" onClick={buscar}>
              Buscar
            </button>
          }
        />
      )}
      {resultado}
      {origem ? null : (
        <GrupoDeOpcoes
          ref={refUnidade}
          legenda="Unidade de venda"
          nome="unidade"
          opcoes={OPCOES_DE_UNIDADE}
          valor={unidade}
          aoEscolher={(valor) => {
            setUnidade(valor as Unidade);
            limpar('unidade');
          }}
          erro={erros.unidade}
          ajuda="A mesma da nota do fornecedor: a nota só casa com o item quando o código, a NCM e a unidade batem."
        />
      )}
      {!origem && (
        <>
          <Campo
            ref={refCnpj}
            rotulo="CNPJ do fornecedor"
            name="cnpjFornecedor"
            autoComplete="off"
            spellCheck={false}
            autoCapitalize="characters"
            className="num campo__cnpj"
            value={cnpjFornecedor}
            erro={erros.cnpj}
            ajuda="De quem a empresa compra este item. Com ou sem a pontuação."
            onChange={(e) => {
              setCnpjFornecedor(e.target.value);
              limpar('cnpj');
            }}
          />
          <Campo
            ref={refCodigo}
            rotulo="Código do produto no fornecedor"
            name="codigoFornecedor"
            autoComplete="off"
            spellCheck={false}
            value={codigo}
            maxLength={CODIGO_MAXIMO + 20}
            erro={erros.codigo}
            ajuda="O código (cProd) que aparece na nota do fornecedor."
            onChange={(e) => {
              setCodigo(e.target.value);
              limpar('codigo');
            }}
          />
        </>
      )}
      <Campo
        ref={refPreco}
        rotulo="Preço de venda por unidade (R$)"
        name="precoVenda"
        inputMode="decimal"
        autoComplete="off"
        className="num"
        value={preco}
        erro={erros.preco}
        ajuda="Por unidade: o valor do item na nota de venda (vUnCom)."
        onChange={(e) => {
          setPreco(e.target.value);
          limpar('preco');
        }}
      />
      <Campo
        ref={refMargem}
        rotulo="Margem-alvo (%)"
        name="margemAlvoPct"
        inputMode="decimal"
        autoComplete="off"
        className="num"
        value={margem}
        erro={erros.margem}
        ajuda="Uma nota nova que derrube a margem do item para baixo deste valor gera um alerta."
        onChange={(e) => {
          setMargem(e.target.value);
          limpar('margem');
        }}
      />
      {!gravacao.pode && <p className="gravar__motivo">{gravacao.motivo}</p>}
      <p className="so-leitor" role="status">
        {enviando ? 'Cadastrando: a calculadora oficial confere a NCM e a classificação.' : ''}
      </p>
      <Acoes>
        <button type="button" className="botao-secundario" onClick={aoFechar}>
          Cancelar
        </button>
        <button
          type="submit"
          className="botao-principal"
          disabled={!gravacao.pode || enviando || espera.aguardando || (origem !== null && semEscolha)}
        >
          {rotuloDoEnvio(enviando, espera.restanteMs, 'Cadastrando…', 'Cadastrar o item')}
        </button>
      </Acoes>
    </form>
  );
}

interface PropsCadastrar {
  aberto: boolean;
  catalogo: Catalogo | undefined;
  /** A linha sem par da nota de onde o item nasce, ou null (pelo Catálogo). */
  origem: OrigemDaNota | null;
  aoFechar: () => void;
  aoCadastrado: (item: ItemCatalogo) => void;
}

export function CadastrarItem({ aberto, catalogo, origem, aoFechar, aoCadastrado }: PropsCadastrar) {
  return (
    <Molde aberto={aberto && catalogo !== undefined} titulo={origem ? 'Cadastrar este item' : 'Cadastrar item'} aoFechar={aoFechar} largo>
      {catalogo && <FormularioDoItem catalogo={catalogo} origem={origem} aoFechar={aoFechar} aoCadastrado={aoCadastrado} />}
    </Molde>
  );
}

// ---------------------------------------------------------------------------
// Alterar e arquivar o item

/** Os clientes do 409 do item em uso, lidos do corpo com a própria checagem (nunca exibidos como HTML). */
export function clientesDoConflito(erro: unknown): { cnpj: string; nome: string }[] | null {
  if (!(erro instanceof ErroApi) || erro.problema?.type !== TIPO_ITEM_EM_USO) {
    return null;
  }
  const corpo = erro.corpo;
  if (typeof corpo !== 'object' || corpo === null || !('clientes' in corpo) || !Array.isArray(corpo.clientes)) {
    return [];
  }
  return (corpo.clientes as unknown[]).flatMap((c) =>
    typeof c === 'object' && c !== null && 'cnpj' in c && 'nome' in c && typeof c.cnpj === 'string' && typeof c.nome === 'string'
      ? [{ cnpj: c.cnpj, nome: c.nome }]
      : [],
  );
}

/** O corpo do PATCH: só o que mudou, com o fornecedor (CNPJ e código) junto. Sem campo além do CNPJ, nada mudou. */
export function mudancasDoItem(
  item: ItemCatalogo,
  cnpjDaEmpresa: string,
  valores: { descricao: string; margem: string; cnpjFornecedor: string; codigo: string },
): Alteracao {
  const corpo: Alteracao = { cnpj: cnpjDaEmpresa };
  const descricao = valores.descricao.trim();
  if (descricao !== item.descricao) {
    corpo.descricao = descricao;
  }
  if (Number(valores.margem) !== Number(item.margemAlvoPct)) {
    corpo.margemAlvoPct = valores.margem;
  }
  const cnpjFornecedor = normalizarCnpj(valores.cnpjFornecedor);
  const codigo = valores.codigo.trim();
  if (cnpjFornecedor !== item.fornecedor.cnpj || codigo !== item.fornecedor.codigo) {
    corpo.cnpjFornecedor = cnpjFornecedor;
    corpo.codigoFornecedor = codigo;
  }
  return corpo;
}

interface PropsArquivar {
  item: ItemCatalogo;
  cnpj: string;
  aoArquivado: () => void;
}

function ArquivarItem({ item, cnpj, aoArquivado }: PropsArquivar) {
  const { api } = useSessao();
  const gravacao = useGravacao();
  const [confirmando, setConfirmando] = useState(false);
  const [falha, setFalha] = useState<string | null>(null);
  const [clientes, setClientes] = useState<{ cnpj: string; nome: string }[] | null>(null);
  const [enviando, setEnviando] = useState(false);

  const arquivar = async () => {
    setEnviando(true);
    setFalha(null);
    setClientes(null);
    try {
      await chamar(api.POST('/catalogo/{item_id}/arquivar', { params: { path: { item_id: item.id } }, body: { cnpj } }));
      aoArquivado();
    } catch (e) {
      setFalha(falhaDe(e, 'Não foi possível arquivar o item. Tente de novo.').texto);
      setClientes(clientesDoConflito(e));
      setEnviando(false);
    }
  };

  return (
    <section className="conta__secao conta__perigo" aria-labelledby={`arquivar-${item.id}`}>
      <h3 id={`arquivar-${item.id}`}>Arquivar o item</h3>
      <p>
        O item sai do catálogo e dos cálculos da tela. O histórico dele (custos, preços, classificações e alertas) fica
        guardado, e os alertas abertos dele saem das listas. Uma nota nova com o código dele passa a ficar sem par.
      </p>
      <p className="conta__aviso" role="note">
        Arquivar não tem volta. Para vender o item de novo, cadastre-o outra vez: o código do fornecedor fica livre.
      </p>
      <AvisoDeFalha texto={falha} />
      {clientes !== null && (
        <div className="conta__secao">
          {clientes.length > 0 && (
            <ul className="conta__empresas">
              {clientes.map((c) => (
                <li key={c.cnpj}>
                  {c.nome}{' '}
                  <span className="tabela__sub">
                    <span className="num">{formatarCnpj(c.cnpj)}</span>
                  </span>
                </li>
              ))}
            </ul>
          )}
          <p>
            <Link para={ROTA_DOS_CLIENTES.caminho}>Ir aos {ROTA_DOS_CLIENTES.nome.toLowerCase()}</Link>
          </p>
        </div>
      )}
      {confirmando ? (
        <div className="conta__acoes">
          <button type="button" className="botao-perigo" disabled={!gravacao.pode || enviando} onClick={() => void arquivar()}>
            {enviando ? 'Arquivando…' : `Arquivar ${item.descricao}`}
          </button>
          <button
            type="button"
            className="botao-secundario"
            disabled={enviando}
            onClick={() => {
              setConfirmando(false);
              setFalha(null);
              setClientes(null);
            }}
          >
            Não arquivar
          </button>
        </div>
      ) : (
        <p>
          <button
            type="button"
            className="botao-secundario"
            disabled={!gravacao.pode}
            onClick={() => {
              setConfirmando(true);
            }}
          >
            Arquivar o item…
          </button>
        </p>
      )}
    </section>
  );
}

interface PropsFormularioAlterar {
  item: ItemCatalogo;
  cnpj: string;
  aoFechar: () => void;
  aoAlterado: (item: ItemCatalogo) => void;
  aoArquivado: () => void;
}

function FormularioDeAlteracao({ item, cnpj, aoFechar, aoAlterado, aoArquivado }: PropsFormularioAlterar) {
  const { api } = useSessao();
  const gravacao = useGravacao();
  const exigirDigito = useExigeDigito();
  const espera = useEspera();
  const [descricao, setDescricao] = useState(item.descricao);
  const [margem, setMargem] = useState(paraDigitar(item.margemAlvoPct));
  const [cnpjFornecedor, setCnpjFornecedor] = useState(formatarCnpj(item.fornecedor.cnpj));
  const [codigo, setCodigo] = useState(item.fornecedor.codigo);
  const [erros, setErros] = useState({ descricao: null as string | null, margem: null as string | null, cnpj: null as string | null, codigo: null as string | null });
  const [falha, setFalha] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  const refDescricao = useRef<HTMLInputElement>(null);
  const refMargem = useRef<HTMLInputElement>(null);
  const refCnpj = useRef<HTMLInputElement>(null);
  const refCodigo = useRef<HTMLInputElement>(null);
  type Campo = keyof typeof erros;

  const mudar = (campo: Campo, valor: string, definir: (v: string) => void) => {
    definir(valor);
    setAviso(null);
    setErros((e) => (e[campo] === null ? e : { ...e, [campo]: null }));
  };

  const enviar = async (evento: SubmitEvent<HTMLFormElement>) => {
    evento.preventDefault();
    if (enviando || espera.aguardando || !gravacao.pode) {
      return;
    }
    const margemLida = lerMargem(margem);
    const novos = {
      descricao: conferirTexto(descricao, DESCRICAO_MAXIMA, 'a descrição do item'),
      margem: margemLida === null ? FRASE_DA_MARGEM : null,
      cnpj: conferirCnpjDeTerceiro(cnpjFornecedor, exigirDigito),
      codigo: conferirTexto(codigo, CODIGO_MAXIMO, 'o código do produto no fornecedor'),
    };
    setErros(novos);
    const primeiro = (Object.keys(novos) as Campo[]).find((campo) => novos[campo] !== null);
    if (primeiro !== undefined || margemLida === null) {
      setFalha(null);
      if (primeiro !== undefined) {
        const refs = { descricao: refDescricao, margem: refMargem, cnpj: refCnpj, codigo: refCodigo };
        refs[primeiro].current?.focus();
      }
      return;
    }
    const corpo = mudancasDoItem(item, cnpj, { descricao, margem: margemLida, cnpjFornecedor, codigo });
    if (Object.keys(corpo).length === 1) {
      setFalha(null);
      setAviso(FRASE_ITEM_SEM_MUDANCA);
      return;
    }
    setEnviando(true);
    setFalha(null);
    setAviso(null);
    try {
      const { dados } = await chamar(api.PATCH('/catalogo/{item_id}', { params: { path: { item_id: item.id } }, body: corpo }));
      aoAlterado(dados.item);
    } catch (e) {
      const { texto, esperaS } = falhaDe(e, 'Não foi possível salvar o item. Tente de novo.');
      if (esperaS !== null) {
        espera.iniciar(esperaS);
      }
      setFalha(texto);
      setEnviando(false);
    }
  };

  return (
    <div className="dialogo__corpo">
      <form className="formulario" noValidate onSubmit={(e) => void enviar(e)}>
        <AvisoDeFalha texto={falha} />
        <dl className="lado__lista">
          <Dado nome="NCM">
            <span className="num">{formatarNcm(item.ncm)}</span> · {item.ncmDescricaoOficial}
          </Dado>
          <Dado nome="Unidade">{item.unidade}</Dado>
          <Dado nome="Preço de venda">
            <span className="num">{reais(item.precoVenda)}</span> por {item.unidade}. Muda pelo botão Preço, com o histórico.
          </Dado>
        </dl>
        <p className="campo__ajuda">A NCM e a unidade não mudam: um item com outra NCM é outro item.</p>
        <Campo
          ref={refDescricao}
          rotulo="Descrição do item"
          name="descricao"
          autoComplete="off"
          value={descricao}
          maxLength={DESCRICAO_MAXIMA + 20}
          erro={erros.descricao}
          onChange={(e) => {
            mudar('descricao', e.target.value, setDescricao);
          }}
        />
        <Campo
          ref={refMargem}
          rotulo="Margem-alvo (%)"
          name="margemAlvoPct"
          inputMode="decimal"
          autoComplete="off"
          className="num"
          value={margem}
          erro={erros.margem}
          ajuda="Uma nota nova que derrube a margem do item para baixo deste valor gera um alerta."
          onChange={(e) => {
            mudar('margem', e.target.value, setMargem);
          }}
        />
        <Campo
          ref={refCnpj}
          rotulo="CNPJ do fornecedor"
          name="cnpjFornecedor"
          autoComplete="off"
          spellCheck={false}
          autoCapitalize="characters"
          className="num campo__cnpj"
          value={cnpjFornecedor}
          erro={erros.cnpj}
          onChange={(e) => {
            mudar('cnpj', e.target.value, setCnpjFornecedor);
          }}
        />
        <Campo
          ref={refCodigo}
          rotulo="Código do produto no fornecedor"
          name="codigoFornecedor"
          autoComplete="off"
          spellCheck={false}
          value={codigo}
          maxLength={CODIGO_MAXIMO + 20}
          erro={erros.codigo}
          ajuda="A nota casa com o item por este código, do CNPJ acima, com a mesma NCM e a mesma unidade."
          onChange={(e) => {
            mudar('codigo', e.target.value, setCodigo);
          }}
        />
        {!gravacao.pode && <p className="gravar__motivo">{gravacao.motivo}</p>}
        <p className="campo__ajuda" role="status">
          {aviso}
        </p>
        <Acoes>
          <button type="button" className="botao-secundario" onClick={aoFechar}>
            Cancelar
          </button>
          <button type="submit" className="botao-principal" disabled={!gravacao.pode || enviando || espera.aguardando}>
            {rotuloDoEnvio(enviando, espera.restanteMs, 'Salvando…', 'Salvar o item')}
          </button>
        </Acoes>
      </form>
      <ArquivarItem item={item} cnpj={cnpj} aoArquivado={aoArquivado} />
    </div>
  );
}

interface PropsAlterar {
  item: ItemCatalogo | null;
  cnpj: string;
  aoFechar: () => void;
  aoAlterado: (item: ItemCatalogo) => void;
  aoArquivado: (item: ItemCatalogo) => void;
}

export function AlterarItem({ item, cnpj, aoFechar, aoAlterado, aoArquivado }: PropsAlterar) {
  return (
    <Molde aberto={item !== null} titulo="Alterar o item" aoFechar={aoFechar} largo>
      {item && (
        <FormularioDeAlteracao
          key={item.id}
          item={item}
          cnpj={cnpj}
          aoFechar={aoFechar}
          aoAlterado={aoAlterado}
          aoArquivado={() => {
            aoArquivado(item);
          }}
        />
      )}
    </Molde>
  );
}
