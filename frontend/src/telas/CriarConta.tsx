// Criar conta (C2b, T4, etapas 6 e 7; ADR 0016), em três passos:
//   1. e-mail, senha, organização e o aceite dos termos (POST /contas): a conta nasce pendente;
//   2. o QR code (ou o segredo) e o primeiro código do aplicativo (POST /contas/ativar): a conta passa a valer e
//      a sessão começa (SegundoFator.tsx);
//   3. os 10 códigos de recuperação, mostrados uma vez só.
//
// - O formulário do passo 1 mora num componente próprio: quando o passo acaba, ele sai da tela, e a senha sai da
//   memória junto. Nada do cadastro vai ao endereço, ao armazenamento do navegador ou ao log.
// - O envio é por fetch (SessaoConta.cadastrar), e o <form> não tem action: a CSP tem form-action 'none'. O
//   preventDefault segura o envio nativo.
// - Os campos levam autocomplete (username, new-password e organization) e name, para o gerenciador de senhas
//   reconhecer o cadastro e oferecer a senha forte (NIST SP 800-63B-4, §3.1.1.2: SHALL permitir gerenciadores).
// - O aceite dos termos é uma caixa obrigatória; a versão aceita é a de legal.ts, a única que o contrato aceita
//   (plano v2.1, C2, decisão 5). A política de privacidade entra como link, para ler, e não como consentimento.
// - O 409 (e-mail já cadastrado) mostra a frase da API e o caminho para Entrar; o 422 (senha recusada) e o 429
//   (limite, com a espera do Retry-After) mostram a frase da API.
// - Os campos não têm maxLength: o do HTML conta unidades UTF-16 (um emoji vale 2, e o backend conta 1) e corta
//   o texto colado sem avisar. O tamanho é conferido com frase (regrasDeEntrada.ts), contado como o backend conta.

import { useRef, useState, type SubmitEvent } from 'react';
import { ErroApi } from '../api/problema.ts';
import type { Ativacao, Cadastro } from '../sessao/conta.ts';
import { useSessao } from '../sessao/contexto.tsx';
import { Link, navegar } from '../shell/navegacao.tsx';
import { Pagina } from '../shell/Pagina.tsx';
import { INICIO_DO_APP } from '../shell/rotas.ts';
import { PortaDaConta } from './PortaDaConta.tsx';
import { CodigosDeRecuperacao, PassoDoQr, Passos, TituloDoPasso } from './SegundoFator.tsx';
import {
  AvisoDeFalha,
  Campo,
  CaixaDeMarcar,
  CampoSenha,
  falhaDe,
  rotuloDoEnvio,
  useEspera,
} from './formulario.tsx';
import { MedidorDeForca, palavrasDaPessoa, useForcaDaSenha } from './forcaDaSenha.tsx';
import { REGRAS_DA_CONTA, VERSAO_TERMOS, dataDaVersao } from './legal.ts';
import { conferirEmail, conferirOrganizacao, conferirSenhaNova } from './regrasDeEntrada.ts';
import './conta.css';
import './publicas.css';
import './telas.css';

export const PASSOS_DO_CADASTRO = ['Seus dados', 'Aplicativo autenticador', 'Códigos de recuperação'] as const;

type Passo =
  | { tipo: 'dados' }
  | { tipo: 'qr'; email: string; cadastro: Cadastro; recebidoEm: number }
  | { tipo: 'codigos'; email: string; ativacao: Ativacao };

interface Erros {
  email: string | null;
  senha: string | null;
  organizacao: string | null;
  termos: string | null;
}

const SEM_ERROS: Erros = { email: null, senha: null, organizacao: null, termos: null };

export const FRASE_DOS_TERMOS = 'Para criar a conta, marque que você aceita os termos de uso.';

