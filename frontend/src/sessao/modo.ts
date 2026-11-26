// Modo da API (GET /saude):
// - mock: os mocks gerados dos motores, só leitura; as rotas que mudam o estado e os espaços dão 501;
// - real: os motores oficiais; dá para criar espaço de avaliação.

import { chamar, type ClienteApi } from '../api/cliente.ts';
import type { components } from '../api/esquema.gen.ts';
import { ErroApi } from '../api/problema.ts';

export type Saude = components['schemas']['SaudeResposta'];

export type EstadoModo =
  | { tipo: 'carregando' }
  | { tipo: 'pronto'; saude: Saude }
  | { tipo: 'erro'; erro: ErroApi };

type Ouvinte = () => void;

export class SessaoModo {
  private estado: EstadoModo = { tipo: 'carregando' };
  private readonly ouvintes = new Set<Ouvinte>();
  private pedido: Promise<void> | null = null;

  readonly assinar = (ouvinte: Ouvinte): (() => void) => {
    this.ouvintes.add(ouvinte);
    return () => this.ouvintes.delete(ouvinte);
  };

  readonly obter = (): EstadoModo => this.estado;

  /** Espaço de avaliação só existe no modo real (ADR 0010). */
  espacoDisponivel(): boolean {
    return this.estado.tipo === 'pronto' && this.estado.saude.modo === 'real';
  }

  /** Consulta /saude uma vez; chamadas ao mesmo tempo esperam o mesmo pedido. */
  carregar(cliente: ClienteApi): Promise<void> {
    this.pedido ??= this.consultar(cliente).finally(() => {
      this.pedido = null;
    });
    return this.pedido;
  }

  private async consultar(cliente: ClienteApi): Promise<void> {
    if (this.estado.tipo !== 'pronto') {
      this.mudar({ tipo: 'carregando' });
    }
    try {
      const { dados } = await chamar(cliente.GET('/saude'));
      this.mudar({ tipo: 'pronto', saude: dados });
    } catch (erro) {
      this.mudar({ tipo: 'erro', erro: erro instanceof ErroApi ? erro : new ErroApi({ tipo: 'rede', causa: erro }) });
    }
  }

  private mudar(novo: EstadoModo): void {
    this.estado = novo;
    for (const ouvinte of this.ouvintes) {
      ouvinte();
    }
  }
}
