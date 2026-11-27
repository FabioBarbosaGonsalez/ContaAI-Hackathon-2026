// Os passos do segundo fator (C2b, etapa 7; ADR 0016): o QR com o primeiro código, e os códigos de recuperação.
// Criar conta usa os dois; Entrar usa os dois quando a conta ainda está pendente (etapa 8, `etapa: "ativacao"`).
//
// - O segredo, o endereço otpauth:// e os códigos de recuperação só vivem nas props e no estado destes
//   componentes: nada vai ao endereço da página, ao armazenamento do navegador ou ao log. Quando o passo acaba,
//   o componente sai da tela e leva tudo junto (plano v2.1, C2, achado 5).
// - O prazo do passe é contado a partir de quando a resposta chegou, com a duração do backend (PASSE, 5 min),
//   e não pelo `expiraEm` contra o relógio do aparelho: um relógio adiantado ou atrasado mostraria um prazo
//   errado. A diferença é só o tempo da resposta na rede; se o passe vencer antes, a API responde 401 com a
//   frase dela, e a tela a mostra.

import { useEffect, useRef, useState, type SubmitEvent, type ReactNode } from 'react';
import type { Ativacao, Cadastro } from '../sessao/conta.ts';
import { useSessao } from '../sessao/contexto.tsx';
import { Link } from '../shell/navegacao.tsx';
import { QrCode, SegredoParaDigitar } from './QrCode.tsx';
import {
  AvisoDeFalha,
  BotaoCopiar,
  baixarTexto,
  CampoCodigo,
  Contagem,
  falhaDe,
  rotuloDoEnvio,
  useEspera,
  useRestante,
} from './formulario.tsx';
import { REGRAS_DA_CONTA } from './legal.ts';
import { conferirCodigo, normalizarCodigo } from './regrasDeEntrada.ts';
import './conta.css';

/** Quando o passe vence, em ms desde 1970, contado de quando a resposta chegou (ver o topo do arquivo). */
export function prazoDoPasse(recebidoEm: number): number {
  return recebidoEm + REGRAS_DA_CONTA.passeMin * 60_000;
}

/**
 * O título de um passo. Ele recebe o foco quando o passo aparece (menos no primeiro, em que o foco é o da
 * página): quem usa leitor de tela ouve onde está, e o Tab segue dali (WCAG 2.4.3).
 */
export function TituloDoPasso({ children, focar = true }: { children: ReactNode; focar?: boolean }) {
  const ref = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    if (focar) {
      ref.current?.focus({ preventScroll: false });
    }
  }, [focar]);
  return (
    <h2 ref={ref} tabIndex={-1} className="passo__titulo">
      {children}
    </h2>
  );
}

/** "Passo 2 de 3" e os nomes dos passos; o atual leva aria-current="step". */
export function Passos({ nomes, atual }: { nomes: readonly string[]; atual: number }) {
  return (
    <ol className="passos" aria-label="Passos">
      {nomes.map((nome, i) => (
        <li key={nome} aria-current={i === atual ? 'step' : undefined}>
          <span className="passos__numero num">{String(i + 1)}</span> {nome}
        </li>
      ))}
    </ol>
  );
}

interface PropsQr {
  /** O que a API devolveu: o endereço do QR, o segredo e a frase (`aviso`). */
  cadastro: Cadastro;
  /** Quando a resposta chegou (Date.now()), para o prazo do passe. */
  recebidoEm: number;
  /** O e-mail da conta, para a pessoa saber qual conta está no aplicativo. */
  email: string;
  /** O código certo: a conta passa a valer, a sessão começa e chegam os códigos de recuperação. */
  aoAtivar: (ativacao: Ativacao) => void;
  /**
   * Na página Entrar: com o passe vencido, volta ao e-mail e à senha na mesma página (um link para /entrar não
   * sairia do lugar). Sem ele (Criar conta), o passe vencido leva a Entrar.
   */
  aoRecomecar?: () => void;
}

/**
 * Passo 2: o QR (ou o segredo para digitar) e o primeiro código do aplicativo. Com o passe vencido, o QR e o
 * segredo saem da tela (o próximo passe troca o segredo, decisão 1 da C2b) e a página leva a Entrar, que dá um QR
 * novo a quem tem a senha.
 */
