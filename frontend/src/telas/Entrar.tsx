// Entrar (C2b, T5, etapa 8; ADR 0016), em duas etapas:
//   1. e-mail e senha (POST /sessoes). Certos, o passe vai no cookie, e a resposta diz o próximo passo;
//   2. o código do aplicativo, ou um código de recuperação (POST /sessoes/codigo): a sessão começa.
// Numa conta que ainda não confirmou o primeiro código (`etapa: "ativacao"`, decisão 1 da C2b), o passo 2 é o do
// QR, como no cadastro, e depois vêm os 10 códigos de recuperação (SegundoFator.tsx).
//
// - A senha mora só no componente do passo 1: quando ele sai da tela, a senha sai da memória junto. Nada vai ao
//   endereço, ao armazenamento do navegador ou ao log. O e-mail volta ao passo 1 se o passe vencer, para não
//   ser digitado de novo; a senha, não.
// - O envio é por fetch, e o <form> não tem action (a CSP tem form-action 'none'). Os campos levam autocomplete
//   (username, current-password e one-time-code) e name, para o gerenciador de senhas preencher (NIST SP
//   800-63B-4, §3.1.1.2).
// - O 401 tem uma frase só para e-mail, senha, código ou passe errados: a tela mostra a frase da API e não tenta
//   adivinhar qual foi. O 429 segura o botão pelo Retry-After; o da conta bloqueada não mostra contagem
//   (formulario.tsx, falhaDe).
// - O prazo do passe (5 min) conta de quando a resposta chegou, como no cadastro. Vencido, a página volta ao
//   passo 1 e diz por quê.
// - Com um código de recuperação, ele deixa de valer e a API devolve outro no lugar, uma vez só: a página o
//   mostra antes de seguir ao Painel.

import { useEffect, useRef, useState, type SubmitEvent } from 'react';
import type { Ativacao, Cadastro, Entrada } from '../sessao/conta.ts';
import { useSessao } from '../sessao/contexto.tsx';
import { Link, navegar } from '../shell/navegacao.tsx';
import { Pagina } from '../shell/Pagina.tsx';
import { INICIO_DO_APP } from '../shell/rotas.ts';
import { PortaDaConta } from './PortaDaConta.tsx';
import { CodigosDeRecuperacao, PassoDoQr, TituloDoPasso, prazoDoPasse } from './SegundoFator.tsx';
import {
  AvisoDeFalha,
  BotaoCopiar,
  Campo,
  CampoCodigo,
  CampoRecuperacao,
  CampoSenha,
  Contagem,
  falhaDe,
  rotuloDoEnvio,
  useEspera,
  useRestante,
} from './formulario.tsx';
import { REGRAS_DA_CONTA } from './legal.ts';
import {
  conferirCodigo,
  conferirEmail,
  conferirRecuperacao,
  conferirSenhaAtual,
  normalizarCodigo,
  normalizarRecuperacao,
} from './regrasDeEntrada.ts';
import './conta.css';
import './publicas.css';
import './telas.css';

type Passo =
  | { tipo: 'credenciais'; email: string; aviso: string | null }
  | { tipo: 'codigo'; email: string; recebidoEm: number }
  | { tipo: 'qr'; email: string; cadastro: Cadastro; recebidoEm: number }
  | { tipo: 'codigos'; email: string; ativacao: Ativacao }
  | { tipo: 'novo-codigo'; codigo: string; aviso: string | null };

export const FRASE_DO_PASSE_VENCIDO = 'O tempo para o código acabou. Entre de novo com o e-mail e a senha.';

interface PropsCredenciais {
  /** O e-mail de antes (passe vencido), para não digitar de novo. */
  emailInicial: string;
  /** Por que a página voltou a este passo, ou null. */
  aviso: string | null;
  aoPedirCodigo: (email: string) => void;
  aoPedirAtivacao: (email: string, cadastro: Cadastro) => void;
}

