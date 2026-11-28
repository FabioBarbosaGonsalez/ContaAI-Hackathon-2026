// Configurações da empresa (C3b, etapas 3 e 4; ADR 0018, seção da C3b): os dados da empresa da conta, as alíquotas
// do DAS e a exclusão da empresa.
//
// - Só para quem entrou (PortaDaConta). A página é da conta: quem estava vendo a demonstração volta aos dados da
//   conta ao abri-la, e as rotas /empresas levam o cookie de qualquer forma (api/rotas.ts, ROTAS_DA_EMPRESA).
// - Os dados vêm do GET /empresas/{cnpj}. Até o seletor do 3c, a empresa é a primeira do GET /conta.
// - Mudar e excluir são do dono (ADR 0017, etapa 8). O membro vê os dados, sem os formulários.
// - O PATCH leva só o que mudou (a UF e o município juntos, como o contrato pede). A resposta é a empresa nova, e a
//   página passa a mostrá-la. As outras páginas pedem os dados de novo ao abrir.
// - A carga atual (`cargaAtualPct`) não entra aqui: nenhuma tela a mostra, e um campo sem efeito na tela confundiria
//   (registrado no plano).
// - Excluir pede a senha e o CNPJ digitado de novo (o backend confere os dois). A exclusão é imediata e definitiva
//   (decisão 4 da C3), e a conta volta à primeira vez.
// - Todo texto vindo da API é exibido como texto do React, nunca como HTML (docs/seguranca.md).

import { useEffect, useRef, useState, type ReactNode, type SubmitEvent } from 'react';
import { chamar } from '../api/cliente.ts';
import type { components } from '../api/esquema.gen.ts';
import { TRACO, cnpj as formatarCnpj } from '../dados/formatar.ts';
import { NOME_REGIME, type Regime } from '../dados/pedidos.ts';
import { useRecurso, type EstadoRecurso } from '../dados/recurso.ts';
import type { Conta } from '../sessao/conta.ts';
import { useSessao } from '../sessao/contexto.tsx';
import { useConta } from '../sessao/ganchos.ts';
import { BotaoDemonstracao } from '../shell/demonstracao.tsx';
import { Link } from '../shell/navegacao.tsx';
import { Pagina } from '../shell/Pagina.tsx';
import { ROTA_DA_EMPRESA, ROTA_DO_CADASTRO } from '../shell/rotas.ts';
import {
  AJUDA_DO_REGIME,
  CampoDaAtividade,
  CamposDoLocal,
  OPCOES_DE_REGIME,
  useAtividades,
  type Atividades,
} from './camposDaEmpresa.tsx';
import { Carregando, FalhaNoBloco } from './comum.tsx';
import { AvisoDeFalha, Campo, CampoSenha, GrupoDeOpcoes, falhaDe, rotuloDoEnvio, useEspera } from './formulario.tsx';
import { PortaDaConta } from './PortaDaConta.tsx';
import {
  FRASE_DA_ALIQUOTA,
  conferirCnpjDaConfirmacao,
  conferirRazaoSocial,
  conferirSenhaAtual,
  lerAliquotaDoDas,
  normalizarCnpj,
} from './regrasDeEntrada.ts';
import { TituloDoPasso } from './SegundoFator.tsx';
import './conta.css';
import './empresa.css';
import './publicas.css';
import './telas.css';

export type Empresa = components['schemas']['EmpresaResposta'];
type Configuracao = components['schemas']['EmpresaConfiguracaoRequisicao'];

export const FRASE_NADA_MUDOU = 'Nada mudou: os dados já são estes.';
export const FRASE_SALVO = 'Configurações salvas.';
/** A ajuda dos campos das alíquotas: o formato. O valor atual já está no campo (sem uma segunda cópia arredondada). */
const AJUDA_DA_ALIQUOTA = 'Em %, com até 4 casas depois da vírgula.';

export const FRASE_GUARDE_AS_NOTAS = 'Guarde suas notas: o ContaAI não é o seu arquivo fiscal.';

