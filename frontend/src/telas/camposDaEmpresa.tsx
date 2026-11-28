// Os campos da empresa que o cadastro (C3a) e as configurações (C3b) usam: o regime, a UF, o município e a
// atividade. As listas vêm dos motores oficiais, pela API (GET /referencias/...), com a fonte impressa; nenhuma lista
// fica escrita na tela (ADR 0018).

import type { Ref } from 'react';
import { chamar } from '../api/cliente.ts';
import type { components } from '../api/esquema.gen.ts';
import { NOME_REGIME, type Regime } from '../dados/pedidos.ts';
import { useRecurso, type EstadoRecurso } from '../dados/recurso.ts';
import { useSessao } from '../sessao/contexto.tsx';
import { Carregando, FalhaNoBloco } from './comum.tsx';
import { CampoDeLista, GrupoDeOpcoes, type Opcao } from './formulario.tsx';

/**
 * Os dois regimes que o cadastro aceita. A definição é a do ADR 0003 (conferida na LC 214/2025, art. 41, §3º):
 * no tradicional, a CBS e o IBS ficam dentro do DAS; no híbrido, a empresa os paga por fora, no regime regular.
 */
export const OPCOES_DE_REGIME: readonly (Opcao & { valor: Regime })[] = [
  { valor: 'simples_tradicional', rotulo: NOME_REGIME.simples_tradicional, detalhe: 'A CBS e o IBS dentro do DAS.' },
  {
    valor: 'simples_hibrido',
    rotulo: NOME_REGIME.simples_hibrido,
    detalhe: 'A CBS e o IBS por fora do DAS, no regime regular (LC 214/2025, art. 41, §3º).',
  },
];

export const AJUDA_DO_REGIME =
  'O ContaAI atende só empresas do Simples Nacional. O MEI e as empresas do lucro presumido ou do lucro real não são atendidos.';

export type Atividades = components['schemas']['AtividadesResposta'];
type Ufs = components['schemas']['UfsResposta'];
type Municipios = components['schemas']['MunicipiosResposta'];

/** A lista de uma referência que não carregou: o nome do campo, a falha e o "Tentar de novo" (app-screens §11). */
export function FalhaDaLista({ rotulo, erro, aoTentar }: { rotulo: string; erro: unknown; aoTentar: () => void }) {
  return (
    <div className="campo campo--formulario">
      <p className="campo__nome">{rotulo}</p>
      <FalhaNoBloco erro={erro} aoTentar={aoTentar} />
    </div>
  );
}

/** As UFs e os municípios da UF escolhida (sem UF, nenhum pedido de municípios sai). */
export function useListasDaEmpresa(uf: string): { ufs: EstadoRecurso<Ufs>; municipios: EstadoRecurso<Municipios> } {
  const { api } = useSessao();
  const ufs = useRecurso('referencias:ufs', (sinal) => chamar(api.GET('/referencias/ufs', { signal: sinal })));
  const municipios = useRecurso(uf === '' ? null : `referencias:municipios:${uf}`, (sinal) =>
    chamar(api.GET('/referencias/municipios', { params: { query: { uf } }, signal: sinal })),
  );
  return { ufs, municipios };
}

/** A lista de atividades: pedida por quem monta a página, que também usa a data do cenário. */
export function useAtividades(pedir: boolean): EstadoRecurso<Atividades> {
  const { api } = useSessao();
  return useRecurso(pedir ? 'referencias:atividades' : null, (sinal) =>
    chamar(api.GET('/referencias/atividades', { signal: sinal })),
  );
}

interface PropsLocal {
  refUf: Ref<HTMLSelectElement>;
  refMunicipio: Ref<HTMLSelectElement>;
  uf: string;
  municipio: string;
  erroUf: string | null;
  erroMunicipio: string | null;
  aoMudarUf: (uf: string) => void;
  aoMudarMunicipio: (municipio: string) => void;
}

