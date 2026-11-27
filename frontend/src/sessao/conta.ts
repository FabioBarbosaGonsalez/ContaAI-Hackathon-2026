// A conta de quem entrou (C1 e C2, ADR 0015 e ADR 0016).
//
// - A sessão é um cookie HttpOnly: o JavaScript não o lê. A tela só sabe se há conta pelo GET /conta, que ela
//   pede ao abrir, e só no modo real (no modo mock, as rotas de conta respondem 501).
// - Nada da conta vai ao localStorage, ao sessionStorage ou ao endereço da página. Recarregar pede o GET /conta
//   de novo.
// - Quem tem conta também pode ver a demonstração compartilhada, como todo mundo (plano v2.1, C2, decisão 2).
//   Nesse caso, os pedidos de dados saem sem o cookie (`credentials: 'omit'`, no middleware da sessão), e a API
//   responde como a quem não tem conta.
// - As ações (cadastrar, ativar, entrar, código, sair, sair de todos e excluir, C2b) só mudam o estado da conta.
//   O segredo do segundo fator e os códigos de recuperação voltam a quem chamou e não ficam aqui: o componente
//   os guarda na memória dele, e eles somem quando a pessoa sai do passo (plano v2.1, C2b, etapa 4).

import { chamar, type ClienteApi } from '../api/cliente.ts';
import type { components } from '../api/esquema.gen.ts';
import { ErroApi } from '../api/problema.ts';
import type { SessaoModo } from './modo.ts';

export type Conta = components['schemas']['ContaResposta'];
export type DadosDoCadastro = components['schemas']['CadastroRequisicao'];
export type Cadastro = components['schemas']['CadastroResposta'];
export type DadosDaEntrada = components['schemas']['EntrarRequisicao'];
export type SegundaEtapa = { codigo: string } | { codigoRecuperacao: string };

/** Depois da senha certa: o código, ou (conta pendente) o QR de novo, com o mesmo formato do cadastro. */
export type ProximoPasso = { etapa: 'codigo'; expiraEm: string } | { etapa: 'ativacao'; cadastro: Cadastro };

/** O que a ativação devolve além da conta: os 10 códigos de recuperação, mostrados uma vez só. */
export interface Ativacao {
  codigosRecuperacao: string[];
  aviso: string;
}