/** O número do contrato ("1.1612" ou 1.1612) como a pessoa digita: "1,1612". */
function paraDigitar(valor: string | number | null | undefined): string {
  return valor === null || valor === undefined ? '' : String(valor).replace('.', ',');
}

/** A alíquota como foi informada, sem arredondar (até 4 casas): "1,1612%", ou um traço sem valor. */
function aliquota(valor: string | number | null | undefined): string {
  const texto = paraDigitar(valor);
  return texto === '' ? TRACO : `${texto}%`;
}

/** Os dados como o formulário os guarda (os valores dos campos). */
interface Valores {
  razaoSocial: string;
  regime: Regime;
  uf: string;
  municipio: string;
  atividade: string;
}

function valoresDe(empresa: Empresa): Valores {
  return {
    razaoSocial: empresa.empresa.razaoSocial,
    regime: empresa.empresa.regimeAtual,
    uf: empresa.empresa.uf,
    municipio: String(empresa.empresa.municipio),
    atividade: empresa.atividade.cAtivSN,
  };
}

/** O corpo do PATCH: só o que mudou, com a UF e o município juntos. Vazio, nada mudou. */
export function mudancasDosDados(antes: Valores, depois: Valores): Configuracao {
  const corpo: Configuracao = {};
  if (depois.razaoSocial.trim() !== antes.razaoSocial) {
    corpo.razaoSocial = depois.razaoSocial.trim();
  }
  if (depois.regime !== antes.regime) {
    corpo.regimeAtual = depois.regime;
  }
  if (depois.uf !== antes.uf || depois.municipio !== antes.municipio) {
    corpo.uf = depois.uf;
    corpo.municipio = Number(depois.municipio);
  }
  if (depois.atividade !== antes.atividade) {
    corpo.cAtivSN = depois.atividade;
  }
  return corpo;
}

interface PropsGravacao {
  cnpj: string;
  aoSalvar: (empresa: Empresa, frase: string) => void;
}

/** O PATCH da empresa. Lança ErroApi; quem chama mostra a frase (falhaDe). */
function useConfigurar(cnpj: string) {
  const { api } = useSessao();
  return async (corpo: Configuracao): Promise<Empresa> => {
    const { dados } = await chamar(api.PATCH('/empresas/{cnpj}', { params: { path: { cnpj } }, body: corpo }));
    return dados;
  };
}

interface Erros {
  razaoSocial: string | null;
  uf: string | null;
  municipio: string | null;
  atividade: string | null;
}

const SEM_ERROS: Erros = { razaoSocial: null, uf: null, municipio: null, atividade: null };

