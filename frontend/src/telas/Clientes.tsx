// Clientes empresa (C3b, etapa 9; ADR 0018, seção da C3b2): "a quem a empresa vende, e o quê, por mês?".
//
// - A lista vem do GET /catalogo (`clientesB2B`): não há rota que liste só os clientes (achado no mapa da C3b). Cada
//   cliente é uma venda mensal que o Regime compara nos dois regimes.
// - Criar, alterar e excluir pelas rotas /clientes, com a mesma regra de gravação das outras telas (useGravacao): na
//   conta, na demonstração com o token e no espaço de avaliação.
// - O cliente é do regime regular: a comparação de regimes é feita na venda a um cliente do regime regular, e o
//   backend recusa um cliente do Simples (422). A tela não oferece a escolha.
// - A compra mensal usa os itens ativos do catálogo, cada um uma vez, com a quantidade por mês na unidade do item.
//   Sem itens no catálogo, não há compra para montar.
// - Excluir é de vez: o ContaAI não guarda histórico de clientes (backend, `excluir_cliente`).
// - O nome do município vem da lista dos motores (GET /referencias/municipios); sem ela (no modo mock, que só lê), a
//   tela mostra o código.

import { useId, useRef, useState, type SubmitEvent } from 'react';
import { chamar } from '../api/cliente.ts';
import { useCatalogo, useEmpresaDaTela, useGravacao } from '../dados/empresa.ts';
import { cnpj as formatarCnpj, inteiro } from '../dados/formatar.ts';
import type { Catalogo, ClienteB2B, Esquemas } from '../dados/pedidos.ts';
import { useListasDaEmpresa } from './camposDaEmpresa.tsx';
import { useSessao } from '../sessao/contexto.tsx';
import { Link } from '../shell/navegacao.tsx';
import { Pagina } from '../shell/Pagina.tsx';
import { ROTA_DOS_CLIENTES } from '../shell/rotas.ts';
import { CamposDoLocal } from './camposDaEmpresa.tsx';
import { Bloco, Carregando, FalhaNoBloco } from './comum.tsx';
import { Molde } from './Dialogos.tsx';
import { AvisoDeFalha, Campo, falhaDe, rotuloDoEnvio, useEspera } from './formulario.tsx';
import { conferirCnpjDeTerceiro, FRASE_DA_QUANTIDADE, lerQuantidade } from './regrasDoCatalogo.ts';
import { conferirRazaoSocial, normalizarCnpj } from './regrasDeEntrada.ts';
import './conta.css';
import './empresa.css';
import './telas.css';

type Novo = Esquemas['ClienteNovoRequisicao'];
type Alteracao = Esquemas['ClienteAlteracaoRequisicao'];

export const FRASE_CLIENTE_SEM_MUDANCA = 'Nada mudou: o cliente já tem estes dados.';
export const FRASE_SEM_ITENS = 'Cadastre itens no Catálogo primeiro: a compra mensal usa os itens do catálogo.';
export const FRASE_DO_REGIME_DO_CLIENTE =
  'O cliente é do regime regular: a comparação de regimes é feita na venda a um cliente do regime regular, e um cliente do Simples Nacional não entra.';

/** A quantidade do contrato ("2485.0000") como a pessoa digita ("2485"). */
function paraDigitar(valor: string): string {
  return String(Number(valor)).replace('.', ',');
}

function NomeDoMunicipio({ uf, codigo }: { uf: string; codigo: number }) {
  const { municipios } = useListasDaEmpresa(uf);
  const nome = municipios.dados?.uf === uf ? municipios.dados.municipios.find((m) => m.codigo === codigo)?.nome : undefined;
  return nome ? (
    <>
      {nome} · {uf}
    </>
  ) : (
    <>
      município <span className="num">{codigo}</span> · {uf}
    </>
  );
}

