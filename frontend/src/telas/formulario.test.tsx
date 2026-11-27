import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ErroApi } from '../api/problema.ts';
import {
  AvisoDeFalha,
  CaixaDeMarcar,
  Campo,
  CampoCodigo,
  CampoRecuperacao,
  CampoSenha,
  Contagem,
  falhaDe,
  TIPO_CONTA_BLOQUEADA,
  formatarRestante,
  rotuloDoEnvio,
  useEspera,
  useRestante,
} from './formulario.tsx';

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

function problema(
  status: number,
  detail: string | null,
  retryAfterS: number | null = null,
  type = 'about:blank',
): ErroApi {
  return new ErroApi({ tipo: 'resposta', problema: { type, title: 'x', status, detail }, retryAfterS });
}

describe('Campo', () => {
  it('rótulo ligado à entrada; ajuda e erro lidos junto (aria-describedby) e aria-invalid só com erro', () => {
    const { rerender } = render(<Campo rotulo="E-mail" type="email" ajuda="O da sua conta." />);
    const entrada = screen.getByLabelText('E-mail');
    expect(entrada.getAttribute('aria-invalid')).toBeNull();
    expect(entrada.getAttribute('aria-describedby')).toBe(screen.getByText('O da sua conta.').id);

    rerender(<Campo rotulo="E-mail" type="email" ajuda="O da sua conta." erro="Informe o e-mail." />);
    const ids = (screen.getByLabelText('E-mail').getAttribute('aria-describedby') ?? '').split(' ');
    expect(ids).toEqual([screen.getByText('O da sua conta.').id, screen.getByText('Informe o e-mail.').id]);
    expect(screen.getByLabelText('E-mail').getAttribute('aria-invalid')).toBe('true');
  });

  it('sem ajuda nem erro, não aponta para nada', () => {
    render(<Campo rotulo="Organização" />);
    expect(screen.getByLabelText('Organização').getAttribute('aria-describedby')).toBeNull();
  });

  it('dois campos na tela têm ids diferentes', () => {
    render(
      <>
        <Campo rotulo="A" />
        <Campo rotulo="B" />
      </>,
    );
    expect(screen.getByLabelText('A').id).not.toBe(screen.getByLabelText('B').id);
  });

  it('o erro vira texto, nunca HTML', () => {
    render(<Campo rotulo="X" erro="<img src=x onerror=alert(1)>" />);
    expect(screen.getByText('<img src=x onerror=alert(1)>')).toBeDefined();
    expect(document.querySelector('img')).toBeNull();
  });
});

describe('CampoSenha', () => {
  it('começa escondida, "Mostrar" alterna (aria-pressed) e o corretor fica desligado', () => {
    render(<CampoSenha rotulo="Senha" autoComplete="new-password" />);
    const senha = screen.getByLabelText('Senha');
    const mostrar = screen.getByRole('button', { name: 'Mostrar' });
    expect(senha.getAttribute('type')).toBe('password');
    expect(senha.getAttribute('autocomplete')).toBe('new-password');
    expect(mostrar.getAttribute('aria-pressed')).toBe('false');
    expect(mostrar.getAttribute('aria-controls')).toBe(senha.id);
    expect(mostrar.getAttribute('type')).toBe('button'); // não envia o formulário

    fireEvent.click(mostrar);
    expect(senha.getAttribute('type')).toBe('text');
    expect(mostrar.getAttribute('aria-pressed')).toBe('true');
    expect(senha.getAttribute('spellcheck')).toBe('false');
    expect(senha.getAttribute('autocorrect')).toBe('off');
    expect(senha.getAttribute('autocapitalize')).toBe('off');

    fireEvent.click(mostrar);
    expect(senha.getAttribute('type')).toBe('password');
  });

  it('não impede colar', () => {
    render(<CampoSenha rotulo="Senha" autoComplete="current-password" />);
    const senha = screen.getByLabelText('Senha');
    const colar = new Event('paste', { bubbles: true, cancelable: true });
    senha.dispatchEvent(colar);
    expect(colar.defaultPrevented).toBe(false);
    expect(senha.getAttribute('autocomplete')).toBe('current-password');
  });
});

