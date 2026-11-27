// Peças dos formulários da conta (C2b, ADR 0016): Criar conta, Entrar e excluir a conta; e do cadastro da empresa
// (C3a, ADR 0018): a lista de escolha e o grupo de opções.
//
// - Cada campo tem rótulo visível, e a ajuda e o erro ficam ligados ao campo por aria-describedby, para o leitor
//   de tela ler junto (WCAG 1.3.1 e 3.3.1). O campo com erro leva aria-invalid.
// - Os formulários usam noValidate: a conferência é a da tela (regrasDeEntrada.ts), com frases em português, e
//   não o balão do navegador. O backend confere de novo e tem a palavra final.
// - A senha e os códigos ficam fora do corretor ortográfico e da maiúscula automática: com a senha visível
//   (type="text"), o navegador a trataria como texto comum. Por isso spellCheck, autoCorrect e autoCapitalize
//   ficam desligados.
// - Nada impede colar nem o gerenciador de senhas (NIST SP 800-63B-4, §3.1.1.2: SHALL permitir gerenciadores e
//   preenchimento automático; SHOULD permitir colar).
// - O erro da API é mostrado como texto (o React escapa), nunca como HTML (docs/seguranca.md, regras, item 1).

import {
  useEffect,
  useEffectEvent,
  useId,
  useRef,
  useState,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type Ref,
} from 'react';
import { ErroApi } from '../api/problema.ts';
import './conta.css';
import { REGRAS_DA_CONTA } from './legal.ts';

type PropsEntrada = Omit<InputHTMLAttributes<HTMLInputElement>, 'id' | 'aria-describedby' | 'aria-invalid'>;

interface PropsCampo extends PropsEntrada {
  rotulo: string;
  /** Uma frase sobre o campo, sempre visível. */
  ajuda?: ReactNode;
  /** A frase do erro deste campo, ou null. */
  erro?: string | null;
  /** Depois da entrada, na mesma linha (ex.: o botão de mostrar a senha). */
  depois?: ReactNode;
  /** Logo abaixo da entrada, lido junto do campo (ex.: o medidor de força da senha). */
  abaixo?: ReactNode;
  id?: string;
  ref?: Ref<HTMLInputElement>;
}

/** O id que o campo usa, para outra peça (como o botão de mostrar) apontar para ele. */
function useIdDoCampo(id: string | undefined): string {
  const gerado = useId();
  return id ?? `campo-${gerado.replace(/[^a-zA-Z0-9]/gu, '')}`;
}

export function Campo({ rotulo, ajuda, erro = null, depois, abaixo, id, ref, className, ...entrada }: PropsCampo) {
  const idCampo = useIdDoCampo(id);
  const idAbaixo = `${idCampo}-abaixo`;
  const idAjuda = `${idCampo}-ajuda`;
  const idErro = `${idCampo}-erro`;
  const temAbaixo = abaixo !== undefined && abaixo !== null && abaixo !== false;
  const descricao = [temAbaixo ? idAbaixo : null, ajuda === undefined ? null : idAjuda, erro === null ? null : idErro]
    .filter((x) => x !== null)
    .join(' ');
  return (
    <div className="campo campo--formulario">
      <label htmlFor={idCampo}>{rotulo}</label>
      <div className="campo__entrada">
        <input
          {...entrada}
          ref={ref}
          id={idCampo}
          className={className}
          aria-invalid={erro === null ? undefined : true}
          aria-describedby={descricao === '' ? undefined : descricao}
        />
        {depois}
      </div>
      {temAbaixo && <div id={idAbaixo}>{abaixo}</div>}
      {ajuda !== undefined && (
        <p id={idAjuda} className="campo__ajuda">
          {ajuda}
        </p>
      )}
      {erro !== null && (
        <p id={idErro} className="campo__erro">
          {erro}
        </p>
      )}
    </div>
  );
}

/** Desliga o que manda o texto do campo a terceiros ou o altera (corretor, maiúscula automática). */
const SEM_CORRETOR = { spellCheck: false, autoCorrect: 'off', autoCapitalize: 'off' } as const;

interface PropsSenha extends Omit<PropsCampo, 'type' | 'depois' | 'autoComplete'> {
  /** `new-password` no cadastro; `current-password` para entrar e para excluir a conta. */
  autoComplete: 'new-password' | 'current-password';
}

/**
 * Senha com o botão "Mostrar" (aria-pressed), para conferir o que foi digitado. NIST SP 800-63B-4, §3.1.1.2: o
 * verificador SHOULD oferecer a opção de mostrar a senha, em vez de pontos, enquanto ela é digitada.
 */
