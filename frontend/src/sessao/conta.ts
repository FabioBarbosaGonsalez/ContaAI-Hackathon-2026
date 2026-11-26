// A conta de quem entrou (C1 e C2, ADR 0015 e ADR 0016).
//
// - A sessão é um cookie HttpOnly: o JavaScript não o lê. A tela só sabe se há conta pelo GET /conta, que ela
//   pede ao abrir, e só no modo real (no modo mock, as rotas de conta respondem 501).
// - Nada da conta vai ao localStorage, ao sessionStorage ou ao endereço da página. Recarregar pede o GET /conta
//   de novo.
// - Quem tem conta também pode ver a demonstração compartilhada, como todo mundo (plano v2.1, C2, decisão 2).
//   Nesse caso, os pedidos de dados saem sem o cookie (`credentials: 'omit'`, no middleware da sessão), e a API
//   responde como a quem não tem conta.

import { chamar, type ClienteApi } from '../api/cliente.ts';
import type { components } from '../api/esquema.gen.ts';
import { ErroApi } from '../api/problema.ts';
import type { SessaoModo } from './modo.ts';

export type Conta = components['schemas']['ContaResposta'];

export type EstadoConta =
  /** Sem contas: modo mock, ou a API ainda não respondeu ao /saude. */
  | { tipo: 'desligada' }
  | { tipo: 'carregando' }
  /** Ninguém entrou neste navegador. */
  | { tipo: 'anonima' }
  /** `naDemo`: a pessoa escolheu ver a demonstração; a conta continua aberta. */
  | { tipo: 'conectada'; conta: Conta; naDemo: boolean }
  /** A pessoa tinha entrado, e a API respondeu 401: a sessão venceu ou foi encerrada em outro aparelho. */
  | { tipo: 'encerrada' }
  /** O GET /conta falhou por outro motivo (rede, 5xx). A tela segue como quem não tem conta. */
  | { tipo: 'erro'; erro: ErroApi };

type Ouvinte = () => void;

export class SessaoConta {
  private estado: EstadoConta = { tipo: 'desligada' };
  private readonly ouvintes = new Set<Ouvinte>();
  private pedido: Promise<void> | null = null;

  readonly assinar = (ouvinte: Ouvinte): (() => void) => {
    this.ouvintes.add(ouvinte);
    return () => this.ouvintes.delete(ouvinte);
  };

  readonly obter = (): EstadoConta => this.estado;

  /** A tela mostra os dados da conta (e não os da demonstração): os pedidos levam o cookie e nenhum espaço. */
  naConta(): boolean {
    return this.estado.tipo === 'conectada' && !this.estado.naDemo;
  }

  /**
   * Antes do /saude: a tela ainda não sabe se há conta, e nenhum dado é pedido até saber (useOrigemDosDados).
   * Sem isso, os pedidos da demonstração sairiam no intervalo entre o /saude e o /conta.
   */
  aguardar(): void {
    if (this.estado.tipo !== 'conectada' && this.estado.tipo !== 'carregando') {
      this.mudar({ tipo: 'carregando' });
    }
  }

  /**
   * Pergunta à API quem entrou (GET /conta). Só no modo real; fora dele, as contas ficam desligadas.
   * Chamadas ao mesmo tempo esperam o mesmo pedido.
   */
  carregar(cliente: ClienteApi, modo: SessaoModo): Promise<void> {
    if (!modo.espacoDisponivel()) {
      this.mudar({ tipo: 'desligada' });
      return Promise.resolve();
    }
    this.pedido ??= this.consultar(cliente).finally(() => {
      this.pedido = null;
    });
    return this.pedido;
  }

  private async consultar(cliente: ClienteApi): Promise<void> {
    const anterior = this.estado;
    if (anterior.tipo !== 'conectada') {
      this.mudar({ tipo: 'carregando' });
    }
    try {
      const { dados } = await chamar(cliente.GET('/conta'));
      this.mudar({ tipo: 'conectada', conta: dados, naDemo: anterior.tipo === 'conectada' && anterior.naDemo });
    } catch (erro) {
      if (erro instanceof ErroApi && erro.status === 401) {
        this.mudar(anterior.tipo === 'conectada' ? { tipo: 'encerrada' } : { tipo: 'anonima' });
        return;
      }
      this.mudar({ tipo: 'erro', erro: erro instanceof ErroApi ? erro : new ErroApi({ tipo: 'rede', causa: erro }) });
    }
  }

  /** A API respondeu 401 a um pedido com o cookie: a sessão acabou. Só muda quem estava conectado. */
  marcarEncerrada(): void {
    if (this.estado.tipo === 'conectada') {
      this.mudar({ tipo: 'encerrada' });
    }
  }

  /** "Sua sessão terminou" foi lido: a tela segue como quem não tem conta. */
  dispensarAviso(): void {
    if (this.estado.tipo === 'encerrada') {
      this.mudar({ tipo: 'anonima' });
    }
  }

  /** Quem tem conta passa a ver a demonstração (sem o cookie nos pedidos de dados). */
  verDemonstracao(): void {
    if (this.estado.tipo === 'conectada' && !this.estado.naDemo) {
      this.mudar({ ...this.estado, naDemo: true });
    }
  }

  /** Volta da demonstração para os dados da conta. */
  voltarParaConta(): void {
    if (this.estado.tipo === 'conectada' && this.estado.naDemo) {
      this.mudar({ ...this.estado, naDemo: false });
    }
  }

  private mudar(novo: EstadoConta): void {
    this.estado = novo;
    for (const ouvinte of this.ouvintes) {
      ouvinte();
    }
  }
}
