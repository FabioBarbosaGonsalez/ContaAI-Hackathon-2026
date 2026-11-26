// Diálogos que gravam no catálogo: corrigir a classificação (REG-011/VSN-047) e alterar o preço.
//
// Nada é gravado sem o clique (P3). As candidatas vêm de GET /busca/ncm para a NCM do item, na data do
// cenário: o backend só aceita uma delas e tira o CST da fundamentação oficial (ADR 0011).

import { useEffect, useId, useRef, useState, type ReactNode, type SubmitEvent } from 'react';
import { chamar } from '../api/cliente.ts';
import { ErroApi } from '../api/problema.ts';
import { CNPJ_DEMONSTRACAO, useGravacao } from '../dados/empresa.ts';
import { ncm as formatarNcm, porcentagem, reais } from '../dados/formatar.ts';
import type { Candidata, Catalogo, ErroMotor, ItemCatalogo } from '../dados/pedidos.ts';
import { useRecurso } from '../dados/recurso.ts';
import { useSessao } from '../sessao/contexto.tsx';
import { Carregando, FalhaNoBloco } from './comum.tsx';

function useDialogo(aberto: boolean) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialogo = ref.current;
    if (!dialogo) {
      return;
    }
    if (aberto && !dialogo.open) {
      dialogo.showModal();
    } else if (!aberto && dialogo.open) {
      dialogo.close();
    }
  }, [aberto]);
  return ref;
}

function mensagemDaFalha(erro: unknown): string {
  return erro instanceof ErroApi ? erro.message : 'Não foi possível gravar.';
}

interface PropsMolde {
  aberto: boolean;
  titulo: string;
  aoFechar: () => void;
  children: ReactNode;
}

function Molde({ aberto, titulo, aoFechar, children }: PropsMolde) {
  const ref = useDialogo(aberto);
  const idTitulo = useId();
  return (
    <dialog ref={ref} className="dialogo" aria-labelledby={idTitulo} onClose={aoFechar}>
      <h2 id={idTitulo}>{titulo}</h2>
      {aberto && children}
    </dialog>
  );
}

// ---------------------------------------------------------------------------
// Corrigir a classificação

export interface PedidoDeCorrecao {
  item: ItemCatalogo;
  erro: ErroMotor;
}

function OpcaoCandidata({ c, nome, atual }: { c: Candidata; nome: string; atual: boolean }) {
  const id = useId();
  return (
    <div className="candidata">
      <input id={id} type="radio" name={nome} value={c.cClassTrib} disabled={atual} />
      <label htmlFor={id} className="candidata__texto">
        <span className="candidata__linha">
          <span className="num">{c.cClassTrib}</span>
          <span>{c.descricao}</span>
        </span>
        <span className="candidata__meta">
          Redução de <span className="num">{porcentagem(c.reducaoPct)}</span>
          {c.especificaDoProduto ? ' · específica deste produto' : ' · vale para qualquer produto'}
          {atual ? ' · a classificação atual' : ''}
        </span>
      </label>
    </div>
  );
}

interface PropsCorrigir {
  pedido: PedidoDeCorrecao | null;
  catalogo: Catalogo;
  aoFechar: () => void;
  aoGravar: () => void;
}

export function CorrigirClassificacao({ pedido, catalogo, aoFechar, aoGravar }: PropsCorrigir) {
  const { api } = useSessao();
  const gravacao = useGravacao();
  const nome = useId();
  const [falha, setFalha] = useState<string | null>(null);
  const [gravando, setGravando] = useState(false);
  const data = catalogo.cenario.operacao.data;

  const item = pedido?.item;
  const busca = useRecurso(item?.ncm ? `busca:${item.ncm}:${data}` : null, (sinal) =>
    chamar(api.GET('/busca/ncm', { params: { query: { q: item?.ncm ?? '', data } }, signal: sinal })),
  );
  const candidatas = busca.dados?.candidatos.find((c) => c.ncm === item?.ncm)?.classificacoes ?? [];

  const fechar = () => {
    setFalha(null);
    aoFechar();
  };

  const gravar = async (evento: SubmitEvent<HTMLFormElement>) => {
    evento.preventDefault();
    const escolhida = new FormData(evento.currentTarget).get(nome);
    if (!item || typeof escolhida !== 'string') {
      setFalha('Escolha uma das classificações.');
      return;
    }
    setGravando(true);
    setFalha(null);
    try {
      await chamar(
        api.POST('/catalogo/{item_id}/classificacao', {
          params: { path: { item_id: item.id } },
          body: { cnpj: CNPJ_DEMONSTRACAO, cClassTrib: escolhida },
        }),
      );
      aoGravar();
      fechar();
    } catch (erro) {
      setFalha(mensagemDaFalha(erro));
    } finally {
      setGravando(false);
    }
  };

  return (
    <Molde aberto={pedido !== null} titulo="Corrigir a classificação" aoFechar={fechar}>
      {pedido && item && (
        <form className="dialogo__corpo" onSubmit={(e) => void gravar(e)}>
          <p>
            {item.descricao}, NCM <span className="num">{formatarNcm(item.ncm)}</span>. O motor recusou a
            classificação <span className="num">{item.cClassTrib}</span> ({pedido.erro.codigo}: {pedido.erro.titulo}).
          </p>
          <p className="texto-suave">
            As opções são as classificações válidas para esta NCM nos dados abertos da calculadora oficial, na data
            do cenário. A escolha é sua; confira com o contador.
          </p>
          {busca.erro !== undefined ? (
            <FalhaNoBloco erro={busca.erro} aoTentar={busca.recarregar} />
          ) : busca.dados === undefined ? (
            <Carregando linhas={2} />
          ) : candidatas.length === 0 ? (
            <p>Não há classificação válida para esta NCM nos dados abertos.</p>
          ) : (
            <fieldset className="candidatas">
              <legend className="so-leitor">Classificações válidas para a NCM</legend>
              {candidatas.map((c) => (
                <OpcaoCandidata key={c.cClassTrib} c={c} nome={nome} atual={c.cClassTrib === item.cClassTrib} />
              ))}
            </fieldset>
          )}
          {falha !== null && (
            <p className="dialogo__falha" role="alert">
              {falha}
            </p>
          )}
          {!gravacao.pode && <p className="gravar__motivo">{gravacao.motivo}</p>}
          <div className="dialogo__acoes">
            <button type="button" className="botao-secundario" onClick={fechar}>
              Cancelar
            </button>
            <button type="submit" className="botao-principal" disabled={!gravacao.pode || gravando || candidatas.length === 0}>
              Gravar a classificação
            </button>
          </div>
        </form>
      )}
    </Molde>
  );
}