export function CampoSenha({ id, autoComplete, ...resto }: PropsSenha) {
  const idCampo = useIdDoCampo(id);
  const [visivel, setVisivel] = useState(false);
  return (
    <Campo
      {...resto}
      {...SEM_CORRETOR}
      id={idCampo}
      type={visivel ? 'text' : 'password'}
      autoComplete={autoComplete}
      depois={
        <button
          type="button"
          className="botao-secundario campo__mostrar"
          aria-pressed={visivel}
          aria-controls={idCampo}
          onClick={() => {
            setVisivel((v) => !v);
          }}
        >
          Mostrar
        </button>
      }
    />
  );
}

interface PropsCodigo extends Omit<PropsCampo, 'type' | 'inputMode' | 'autoComplete' | 'rotulo'> {
  rotulo?: string;
}

/** O código de 6 dígitos do aplicativo. `one-time-code` deixa o celular e o gerenciador de senhas o sugerirem. */
export function CampoCodigo({ rotulo = 'Código do aplicativo', ...resto }: PropsCodigo) {
  return (
    <Campo
      {...resto}
      {...SEM_CORRETOR}
      rotulo={rotulo}
      type="text"
      inputMode="numeric"
      autoComplete="one-time-code"
      maxLength={REGRAS_DA_CONTA.digitosDoCodigo + 2}
      className="num campo__codigo"
    />
  );
}

/** Um código de recuperação (13 caracteres, com ou sem os hífens). Não é sugerido pelo navegador. */
export function CampoRecuperacao({ rotulo = 'Código de recuperação', ...resto }: PropsCodigo) {
  return (
    <Campo
      {...resto}
      {...SEM_CORRETOR}
      rotulo={rotulo}
      type="text"
      autoComplete="off"
      maxLength={20}
      className="num campo__recuperacao"
    />
  );
}

/**
 * O que a pessoa lê quando o envio falha, e a espera do 429 (Retry-After), se veio.
 * A frase é a da API (o `detail`), ou a frase fixa do tipo de erro (problema.ts).
 */
export interface Falha {
  texto: string;
  /** Segundos até poder tentar de novo, ou null. */
  esperaS: number | null;
  /** A conta foi bloqueada (100 falhas): só o administrador desbloqueia, e esperar não adianta. */
  bloqueada: boolean;
}

/** O tipo do 429 da conta bloqueada (backend, app/api/problemas.py). As outras esperas são about:blank. */
export const TIPO_CONTA_BLOQUEADA = '/problemas/conta-bloqueada';

/**
 * A conta bloqueada também responde 429 com Retry-After (1 h, para clientes automáticos não insistirem), mas a
 * tela não mostra contagem: "Aguarde 60 min" daria a entender que a conta volta sozinha (plano v2.1, C2b).
 */
export function falhaDe(erro: unknown, frasePadrao = 'Não foi possível concluir. Tente de novo.'): Falha {
  if (!(erro instanceof ErroApi)) {
    return { texto: frasePadrao, esperaS: null, bloqueada: false };
  }
  const bloqueada = erro.status === 429 && erro.problema?.type === TIPO_CONTA_BLOQUEADA;
  const esperaS =
    !bloqueada && erro.status === 429 && erro.retryAfterS !== null && erro.retryAfterS > 0 ? erro.retryAfterS : null;
  return { texto: erro.message, esperaS, bloqueada };
}

/**
 * O aviso do erro do formulário. Ele recebe o foco quando aparece ou muda: quem usa teclado ou leitor de tela
 * fica sabendo na hora, e o Tab segue para o formulário (WCAG 3.3.1). `role="alert"` também o anuncia.
 */
export function AvisoDeFalha({ texto }: { texto: string | null }) {
  const ref = useRef<HTMLParagraphElement>(null);
  useEffect(() => {
    if (texto !== null) {
      ref.current?.focus();
    }
  }, [texto]);
  if (texto === null) {
    return null;
  }
  return (
    <p ref={ref} className="formulario__falha" role="alert" tabIndex={-1}>
      {texto}
    </p>
  );
}

/** "4 min 05 s", "45 s": o tempo que falta, em minutos e segundos. */
export function formatarRestante(restanteMs: number): string {
  const total = Math.max(0, Math.ceil(restanteMs / 1000));
  const minutos = Math.floor(total / 60);
  const segundos = total % 60;
  if (minutos === 0) {
    return `${String(segundos)} s`;
  }
  return `${String(minutos)} min ${String(segundos).padStart(2, '0')} s`;
}

/**
 * Quanto falta até `ate` (em ms desde 1970), atualizado a cada segundo; 0 depois de passar. null sem prazo.
 * `aoVencer` é chamado uma vez, quando o prazo passa.
 */