/** Passo 1: os dados da conta e o aceite. `aoCadastrar` recebe o e-mail como foi enviado e a resposta da API. */
function DadosDaConta({ aoCadastrar }: { aoCadastrar: (email: string, cadastro: Cadastro) => void }) {
  const sessao = useSessao();
  const [email, setEmail] = useState('');
  const [senha, setSenha] = useState('');
  const [organizacao, setOrganizacao] = useState('');
  const [aceite, setAceite] = useState(false);
  const [erros, setErros] = useState<Erros>(SEM_ERROS);
  const [falha, setFalha] = useState<{ texto: string; jaTemConta: boolean } | null>(null);
  const [enviando, setEnviando] = useState(false);
  const espera = useEspera();
  const forca = useForcaDaSenha(senha, palavrasDaPessoa(email, organizacao));
  const refEmail = useRef<HTMLInputElement>(null);
  const refSenha = useRef<HTMLInputElement>(null);
  const refOrganizacao = useRef<HTMLInputElement>(null);
  const refTermos = useRef<HTMLInputElement>(null);

  const enviar = async (evento: SubmitEvent<HTMLFormElement>) => {
    evento.preventDefault();
    if (enviando || espera.aguardando) {
      return;
    }
    const novos: Erros = {
      email: conferirEmail(email),
      senha: conferirSenhaNova(senha),
      organizacao: conferirOrganizacao(organizacao),
      termos: aceite ? null : FRASE_DOS_TERMOS,
    };
    setErros(novos);
    // O foco vai ao primeiro campo com erro, na ordem da tela (WCAG 3.3.1).
    const ordem = [
      [novos.email, refEmail],
      [novos.senha, refSenha],
      [novos.organizacao, refOrganizacao],
      [novos.termos, refTermos],
    ] as const;
    const primeiro = ordem.find(([erro]) => erro !== null);
    if (primeiro !== undefined) {
      setFalha(null);
      primeiro[1].current?.focus();
      return;
    }
    setEnviando(true);
    setFalha(null);
    const enviado = email.trim();
    try {
      const cadastro = await sessao.conta.cadastrar(sessao.api, {
        email: enviado,
        senha,
        organizacao: organizacao.trim(),
        termosAceitos: VERSAO_TERMOS,
      });
      aoCadastrar(enviado, cadastro);
    } catch (e) {
      const { texto, esperaS } = falhaDe(e);
      if (esperaS !== null) {
        espera.iniciar(esperaS);
      }
      setFalha({ texto, jaTemConta: e instanceof ErroApi && e.status === 409 });
      setEnviando(false);
    }
  };

  return (
    <section className="passo">
      <TituloDoPasso focar={false}>Seus dados</TituloDoPasso>
      <form className="formulario" noValidate onSubmit={(e) => void enviar(e)}>
        <AvisoDeFalha texto={falha?.texto ?? null} />
        {falha?.jaTemConta === true && (
          <p className="porta__alternativa">
            <Link para="/entrar">Entrar</Link>
          </p>
        )}
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
          ajuda="Não há e-mail de confirmação: confira antes de seguir."
          onChange={(e) => {
            setEmail(e.target.value);
          }}
        />
        <CampoSenha
          ref={refSenha}
          rotulo="Senha"
          name="senha"
          autoComplete="new-password"
          value={senha}
          abaixo={forca === null ? undefined : <MedidorDeForca forca={forca} />}
          erro={erros.senha}
          ajuda={`Pelo menos ${String(REGRAS_DA_CONTA.senhaMinima)} caracteres. Prefira uma frase longa.`}
          onChange={(e) => {
            setSenha(e.target.value);
          }}
        />
        <Campo
          ref={refOrganizacao}
          rotulo="Organização"
          name="organizacao"
          autoComplete="organization"
          value={organizacao}
          erro={erros.organizacao}
          ajuda="Nome do escritório ou da empresa."
          onChange={(e) => {
            setOrganizacao(e.target.value);
          }}
        />
        <div className="formulario__termos">
          <p className="campo__ajuda">
            <Link para="/termos" target="_blank">
              Termos de uso
            </Link>{' '}
            ·{' '}
            <Link para="/privacidade" target="_blank">
              Privacidade
            </Link>{' '}
            (abrem em outra aba)
          </p>
          <CaixaDeMarcar
            ref={refTermos}
            name="termos"
            checked={aceite}
            erro={erros.termos}
            onChange={(e) => {
              setAceite(e.target.checked);
            }}
          >
            Li e aceito os termos de uso (versão de {dataDaVersao(VERSAO_TERMOS)}).
          </CaixaDeMarcar>
        </div>
        <p>
          <button type="submit" className="botao-principal" disabled={enviando || espera.aguardando}>
            {rotuloDoEnvio(enviando, espera.restanteMs, 'Criando…', 'Continuar')}
          </button>
        </p>
      </form>
      <p className="porta__alternativa">
        Já tem conta? <Link para="/entrar">Entrar</Link>
      </p>
    </section>
  );
}

const R = REGRAS_DA_CONTA;

/**
 * Ao lado dos passos: como a conta é protegida. As regras vêm de legal.ts (conferidas com o backend em
 * legal.test.ts) e dizem o mesmo que os termos de uso (Termos.tsx, "A conta").
 */
function ComoAContaEProtegida() {
  return (
    <aside className="cadastro__lado" aria-labelledby="cadastro-protecao">
      <h2 id="cadastro-protecao">Como a conta é protegida</h2>
      <dl className="lado__lista">
        <div className="lado__item">
          <dt>Senha</dt>
          <dd>Guardada só como resumo (Argon2id). Não há recuperação de senha.</dd>
        </div>
        <div className="lado__item">
          <dt>Segundo fator</dt>
          <dd>Um código de {R.digitosDoCodigo} dígitos do aplicativo autenticador a cada entrada.</dd>
        </div>
        <div className="lado__item">
          <dt>Recuperação</dt>
          <dd>{R.codigosDeRecuperacao} códigos de uso único, para quando faltar o aplicativo.</dd>
        </div>
        <div className="lado__item">
          <dt>Sessão</dt>
          <dd>
            Termina com {R.sessaoOciosaMin} minutos sem uso ou {R.sessaoTotalH} horas depois de entrar.
          </dd>
        </div>
      </dl>
    </aside>
  );
}

export function CriarConta() {
  const [passo, setPasso] = useState<Passo>({ tipo: 'dados' });
  const atual = { dados: 0, qr: 1, codigos: 2 }[passo.tipo];

  return (
    <Pagina titulo="Criar conta">
      {/* Do passo 2 em diante, a página não vai sozinha ao Painel quando a sessão começa (os códigos ainda vão
          aparecer). */}
      <PortaDaConta exige="visitante" fluxoAberto={passo.tipo !== 'dados'}>
        <div className="cadastro">
          <div className="cadastro__principal">
            <Passos nomes={PASSOS_DO_CADASTRO} atual={atual} />
            {passo.tipo === 'dados' && (
              <DadosDaConta
                aoCadastrar={(email, cadastro) => {
                  setPasso({ tipo: 'qr', email, cadastro, recebidoEm: Date.now() });
                }}
              />
            )}
            {passo.tipo === 'qr' && (
              <PassoDoQr
                cadastro={passo.cadastro}
                recebidoEm={passo.recebidoEm}
                email={passo.email}
                aoAtivar={(ativacao) => {
                  setPasso({ tipo: 'codigos', email: passo.email, ativacao });
                }}
              />
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
          </div>
          <ComoAContaEProtegida />
        </div>
      </PortaDaConta>
    </Pagina>
  );
}