export function PassoDoQr({ cadastro, recebidoEm, email, aoAtivar, aoRecomecar }: PropsQr) {
  const sessao = useSessao();
  const [vencido, setVencido] = useState(false);
  const restante = useRestante(prazoDoPasse(recebidoEm), () => {
    setVencido(true);
  });
  const [codigo, setCodigo] = useState('');
  const [erroCodigo, setErroCodigo] = useState<string | null>(null);
  const [falha, setFalha] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  const espera = useEspera();
  const refCodigo = useRef<HTMLInputElement>(null);

  if (vencido) {
    return (
      <section className="passo">
        <TituloDoPasso>O tempo para confirmar acabou</TituloDoPasso>
        <p>Entre com o e-mail e a senha para receber um QR code novo.</p>
        <p className="campo__ajuda">
          Sem confirmação em {String(REGRAS_DA_CONTA.pendenteMin)} min, o cadastro é apagado e o e-mail fica livre.
        </p>
        <p className="porta__acoes">
          {aoRecomecar === undefined ? (
            <Link para="/entrar" className="botao-principal">
              Entrar
            </Link>
          ) : (
            <button type="button" className="botao-principal" onClick={aoRecomecar}>
              Entrar de novo
            </button>
          )}
        </p>
      </section>
    );
  }

  const enviar = async (evento: SubmitEvent<HTMLFormElement>) => {
    evento.preventDefault();
    if (enviando || espera.aguardando) {
      return;
    }
    const erro = conferirCodigo(codigo);
    setErroCodigo(erro);
    if (erro !== null) {
      setFalha(null);
      refCodigo.current?.focus();
      return;
    }
    setEnviando(true);
    setFalha(null);
    try {
      const ativacao = await sessao.conta.ativar(sessao.api, normalizarCodigo(codigo));
      aoAtivar(ativacao);
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

  return (
    <section className="passo">
      <TituloDoPasso>Ligue o aplicativo autenticador</TituloDoPasso>
      <div className="segundo-fator">
        <div className="segundo-fator__qr">
          <QrCode endereco={cadastro.otpauth} />
        </div>
        <div className="segundo-fator__texto">
          <p>{cadastro.aviso}</p>
          <p className="campo__ajuda">
            Conta: <span translate="no">{email}</span>
          </p>
          <div className="segredo__bloco">
            <p className="campo__ajuda">Ou digite o segredo:</p>
            <SegredoParaDigitar segredo={cadastro.segredo} />
            <BotaoCopiar texto={cadastro.segredo} rotulo="Copiar o segredo" />
          </div>
          <form className="formulario" noValidate onSubmit={(e) => void enviar(e)}>
            <AvisoDeFalha texto={falha} />
            <CampoCodigo
              ref={refCodigo}
              name="codigo"
              value={codigo}
              erro={erroCodigo}
              onChange={(e) => {
                setCodigo(e.target.value);
              }}
            />
            {restante !== null && <Contagem restanteMs={restante} rotulo="Vale por mais" />}
            <p>
              <button type="submit" className="botao-principal" disabled={enviando || espera.aguardando}>
                {rotuloDoEnvio(enviando, espera.restanteMs, 'Confirmando…', 'Confirmar o código')}
              </button>
            </p>
          </form>
        </div>
      </div>
    </section>
  );
}

/** O arquivo .txt dos códigos: texto puro, sem nada além do e-mail da conta e dos códigos. */
export function textoDosCodigos(email: string, codigos: readonly string[], geradosEm: Date): string {
  const data = geradosEm.toLocaleDateString('pt-BR');
  return [
    'ContaAI: códigos de recuperação',
    `Conta: ${email}`,
    `Gerados em ${data}`,
    '',
    'Cada código vale uma vez, no lugar do código do aplicativo autenticador.',
    'Guarde este arquivo fora do celular e apague as cópias que não forem precisas.',
    '',
    ...codigos.map((c, i) => `${String(i + 1).padStart(2, ' ')}. ${c}`),
    '',
  ].join('\n');
}

export const ARQUIVO_DOS_CODIGOS = 'contaai-codigos-de-recuperacao.txt';

interface PropsCodigos {
  email: string;
  ativacao: Ativacao;
  /** "Guardei os códigos": a página segue para o app. */
  aoConcluir: () => void;
}

/**
 * Passo 3: os 10 códigos de recuperação, mostrados uma vez só. Copiar, baixar (.txt) e "Guardei os códigos".
 * Fechar ou recarregar a aba neste passo pede confirmação ao navegador (beforeunload): os códigos não voltam.
 */
export function CodigosDeRecuperacao({ email, ativacao, aoConcluir }: PropsCodigos) {
  const { codigosRecuperacao: codigos, aviso } = ativacao;

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
      <TituloDoPasso>Guarde os códigos de recuperação</TituloDoPasso>
      <p>
        Conta criada. {aviso}
      </p>
      {/* role="list": sem o marcador (contador do CSS), o Safari tiraria o papel de lista do <ol>. */}
      {/* eslint-disable-next-line jsx-a11y/no-redundant-roles */}
      <ol className="codigos num" role="list" aria-label="Códigos de recuperação" translate="no">
        {codigos.map((c) => (
          <li key={c}>{c}</li>
        ))}
      </ol>
      <p className="codigos__acoes">
        <BotaoCopiar texto={codigos.join('\n')} rotulo="Copiar os códigos" />
        <button
          type="button"
          className="botao-secundario"
          onClick={() => {
            baixarTexto(ARQUIVO_DOS_CODIGOS, textoDosCodigos(email, codigos, new Date()));
          }}
        >
          Baixar (.txt)
        </button>
      </p>
      <p>
        <button type="button" className="botao-principal" onClick={aoConcluir}>
          Guardei os códigos
        </button>
      </p>
    </section>
  );
}