export function useRestante(ate: number | null, aoVencer?: () => void): number | null {
  const [agora, setAgora] = useState(() => Date.now());
  const vencer = useEffectEvent(() => {
    aoVencer?.();
  });

  useEffect(() => {
    if (ate === null) {
      return undefined;
    }
    let avisado = false;
    // `contar` só roda depois desta função (setTimeout e setInterval), quando `relogio` já existe.
    const contar = () => {
      const instante = Date.now();
      setAgora(instante);
      if (!avisado && instante >= ate) {
        avisado = true;
        clearInterval(relogio);
        vencer();
      }
    };
    // A primeira leitura sai logo (o `agora` guardado pode ser de antes do prazo novo); depois, a cada segundo.
    const primeira = setTimeout(contar, 0);
    const relogio = setInterval(contar, 1000);
    return () => {
      clearTimeout(primeira);
      clearInterval(relogio);
    };
  }, [ate]);

  return ate === null ? null : Math.max(0, ate - agora);
}

/**
 * O tempo do passe (5 min) para a segunda etapa. `role="timer"` não é anunciado a cada segundo; o texto ao lado
 * diz o que acontece no fim.
 */
export function Contagem({ restanteMs, rotulo }: { restanteMs: number; rotulo: string }) {
  return (
    <p className="campo__ajuda contagem">
      {rotulo}{' '}
      <span role="timer" className="num">
        {formatarRestante(restanteMs)}
      </span>
    </p>
  );
}

/**
 * A espera depois de um 429: o botão de enviar fica desligado e diz quanto falta. `iniciar(segundos)` começa a
 * espera; ela termina sozinha.
 */
export function useEspera(): { restanteMs: number | null; aguardando: boolean; iniciar: (segundos: number) => void } {
  const [ate, setAte] = useState<number | null>(null);
  const restanteMs = useRestante(ate, () => {
    setAte(null);
  });
  return {
    restanteMs,
    aguardando: restanteMs !== null && restanteMs > 0,
    iniciar: (segundos: number) => {
      setAte(Date.now() + segundos * 1000);
    },
  };
}

interface PropsCaixa extends Omit<PropsEntrada, 'type' | 'children'> {
  /** O texto ao lado da caixa (o rótulo). */
  children: ReactNode;
  erro?: string | null;
  id?: string;
  ref?: Ref<HTMLInputElement>;
}

/**
 * Uma caixa de marcar com o rótulo ao lado e o erro ligado por aria-describedby (o aceite dos termos). O rótulo
 * não leva link: um link dentro do <label> confunde o clique (marcar ou abrir) e o leitor de tela.
 */
export function CaixaDeMarcar({ children, erro = null, id, ref, ...entrada }: PropsCaixa) {
  const idCampo = useIdDoCampo(id);
  const idErro = `${idCampo}-erro`;
  return (
    <div className="caixa">
      <div className="caixa__linha">
        <input
          {...entrada}
          ref={ref}
          id={idCampo}
          type="checkbox"
          aria-invalid={erro === null ? undefined : true}
          aria-describedby={erro === null ? undefined : idErro}
        />
        <label htmlFor={idCampo}>{children}</label>
      </div>
      {erro !== null && (
        <p id={idErro} className="campo__erro">
          {erro}
        </p>
      )}
    </div>
  );
}

/**
 * Copia um texto para a área de transferência e diz se deu certo (role="status", lido sem tirar o foco do botão).
 * Sem a API (endereço sem HTTPS, permissão negada), a frase pede para selecionar e copiar à mão.
 */
export function BotaoCopiar({ texto, rotulo }: { texto: string; rotulo: string }) {
  const [resultado, setResultado] = useState<'copiado' | 'falhou' | null>(null);
  const copiar = async () => {
    try {
      await navigator.clipboard.writeText(texto);
      setResultado('copiado');
    } catch {
      // Sem navigator.clipboard (contexto inseguro) o acesso lança TypeError, e cai aqui como a permissão negada.
      setResultado('falhou');
    }
  };
  return (
    <span className="copiar">
      <button type="button" className="botao-secundario" onClick={() => void copiar()}>
        {rotulo}
      </button>
      <span role="status" className="copiar__resultado">
        {resultado === 'copiado' && 'Copiado.'}
        {resultado === 'falhou' && 'Não deu para copiar. Selecione o texto e copie.'}
      </span>
    </span>
  );
}

/**
 * Entrega um texto como arquivo para salvar, sem servidor: um Blob na memória, um link `blob:` com `download`,
 * um clique, e o endereço do Blob é revogado logo depois (o arquivo tem os códigos de recuperação).
 */
