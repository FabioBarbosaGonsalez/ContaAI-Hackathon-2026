// Sua conta (C2b, T6, etapa 9; ADR 0016): os dados que o GET /conta devolve e as ações da conta.
//
// - Os dados vêm só do estado da sessão (o GET /conta que a tela já fez): a página não pede nada à API para
//   mostrar. O e-mail, a organização e os CNPJs vão como texto (o React escapa).
// - "Ver os seus dados", "baixar os seus dados" (C3b) e "excluir a conta" são os direitos que a política de
//   privacidade aponta para cá (LGPD, art. 18). A página não diz que mostra tudo o que é guardado: a lista completa
//   está na política, e o arquivo baixado diz o que fica de fora (`naoIncluido`).
// - Sair e sair de todos os aparelhos levam à página inicial, sem deixar esta página no voltar.
// - Excluir pede a senha de novo e a confirmação de que não dá para desfazer (o backend só exige a senha; a caixa
//   evita o clique por engano). O 401 da API vale tanto para a senha errada quanto para a sessão que acabou: a
//   SessaoConta pergunta de novo quem entrou, e, sem sessão, a página mostra "Sua sessão terminou" (PortaDaConta).
// - O aviso de poucos códigos de recuperação aparece com 3 ou menos (decisão 3 da C2b).

import { useRef, useState, type ReactNode, type SubmitEvent } from 'react';
import { cnpj, instante } from '../dados/formatar.ts';
import type { Conta as DadosDaConta } from '../sessao/conta.ts';
import { useSessao } from '../sessao/contexto.tsx';
import { useConta } from '../sessao/ganchos.ts';
import { FRASE_SAIR_FALHOU, useSair } from '../shell/MenuDaConta.tsx';
import { Link, navegar } from '../shell/navegacao.tsx';
import { Pagina } from '../shell/Pagina.tsx';
import { ROTA_DA_CONTA } from '../shell/rotas.ts';
import { PortaDaConta } from './PortaDaConta.tsx';
import { TituloDoPasso } from './SegundoFator.tsx';
import {
  AvisoDeFalha,
  CaixaDeMarcar,
  CampoSenha,
  baixarTexto,
  falhaDe,
  rotuloDoEnvio,
  useEspera,
} from './formulario.tsx';
import { REGRAS_DA_CONTA, dataDaVersao } from './legal.ts';
import { conferirSenhaAtual } from './regrasDeEntrada.ts';
import './conta.css';
import './publicas.css';
import './telas.css';

/** Com quantos códigos de recuperação (ou menos) a página avisa (decisão 3 da C2b). */
export const AVISO_DE_CODIGOS = 3;

export const FRASE_DA_CONFIRMACAO = 'Marque que você entende que a exclusão não pode ser desfeita.';

type Evento = DadosDaConta['eventos'][number];

/** O nome de cada aviso de segurança. O tipo vem do contrato: um tipo novo lá obriga a escrever o nome aqui. */
const NOME_DO_EVENTO: Record<Evento['tipo'], string> = {
  'codigo-recuperacao-usado': 'Código de recuperação usado para entrar',
};

const NOME_DO_PAPEL: Record<DadosDaConta['organizacao']['papel'], string> = {
  dono: 'Dono',
  membro: 'Membro',
};

function Item({ nome, children }: { nome: string; children: ReactNode }) {
  return (
    <div className="lado__item">
      <dt>{nome}</dt>
      <dd>{children}</dd>
    </div>
  );
}