describe('códigos', () => {
  it('do aplicativo: teclado numérico, one-time-code e sem corretor', () => {
    render(<CampoCodigo />);
    const codigo = screen.getByLabelText('Código do aplicativo');
    expect(codigo.getAttribute('inputmode')).toBe('numeric');
    expect(codigo.getAttribute('autocomplete')).toBe('one-time-code');
    expect(codigo.getAttribute('spellcheck')).toBe('false');
    expect(codigo.getAttribute('type')).toBe('text');
  });

  it('de recuperação: o navegador não sugere nem guarda', () => {
    render(<CampoRecuperacao />);
    const codigo = screen.getByLabelText('Código de recuperação');
    expect(codigo.getAttribute('autocomplete')).toBe('off');
    expect(codigo.getAttribute('spellcheck')).toBe('false');
  });
});

describe('falha e aviso', () => {
  it('usa a frase da API; o 429 traz a espera do Retry-After', () => {
    expect(falhaDe(problema(401, 'E-mail, senha ou código incorretos.'))).toEqual({
      texto: 'E-mail, senha ou código incorretos.',
      esperaS: null,
      bloqueada: false,
    });
    expect(falhaDe(problema(429, 'Muitas tentativas erradas.', 30))).toEqual({
      texto: 'Muitas tentativas erradas.',
      esperaS: 30,
      bloqueada: false,
    });
    // Sem Retry-After, ou com 0, não há espera a contar.
    expect(falhaDe(problema(429, 'Muitas tentativas.', 0)).esperaS).toBeNull();
    expect(falhaDe(problema(429, 'Muitas tentativas.')).esperaS).toBeNull();
    // Retry-After em outro status não vira espera.
    expect(falhaDe(problema(503, 'Indisponível.', 10)).esperaS).toBeNull();
  });

  it('a conta bloqueada não vira contagem, mesmo com o Retry-After de 1 h: esperar não adianta', () => {
    const frase = 'Conta bloqueada depois de muitas tentativas erradas. Peça o desbloqueio ao administrador do ContaAI.';
    expect(falhaDe(problema(429, frase, 3600, TIPO_CONTA_BLOQUEADA))).toEqual({
      texto: frase,
      esperaS: null,
      bloqueada: true,
    });
    // O mesmo tipo em outro status não é o bloqueio.
    expect(falhaDe(problema(400, 'x', null, TIPO_CONTA_BLOQUEADA)).bloqueada).toBe(false);
  });

  it('erro de rede tem a frase fixa; erro que não é da API, a frase padrão (nada interno vaza)', () => {
    expect(falhaDe(new ErroApi({ tipo: 'rede' })).texto).toBe(
      'Não foi possível falar com a API. Confira se ela está no ar.',
    );
    expect(falhaDe(new Error('segredo interno')).texto).toBe('Não foi possível concluir. Tente de novo.');
  });

  it('o aviso recebe o foco quando aparece e quando muda, e é anunciado (role="alert")', () => {
    const { rerender } = render(<AvisoDeFalha texto={null} />);
    expect(screen.queryByRole('alert')).toBeNull();
    rerender(<AvisoDeFalha texto="Primeira." />);
    expect(document.activeElement).toBe(screen.getByRole('alert'));
    screen.getByRole('alert').blur();
    rerender(<AvisoDeFalha texto="Segunda." />);
    expect(document.activeElement?.textContent).toBe('Segunda.');
  });
});