export function baixarTexto(nomeDoArquivo: string, texto: string): void {
  const url = URL.createObjectURL(new Blob([texto], { type: 'text/plain;charset=utf-8' }));
  const link = document.createElement('a');
  link.href = url;
  link.download = nomeDoArquivo;
  link.rel = 'noopener';
  document.body.append(link);
  try {
    link.click();
  } finally {
    link.remove();
    setTimeout(() => {
      URL.revokeObjectURL(url);
    }, 0);
  }
}

/** O texto do botão de enviar: a espera do 429, o envio em curso ou a ação. */
export function rotuloDoEnvio(enviando: boolean, esperaMs: number | null, durante: string, acao: string): string {
  if (esperaMs !== null && esperaMs > 0) {
    return `Aguarde ${formatarRestante(esperaMs)}`;
  }
  return enviando ? durante : acao;
}

interface PropsLista extends Omit<SelectHTMLAttributes<HTMLSelectElement>, 'id' | 'aria-describedby' | 'aria-invalid'> {
  rotulo: string;
  ajuda?: ReactNode;
  erro?: string | null;
  id?: string;
  ref?: Ref<HTMLSelectElement>;
  children: ReactNode;
}

/** Uma lista de escolha (o `<select>` do navegador), com o rótulo, a ajuda e o erro como os outros campos. */
export function CampoDeLista({ rotulo, ajuda, erro = null, id, ref, children, ...lista }: PropsLista) {
  const idCampo = useIdDoCampo(id);
  const idAjuda = `${idCampo}-ajuda`;
  const idErro = `${idCampo}-erro`;
  const descricao = [ajuda === undefined ? null : idAjuda, erro === null ? null : idErro].filter((x) => x !== null).join(' ');
  return (
    <div className="campo campo--formulario">
      <label htmlFor={idCampo}>{rotulo}</label>
      <select
        {...lista}
        ref={ref}
        id={idCampo}
        className="campo__lista"
        aria-invalid={erro === null ? undefined : true}
        aria-describedby={descricao === '' ? undefined : descricao}
      >
        {children}
      </select>
      {ajuda !== undefined && (
        <p id={idAjuda} className="campo__ajuda">
          {ajuda}
        </p>
      )}
      {erro !== null && (
        <p id={idErro} className="campo__erro">
          {erro}
        </p>
      )}
    </div>
  );
}

export interface Opcao {
  valor: string;
  rotulo: ReactNode;
  /** Uma frase sob o rótulo, lida junto da opção. */
  detalhe?: ReactNode;
}

interface PropsOpcoes {
  legenda: string;
  nome: string;
  opcoes: readonly Opcao[];
  valor: string | null;
  aoEscolher: (valor: string) => void;
  ajuda?: ReactNode;
  erro?: string | null;
  /** A primeira opção recebe o foco quando o envio acusa este grupo. */
  ref?: Ref<HTMLInputElement>;
}

/**
 * Uma escolha entre poucas opções, com a frase de cada uma à vista (rádios num fieldset com a legenda). O erro e a
 * ajuda ficam ligados ao grupo pelo aria-describedby do fieldset.
 */
export function GrupoDeOpcoes({ legenda, nome, opcoes, valor, aoEscolher, ajuda, erro = null, ref }: PropsOpcoes) {
  const base = useIdDoCampo(undefined);
  const idAjuda = `${base}-ajuda`;
  const idErro = `${base}-erro`;
  const descricao = [ajuda === undefined ? null : idAjuda, erro === null ? null : idErro].filter((x) => x !== null).join(' ');
  return (
    <fieldset
      className="opcoes"
      aria-invalid={erro === null ? undefined : true}
      aria-describedby={descricao === '' ? undefined : descricao}
    >
      <legend>{legenda}</legend>
      {ajuda !== undefined && (
        <p id={idAjuda} className="campo__ajuda">
          {ajuda}
        </p>
      )}
      {opcoes.map((opcao, i) => {
        const idOpcao = `${base}-${String(i)}`;
        return (
          <div key={opcao.valor} className="opcoes__opcao">
            <input
              ref={i === 0 ? ref : undefined}
              id={idOpcao}
              type="radio"
              name={nome}
              value={opcao.valor}
              checked={valor === opcao.valor}
              aria-describedby={opcao.detalhe === undefined ? undefined : `${idOpcao}-detalhe`}
              onChange={() => {
                aoEscolher(opcao.valor);
              }}
            />
            <label htmlFor={idOpcao} className="opcoes__texto">
              <span className="opcoes__rotulo">{opcao.rotulo}</span>
              {opcao.detalhe !== undefined && (
                <span id={`${idOpcao}-detalhe`} className="opcoes__detalhe">
                  {opcao.detalhe}
                </span>
              )}
            </label>
          </div>
        );
      })}
      {erro !== null && (
        <p id={idErro} className="campo__erro">
          {erro}
        </p>
      )}
    </fieldset>
  );
}
