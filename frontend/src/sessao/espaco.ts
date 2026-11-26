// Espaço de avaliação do visitante (ADR 0010): uma cópia própria dos dados fictícios, que vence em 120 min.
//
// - O id é a chave do espaço. Fica só no navegador (localStorage) e vai no header X-ContaAI-Espaco, nunca
//   no endereço da página (docs/seguranca.md, regras da interface, item 5).
// - O localStorage, e não o sessionStorage, para que uma segunda aba aberta pela banca use o mesmo espaço.
//   O evento `storage` mantém as abas iguais.
// - A validade é contada no relógio do navegador: a duração que o servidor dá (expiraEm − criadoEm), somada
//   à hora local em que a resposta chegou. Assim, um relógio local adiantado ou atrasado não muda a conta.
// - Um id lido do armazenamento só é aceito se seguir o padrão do contrato (32 hexadecimais).

const CHAVE = 'contaai.espaco';
const PADRAO_ID = /^[0-9a-f]{32}$/;

/** Duração máxima aceita de um espaço: o padrão do backend é 120 min; acima de um dia, é dado inválido. */
const DURACAO_MAXIMA_MS = 24 * 60 * 60 * 1000;

export interface Espaco {
  id: string;
  /** Hora local, em ms desde a época, em que o espaço vence. */
  expiraEm: number;
}

export type EstadoEspaco =
  /** Sem espaço: as telas usam a demonstração compartilhada. */
  | { tipo: 'ausente' }
  | { tipo: 'ativo'; espaco: Espaco }
  /** O espaço venceu, ou a API não o reconhece mais. */
  | { tipo: 'expirado' };

type Ouvinte = () => void;

export interface Armazenamento {
  getItem(chave: string): string | null;
  setItem(chave: string, valor: string): void;
  removeItem(chave: string): void;
}

export interface OpcoesSessaoEspaco {
  armazenamento?: Armazenamento | null;
  agora?: () => number;
}

function armazenamentoPadrao(): Armazenamento | null {
  try {
    return globalThis.localStorage;
  } catch {
    // Navegação privada ou armazenamento bloqueado: o espaço vale só enquanto a página estiver aberta.
    return null;
  }
}

/** Lê um espaço salvo, conferindo o formato. Devolve null para qualquer coisa fora do formato. */
export function lerEspacoSalvo(texto: string | null): Espaco | null {
  if (texto === null) {
    return null;
  }
  let dado: unknown;
  try {
    dado = JSON.parse(texto);
  } catch {
    return null;
  }
  if (typeof dado !== 'object' || dado === null) {
    return null;
  }
  const { id, expiraEm } = dado as Record<string, unknown>;
  if (typeof id !== 'string' || !PADRAO_ID.test(id) || typeof expiraEm !== 'number' || !Number.isFinite(expiraEm)) {
    return null;
  }
  return { id, expiraEm };
}

/**
 * Monta o espaço a partir da resposta de POST /espacos ou GET /espacos/atual.
 * Devolve null se o id ou as datas não seguirem o contrato.
 */
export function espacoDaResposta(
  resposta: { id: string; criadoEm: string; expiraEm: string },
  agoraLocal: number,
): Espaco | null {
  const criado = Date.parse(resposta.criadoEm);
  const expira = Date.parse(resposta.expiraEm);
  const duracao = expira - criado;
  if (!PADRAO_ID.test(resposta.id) || !Number.isFinite(duracao) || duracao <= 0 || duracao > DURACAO_MAXIMA_MS) {
    return null;
  }
  return { id: resposta.id, expiraEm: agoraLocal + duracao };
}

export class SessaoEspaco {
  private estado: EstadoEspaco = { tipo: 'ausente' };
  private readonly ouvintes = new Set<Ouvinte>();
  private readonly armazenamento: Armazenamento | null;
  private readonly agora: () => number;
  private relogio: ReturnType<typeof setTimeout> | undefined;