/** Passo 1: e-mail e senha. */
function Credenciais({ emailInicial, aviso, aoPedirCodigo, aoPedirAtivacao }: PropsCredenciais) {
  const sessao = useSessao();
  const [email, setEmail] = useState(emailInicial);
  const [senha, setSenha] = useState('');
  const [erros, setErros] = useState<{ email: string | null; senha: string | null }>({ email: null, senha: null });
  const [falha, setFalha] = useState<string | null>(aviso);
  const [enviando, setEnviando] = useState(false);
  const espera = useEspera();
  const refEmail = useRef<HTMLInputElement>(null);
  const refSenha = useRef<HTMLInputElement>(null);

  const enviar = async (evento: SubmitEvent<HTMLFormElement>) => {
    evento.preventDefault();
    if (enviando || espera.aguardando) {
      return;
    }
    const novos = { email: conferirEmail(email), senha: conferirSenhaAtual(senha) };
    setErros(novos);
    if (novos.email !== null || novos.senha !== null) {
      setFalha(null);
      (novos.email === null ? refSenha : refEmail).current?.focus();
      return;
    }
    setEnviando(true);
    setFalha(null);
    const enviado = email.trim();
    try {
      const proximo = await sessao.conta.entrar(sessao.api, { email: enviado, senha });
      if (proximo.etapa === 'ativacao') {
        aoPedirAtivacao(enviado, proximo.cadastro);
      } else {
        aoPedirCodigo(enviado);
      }
    } catch (e) {
      const { texto, esperaS } = falhaDe(e);
      if (esperaS !== null) {
        espera.iniciar(esperaS);
      }
      // A senha errada sai do campo; o e-mail fica (a frase não diz qual dos dois estava errado).
      setSenha('');
      setFalha(texto);
      setEnviando(false);
    }
  };

  return (
    <section className="passo">
      <TituloDoPasso focar={false}>E-mail e senha</TituloDoPasso>
      <form className="formulario" noValidate onSubmit={(e) => void enviar(e)}>
        <AvisoDeFalha texto={falha} />
        <Campo
          ref={refEmail}
          rotulo="E-mail"
          type="email"
          name="email"
          autoComplete="username"
          inputMode="email"
          spellCheck={false}
          autoCapitalize="off"
          value={email}
          erro={erros.email}
          onChange={(e) => {
            setEmail(e.target.value);
          }}
        />
        <CampoSenha
          ref={refSenha}
          rotulo="Senha"
          name="senha"
          autoComplete="current-password"
          value={senha}
          erro={erros.senha}
          onChange={(e) => {
            setSenha(e.target.value);
          }}
        />
        <p>
          <button type="submit" className="botao-principal" disabled={enviando || espera.aguardando}>
            {rotuloDoEnvio(enviando, espera.restanteMs, 'Conferindo…', 'Continuar')}
          </button>
        </p>
      </form>
      <p className="porta__alternativa">
        Ainda não tem conta? <Link para="/criar-conta">Criar conta</Link>
      </p>
    </section>
  );
}

interface PropsCodigo {
  email: string;
  recebidoEm: number;
  aoEntrar: (entrada: Entrada) => void;
  aoVencer: () => void;
}

