// Explicação lateral (inventário §2): "por que este item paga isso?".
//
// Lê GET /explicar/{itemId} no regime pedido: a redução, a fundamentação legal dos dados abertos, a memória
// de cálculo do motor oficial e as premissas. Nada aqui é escrito pela tela: só rótulos.

import { useEffect, useRef } from 'react';
import { chamar } from '../api/cliente.ts';
import { CNPJ_DEMONSTRACAO, useOrigemDosDados } from '../dados/empresa.ts';
import { porcentagem } from '../dados/formatar.ts';
import { estadoEmPalavras, NOME_REGIME, type Explicacao as DadosExplicacao, type Regime } from '../dados/pedidos.ts';
import { useRecurso } from '../dados/recurso.ts';
import { useSessao } from '../sessao/contexto.tsx';
import { Carregando, FalhaNoBloco, ListaDePremissas } from './comum.tsx';

const NOME_MEMORIA: Record<string, string> = {
  cbs: 'CBS',
  ibs: 'IBS',
  ibsUF: 'IBS estadual',
  ibsMun: 'IBS municipal',
  impostoSeletivo: 'Imposto Seletivo',
  is: 'Imposto Seletivo',
};

export interface PedidoDeExplicacao {
  itemId: string;
  descricao: string;
  regime: Regime;
}

function Conteudo({ dados }: { dados: DadosExplicacao }) {
  const memoria = Object.entries(dados.memoria ?? {});
  return (
    <>
      <p className="lateral__estado">
        {NOME_REGIME[dados.regime]} · {estadoEmPalavras({ ...dados, motivoEstado: null })}
      </p>

      <section className="lateral__secao" aria-label="Por que paga isso">
        <h3>Por que paga isso</h3>
        {dados.reducaoPct !== null && dados.reducaoPct !== undefined && (
          <p>
            Redução de <span className="num">{porcentagem(dados.reducaoPct)}</span> na alíquota de CBS e IBS.
          </p>
        )}
        {dados.fundamentacoes.length === 0 ? (
          <p className="texto-suave">Sem fundamentação específica: tributação integral.</p>
        ) : (
          dados.fundamentacoes.map((f) => (
            <div key={f.cClassTrib} className="lateral__lei">
              {/* Só o que vem dos dados abertos: o texto curto já diz o artigo ou a lei. */}
              <p>
                <strong>{f.textoCurto}</strong> · classificação <span className="num">{f.cClassTrib}</span>
              </p>
              <p className="lateral__texto-lei">{f.texto}</p>
            </div>
          ))
        )}
        {dados.erros.map((e) => (
          <p key={e.codigo}>
            <span className="num">{e.codigo}</span> {e.titulo}
            {e.detalhe ? `: ${e.detalhe}` : ''}
          </p>
        ))}
      </section>

      <section className="lateral__secao" aria-label="Memória de cálculo do motor">
        <h3>Memória de cálculo do motor</h3>
        {memoria.length === 0 ? (
          <p className="texto-suave">O motor não devolveu memória para este item.</p>
        ) : (
          <dl className="memoria">
            {memoria.map(([tributo, texto]) => (
              <div key={tributo}>
                <dt>{NOME_MEMORIA[tributo] ?? tributo}</dt>
                <dd>{texto}</dd>
              </div>
            ))}
          </dl>
        )}
      </section>

      <section className="lateral__secao" aria-label="Premissas">
        <h3>Premissas</h3>
        <ListaDePremissas premissas={dados.premissas} />
      </section>

      <p className="lateral__aviso">{dados.aviso}</p>
    </>
  );
}

export function Explicacao({ pedido, aoFechar }: { pedido: PedidoDeExplicacao | null; aoFechar: () => void }) {
  const { api } = useSessao();
  const origem = useOrigemDosDados();
  const ref = useRef<HTMLDialogElement>(null);

  const chave = pedido && origem ? `explicar:${pedido.itemId}:${pedido.regime}:${origem}` : null;
  const recurso = useRecurso(chave, (sinal) => {
    if (!pedido) {
      return Promise.reject(new Error('sem item'));
    }
    return chamar(
      api.GET('/explicar/{item_id}', {
        params: { path: { item_id: pedido.itemId }, query: { regime: pedido.regime, cnpj: CNPJ_DEMONSTRACAO } },
        signal: sinal,
      }),
    );
  });

  useEffect(() => {
    const dialogo = ref.current;
    if (!dialogo) {
      return;
    }
    if (pedido && !dialogo.open) {
      dialogo.showModal();
    } else if (!pedido && dialogo.open) {
      dialogo.close();
    }
  }, [pedido]);

  return (
    <dialog ref={ref} className="lateral" aria-labelledby="lateral-titulo" onClose={aoFechar}>
      <div className="lateral__topo">
        <h2 id="lateral-titulo">{pedido?.descricao ?? 'Explicação'}</h2>
        <button type="button" className="botao-secundario" onClick={aoFechar}>
          Fechar
        </button>
      </div>
      {recurso.erro !== undefined ? (
        <FalhaNoBloco erro={recurso.erro} aoTentar={recurso.recarregar} />
      ) : recurso.dados === undefined ? (
        <Carregando linhas={6} />
      ) : (
        <Conteudo dados={recurso.dados} />
      )}
    </dialog>
  );
}