  constructor(opcoes: OpcoesSessaoEspaco = {}) {
    this.armazenamento = opcoes.armazenamento === undefined ? armazenamentoPadrao() : opcoes.armazenamento;
    this.agora = opcoes.agora ?? Date.now;
    this.carregar();
  }

  /** Para o useSyncExternalStore do React: devolve a função que cancela a inscrição. */
  readonly assinar = (ouvinte: Ouvinte): (() => void) => {
    this.ouvintes.add(ouvinte);
    return () => this.ouvintes.delete(ouvinte);
  };

  readonly obter = (): EstadoEspaco => this.estado;

  /** O id para o header, ou null sem espaço ativo. Um espaço vencido deixa de ir aqui mesmo antes do relógio. */
  idAtual(): string | null {
    if (this.estado.tipo !== 'ativo') {
      return null;
    }
    if (this.estado.espaco.expiraEm <= this.agora()) {
      this.marcarExpirado();
      return null;
    }
    return this.estado.espaco.id;
  }

  /** Guarda o espaço que a API acabou de criar ou confirmar. */
  ativar(espaco: Espaco): void {
    this.gravar(JSON.stringify(espaco));
    this.mudar({ tipo: 'ativo', espaco });
  }

  /** A API não reconhece mais o espaço (404 /problemas/espaco-inexistente). */
  marcarExpirado(): void {
    this.remover();
    this.mudar({ tipo: 'expirado' });
  }

  /** A pessoa saiu do espaço; as telas voltam à demonstração compartilhada. */
  esquecer(): void {
    this.remover();
    this.mudar({ tipo: 'ausente' });
  }

  /** Relê o armazenamento (outra aba mudou o espaço). */
  recarregar(): void {
    this.carregar();
  }

  private carregar(): void {
    const salvo = lerEspacoSalvo(this.ler());
    if (salvo === null) {
      // Um valor fora do formato é apagado, para não ser lido de novo.
      this.remover();
      this.mudar(this.estado.tipo === 'ativo' ? { tipo: 'ausente' } : this.estado);
      return;
    }
    if (salvo.expiraEm <= this.agora()) {
      this.marcarExpirado();
      return;
    }
    if (salvo.expiraEm - this.agora() > DURACAO_MAXIMA_MS) {
      // Validade maior que a de qualquer espaço: valor alterado à mão. Descarta.
      this.remover();
      this.mudar({ tipo: 'ausente' });
      return;
    }
    this.mudar({ tipo: 'ativo', espaco: salvo });
  }

  private mudar(novo: EstadoEspaco): void {
    clearTimeout(this.relogio);
    this.relogio = undefined;
    if (novo.tipo === 'ativo') {
      // O setTimeout aceita até ~24,8 dias; a duração já foi limitada a um dia.
      const falta = Math.max(novo.espaco.expiraEm - this.agora(), 0);
      this.relogio = setTimeout(() => {
        this.marcarExpirado();
      }, falta);
    }
    const mesmo =
      novo.tipo === this.estado.tipo &&
      (novo.tipo !== 'ativo' ||
        (this.estado.tipo === 'ativo' &&
          this.estado.espaco.id === novo.espaco.id &&
          this.estado.espaco.expiraEm === novo.espaco.expiraEm));
    if (mesmo) {
      return;
    }
    this.estado = novo;
    for (const ouvinte of this.ouvintes) {
      ouvinte();
    }
  }

  private ler(): string | null {
    try {
      return this.armazenamento?.getItem(CHAVE) ?? null;
    } catch {
      return null;
    }
  }

  private gravar(valor: string): void {
    try {
      this.armazenamento?.setItem(CHAVE, valor);
    } catch {
      // Cota cheia ou armazenamento bloqueado: o espaço segue valendo nesta página.
    }
  }

  private remover(): void {
    try {
      this.armazenamento?.removeItem(CHAVE);
    } catch {
      // Sem armazenamento, não há o que apagar.
    }
  }
}

export const CHAVE_ARMAZENAMENTO_ESPACO = CHAVE;