/** Passo 2: o código do aplicativo, ou um código de recuperação (um botão troca o campo). */
function SegundaEtapa({ email, recebidoEm, aoEntrar, aoVencer }: PropsCodigo) {
  const sessao = useSessao();
  const restante = useRestante(prazoDoPasse(recebidoEm), aoVencer);
  const [recuperacao, setRecuperacao] = useState(false);
  const [codigo, setCodigo] = useState('');
  const [erro, setErro] = useState<string | null>(null);
  const [falha, setFalha] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  const espera = useEspera();
  const refCodigo = useRef<HTMLInputElement>(null);

  const trocar = () => {
    setRecuperacao((r) => !r);
    setCodigo('');
    setErro(null);
    setFalha(null);
    // O campo novo recebe o foco depois de aparecer.
    setTimeout(() => {
      refCodigo.current?.focus();
    }, 0);
  };

  const enviar = async (evento: SubmitEvent<HTMLFormElement>) => {
    evento.preventDefault();
    if (enviando || espera.aguardando) {
      return;
    }
    const erroDoCampo = recuperacao ? conferirRecuperacao(codigo) : conferirCodigo(codigo);
    setErro(erroDoCampo);
    if (erroDoCampo !== null) {
      setFalha(null);
      refCodigo.current?.focus();
      return;
    }
    setEnviando(true);
    setFalha(null);
    try {
      const entrada = await sessao.conta.confirmarCodigo(
        sessao.api,
        recuperacao
          ? { codigoRecuperacao: normalizarRecuperacao(codigo) }
          : { codigo: normalizarCodigo(codigo) },
      );
      aoEntrar(entrada);
    } catch (e) {
      const { texto, esperaS } = falhaDe(e);
      if (esperaS !== null) {
        espera.iniciar(esperaS);
      }
      setCodigo('');
      setFalha(texto);
      setEnviando(false);
    }
  };

  const propsDoCampo = {
    ref: refCodigo,
    name: recuperacao ? 'codigo-recuperacao' : 'codigo',
    value: codigo,
    erro,
    onChange: (e: { target: { value: string } }) => {
      setCodigo(e.target.value);
    },
  };

  return (
    <section className="passo">
      <TituloDoPasso>{recuperacao ? 'Código de recuperação' : 'Código do aplicativo'}</TituloDoPasso>
      <p className="campo__ajuda">
        Conta: <span translate="no">{email}</span>
      </p>
      <form className="formulario" noValidate onSubmit={(e) => void enviar(e)}>
        <AvisoDeFalha texto={falha} />
        {recuperacao ? (
          <CampoRecuperacao {...propsDoCampo} ajuda="Cada código vale uma vez. Outro entra no lugar dele." />
        ) : (
          <CampoCodigo
            {...propsDoCampo}
            ajuda={`Os ${String(REGRAS_DA_CONTA.digitosDoCodigo)} números que o aplicativo autenticador mostra agora.`}
          />
        )}
        {restante !== null && <Contagem restanteMs={restante} rotulo="Vale por mais" />}
        <p>
          <button type="submit" className="botao-principal" disabled={enviando || espera.aguardando}>
            {rotuloDoEnvio(enviando, espera.restanteMs, 'Conferindo…', 'Entrar')}
          </button>
        </p>
      </form>
      <p>
        <button type="button" className="botao-secundario" onClick={trocar}>
          {recuperacao ? 'Usar o código do aplicativo' : 'Sem o aplicativo? Use um código de recuperação'}
        </button>
      </p>
    </section>
  );
}

/**
 * Depois de entrar com um código de recuperação: o código novo, que não aparece de novo. Fechar ou recarregar a
 * aba aqui pede confirmação ao navegador, como no passo dos 10 códigos.
 */
function NovoCodigo({ codigo, aviso }: { codigo: string; aviso: string | null }) {
  useEffect(() => {
    const avisar = (evento: BeforeUnloadEvent) => {
      evento.preventDefault();
    };
    globalThis.addEventListener('beforeunload', avisar);
    return () => {
      globalThis.removeEventListener('beforeunload', avisar);
    };
  }, []);
  return (
    <section className="passo">
      <TituloDoPasso>Guarde o código novo</TituloDoPasso>
      <p>{aviso ?? 'O código de recuperação usado deixou de valer. Guarde o novo no lugar dele.'}</p>
      {/* eslint-disable-next-line jsx-a11y/no-redundant-roles */}
      <ol className="codigos codigos--um num" role="list" aria-label="Código de recuperação novo" translate="no">
        <li>{codigo}</li>
      </ol>
      <p className="codigos__acoes">
        <BotaoCopiar texto={codigo} rotulo="Copiar o código" />
      </p>
      <p>
        <button
          type="button"
          className="botao-principal"
          onClick={() => {
            navegar(INICIO_DO_APP, { substituir: true });
          }}
        >
          Guardei o código
        </button>
      </p>
    </section>
  );
}