function Dados({ conta }: { conta: DadosDaConta }) {
  return (
    <section className="conta__secao" aria-labelledby="conta-dados">
      <h2 id="conta-dados">Dados da conta</h2>
      <dl className="lado__lista">
        <Item nome="E-mail">
          <span translate="no">{conta.email}</span>
        </Item>
        <Item nome="Organização">
          {conta.organizacao.nome} · {NOME_DO_PAPEL[conta.organizacao.papel]}
        </Item>
        <Item nome="Criada em">{instante(conta.criadaEm)}</Item>
        <Item nome="Termos de uso">
          {conta.termos === null
            ? 'Sem registro do aceite: a conta é de antes do aceite dos termos.'
            : `Versão de ${dataDaVersao(conta.termos.versao)}, aceita em ${instante(conta.termos.aceitosEm)}.`}
        </Item>
        <Item nome="Empresas">
          {conta.empresas.length === 0 ? (
            'Nenhuma empresa cadastrada.'
          ) : (
            <ul className="conta__empresas num">
              {conta.empresas.map((c) => (
                <li key={c}>{cnpj(c)}</li>
              ))}
            </ul>
          )}
        </Item>
      </dl>
    </section>
  );
}

function SegundoFator({ conta }: { conta: DadosDaConta }) {
  const restantes = conta.codigosRecuperacaoRestantes;
  return (
    <section className="conta__secao" aria-labelledby="conta-segundo-fator">
      <h2 id="conta-segundo-fator">Segundo fator</h2>
      <dl className="lado__lista">
        <Item nome="Aplicativo">Ligado. O código é pedido a cada entrada.</Item>
        <Item nome="Códigos de recuperação">
          {String(restantes)} de {String(REGRAS_DA_CONTA.codigosDeRecuperacao)} válidos. Cada um vale uma vez; o usado é trocado por um novo, mostrado na hora de entrar.
        </Item>
      </dl>
      {restantes <= AVISO_DE_CODIGOS && (
        <p className="conta__aviso" role="note">
          Restam poucos códigos de recuperação. Guarde bem os que restam e mantenha o aplicativo autenticador à mão.
        </p>
      )}
    </section>
  );
}