function FormularioDosDados({ empresa, atividades, cnpj, aoSalvar }: PropsGravacao & { empresa: Empresa; atividades: EstadoRecurso<Atividades> }) {
  const configurar = useConfigurar(cnpj);
  const antes = valoresDe(empresa);
  const [valores, setValores] = useState<Valores>(antes);
  const [erros, setErros] = useState<Erros>(SEM_ERROS);
  const [falha, setFalha] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  const espera = useEspera();
  const refRazao = useRef<HTMLInputElement>(null);
  const refRegime = useRef<HTMLInputElement>(null);
  const refUf = useRef<HTMLSelectElement>(null);
  const refMunicipio = useRef<HTMLSelectElement>(null);
  const refAtividade = useRef<HTMLInputElement>(null);

  const mudar = (campo: keyof Valores, valor: string) => {
    setValores((v) => ({ ...v, [campo]: valor }));
    setAviso(null);
    if (campo in erros) {
      setErros((e) => (e[campo as keyof Erros] === null ? e : { ...e, [campo]: null }));
    }
  };

  const enviar = async (evento: SubmitEvent<HTMLFormElement>) => {
    evento.preventDefault();
    if (enviando || espera.aguardando) {
      return;
    }
    const novos: Erros = {
      razaoSocial: conferirRazaoSocial(valores.razaoSocial),
      uf: valores.uf === '' ? 'Escolha a UF.' : null,
      municipio: valores.municipio === '' ? 'Escolha o município.' : null,
      atividade: valores.atividade === '' ? 'Escolha a atividade da empresa.' : null,
    };
    setErros(novos);
    const ordem = [
      [novos.razaoSocial, refRazao],
      [novos.uf, refUf],
      [novos.municipio, refMunicipio],
      [novos.atividade, refAtividade],
    ] as const;
    const primeiro = ordem.find(([erro]) => erro !== null);
    if (primeiro !== undefined) {
      setFalha(null);
      primeiro[1].current?.focus();
      return;
    }
    const corpo = mudancasDosDados(antes, valores);
    if (Object.keys(corpo).length === 0) {
      setFalha(null);
      setAviso(FRASE_NADA_MUDOU);
      return;
    }
    setEnviando(true);
    setFalha(null);
    setAviso(null);
    try {
      aoSalvar(await configurar(corpo), FRASE_SALVO);
    } catch (e) {
      const { texto, esperaS } = falhaDe(e, 'Não foi possível salvar. Tente de novo.');
      if (esperaS !== null) {
        espera.iniciar(esperaS);
      }
      setFalha(texto);
      setEnviando(false);
    }
  };

  return (
    <section className="conta__secao" aria-labelledby="empresa-dados-titulo">
      <h2 id="empresa-dados-titulo">Dados da empresa</h2>
      <form className="formulario" noValidate onSubmit={(e) => void enviar(e)}>
        <AvisoDeFalha texto={falha} />
        <dl className="lado__lista">
          <div className="lado__item">
            <dt>CNPJ</dt>
            <dd>
              <span className="num">{formatarCnpj(empresa.empresa.cnpj)}</span>. O CNPJ não muda: outro CNPJ é outra
              empresa.
            </dd>
          </div>
        </dl>
        <Campo
          ref={refRazao}
          rotulo="Razão social"
          name="razaoSocial"
          autoComplete="organization"
          value={valores.razaoSocial}
          erro={erros.razaoSocial}
          ajuda="Como está no cartão do CNPJ."
          onChange={(e) => {
            mudar('razaoSocial', e.target.value);
          }}
        />
        <GrupoDeOpcoes
          ref={refRegime}
          legenda="Regime no Simples Nacional"
          nome="regime"
          opcoes={OPCOES_DE_REGIME}
          valor={valores.regime}
          aoEscolher={(valor) => {
            mudar('regime', valor);
          }}
          erro={null}
          ajuda={AJUDA_DO_REGIME}
        />
        <CamposDoLocal
          refUf={refUf}
          refMunicipio={refMunicipio}
          uf={valores.uf}
          municipio={valores.municipio}
          erroUf={erros.uf}
          erroMunicipio={erros.municipio}
          aoMudarUf={(valor) => {
            setValores((v) => ({ ...v, uf: valor, municipio: '' }));
            setAviso(null);
            setErros((e) => ({ ...e, uf: null }));
          }}
          aoMudarMunicipio={(valor) => {
            mudar('municipio', valor);
          }}
        />
        <CampoDaAtividade
          refAtividade={refAtividade}
          atividades={atividades}
          valor={valores.atividade}
          erro={erros.atividade}
          aoEscolher={(valor) => {
            mudar('atividade', valor);
          }}
        />
        <p className="conta__acoes">
          <button type="submit" className="botao-principal" disabled={enviando || espera.aguardando}>
            {rotuloDoEnvio(enviando, espera.restanteMs, 'Salvando…', 'Salvar os dados')}
          </button>
        </p>
        <p className="campo__ajuda" role="status">
          {enviando ? 'Salvando: os motores conferem o município e a atividade.' : aviso}
        </p>
      </form>
    </section>
  );
}