/** Ao lado dos passos: o que fazer sem o aplicativo, e o que os termos dizem sobre o acesso (o link dos termos fica no rodapé). */
function SemAcesso() {
  const R = REGRAS_DA_CONTA;
  return (
    <aside className="cadastro__lado" aria-labelledby="entrar-sem-acesso">
      <h2 id="entrar-sem-acesso">Sem acesso?</h2>
      <dl className="lado__lista">
        <div className="lado__item">
          <dt>Sem o aplicativo</dt>
          <dd>Use um dos {R.codigosDeRecuperacao} códigos de recuperação que a conta recebeu no cadastro.</dd>
        </div>
        <div className="lado__item">
          <dt>Sem a senha</dt>
          <dd>Não há recuperação de senha.</dd>
        </div>
        <div className="lado__item">
          <dt>Erros seguidos</dt>
          <dd>
            Da {R.falhasParaEsperar}ª em diante, há uma espera. Na {R.falhasParaBloquear}ª, a conta é bloqueada.
          </dd>
        </div>
      </dl>
    </aside>
  );
}

export function Entrar() {
  const [passo, setPasso] = useState<Passo>({ tipo: 'credenciais', email: '', aviso: null });
  const recomecar = (email: string) => {
    setPasso({ tipo: 'credenciais', email, aviso: FRASE_DO_PASSE_VENCIDO });
  };

  return (
    <Pagina titulo="Entrar">
      {/* Do passo 2 em diante, a página não vai sozinha ao Painel quando a sessão começa: um código de
          recuperação novo ou os 10 códigos da ativação ainda vão aparecer. */}
      <PortaDaConta exige="visitante" fluxoAberto={passo.tipo !== 'credenciais'}>
        <div className="cadastro entrada">
          <div className="cadastro__principal">
            {passo.tipo === 'credenciais' && (
              <Credenciais
                emailInicial={passo.email}
                aviso={passo.aviso}
                aoPedirCodigo={(email) => {
                  setPasso({ tipo: 'codigo', email, recebidoEm: Date.now() });
                }}
                aoPedirAtivacao={(email, cadastro) => {
                  setPasso({ tipo: 'qr', email, cadastro, recebidoEm: Date.now() });
                }}
              />
            )}
            {passo.tipo === 'codigo' && (
              <SegundaEtapa
                email={passo.email}
                recebidoEm={passo.recebidoEm}
                aoVencer={() => {
                  recomecar(passo.email);
                }}
                aoEntrar={({ novoCodigoRecuperacao, aviso }) => {
                  if (novoCodigoRecuperacao === null) {
                    navegar(INICIO_DO_APP, { substituir: true });
                  } else {
                    setPasso({ tipo: 'novo-codigo', codigo: novoCodigoRecuperacao, aviso });
                  }
                }}
              />
            )}
            {passo.tipo === 'qr' && (
              <>
                <p className="campo__ajuda">Esta conta ainda não confirmou o primeiro código do aplicativo.</p>
                <PassoDoQr
                  cadastro={passo.cadastro}
                  recebidoEm={passo.recebidoEm}
                  email={passo.email}
                  aoAtivar={(ativacao) => {
                    setPasso({ tipo: 'codigos', email: passo.email, ativacao });
                  }}
                  aoRecomecar={() => {
                    recomecar(passo.email);
                  }}
                />
              </>
            )}
            {passo.tipo === 'codigos' && (
              <CodigosDeRecuperacao
                email={passo.email}
                ativacao={passo.ativacao}
                aoConcluir={() => {
                  navegar(INICIO_DO_APP, { substituir: true });
                }}
              />
            )}
            {passo.tipo === 'novo-codigo' && <NovoCodigo codigo={passo.codigo} aviso={passo.aviso} />}
          </div>
          <SemAcesso />
        </div>
      </PortaDaConta>
    </Pagina>
  );
}
