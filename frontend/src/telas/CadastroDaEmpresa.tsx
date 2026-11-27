// Cadastrar a empresa (C3a, ADR 0018): a primeira vez da conta. Leva ao Painel da empresa nova.
//
// - Só para quem entrou (PortaDaConta). A página é da conta: quem estava vendo a demonstração volta aos dados da
//   conta ao abri-la, e as rotas /empresas levam o cookie de qualquer forma (api/rotas.ts, ROTAS_DA_EMPRESA).
// - Só o dono cadastra (ADR 0017, etapa 8). Até o seletor do 3c, uma empresa por conta: com uma, a página leva ao
//   Painel (uma segunda ficaria invisível). O backend aceita até 10.
// - As listas (UF, município e atividade) vêm dos motores oficiais, pela API (GET /referencias/...), com a fonte
//   impressa. Nenhuma lista fica escrita na tela.
// - O CNPJ vai em maiúsculas e sem a pontuação, e o dígito é conferido antes do envio (regrasDeEntrada.ts). O
//   backend confere tudo de novo, consulta os motores e tem a palavra final; a frase dele aparece no aviso.
// - O envio é por fetch (SessaoConta.cadastrarEmpresa), e o <form> não tem action: a CSP tem form-action 'none'.
// - Todo texto vindo da API é exibido como texto do React, nunca como HTML (docs/seguranca.md).

import { useEffect, useRef, useState, type SubmitEvent } from 'react';
import { chamar } from '../api/cliente.ts';
import { ErroApi } from '../api/problema.ts';
import { dataDoDocumento } from '../dados/formatar.ts';
import { NOME_REGIME, type Regime } from '../dados/pedidos.ts';
import { useRecurso, type EstadoRecurso } from '../dados/recurso.ts';
import type { components } from '../api/esquema.gen.ts';
import { useSessao } from '../sessao/contexto.tsx';
import { useConta } from '../sessao/ganchos.ts';
import { BotaoDemonstracao } from '../shell/demonstracao.tsx';
import { Link, navegar } from '../shell/navegacao.tsx';
import { Pagina } from '../shell/Pagina.tsx';
import { INICIO_DO_APP, ROTA_DO_CADASTRO } from '../shell/rotas.ts';
import { Carregando, FalhaNoBloco } from './comum.tsx';
import { PortaDaConta } from './PortaDaConta.tsx';
import {
  AvisoDeFalha,
  Campo,
  CampoDeLista,
  GrupoDeOpcoes,
  falhaDe,
  rotuloDoEnvio,
  useEspera,
  type Opcao,
} from './formulario.tsx';
import { conferirCnpj, conferirRazaoSocial, normalizarCnpj } from './regrasDeEntrada.ts';
import './conta.css';
import './empresa.css';
import './publicas.css';
import './telas.css';

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

interface Erros {
  cnpj: string | null;
  razaoSocial: string | null;
  regime: string | null;
  uf: string | null;
  municipio: string | null;
  atividade: string | null;
}

const SEM_ERROS: Erros = { cnpj: null, razaoSocial: null, regime: null, uf: null, municipio: null, atividade: null };

type Atividades = components['schemas']['AtividadesResposta'];

/** A lista de uma referência que não carregou: o nome do campo, a falha e o "Tentar de novo" (app-screens §11). */
function FalhaDaLista({ rotulo, erro, aoTentar }: { rotulo: string; erro: unknown; aoTentar: () => void }) {
  return (
    <div className="campo campo--formulario">
      <p className="campo__nome">{rotulo}</p>
      <FalhaNoBloco erro={erro} aoTentar={aoTentar} />
    </div>
  );
}