function FormularioDasAliquotas({ empresa, cnpj, aoSalvar }: PropsGravacao & { empresa: Empresa }) {
  const configurar = useConfigurar(cnpj);
  const das = empresa.cenario.operacao.premissasDas;
  const [cbs, setCbs] = useState(paraDigitar(das?.pCBSSN));
  const [ibs, setIbs] = useState(paraDigitar(das?.pIBSSN));
  const [erros, setErros] = useState<{ cbs: string | null; ibs: string | null }>({ cbs: null, ibs: null });
  const [falha, setFalha] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [enviando, setEnviando] = useState<'salvar' | 'simulacao' | null>(null);
  const espera = useEspera();
  const refCbs = useRef<HTMLInputElement>(null);
  const refIbs = useRef<HTMLInputElement>(null);
  const doUsuario = empresa.premissasDasOrigem === 'usuario';

  const gravar = async (corpo: Configuracao, qual: 'salvar' | 'simulacao') => {
    setEnviando(qual);
    setFalha(null);
    setAviso(null);
    try {
      aoSalvar(await configurar(corpo), qual === 'salvar' ? FRASE_SALVO : 'As alíquotas voltaram aos valores da simulação.');
    } catch (e) {
      const { texto, esperaS } = falhaDe(e, 'Não foi possível salvar. Tente de novo.');
      if (esperaS !== null) {
        espera.iniciar(esperaS);
      }
      setFalha(texto);
      setEnviando(null);
    }
  };

  const enviar = (evento: SubmitEvent<HTMLFormElement>) => {
    evento.preventDefault();
    if (enviando !== null || espera.aguardando) {
      return;
    }
    const pCBSSN = lerAliquotaDoDas(cbs);
    const pIBSSN = lerAliquotaDoDas(ibs);
    const novos = { cbs: pCBSSN === null ? FRASE_DA_ALIQUOTA : null, ibs: pIBSSN === null ? FRASE_DA_ALIQUOTA : null };
    setErros(novos);
    if (pCBSSN === null || pIBSSN === null) {
      setFalha(null);
      (pCBSSN === null ? refCbs : refIbs).current?.focus();
      return;
    }
    const iguais = doUsuario && Number(pCBSSN) === Number(das?.pCBSSN) && Number(pIBSSN) === Number(das?.pIBSSN);
    if (iguais) {
      setFalha(null);
      setAviso(FRASE_NADA_MUDOU);
      return;
    }
    void gravar({ premissasDas: { pCBSSN, pIBSSN } }, 'salvar');
  };

  return (
    <section className="conta__secao" aria-labelledby="empresa-das-titulo">
      <h2 id="empresa-das-titulo">Alíquotas do Simples (DAS)</h2>
      <p>
        As alíquotas efetivas de CBS e de IBS do Simples, em %, da apuração da própria empresa. Entram nos cálculos do
        Simples tradicional, também na comparação do Regime. Confira os valores com o contador da empresa.
      </p>
      <p className={doUsuario ? 'campo__ajuda' : 'conta__aviso'} role="note">
        {doUsuario
          ? 'Hoje: as alíquotas informadas aqui.'
          : 'Hoje: valores de exemplo da simulação, rotulados em todo cálculo, até a empresa informar os dela.'}
        {das?.fonte ? ` Fonte: ${das.fonte.replace(/\.$/u, '')}.` : ''}
      </p>
      <form className="formulario" noValidate onSubmit={enviar}>
        <AvisoDeFalha texto={falha} />
        <Campo
          ref={refCbs}
          rotulo="CBS no DAS (%)"
          name="pCBSSN"
          inputMode="decimal"
          autoComplete="off"
          className="num"
          value={cbs}
          erro={erros.cbs}
          ajuda={AJUDA_DA_ALIQUOTA}
          onChange={(e) => {
            setCbs(e.target.value);
            setAviso(null);
            setErros((x) => ({ ...x, cbs: null }));
          }}
        />
        <Campo
          ref={refIbs}
          rotulo="IBS no DAS (%)"
          name="pIBSSN"
          inputMode="decimal"
          autoComplete="off"
          className="num"
          value={ibs}
          erro={erros.ibs}
          ajuda={AJUDA_DA_ALIQUOTA}
          onChange={(e) => {
            setIbs(e.target.value);
            setAviso(null);
            setErros((x) => ({ ...x, ibs: null }));
          }}
        />
        <p className="conta__acoes">
          <button type="submit" className="botao-principal" disabled={enviando !== null || espera.aguardando}>
            {rotuloDoEnvio(enviando === 'salvar', espera.restanteMs, 'Salvando…', 'Salvar as alíquotas')}
          </button>
          {doUsuario && (
            <button
              type="button"
              className="botao-secundario"
              disabled={enviando !== null || espera.aguardando}
              onClick={() => void gravar({ premissasDas: null }, 'simulacao')}
            >
              {enviando === 'simulacao' ? 'Voltando…' : 'Voltar aos valores da simulação'}
            </button>
          )}
        </p>
        <p className="campo__ajuda" role="status">
          {aviso}
        </p>
      </form>
    </section>
  );
}