/** O que o cliente compra, com o nome de cada item no catálogo e a quantidade por mês. */
function compraEmPalavras(catalogo: Catalogo, cliente: ClienteB2B): string {
  return cliente.compraMensal
    .map((c) => {
      const item = catalogo.itens.find((i) => i.id === c.itemId);
      return item ? `${item.descricao} (${paraDigitar(c.quantidade)} ${item.unidade})` : `${c.itemId} (${paraDigitar(c.quantidade)})`;
    })
    .join(' · ');
}

// ---------------------------------------------------------------------------
// O formulário do cliente

interface Erros {
  cnpj: string | null;
  razaoSocial: string | null;
  uf: string | null;
  municipio: string | null;
  compra: string | null;
}

const SEM_ERROS: Erros = { cnpj: null, razaoSocial: null, uf: null, municipio: null, compra: null };

/** A compra mensal lida dos campos: os itens com quantidade, ou o primeiro item com quantidade fora do formato. */
export function lerCompra(
  quantidades: Record<string, string>,
  itens: readonly { id: string }[],
): { compra: { itemId: string; quantidade: string }[] } | { erro: string; itemId: string | null } {
  const compra: { itemId: string; quantidade: string }[] = [];
  for (const item of itens) {
    const texto = (quantidades[item.id] ?? '').trim();
    if (texto === '') {
      continue;
    }
    const quantidade = lerQuantidade(texto);
    if (quantidade === null) {
      return { erro: FRASE_DA_QUANTIDADE, itemId: item.id };
    }
    compra.push({ itemId: item.id, quantidade });
  }
  return compra.length === 0 ? { erro: 'Informe a quantidade por mês de ao menos um item.', itemId: null } : { compra };
}

/** O corpo do PATCH: só o que mudou, com a UF e o município juntos. Sem campo além do CNPJ, nada mudou. */
export function mudancasDoCliente(
  cliente: ClienteB2B,
  cnpjDaEmpresa: string,
  valores: { razaoSocial: string; uf: string; municipio: string; compra: { itemId: string; quantidade: string }[] },
): Alteracao {
  const corpo: Alteracao = { cnpj: cnpjDaEmpresa };
  if (valores.razaoSocial.trim() !== cliente.nome) {
    corpo.razaoSocial = valores.razaoSocial.trim();
  }
  if (valores.uf !== cliente.uf || Number(valores.municipio) !== cliente.municipio) {
    corpo.uf = valores.uf;
    corpo.municipio = Number(valores.municipio);
  }
  const chave = (lista: { itemId: string; quantidade: string | number }[]) =>
    lista
      .map((c) => `${c.itemId}=${String(Number(c.quantidade))}`)
      .sort()
      .join('|');
  if (chave(valores.compra) !== chave(cliente.compraMensal)) {
    corpo.compraMensal = valores.compra;
  }
  return corpo;
}

interface PropsFormulario {
  catalogo: Catalogo;
  /** null: um cliente novo. */
  cliente: ClienteB2B | null;
  aoFechar: () => void;
  aoSalvo: (frase: string) => void;
}