describe('contagem', () => {
  it('formata minutos e segundos', () => {
    expect(formatarRestante(300_000)).toBe('5 min 00 s');
    expect(formatarRestante(245_000)).toBe('4 min 05 s');
    expect(formatarRestante(59_001)).toBe('1 min 00 s'); // arredonda para cima: não mostra 0 s antes da hora
    expect(formatarRestante(45_000)).toBe('45 s');
    expect(formatarRestante(0)).toBe('0 s');
    expect(formatarRestante(-5_000)).toBe('0 s');
  });

  it('o tempo fica num role="timer", que não é anunciado a cada segundo', () => {
    render(<Contagem restanteMs={90_000} rotulo="O código vale por mais" />);
    expect(screen.getByRole('timer').textContent).toBe('1 min 30 s');
  });

  function Relogio({ ate, aoVencer }: { ate: number | null; aoVencer: () => void }) {
    const restante = useRestante(ate, aoVencer);
    return <p>{restante === null ? 'sem prazo' : formatarRestante(restante)}</p>;
  }

  it('useRestante conta a cada segundo e avisa uma vez no fim', () => {
    vi.useFakeTimers({ now: 1_000_000 });
    const aoVencer = vi.fn();
    const { rerender } = render(<Relogio ate={null} aoVencer={aoVencer} />);
    expect(screen.getByText('sem prazo')).toBeDefined();

    // O prazo chega depois de a peça existir há um tempo: a primeira leitura não usa a hora velha.
    act(() => {
      vi.advanceTimersByTime(60_000);
    });
    rerender(<Relogio ate={Date.now() + 3_000} aoVencer={aoVencer} />);
    act(() => {
      vi.advanceTimersByTime(0);
    });
    expect(screen.getByText('3 s')).toBeDefined();
    act(() => {
      vi.advanceTimersByTime(1_000);
    });
    expect(screen.getByText('2 s')).toBeDefined();
    act(() => {
      vi.advanceTimersByTime(5_000);
    });
    expect(screen.getByText('0 s')).toBeDefined();
    expect(aoVencer).toHaveBeenCalledTimes(1);
  });

  function Envio() {
    const espera = useEspera();
    return (
      <>
        <button type="button" disabled={espera.aguardando}>
          {espera.aguardando && espera.restanteMs !== null
            ? `Tente de novo em ${formatarRestante(espera.restanteMs)}`
            : 'Entrar'}
        </button>
        <button
          type="button"
          onClick={() => {
            espera.iniciar(2);
          }}
        >
          falhar
        </button>
      </>
    );
  }

  it('useEspera desliga o envio durante o Retry-After e libera sozinha', () => {
    vi.useFakeTimers({ now: 2_000_000 });
    render(<Envio />);
    fireEvent.click(screen.getByRole('button', { name: 'falhar' }));
    act(() => {
      vi.advanceTimersByTime(0);
    });
    const envio = screen.getByRole<HTMLButtonElement>('button', { name: 'Tente de novo em 2 s' });
    expect(envio.disabled).toBe(true);
    act(() => {
      vi.advanceTimersByTime(2_000);
    });
    expect(screen.getByRole<HTMLButtonElement>('button', { name: 'Entrar' }).disabled).toBe(false);
  });
});

describe('CaixaDeMarcar', () => {
  it('rótulo ligado à caixa; o erro lido junto e aria-invalid só com erro', () => {
    const { rerender } = render(<CaixaDeMarcar name="termos">Aceito</CaixaDeMarcar>);
    const caixa = screen.getByRole('checkbox', { name: 'Aceito' });
    expect(caixa.getAttribute('aria-invalid')).toBeNull();
    expect(caixa.getAttribute('aria-describedby')).toBeNull();
    rerender(
      <CaixaDeMarcar name="termos" erro="Marque para seguir.">
        Aceito
      </CaixaDeMarcar>,
    );
    expect(caixa.getAttribute('aria-invalid')).toBe('true');
    expect(caixa.getAttribute('aria-describedby')).toBe(screen.getByText('Marque para seguir.').id);
  });
});

describe('rotuloDoEnvio', () => {
  it('a espera do 429 vem antes do envio em curso e da ação', () => {
    expect(rotuloDoEnvio(false, null, 'Enviando…', 'Enviar')).toBe('Enviar');
    expect(rotuloDoEnvio(true, null, 'Enviando…', 'Enviar')).toBe('Enviando…');
    expect(rotuloDoEnvio(true, 30_000, 'Enviando…', 'Enviar')).toBe('Aguarde 30 s');
    expect(rotuloDoEnvio(false, 0, 'Enviando…', 'Enviar')).toBe('Enviar');
  });
});