function ExcluirEmpresa({ empresa, email, aoExcluir }: { empresa: Empresa; email: string; aoExcluir: () => void }) {
  const sessao = useSessao();
  const cnpj = empresa.empresa.cnpj;
  const [aberto, setAberto] = useState(false);
  const [confirmacao, setConfirmacao] = useState('');
  const [senha, setSenha] = useState('');
  const [erros, setErros] = useState<{ cnpj: string | null; senha: string | null }>({ cnpj: null, senha: null });
  const [falha, setFalha] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  const espera = useEspera();
  const refCnpj = useRef<HTMLInputElement>(null);
  const refSenha = useRef<HTMLInputElement>(null);
  const refAbrir = useRef<HTMLButtonElement>(null);

  const fechar = () => {
    setAberto(false);
    setConfirmacao('');
    setSenha('');
    setErros({ cnpj: null, senha: null });
    setFalha(null);
    setTimeout(() => {
      refAbrir.current?.focus();
    }, 0);
  };

  const enviar = async (evento: SubmitEvent<HTMLFormElement>) => {
    evento.preventDefault();
    if (enviando || espera.aguardando) {
      return;
    }
    const novos = { cnpj: conferirCnpjDaConfirmacao(confirmacao, cnpj), senha: conferirSenhaAtual(senha) };
    setErros(novos);
    if (novos.cnpj !== null || novos.senha !== null) {
      setFalha(null);
      (novos.cnpj === null ? refSenha : refCnpj).current?.focus();
      return;
    }
    setEnviando(true);
    setFalha(null);
    try {
      await sessao.conta.excluirEmpresa(sessao.api, cnpj, senha, normalizarCnpj(confirmacao));
      aoExcluir();
    } catch (e) {
      const { texto, esperaS } = falhaDe(e);
      if (esperaS !== null) {
        espera.iniciar(esperaS);
      }
      setSenha('');
      setFalha(texto);
      setEnviando(false);
    }
  };

  return (
    <section className="conta__secao conta__perigo" aria-labelledby="empresa-excluir">
      <h2 id="empresa-excluir">Excluir a empresa</h2>
      <p>
        A exclusão apaga, na hora e de vez, a empresa e tudo o que ela guarda no ContaAI: o catálogo, as notas
        importadas, os custos, os preços, os alertas e os clientes empresa. Não dá para desfazer.
      </p>
      <p className="conta__aviso" role="note">
        {FRASE_GUARDE_AS_NOTAS} O XML das notas não fica guardado aqui: a guarda é da empresa (Ajuste SINIEF 07/05,
        cláusula décima).
      </p>
      {aberto ? (
        <form className="formulario" noValidate onSubmit={(e) => void enviar(e)}>
          <AvisoDeFalha texto={falha} />
          <Campo
            ref={refCnpj}
            rotulo="CNPJ da empresa"
            name="cnpjConfirmacao"
            autoComplete="off"
            spellCheck={false}
            autoCapitalize="characters"
            className="num campo__cnpj"
            value={confirmacao}
            erro={erros.cnpj}
            ajuda={
              <>
                Digite <span className="num">{formatarCnpj(cnpj)}</span> para confirmar, com ou sem a pontuação.
              </>
            }
            onChange={(e) => {
              setConfirmacao(e.target.value);
              setErros((x) => ({ ...x, cnpj: null }));
            }}
          />
          {/* O e-mail da conta, oculto, para o gerenciador de senhas (como em Sua conta). Não é enviado. */}
          <input type="email" name="email" autoComplete="username" value={email} readOnly hidden />
          <CampoSenha
            ref={refSenha}
            rotulo="Senha"
            name="senha"
            autoComplete="current-password"
            value={senha}
            erro={erros.senha}
            ajuda="A senha da sua conta, para confirmar que é você."
            onChange={(e) => {
              setSenha(e.target.value);
              setErros((x) => ({ ...x, senha: null }));
            }}
          />
          <p className="conta__acoes">
            <button type="submit" className="botao-perigo" disabled={enviando || espera.aguardando}>
              {rotuloDoEnvio(enviando, espera.restanteMs, 'Excluindo…', 'Excluir a empresa')}
            </button>
            <button type="button" className="botao-secundario" disabled={enviando} onClick={fechar}>
              Cancelar
            </button>
          </p>
        </form>
      ) : (
        <p>
          <button
            ref={refAbrir}
            type="button"
            className="botao-secundario"
            onClick={() => {
              setAberto(true);
              setTimeout(() => {
                refCnpj.current?.focus();
              }, 0);
            }}
          >
            Excluir a empresa…
          </button>
        </p>
      )}
    </section>
  );
}

