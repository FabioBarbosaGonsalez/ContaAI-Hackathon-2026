// Token da demonstração (ADR 0006 e ADR 0008).
//
// - Só fica na memória da aba: nunca vai ao localStorage, ao sessionStorage, a cookie ou ao endereço da
//   página. Recarregar a página o apaga (docs/seguranca.md, regras da interface, item 4).
// - A tela só pede o token quando a API responde 401, num campo; ele nunca vem de variável VITE_*.
// - Dentro de um espaço de avaliação, só o /chat pede o token (ADR 0010).

type Ouvinte = () => void;

/** O backend não limita o tamanho; 512 caracteres sobra para um token e barra colagem acidental de texto. */
const TAMANHO_MAXIMO = 512;

/** Só caracteres visíveis do ASCII: um header HTTP não aceita quebra de linha nem caractere de controle. */
const FORMATO = /^[\x21-\x7e]+$/;

export class SessaoToken {
  private token: string | null = null;
  private readonly ouvintes = new Set<Ouvinte>();

  readonly assinar = (ouvinte: Ouvinte): (() => void) => {
    this.ouvintes.add(ouvinte);
    return () => this.ouvintes.delete(ouvinte);
  };

  /** Para o React: só diz se há token, sem expor o valor à árvore de componentes. */
  readonly temToken = (): boolean => this.token !== null;

  /** O token para o header, ou null. */
  atual(): string | null {
    return this.token;
  }

  /**
   * Guarda o token digitado. Devolve false, sem guardar, se ele estiver vazio, for longo demais ou tiver
   * caractere que não pode ir num header.
   */
  definir(valor: string): boolean {
    const token = valor.trim();
    if (token.length === 0 || token.length > TAMANHO_MAXIMO || !FORMATO.test(token)) {
      return false;
    }
    this.token = token;
    this.avisar();
    return true;
  }

  /** Apaga o token, por exemplo depois de um 401 com o token errado. */
  limpar(): void {
    if (this.token === null) {
      return;
    }
    this.token = null;
    this.avisar();
  }

  private avisar(): void {
    for (const ouvinte of this.ouvintes) {
      ouvinte();
    }
  }
}