function FormularioDoCliente({ catalogo, cliente, aoFechar, aoSalvo }: PropsFormulario) {
  const { api } = useSessao();
  const gravacao = useGravacao();
  const exigirDigito = useEmpresaDaTela().tipo === 'conta';
  const espera = useEspera();
  const idCompra = useId();
  const [cnpjCliente, setCnpjCliente] = useState('');
  const [razaoSocial, setRazaoSocial] = useState(cliente?.nome ?? '');
  const [uf, setUf] = useState(cliente?.uf ?? '');
  const [municipio, setMunicipio] = useState(cliente ? String(cliente.municipio) : '');
  const [quantidades, setQuantidades] = useState<Record<string, string>>(() =>
    Object.fromEntries((cliente?.compraMensal ?? []).map((c) => [c.itemId, paraDigitar(c.quantidade)])),
  );
  const [erros, setErros] = useState<Erros>(SEM_ERROS);
  const [itemComErro, setItemComErro] = useState<string | null>(null);
  const [falha, setFalha] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  const refCnpj = useRef<HTMLInputElement>(null);
  const refRazao = useRef<HTMLInputElement>(null);
  const refUf = useRef<HTMLSelectElement>(null);
  const refMunicipio = useRef<HTMLSelectElement>(null);
  const refCompra = useRef<HTMLFieldSetElement>(null);
  const empresa = catalogo.empresa.cnpj;

  const limpar = (campo: keyof Erros) => {
    setAviso(null);
    setErros((e) => (e[campo] === null ? e : { ...e, [campo]: null }));
  };

  const enviar = async (evento: SubmitEvent<HTMLFormElement>) => {
    evento.preventDefault();
    if (enviando || espera.aguardando || !gravacao.pode) {
      return;
    }
    const lida = lerCompra(quantidades, catalogo.itens);
    let erroCnpj: string | null = null;
    if (cliente === null) {
      erroCnpj = conferirCnpjDeTerceiro(cnpjCliente, exigirDigito);
      if (erroCnpj === null && normalizarCnpj(cnpjCliente) === empresa) {
        erroCnpj = 'O cliente não pode ser a própria empresa.';
      }
    }
    const novos: Erros = {
      cnpj: erroCnpj,
      razaoSocial: conferirRazaoSocial(razaoSocial),
      uf: uf === '' ? 'Escolha a UF.' : null,
      municipio: municipio === '' ? 'Escolha o município.' : null,
      compra: 'erro' in lida ? lida.erro : null,
    };
    setErros(novos);
    setItemComErro('erro' in lida ? lida.itemId : null);
    const ordem = [
      [novos.cnpj, refCnpj],
      [novos.razaoSocial, refRazao],
      [novos.uf, refUf],
      [novos.municipio, refMunicipio],
    ] as const;
    const primeiro = ordem.find(([erro]) => erro !== null);
    if (primeiro !== undefined || 'erro' in lida) {
      setFalha(null);
      if (primeiro !== undefined) {
        primeiro[1].current?.focus();
      } else if ('erro' in lida) {
        const campo = lida.itemId === null ? null : refCompra.current?.querySelector<HTMLInputElement>(`input[data-item="${lida.itemId}"]`);
        (campo ?? refCompra.current?.querySelector<HTMLInputElement>('input'))?.focus();
      }
      return;
    }
    setEnviando(true);
    setFalha(null);
    setAviso(null);
    try {
      if (cliente === null) {
        const corpo: Novo = {
          cnpj: empresa,
          cnpjCliente: normalizarCnpj(cnpjCliente),
          razaoSocial: razaoSocial.trim(),
          regime: 'regime_regular',
          uf,
          municipio: Number(municipio),
          compraMensal: lida.compra,
        };
        const { dados } = await chamar(api.POST('/clientes', { body: corpo }));
        aoSalvo(`Cliente cadastrado: ${dados.cliente.nome}.`);
      } else {
        const corpo = mudancasDoCliente(cliente, empresa, { razaoSocial, uf, municipio, compra: lida.compra });
        if (Object.keys(corpo).length === 1) {
          setAviso(FRASE_CLIENTE_SEM_MUDANCA);
          setEnviando(false);
          return;
        }
        const { dados } = await chamar(
          api.PATCH('/clientes/{cnpj_cliente}', { params: { path: { cnpj_cliente: cliente.cnpj } }, body: corpo }),
        );
        aoSalvo(`Cliente salvo: ${dados.cliente.nome}.`);
      }
    } catch (e) {
      const { texto, esperaS } = falhaDe(e, 'Não foi possível salvar o cliente. Tente de novo.');
      if (esperaS !== null) {
        espera.iniciar(esperaS);
      }
      setFalha(texto);
      setEnviando(false);
    }
  };

  return (
    <form className="dialogo__corpo formulario" noValidate onSubmit={(e) => void enviar(e)}>
      <AvisoDeFalha texto={falha} />
      {cliente === null ? (
        <Campo
          ref={refCnpj}
          rotulo="CNPJ do cliente"
          name="cnpjCliente"
          autoComplete="off"
          spellCheck={false}
          autoCapitalize="characters"
          className="num campo__cnpj"
          value={cnpjCliente}
          erro={erros.cnpj}
          ajuda="Com ou sem a pontuação. O CNPJ não muda depois: outro CNPJ é outro cliente."
          onChange={(e) => {
            setCnpjCliente(e.target.value);
            limpar('cnpj');
          }}
        />
      ) : (
        <dl className="lado__lista">
          <div className="lado__item">
            <dt>CNPJ</dt>
            <dd>
              <span className="num">{formatarCnpj(cliente.cnpj)}</span>. O CNPJ não muda: outro CNPJ é outro cliente.
            </dd>
          </div>
        </dl>
      )}
      <Campo
        ref={refRazao}
        rotulo="Razão social"
        name="razaoSocial"
        autoComplete="off"
        value={razaoSocial}
        erro={erros.razaoSocial}
        onChange={(e) => {
          setRazaoSocial(e.target.value);
          limpar('razaoSocial');
        }}
      />
      <p className="campo__ajuda">{FRASE_DO_REGIME_DO_CLIENTE}</p>
      <CamposDoLocal
        refUf={refUf}
        refMunicipio={refMunicipio}
        uf={uf}
        municipio={municipio}
        erroUf={erros.uf}
        erroMunicipio={erros.municipio}
        aoMudarUf={(valor) => {
          setUf(valor);
          setMunicipio('');
          limpar('uf');
        }}
        aoMudarMunicipio={(valor) => {
          setMunicipio(valor);
          limpar('municipio');
        }}
      />
      <fieldset
        ref={refCompra}
        className="compra"
        aria-describedby={`${idCompra}-ajuda${erros.compra === null ? '' : ` ${idCompra}-erro`}`}
        aria-invalid={erros.compra === null ? undefined : true}
      >
        <legend>Compra mensal</legend>
        <p id={`${idCompra}-ajuda`} className="campo__ajuda">
          Quanto o cliente compra por mês, na unidade de cada item. Deixe em branco o que ele não compra.
        </p>
        <ul className="compra__lista">
          {catalogo.itens.map((item) => (
            <li key={item.id} className="compra__linha">
              <label htmlFor={`${idCompra}-${item.id}`} className="compra__item">
                {item.descricao}
              </label>
              <span className="compra__entrada">
                <input
                  id={`${idCompra}-${item.id}`}
                  data-item={item.id}
                  className="num"
                  inputMode="decimal"
                  autoComplete="off"
                  value={quantidades[item.id] ?? ''}
                  aria-invalid={itemComErro === item.id ? true : undefined}
                  onChange={(e) => {
                    const valor = e.target.value;
                    setQuantidades((q) => ({ ...q, [item.id]: valor }));
                    setItemComErro(null);
                    limpar('compra');
                  }}
                />
                <span className="texto-suave">{item.unidade} por mês</span>
              </span>
            </li>
          ))}
        </ul>
        {erros.compra !== null && (
          <p id={`${idCompra}-erro`} className="campo__erro">
            {erros.compra}
          </p>
        )}
      </fieldset>
      {!gravacao.pode && <p className="gravar__motivo">{gravacao.motivo}</p>}
      <p className="campo__ajuda" role="status">
        {enviando ? 'Salvando: a calculadora oficial confere o município.' : aviso}
      </p>
      <div className="dialogo__acoes">
        <button type="button" className="botao-secundario" onClick={aoFechar}>
          Cancelar
        </button>
        <button type="submit" className="botao-principal" disabled={!gravacao.pode || enviando || espera.aguardando}>
          {rotuloDoEnvio(enviando, espera.restanteMs, 'Salvando…', cliente === null ? 'Cadastrar o cliente' : 'Salvar o cliente')}
        </button>
      </div>
    </form>
  );
}