/** Com um código de recuperação, o código novo que entra no lugar dele (mostrado uma vez só). */
export interface Entrada {
  novoCodigoRecuperacao: string | null;
  aviso: string | null;
}

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
  /**
   * Sobe a cada ação que muda a conta (entrar, sair...). Um GET /conta que saiu antes e chega depois da ação não
   * desfaz o que ela fez: a resposta é descartada.
   */
  private versao = 0;

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
    const versao = this.versao;
    if (anterior.tipo !== 'conectada') {
      this.mudar({ tipo: 'carregando' });
    }
    try {
      const { dados } = await chamar(cliente.GET('/conta'));
      if (versao !== this.versao) {
        return;
      }
      this.mudar({ tipo: 'conectada', conta: dados, naDemo: anterior.tipo === 'conectada' && anterior.naDemo });
    } catch (erro) {
      if (versao !== this.versao) {
        return;
      }
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

  // ---- Ações da conta (C2b). Todas lançam ErroApi; quem chama mostra a frase (formulario.tsx, falhaDe). ----

  /**
   * Primeiro passo do cadastro (POST /contas): a conta nasce pendente, e o passe da ativação vai no cookie.
   * O estado não muda: só a ativação abre a sessão. 409: e-mail já usado; 422: senha recusada; 429: limite.
   */
  async cadastrar(cliente: ClienteApi, dados: DadosDoCadastro): Promise<Cadastro> {
    const resposta = await chamar(cliente.POST('/contas', { body: dados }));
    return resposta.dados;
  }

  /**
   * O primeiro código do aplicativo (POST /contas/ativar): a conta passa a valer e a sessão começa.
   * 401: código errado ou passe vencido (a sessão da tela não muda); 429: espera.
   */
  async ativar(cliente: ClienteApi, codigo: string): Promise<Ativacao> {
    const { dados } = await chamar(cliente.POST('/contas/ativar', { body: { codigo } }));
    this.abrir(dados.conta);
    return { codigosRecuperacao: dados.codigosRecuperacao, aviso: dados.aviso };
  }

  /**
   * Primeira etapa da entrada (POST /sessoes): e-mail e senha. Certos, o passe vai no cookie, e a resposta diz o
   * próximo passo:
   * - `codigo`: falta o código (confirmarCodigo);
   * - `ativacao`: a conta ainda não confirmou o primeiro código. Vem um segredo novo para o QR, e o próximo passo
   *   é `ativar`, como no cadastro (plano v2.1, C2b, decisão 1). O segredo volta a quem chamou e não fica aqui.
   * O estado não muda. 401: algum dos dois errado (a frase não diz qual); 429: espera ou bloqueio.
   */
  async entrar(cliente: ClienteApi, dados: DadosDaEntrada): Promise<ProximoPasso> {
    const { dados: resposta } = await chamar(cliente.POST('/sessoes', { body: dados }));
    if (resposta.etapa === 'ativacao') {
      const { otpauth, segredo, expiraEm, aviso } = resposta;
      return { etapa: 'ativacao', cadastro: { otpauth, segredo, expiraEm, aviso } };
    }
    return { etapa: 'codigo', expiraEm: resposta.expiraEm };
  }

  /**
   * Segunda etapa (POST /sessoes/codigo): o código do aplicativo ou um de recuperação. Certo, a sessão começa.
   * 401: código errado ou passe vencido; 429: espera.
   */
  async confirmarCodigo(cliente: ClienteApi, segunda: SegundaEtapa): Promise<Entrada> {
    const { dados } = await chamar(cliente.POST('/sessoes/codigo', { body: segunda }));
    this.abrir(dados.conta);
    return { novoCodigoRecuperacao: dados.novoCodigoRecuperacao ?? null, aviso: dados.aviso ?? null };
  }

  /**
   * Sai neste aparelho (DELETE /sessoes/atual): a API apaga a sessão no servidor e o cookie. Se o pedido falha
   * (rede, 5xx), a sessão pode continuar aberta no servidor: o estado não muda, e o erro sobe.
   */
  async sair(cliente: ClienteApi): Promise<void> {
    await chamar(cliente.DELETE('/sessoes/atual'));
    this.fechar();
  }

  /**
   * Sai em todos os aparelhos (DELETE /sessoes). O 401 quer dizer que a sessão já tinha acabado: o resultado é o
   * mesmo, e a tela segue como quem saiu.
   */
  async sairDeTodos(cliente: ClienteApi): Promise<void> {
    try {
      await chamar(cliente.DELETE('/sessoes'));
    } catch (erro) {
      if (!(erro instanceof ErroApi && erro.status === 401)) {
        throw erro;
      }
    }
    this.fechar();
  }

  /**
   * Exclui a conta (POST /conta/excluir), com a senha de novo. Na API, o 401 tanto é "senha errada" quanto "sem
   * sessão"; para saber qual, a tela pergunta de novo quem entrou (GET /conta). Sem sessão, o estado vira
   * "encerrada". O erro sobe nos dois casos. 409: a dona precisa passar a posse antes; 429: espera.
   */
  async excluir(cliente: ClienteApi, senha: string): Promise<void> {
    try {
      await chamar(cliente.POST('/conta/excluir', { body: { senha } }));
    } catch (erro) {
      if (erro instanceof ErroApi && erro.status === 401 && this.estado.tipo === 'conectada') {
        await this.consultar(cliente);
      }
      throw erro;
    }
    this.fechar();
  }

  /** A sessão começou: a tela passa a mostrar os dados da conta (e não os da demonstração). */
  private abrir(conta: Conta): void {
    this.versao += 1;
    this.mudar({ tipo: 'conectada', conta, naDemo: false });
  }

  /** A pessoa saiu (ou excluiu a conta): a tela segue como quem não tem conta, sem o aviso de sessão encerrada. */
  private fechar(): void {
    this.versao += 1;
    this.mudar({ tipo: 'anonima' });
  }

  private mudar(novo: EstadoConta): void {
    this.estado = novo;
    for (const ouvinte of this.ouvintes) {
      ouvinte();
    }
  }
}
