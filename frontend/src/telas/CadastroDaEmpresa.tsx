// Cadastrar a empresa (C3a, ADR 0018): a primeira vez da conta. Leva ao Painel da empresa nova.
//
// - Só para quem entrou (PortaDaConta). A página é da conta: quem estava vendo a demonstração volta aos dados da
//   conta ao abri-la, e as rotas /empresas levam o cookie de qualquer forma (api/rotas.ts, ROTAS_DA_EMPRESA).
// - Só o dono cadastra (ADR 0017, etapa 8). Até o seletor do 3c, uma empresa por conta: com uma, a página leva ao
//   Painel (uma segunda ficaria invisível). O backend aceita até 10.
// - As listas (UF, município e atividade) vêm dos motores oficiais, pela API (GET /referencias/...), com a fonte
//   impressa. Nenhuma lista fica escrita na tela. Os campos ficam em camposDaEmpresa.tsx, com as configurações (C3b).
// - O CNPJ vai em maiúsculas e sem a pontuação, e o dígito é conferido antes do envio (regrasDeEntrada.ts). O
//   backend confere tudo de novo, consulta os motores e tem a palavra final; a frase dele aparece no aviso.
// - O envio é por fetch (SessaoConta.cadastrarEmpresa), e o <form> não tem action: a CSP tem form-action 'none'.
// - Todo texto vindo da API é exibido como texto do React, nunca como HTML (docs/seguranca.md).

import { useEffect, useRef, useState, type SubmitEvent } from 'react';
import { ErroApi } from '../api/problema.ts';
import { dataDoDocumento } from '../dados/formatar.ts';
import type { Regime } from '../dados/pedidos.ts';
import type { EstadoRecurso } from '../dados/recurso.ts';
import { useSessao } from '../sessao/contexto.tsx';
import { useConta } from '../sessao/ganchos.ts';
import { BotaoDemonstracao } from '../shell/demonstracao.tsx';
import { Link, navegar } from '../shell/navegacao.tsx';
import { Pagina } from '../shell/Pagina.tsx';
import { INICIO_DO_APP, ROTA_DO_CADASTRO } from '../shell/rotas.ts';
import {
  AJUDA_DO_REGIME,
  CampoDaAtividade,
  CamposDoLocal,
  OPCOES_DE_REGIME,
  useAtividades,
  type Atividades,
} from './camposDaEmpresa.tsx';
import { PortaDaConta } from './PortaDaConta.tsx';
import { AvisoDeFalha, Campo, GrupoDeOpcoes, falhaDe, rotuloDoEnvio, useEspera } from './formulario.tsx';
import { conferirCnpj, conferirRazaoSocial, normalizarCnpj } from './regrasDeEntrada.ts';
import './conta.css';
import './empresa.css';
import './publicas.css';
import './telas.css';

interface Erros {
  cnpj: string | null;
  razaoSocial: string | null;
  regime: string | null;
  uf: string | null;
  municipio: string | null;
  atividade: string | null;
}

const SEM_ERROS: Erros = { cnpj: null, razaoSocial: null, regime: null, uf: null, municipio: null, atividade: null };

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
          ajuda={AJUDA_DO_REGIME}
        />
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
        <CampoDaAtividade
          refAtividade={refAtividade}
          atividades={atividades}
          valor={atividade}
          erro={erros.atividade}
          aoEscolher={(valor) => {
            setAtividade(valor);
            limpar('atividade');
          }}
        />
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
  const atividades = useAtividades(cadastra);

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