function ExcluirCliente({ cliente, empresa, aoFechar, aoExcluido }: { cliente: ClienteB2B; empresa: string; aoFechar: () => void; aoExcluido: () => void }) {
  const { api } = useSessao();
  const gravacao = useGravacao();
  const [falha, setFalha] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  const excluir = async () => {
    setEnviando(true);
    setFalha(null);
    try {
      await chamar(
        api.POST('/clientes/{cnpj_cliente}/excluir', { params: { path: { cnpj_cliente: cliente.cnpj } }, body: { cnpj: empresa } }),
      );
      aoExcluido();
    } catch (e) {
      setFalha(falhaDe(e, 'Não foi possível excluir o cliente. Tente de novo.').texto);
      setEnviando(false);
    }
  };

  return (
    <div className="dialogo__corpo">
      <AvisoDeFalha texto={falha} />
      <p>
        {cliente.nome} sai de vez: o ContaAI não guarda histórico de clientes. A comparação do Regime deixa de mostrar a
        venda a ele.
      </p>
      {!gravacao.pode && <p className="gravar__motivo">{gravacao.motivo}</p>}
      <div className="dialogo__acoes">
        <button type="button" className="botao-secundario" onClick={aoFechar}>
          Cancelar
        </button>
        <button type="button" className="botao-perigo" disabled={!gravacao.pode || enviando} onClick={() => void excluir()}>
          {enviando ? 'Excluindo…' : `Excluir ${cliente.nome}`}
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// A página

function Tabela({
  catalogo,
  aoAlterar,
  aoExcluir,
}: {
  catalogo: Catalogo;
  aoAlterar: (c: ClienteB2B) => void;
  aoExcluir: (c: ClienteB2B) => void;
}) {
  return (
    <div className="tabela__moldura">
      <table className="tabela tabela--lista">
        <caption className="so-leitor">Clientes empresa e a compra mensal de cada um</caption>
        <thead>
          <tr>
            <th scope="col">Cliente</th>
            <th scope="col">Local</th>
            <th scope="col" className="num">
              Itens por mês
            </th>
            <th scope="col">Compra mensal</th>
            <th scope="col">
              <span className="so-leitor">Ações</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {catalogo.clientesB2B.map((c) => (
            <tr key={c.cnpj}>
              <th scope="row" className="tabela__item">
                <span className="tabela__nome">{c.nome}</span>
                <span className="tabela__sub">
                  <span className="num">{formatarCnpj(c.cnpj)}</span>
                </span>
              </th>
              <td data-rotulo="Local">
                <NomeDoMunicipio uf={c.uf} codigo={c.municipio} />
              </td>
              <td data-rotulo="Itens por mês" className="num">
                {inteiro(c.compraMensal.length)}
              </td>
              <td data-rotulo="Compra mensal" className="clientes__compra">
                {compraEmPalavras(catalogo, c)}
                <span className="tabela__sub tabela__sub--texto">{c.compraMensalDescricao}</span>
              </td>
              <td className="tabela__acoes">
                <button
                  type="button"
                  className="botao-texto"
                  aria-label={`Alterar ${c.nome}`}
                  onClick={() => {
                    aoAlterar(c);
                  }}
                >
                  Alterar
                </button>
                <button
                  type="button"
                  className="botao-texto"
                  aria-label={`Excluir ${c.nome}`}
                  onClick={() => {
                    aoExcluir(c);
                  }}
                >
                  Excluir
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Clientes() {
  const catalogo = useCatalogo();
  const gravacao = useGravacao();
  const idMotivo = useId();
  const [editando, setEditando] = useState<ClienteB2B | 'novo' | null>(null);
  const [excluindo, setExcluindo] = useState<ClienteB2B | null>(null);
  const [salvo, setSalvo] = useState<string | null>(null);
  const dados = catalogo.dados;
  const semItens = dados !== undefined && dados.itens.length === 0;
  const motivo = !gravacao.pode ? gravacao.motivo : semItens ? FRASE_SEM_ITENS : null;

  const depoisDeGravar = (frase: string) => {
    setEditando(null);
    setExcluindo(null);
    setSalvo(frase);
    catalogo.recarregar();
  };

  let corpo;
  if (catalogo.erro !== undefined && dados === undefined) {
    corpo = <FalhaNoBloco erro={catalogo.erro} aoTentar={catalogo.recarregar} />;
  } else if (dados === undefined) {
    corpo = <Carregando linhas={4} />;
  } else if (dados.clientesB2B.length === 0) {
    corpo = (
      <div className="vazio">
        <p>Nenhum cliente empresa cadastrado.</p>
        <p className="texto-suave">
          A comparação de regimes usa a venda mensal a um cliente do regime regular.
          {semItens && (
            <>
              {' '}
              A compra mensal usa os itens do catálogo: <Link para="/catalogo">cadastre os itens</Link> primeiro.
            </>
          )}
        </p>
      </div>
    );
  } else {
    corpo = (
      <Tabela
        catalogo={dados}
        aoAlterar={(c) => {
          setSalvo(null);
          setEditando(c);
        }}
        aoExcluir={(c) => {
          setSalvo(null);
          setExcluindo(c);
        }}
      />
    );
  }

  const subtitulo = dados ? `${dados.empresa.razaoSocial} · a venda mensal a cada cliente, que o Regime compara nos dois regimes` : undefined;
  return (
    <Pagina
      titulo={ROTA_DOS_CLIENTES.nome}
      {...(subtitulo ? { subtitulo } : {})}
      acao={<Link para="/regime">Comparar no Regime</Link>}
    >
      {salvo !== null && (
        <p className="conta__salvo" role="status">
          {salvo}
        </p>
      )}
      <Bloco
        titulo="Clientes"
        extra={
          dados && (
            <button
              type="button"
              className="botao-principal"
              disabled={motivo !== null}
              aria-describedby={motivo === null ? undefined : idMotivo}
              onClick={() => {
                setSalvo(null);
                setEditando('novo');
              }}
            >
              Cadastrar cliente
            </button>
          )
        }
      >
        {corpo}
        {dados && motivo !== null && (
          <p id={idMotivo} className="gravar__motivo catalogo__motivo">
            {motivo}
          </p>
        )}
      </Bloco>
      {dados && (
        <>
          <Molde
            aberto={editando !== null}
            titulo={editando === 'novo' ? 'Cadastrar cliente' : 'Alterar o cliente'}
            aoFechar={() => {
              setEditando(null);
            }}
            largo
          >
            {editando !== null && (
              <FormularioDoCliente
                key={editando === 'novo' ? 'novo' : editando.cnpj}
                catalogo={dados}
                cliente={editando === 'novo' ? null : editando}
                aoFechar={() => {
                  setEditando(null);
                }}
                aoSalvo={depoisDeGravar}
              />
            )}
          </Molde>
          <Molde
            aberto={excluindo !== null}
            titulo="Excluir o cliente"
            aoFechar={() => {
              setExcluindo(null);
            }}
          >
            {excluindo !== null && (
              <ExcluirCliente
                cliente={excluindo}
                empresa={dados.empresa.cnpj}
                aoFechar={() => {
                  setExcluindo(null);
                }}
                aoExcluido={() => {
                  depoisDeGravar(`Cliente excluído: ${excluindo.nome}.`);
                }}
              />
            )}
          </Molde>
        </>
      )}
    </Pagina>
  );
}