// ---------------------------------------------------------------------------
// Alterar o preço de venda

interface PropsPreco {
  item: ItemCatalogo | null;
  aoFechar: () => void;
  aoGravar: () => void;
}

/** "3,97" ou "3.97" → "3.97"; até 2 casas, sem sinal. Fora disso, null. */
export function lerPreco(texto: string): string | null {
  const limpo = texto.trim().replace(/^R\$\s*/u, '').replace(',', '.');
  return /^\d{1,9}(\.\d{1,2})?$/u.test(limpo) && Number(limpo) > 0 ? limpo : null;
}

export function AlterarPreco({ item, aoFechar, aoGravar }: PropsPreco) {
  const { api } = useSessao();
  const gravacao = useGravacao();
  const idCampo = useId();
  const idAjuda = useId();
  const [falha, setFalha] = useState<string | null>(null);
  const [gravando, setGravando] = useState(false);

  const fechar = () => {
    setFalha(null);
    aoFechar();
  };

  const gravar = async (evento: SubmitEvent<HTMLFormElement>) => {
    evento.preventDefault();
    const texto = new FormData(evento.currentTarget).get('preco');
    const valor = typeof texto === 'string' ? lerPreco(texto) : null;
    if (!item || valor === null) {
      setFalha('Informe o preço em reais, com até 2 casas (ex.: 3,99).');
      return;
    }
    setGravando(true);
    setFalha(null);
    try {
      await chamar(
        api.POST('/catalogo/{item_id}/preco', {
          params: { path: { item_id: item.id } },
          body: { cnpj: CNPJ_DEMONSTRACAO, valorUnitario: valor },
        }),
      );
      aoGravar();
      fechar();
    } catch (erro) {
      setFalha(mensagemDaFalha(erro));
    } finally {
      setGravando(false);
    }
  };

  return (
    <Molde aberto={item !== null} titulo="Alterar o preço de venda" aoFechar={fechar}>
      {item && (
        <form className="dialogo__corpo" onSubmit={(e) => void gravar(e)}>
          <p>
            {item.descricao}. Preço atual <span className="num dinheiro">{reais(item.precoVenda)}</span> por{' '}
            {item.unidade}.
          </p>
          <div className="campo">
            <label htmlFor={idCampo}>Novo preço por unidade</label>
            <input
              id={idCampo}
              name="preco"
              className="num"
              inputMode="decimal"
              autoComplete="off"
              defaultValue={item.precoVenda.replace('.', ',')}
              aria-describedby={idAjuda}
              required
            />
            <p id={idAjuda} className="campo__ajuda">
              Em reais, com até 2 casas. Os tributos são recalculados pelos motores depois de gravar.
            </p>
          </div>
          {falha !== null && (
            <p className="dialogo__falha" role="alert">
              {falha}
            </p>
          )}
          {!gravacao.pode && <p className="gravar__motivo">{gravacao.motivo}</p>}
          <div className="dialogo__acoes">
            <button type="button" className="botao-secundario" onClick={fechar}>
              Cancelar
            </button>
            <button type="submit" className="botao-principal" disabled={!gravacao.pode || gravando}>
              Gravar o preço
            </button>
          </div>
        </form>
      )}
    </Molde>
  );
}