function Item({ nome, children }: { nome: string; children: ReactNode }) {
  return (
    <div className="lado__item">
      <dt>{nome}</dt>
      <dd>{children}</dd>
    </div>
  );
}

/** O que o membro vê: os dados, sem os formulários. */
function DadosParaLer({ empresa }: { empresa: Empresa }) {
  const das = empresa.cenario.operacao.premissasDas;
  return (
    <section className="conta__secao" aria-labelledby="empresa-dados-titulo">
      <h2 id="empresa-dados-titulo">Dados da empresa</h2>
      <p className="campo__ajuda">Só o dono da organização muda as configurações e exclui a empresa.</p>
      <dl className="lado__lista">
        <Item nome="CNPJ">
          <span className="num">{formatarCnpj(empresa.empresa.cnpj)}</span>
        </Item>
        <Item nome="Razão social">{empresa.empresa.razaoSocial}</Item>
        <Item nome="Regime">{NOME_REGIME[empresa.empresa.regimeAtual]}</Item>
        <Item nome="Município">
          {empresa.empresa.municipioNome} · {empresa.empresa.uf}
        </Item>
        <Item nome="Atividade no Simples">
          {empresa.atividade.descricao} (anexo {empresa.atividade.anexo})
        </Item>
        <Item nome="Alíquotas do DAS">
          CBS {aliquota(das?.pCBSSN)} · IBS {aliquota(das?.pIBSSN)}
          {empresa.premissasDasOrigem === 'simulacao' ? ' (valores de exemplo da simulação)' : ''}
        </Item>
      </dl>
    </section>
  );
}

/** Ao lado: o que muda quando a empresa muda. Cada frase foi conferida no código (ADR 0017 e ADR 0018). */
function OQueMuda() {
  return (
    <aside className="cadastro__lado" aria-labelledby="empresa-muda">
      <h2 id="empresa-muda">O que muda nos cálculos</h2>
      <dl className="lado__lista">
        <Item nome="Os próximos cálculos">
          Usam os dados novos: o regime, o município, a atividade e as alíquotas do DAS.
        </Item>
        <Item nome="O que já foi gravado">
          As notas, os custos e os alertas ficam como foram calculados na hora em que entraram.
        </Item>
        <Item nome="Os motores">Recebem a UF, o município e a atividade. Nunca o CNPJ nem a razão social.</Item>
      </dl>
    </aside>
  );
}

function EmpresaExcluida({ dono }: { dono: boolean }) {
  return (
    <section className="passo porta__curta">
      <TituloDoPasso>A empresa foi excluída</TituloDoPasso>
      <p>A empresa e os dados dela saíram do ContaAI.</p>
      <p className="porta__acoes">
        {dono && (
          <Link para={ROTA_DO_CADASTRO.caminho} className="botao-principal">
            {ROTA_DO_CADASTRO.nome}
          </Link>
        )}
        <BotaoDemonstracao className="botao-secundario" />
      </p>
    </section>
  );
}