/** A UF e o município. Trocar a UF limpa o município (quem chama faz isso em `aoMudarUf`). */
export function CamposDoLocal({
  refUf,
  refMunicipio,
  uf,
  municipio,
  erroUf,
  erroMunicipio,
  aoMudarUf,
  aoMudarMunicipio,
}: PropsLocal) {
  const { ufs, municipios } = useListasDaEmpresa(uf);
  const listaDeUfs = ufs.dados?.ufs ?? [];
  const listaDeMunicipios = municipios.dados?.uf === uf ? municipios.dados.municipios : [];
  return (
    <>
      {ufs.erro !== undefined && ufs.dados === undefined ? (
        <FalhaDaLista rotulo="UF" erro={ufs.erro} aoTentar={ufs.recarregar} />
      ) : (
        <CampoDeLista
          ref={refUf}
          rotulo="UF"
          name="uf"
          value={uf}
          disabled={ufs.dados === undefined}
          erro={erroUf}
          ajuda={ufs.dados ? `Fonte: ${ufs.dados.fonte}` : 'Carregando as UFs…'}
          onChange={(e) => {
            aoMudarUf(e.target.value);
          }}
        >
          <option value="">Escolha a UF</option>
          {listaDeUfs.map((u) => (
            <option key={u.sigla} value={u.sigla}>
              {u.sigla} · {u.nome}
            </option>
          ))}
        </CampoDeLista>
      )}
      {municipios.erro !== undefined && listaDeMunicipios.length === 0 ? (
        <FalhaDaLista rotulo="Município" erro={municipios.erro} aoTentar={municipios.recarregar} />
      ) : (
        <CampoDeLista
          ref={refMunicipio}
          rotulo="Município"
          name="municipio"
          value={municipio}
          disabled={uf === '' || municipios.carregando}
          erro={erroMunicipio}
          ajuda={
            uf === ''
              ? 'Escolha a UF primeiro.'
              : municipios.carregando
                ? 'Carregando os municípios…'
                : municipios.dados
                  ? `Fonte: ${municipios.dados.fonte}`
                  : undefined
          }
          onChange={(e) => {
            aoMudarMunicipio(e.target.value);
          }}
        >
          <option value="">Escolha o município</option>
          {listaDeMunicipios.map((m) => (
            <option key={m.codigo} value={String(m.codigo)}>
              {m.nome}
            </option>
          ))}
        </CampoDeLista>
      )}
    </>
  );
}

interface PropsAtividade {
  refAtividade: Ref<HTMLInputElement>;
  atividades: EstadoRecurso<Atividades>;
  valor: string | null;
  erro: string | null;
  aoEscolher: (valor: string) => void;
}

/** A atividade no Simples, entre as que o ContaAI calcula. */
export function CampoDaAtividade({ refAtividade, atividades, valor, erro, aoEscolher }: PropsAtividade) {
  if (atividades.erro !== undefined && atividades.dados === undefined) {
    return <FalhaDaLista rotulo="Atividade no Simples" erro={atividades.erro} aoTentar={atividades.recarregar} />;
  }
  if (atividades.dados === undefined) {
    return <Carregando linhas={3} />;
  }
  const opcoes: Opcao[] = atividades.dados.atividades.map((a) => ({
    valor: a.cAtivSN,
    rotulo: a.descricao,
    detalhe: (
      <>
        Código <span className="num">{a.cAtivSN}</span> · anexo {a.anexo} do Simples
      </>
    ),
  }));
  return (
    <GrupoDeOpcoes
      ref={refAtividade}
      legenda="Atividade no Simples"
      nome="atividade"
      opcoes={opcoes}
      valor={valor}
      aoEscolher={aoEscolher}
      erro={erro}
      ajuda={`As que o ContaAI calcula: admissíveis na NF-e, com anexo e sem o fator R. Fonte: ${atividades.dados.fonte}`}
    />
  );
}