function Formulario({ atividades }: { atividades: EstadoRecurso<Atividades> }) {
  const sessao = useSessao();
  const { api } = sessao;
  const [cnpj, setCnpj] = useState('');
  const [razaoSocial, setRazaoSocial] = useState('');
  const [regime, setRegime] = useState<string | null>(null);
  const [uf, setUf] = useState('');
  const [municipio, setMunicipio] = useState('');
  const [atividade, setAtividade] = useState<string | null>(null);
  const [erros, setErros] = useState<Erros>(SEM_ERROS);
  const [falha, setFalha] = useState<{ texto: string; jaCadastrada: boolean } | null>(null);
  const [enviando, setEnviando] = useState(false);
  const espera = useEspera();
  const refCnpj = useRef<HTMLInputElement>(null);
  const refRazao = useRef<HTMLInputElement>(null);
  const refRegime = useRef<HTMLInputElement>(null);
  const refUf = useRef<HTMLSelectElement>(null);
  const refMunicipio = useRef<HTMLSelectElement>(null);
  const refAtividade = useRef<HTMLInputElement>(null);
  // O erro de um campo some quando a pessoa o muda: a borda vermelha não fica num campo já corrigido.
  const limpar = (campo: keyof Erros) => {
    setErros((e) => (e[campo] === null ? e : { ...e, [campo]: null }));
  };

  const ufs = useRecurso('referencias:ufs', (sinal) => chamar(api.GET('/referencias/ufs', { signal: sinal })));
  const municipios = useRecurso(uf === '' ? null : `referencias:municipios:${uf}`, (sinal) =>
    chamar(api.GET('/referencias/municipios', { params: { query: { uf } }, signal: sinal })),
  );

  const enviar = async (evento: SubmitEvent<HTMLFormElement>) => {
    evento.preventDefault();
    if (enviando || espera.aguardando) {
      return;
    }
    const novos: Erros = {
      cnpj: conferirCnpj(cnpj),
      razaoSocial: conferirRazaoSocial(razaoSocial),
      regime: regime === null ? 'Escolha o regime da empresa no Simples Nacional.' : null,
      uf: uf === '' ? 'Escolha a UF.' : null,
      municipio: municipio === '' ? 'Escolha o município.' : null,
      atividade: atividade === null ? 'Escolha a atividade da empresa.' : null,
    };
    setErros(novos);
    // O foco vai ao primeiro campo com erro, na ordem da tela (WCAG 3.3.1).
    const ordem = [
      [novos.cnpj, refCnpj],
      [novos.razaoSocial, refRazao],
      [novos.regime, refRegime],
      [novos.uf, refUf],
      [novos.municipio, refMunicipio],
      [novos.atividade, refAtividade],
    ] as const;
    const primeiro = ordem.find(([erro]) => erro !== null);
    if (primeiro !== undefined || regime === null || atividade === null) {
      setFalha(null);
      primeiro?.[1].current?.focus();
      return;
    }
    setEnviando(true);
    setFalha(null);
    try {
      await sessao.conta.cadastrarEmpresa(api, {
        cnpj: normalizarCnpj(cnpj),
        razaoSocial: razaoSocial.trim(),
        regimeAtual: regime as Regime,
        uf,
        municipio: Number(municipio),
        cAtivSN: atividade,
      });
      navegar(INICIO_DO_APP, { substituir: true });
    } catch (e) {
      const { texto, esperaS } = falhaDe(e, 'Não foi possível cadastrar a empresa. Tente de novo.');
      if (esperaS !== null) {
        espera.iniciar(esperaS);
      }
      const jaCadastrada = e instanceof ErroApi && e.status === 409;
      if (jaCadastrada) {
        // Outra aba pode ter cadastrado: a conta é lida de novo, e a página passa a levar ao Painel.
        void sessao.conta.carregar(api, sessao.modo);
      }
      setFalha({ texto, jaCadastrada });
      setEnviando(false);
    }
  };

  const listaDeUfs = ufs.dados?.ufs ?? [];
  const listaDeMunicipios = municipios.dados?.uf === uf ? municipios.dados.municipios : [];
  const opcoesDeAtividade: Opcao[] = (atividades.dados?.atividades ?? []).map((a) => ({
    valor: a.cAtivSN,
    rotulo: a.descricao,
    detalhe: (
      <>
        Código <span className="num">{a.cAtivSN}</span> · anexo {a.anexo} do Simples
      </>
    ),
  }));

  return (
    <section className="passo">
      <form className="formulario" noValidate onSubmit={(e) => void enviar(e)}>
        <AvisoDeFalha texto={falha?.texto ?? null} />
        {falha?.jaCadastrada === true && (
          <p className="porta__alternativa">
            <Link para={INICIO_DO_APP}>Ir ao Painel</Link>
          </p>
        )}
        <Campo
          ref={refCnpj}
          rotulo="CNPJ"
          name="cnpj"
          autoComplete="off"
          spellCheck={false}
          autoCapitalize="characters"
          className="num campo__cnpj"
          value={cnpj}
          erro={erros.cnpj}
          ajuda="Com ou sem os pontos, a barra e o traço. O CNPJ com letras também vale."
          onChange={(e) => {
            setCnpj(e.target.value);
            limpar('cnpj');
          }}
          onBlur={() => {
            // Só a forma muda (maiúsculas); a pontuação fica como a pessoa digitou até o envio.
            setCnpj((v) => v.toUpperCase());
          }}
        />
        <Campo
          ref={refRazao}
          rotulo="Razão social"
          name="razaoSocial"
          autoComplete="organization"
          value={razaoSocial}
          erro={erros.razaoSocial}
          ajuda="Como está no cartão do CNPJ."
          onChange={(e) => {
            setRazaoSocial(e.target.value);
            limpar('razaoSocial');
          }}
        />
        <GrupoDeOpcoes
          ref={refRegime}
          legenda="Regime no Simples Nacional"
          nome="regime"
          opcoes={OPCOES_DE_REGIME}
          valor={regime}
          aoEscolher={(valor) => {
            setRegime(valor);
            limpar('regime');
          }}
          erro={erros.regime}
          ajuda="O ContaAI atende só empresas do Simples Nacional. O MEI e as empresas do lucro presumido ou do lucro real não são atendidos."
        />
        {ufs.erro !== undefined && ufs.dados === undefined ? (
          <FalhaDaLista rotulo="UF" erro={ufs.erro} aoTentar={ufs.recarregar} />
        ) : (
          <CampoDeLista
            ref={refUf}
            rotulo="UF"
            name="uf"
            value={uf}
            disabled={ufs.dados === undefined}
            erro={erros.uf}
            ajuda={ufs.dados ? `Fonte: ${ufs.dados.fonte}` : 'Carregando as UFs…'}
            onChange={(e) => {
              setUf(e.target.value);
              setMunicipio('');
              limpar('uf');
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
            erro={erros.municipio}
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
              setMunicipio(e.target.value);
              limpar('municipio');
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
        {atividades.erro !== undefined && atividades.dados === undefined ? (
          <FalhaDaLista rotulo="Atividade no Simples" erro={atividades.erro} aoTentar={atividades.recarregar} />
        ) : atividades.dados === undefined ? (
          <Carregando linhas={3} />
        ) : (
          <GrupoDeOpcoes
            ref={refAtividade}
            legenda="Atividade no Simples"
            nome="atividade"
            opcoes={opcoesDeAtividade}
            valor={atividade}
            aoEscolher={(valor) => {
              setAtividade(valor);
              limpar('atividade');
            }}
            erro={erros.atividade}
            ajuda={`As que o ContaAI calcula: admissíveis na NF-e, com anexo e sem o fator R. Fonte: ${atividades.dados.fonte}`}
          />
        )}
        <p>
          <button type="submit" className="botao-principal" disabled={enviando || espera.aguardando}>
            {rotuloDoEnvio(enviando, espera.restanteMs, 'Cadastrando…', 'Cadastrar a empresa')}
          </button>
        </p>
        <p className="so-leitor" role="status">
          {enviando ? 'Cadastrando: os motores conferem o município e a atividade.' : ''}
        </p>
      </form>
    </section>
  );
}

/**
 * Ao lado do formulário: o que o ContaAI faz com estes dados. Cada frase foi conferida no código (ADR 0017 e
 * ADR 0018): o CNPJ não é consultado em lugar nenhum, e os motores não recebem o CNPJ nem a razão social
 * (backend/app/motores/requisicoes.py).
 */
function OQueFazComOsDados({ dataDoCenario }: { dataDoCenario: string | undefined }) {
  return (
    <aside className="cadastro__lado" aria-labelledby="empresa-dados">
      <h2 id="empresa-dados">O que o ContaAI faz com estes dados</h2>
      <dl className="lado__lista">
        <div className="lado__item">
          <dt>CNPJ</dt>
          <dd>
            Conferido pelos dígitos verificadores (o cálculo do Serpro), sem consulta à Receita. O mesmo CNPJ pode estar
            em outra conta, cada uma com os próprios dados.
          </dd>
        </div>
        <div className="lado__item">
          <dt>Município e atividade</dt>
          <dd>Das listas das calculadoras oficiais. A atividade define o anexo do Simples nos cálculos.</dd>
        </div>
        <div className="lado__item">
          <dt>Os cálculos</dt>
          <dd>
            Começam com as premissas da simulação, rotuladas em todo resultado
            {dataDoCenario ? (
              <>
                , na data do cenário (<span className="num">{dataDoDocumento(dataDoCenario)}</span>)
              </>
            ) : null}
            . São estimativas: não são apuração fiscal e não substituem o contador.
          </dd>
        </div>
        <div className="lado__item">
          <dt>Os motores</dt>
          <dd>Recebem os itens, a data, a UF, o município e a atividade. Nunca o CNPJ nem a razão social.</dd>
        </div>
      </dl>
    </aside>
  );
}

function ConteudoDoCadastro() {
  const sessao = useSessao();
  const estado = useConta();
  const naDemo = estado.tipo === 'conectada' && estado.naDemo;
  const cadastra =
    estado.tipo === 'conectada' && estado.conta.empresas.length === 0 && estado.conta.organizacao.papel === 'dono';
  // Pedida aqui, uma vez: o formulário usa a lista, e o quadro ao lado, a data do cenário.
  const atividades = useRecurso(cadastra ? 'referencias:atividades' : null, (sinal) =>
    chamar(sessao.api.GET('/referencias/atividades', { signal: sinal })),
  );

  // A página é da conta: quem estava vendo a demonstração volta aos dados dela (sem a faixa da demonstração).
  useEffect(() => {
    if (naDemo) {
      sessao.conta.voltarParaConta();
    }
  }, [naDemo, sessao]);

  if (estado.tipo !== 'conectada') {
    return null; // a PortaDaConta só mostra este conteúdo a quem entrou
  }
  const { conta } = estado;
  if (conta.empresas.length > 0) {
    return (
      <div className="vazio porta__curta">
        <p>A empresa da sua conta já está cadastrada.</p>
        <p className="porta__acoes">
          <Link para={INICIO_DO_APP} className="botao-principal">
            Ir ao Painel
          </Link>
        </p>
      </div>
    );
  }
  if (conta.organizacao.papel !== 'dono') {
    return (
      <div className="vazio porta__curta">
        <p>Só o dono da organização cadastra a empresa.</p>
        <p className="porta__acoes">
          <BotaoDemonstracao className="botao-secundario" />
        </p>
      </div>
    );
  }
  return (
    <div className="cadastro">
      <div className="cadastro__principal">
        <Formulario atividades={atividades} />
      </div>
      <OQueFazComOsDados dataDoCenario={atividades.dados?.data} />
    </div>
  );
}

export function CadastroDaEmpresa() {
  return (
    <Pagina titulo={ROTA_DO_CADASTRO.nome}>
      <PortaDaConta exige="conta" paraQue="cadastrar a sua empresa">
        <ConteudoDoCadastro />
      </PortaDaConta>
    </Pagina>
  );
}