function SemEmpresa({ conta }: { conta: Conta }) {
  const dono = conta.organizacao.papel === 'dono';
  return (
    <div className="vazio porta__curta">
      <p>{dono ? 'A sua conta ainda não tem empresa.' : 'A sua organização ainda não tem empresa. Só o dono a cadastra.'}</p>
      <p className="porta__acoes">
        {dono ? (
          <Link para={ROTA_DO_CADASTRO.caminho} className="botao-principal">
            {ROTA_DO_CADASTRO.nome}
          </Link>
        ) : (
          <BotaoDemonstracao className="botao-principal" />
        )}
      </p>
    </div>
  );
}

function ComEmpresa({ conta, cnpj, aoExcluir }: { conta: Conta; cnpj: string; aoExcluir: () => void }) {
  const { api } = useSessao();
  const dono = conta.organizacao.papel === 'dono';
  const lida = useRecurso(`empresa:${cnpj}:conta:${conta.organizacao.id}`, (sinal) =>
    chamar(api.GET('/empresas/{cnpj}', { params: { path: { cnpj } }, signal: sinal })),
  );
  const atividades = useAtividades(dono);
  // A resposta do PATCH é a empresa nova: ela vale até a próxima leitura (que só sai ao abrir a página de novo).
  const [salva, setSalva] = useState<{ empresa: Empresa; frase: string; vez: number } | null>(null);
  const empresa = salva?.empresa ?? lida.dados;

  if (empresa === undefined) {
    return lida.erro !== undefined ? <FalhaNoBloco erro={lida.erro} aoTentar={lida.recarregar} /> : <Carregando linhas={6} />;
  }
  const aoSalvar = (nova: Empresa, frase: string) => {
    setSalva((s) => ({ empresa: nova, frase, vez: (s?.vez ?? 0) + 1 }));
  };
  // Os formulários recomeçam com os valores gravados depois de cada gravação (a chave muda).
  const chave = String(salva?.vez ?? 0);
  return (
    <div className="cadastro conta">
      <div className="cadastro__principal">
        {salva !== null && (
          <p className="conta__salvo" role="status">
            {salva.frase}
          </p>
        )}
        {dono ? (
          <>
            <FormularioDosDados key={`dados-${chave}`} empresa={empresa} atividades={atividades} cnpj={cnpj} aoSalvar={aoSalvar} />
            <FormularioDasAliquotas key={`das-${chave}`} empresa={empresa} cnpj={cnpj} aoSalvar={aoSalvar} />
          </>
        ) : (
          <DadosParaLer empresa={empresa} />
        )}
      </div>
      <OQueMuda />
      {dono && (
        <div className="cadastro__principal">
          <ExcluirEmpresa empresa={empresa} email={conta.email} aoExcluir={aoExcluir} />
        </div>
      )}
    </div>
  );
}

function ConteudoDasConfiguracoes() {
  const sessao = useSessao();
  const estado = useConta();
  const naDemo = estado.tipo === 'conectada' && estado.naDemo;
  const [excluida, setExcluida] = useState(false);

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
  if (excluida) {
    return <EmpresaExcluida dono={conta.organizacao.papel === 'dono'} />;
  }
  const [cnpj] = conta.empresas;
  if (cnpj === undefined) {
    return <SemEmpresa conta={conta} />;
  }
  return (
    <ComEmpresa
      key={cnpj}
      conta={conta}
      cnpj={cnpj}
      aoExcluir={() => {
        setExcluida(true);
      }}
    />
  );
}

export function ConfiguracoesDaEmpresa() {
  return (
    <Pagina titulo={ROTA_DA_EMPRESA.nome}>
      <PortaDaConta exige="conta" paraQue="ver as configurações da empresa">
        <ConteudoDasConfiguracoes />
      </PortaDaConta>
    </Pagina>
  );
}