function Avisos({ eventos }: { eventos: readonly Evento[] }) {
  return (
    <section className="conta__secao" aria-labelledby="conta-avisos">
      <h2 id="conta-avisos">Avisos de segurança</h2>
      {eventos.length === 0 ? (
        <p className="campo__ajuda">Nenhum aviso.</p>
      ) : (
        <ul className="conta__eventos">
          {eventos.map((e, i) => (
            // A API não dá id ao evento; tipo, momento e posição bastam (a lista não muda de ordem na tela).
            <li key={`${e.tipo}-${e.em}-${String(i)}`}>
              <span>{NOME_DO_EVENTO[e.tipo]}</span>
              <span className="campo__ajuda">{instante(e.em)}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export const FRASE_ARQUIVO_BAIXADO = 'O arquivo foi baixado. Guarde-o num lugar seguro: ele tem os seus dados.';

/**
 * Baixar os seus dados (C3b, etapa 5): o JSON do POST /conta/dados, salvo com o nome que a API manda. A senha é
 * pedida de novo (o arquivo tem dados pessoais) e some do campo depois do envio, dê certo ou não.
 */
function BaixarDados({ email }: { email: string }) {
  const sessao = useSessao();
  const [aberto, setAberto] = useState(false);
  const [senha, setSenha] = useState('');
  const [erro, setErro] = useState<string | null>(null);
  const [falha, setFalha] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  const espera = useEspera();
  const refSenha = useRef<HTMLInputElement>(null);
  const refAbrir = useRef<HTMLButtonElement>(null);

  const fechar = () => {
    setAberto(false);
    setSenha('');
    setErro(null);
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
    const novo = conferirSenhaAtual(senha);
    setErro(novo);
    if (novo !== null) {
      setFalha(null);
      refSenha.current?.focus();
      return;
    }
    setEnviando(true);
    setFalha(null);
    try {
      const arquivo = await sessao.conta.baixarDados(sessao.api, senha);
      baixarTexto(arquivo.nome, arquivo.texto, 'application/json;charset=utf-8');
      setSenha('');
      setAberto(false);
      setAviso(FRASE_ARQUIVO_BAIXADO);
      setEnviando(false);
      setTimeout(() => {
        refAbrir.current?.focus();
      }, 0);
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
    <section className="conta__secao" aria-labelledby="conta-baixar">
      <h2 id="conta-baixar">Baixar os seus dados</h2>
      <p>
        Um arquivo JSON com os dados da conta e os das empresas da sua organização, como o ContaAI os guarda. O próprio
        arquivo diz o que fica de fora, como a senha e o segredo do segundo fator.
      </p>
      {aberto ? (
        <form className="formulario" noValidate onSubmit={(e) => void enviar(e)}>
          <AvisoDeFalha texto={falha} />
          <input type="email" name="email" autoComplete="username" value={email} readOnly hidden />
          <CampoSenha
            ref={refSenha}
            rotulo="Senha"
            name="senha"
            autoComplete="current-password"
            value={senha}
            erro={erro}
            ajuda="A senha de novo: o arquivo tem os seus dados."
            onChange={(e) => {
              setSenha(e.target.value);
              setErro(null);
            }}
          />
          <p className="conta__acoes">
            <button type="submit" className="botao-principal" disabled={enviando || espera.aguardando}>
              {rotuloDoEnvio(enviando, espera.restanteMs, 'Preparando…', 'Baixar o arquivo')}
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
              setAviso(null);
              setTimeout(() => {
                refSenha.current?.focus();
              }, 0);
            }}
          >
            Baixar os seus dados…
          </button>
        </p>
      )}
      <p className="campo__ajuda" role="status">
        {aviso}
      </p>
    </section>
  );
}

function Sessao({ conta }: { conta: DadosDaConta }) {
  const sessao = useSessao();
  const { sair, saindo, erro } = useSair();
  const [saindoDeTodos, setSaindoDeTodos] = useState(false);
  const [erroDeTodos, setErroDeTodos] = useState<string | null>(null);

  const sairDeTodos = async () => {
    setSaindoDeTodos(true);
    setErroDeTodos(null);
    try {
      await sessao.conta.sairDeTodos(sessao.api);
      navegar('/', { substituir: true });
    } catch {
      setErroDeTodos(FRASE_SAIR_FALHOU);
      setSaindoDeTodos(false);
    }
  };

  const ocupado = saindo || saindoDeTodos;
  return (
    <aside className="cadastro__lado" aria-labelledby="conta-sessao">
      <h2 id="conta-sessao">Sessão</h2>
      <p className="campo__ajuda">
        Termina em {instante(conta.sessaoExpiraEm)}, ou antes, com{' '}
        {REGRAS_DA_CONTA.sessaoOciosaMin} minutos sem uso.
      </p>
      <p className="conta__acoes">
        <button type="button" className="botao-secundario" disabled={ocupado} onClick={() => void sair()}>
          {saindo ? 'Saindo…' : 'Sair'}
        </button>
        <button type="button" className="botao-secundario" disabled={ocupado} onClick={() => void sairDeTodos()}>
          {saindoDeTodos ? 'Saindo…' : 'Sair de todos os aparelhos'}
        </button>
      </p>
      <p className="campo__ajuda">“Sair de todos os aparelhos” encerra as sessões em todos os navegadores, inclusive este.</p>
      <AvisoDeFalha texto={erro ?? erroDeTodos} />
    </aside>
  );
}

function ExcluirConta({ email, aoExcluir }: { email: string; aoExcluir: () => void }) {
  const sessao = useSessao();
  const [aberto, setAberto] = useState(false);
  const [senha, setSenha] = useState('');
  const [entendi, setEntendi] = useState(false);
  const [erros, setErros] = useState<{ senha: string | null; entendi: string | null }>({ senha: null, entendi: null });
  const [falha, setFalha] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  const espera = useEspera();
  const refSenha = useRef<HTMLInputElement>(null);
  const refEntendi = useRef<HTMLInputElement>(null);
  const refAbrir = useRef<HTMLButtonElement>(null);

  const fechar = () => {
    setAberto(false);
    setSenha('');
    setEntendi(false);
    setErros({ senha: null, entendi: null });
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
    const novos = { senha: conferirSenhaAtual(senha), entendi: entendi ? null : FRASE_DA_CONFIRMACAO };
    setErros(novos);
    if (novos.senha !== null || novos.entendi !== null) {
      setFalha(null);
      (novos.senha === null ? refEntendi : refSenha).current?.focus();
      return;
    }
    setEnviando(true);
    setFalha(null);
    try {
      await sessao.conta.excluir(sessao.api, senha);
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
    <section className="conta__secao conta__perigo" aria-labelledby="conta-excluir">
      <h2 id="conta-excluir">Excluir a conta</h2>
      <p>
        A exclusão apaga a conta na hora. Se você for a única pessoa da organização, a organização e os dados dela são
        apagados junto. Se houver outros membros e você for o único dono, passe a posse a um deles antes.
      </p>
      {aberto ? (
        <form className="formulario" noValidate onSubmit={(e) => void enviar(e)}>
          <AvisoDeFalha texto={falha} />
          {/* O e-mail da conta, oculto: o gerenciador de senhas sabe de qual conta é a senha (recomendação que o
              próprio Chrome mostra para formulário de senha sem usuário). Não é enviado: o envio é por fetch. */}
          <input type="email" name="email" autoComplete="username" value={email} readOnly hidden />
          <CampoSenha
            ref={refSenha}
            rotulo="Senha"
            name="senha"
            autoComplete="current-password"
            value={senha}
            erro={erros.senha}
            ajuda="A senha de novo, para confirmar que é você."
            onChange={(e) => {
              setSenha(e.target.value);
            }}
          />
          <CaixaDeMarcar
            ref={refEntendi}
            name="entendi"
            checked={entendi}
            erro={erros.entendi}
            onChange={(e) => {
              setEntendi(e.target.checked);
            }}
          >
            Entendo que a exclusão não pode ser desfeita.
          </CaixaDeMarcar>
          <p className="conta__acoes">
            <button type="submit" className="botao-perigo" disabled={enviando || espera.aguardando}>
              {rotuloDoEnvio(enviando, espera.restanteMs, 'Excluindo…', 'Excluir a conta')}
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
                refSenha.current?.focus();
              }, 0);
            }}
          >
            Excluir a conta…
          </button>
        </p>
      )}
    </section>
  );
}

function ContaExcluida() {
  return (
    <section className="passo porta__curta">
      <TituloDoPasso>A conta foi excluída</TituloDoPasso>
      <p>A sessão terminou neste aparelho. Para usar o ContaAI de novo, crie outra conta.</p>
      <p className="porta__acoes">
        <Link para="/" className="botao-principal">
          Ir à página inicial
        </Link>
      </p>
    </section>
  );
}

function ConteudoDaConta({ aoExcluir }: { aoExcluir: () => void }) {
  const estado = useConta();
  if (estado.tipo !== 'conectada') {
    return null; // a PortaDaConta só mostra este conteúdo a quem entrou
  }
  const { conta } = estado;
  return (
    // A exclusão vem depois da sessão no código: no celular, as colunas empilham, e a zona de perigo fica por último.
    <div className="cadastro conta">
      <div className="cadastro__principal">
        <Dados conta={conta} />
        <SegundoFator conta={conta} />
        <Avisos eventos={conta.eventos} />
        <BaixarDados email={conta.email} />
      </div>
      <Sessao conta={conta} />
      <div className="cadastro__principal">
        <ExcluirConta email={conta.email} aoExcluir={aoExcluir} />
      </div>
    </div>
  );
}

export function Conta() {
  const [excluida, setExcluida] = useState(false);
  return (
    <Pagina titulo={ROTA_DA_CONTA.nome}>
      {excluida ? (
        <ContaExcluida />
      ) : (
        <PortaDaConta exige="conta">
          <ConteudoDaConta
            aoExcluir={() => {
              setExcluida(true);
            }}
          />
        </PortaDaConta>
      )}
    </Pagina>
  );
}
