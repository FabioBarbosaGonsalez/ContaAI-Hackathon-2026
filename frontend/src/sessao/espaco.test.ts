import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  CHAVE_ARMAZENAMENTO_ESPACO,
  SessaoEspaco,
  espacoDaResposta,
  lerEspacoSalvo,
  type Armazenamento,
} from './espaco.ts';

const ID = '0123456789abcdef0123456789abcdef';
const MINUTO = 60_000;

function armazenamentoFalso(inicial: Record<string, string> = {}): Armazenamento & { dados: Map<string, string> } {
  const dados = new Map(Object.entries(inicial));
  return {
    dados,
    getItem: (chave) => dados.get(chave) ?? null,
    setItem: (chave, valor) => {
      dados.set(chave, valor);
    },
    removeItem: (chave) => {
      dados.delete(chave);
    },
  };
}

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date('2026-11-25T12:00:00Z'));
});

afterEach(() => {
  vi.useRealTimers();
});

describe('espacoDaResposta', () => {
  it('conta a validade pela duração do servidor, no relógio local', () => {
    // O relógio do servidor está 3 horas à frente do local: a duração (120 min) é o que vale.
    const resposta = { id: ID, criadoEm: '2026-11-25T15:00:00Z', expiraEm: '2026-11-25T17:00:00Z' };
    expect(espacoDaResposta(resposta, 1_000)).toEqual({ id: ID, expiraEm: 1_000 + 120 * MINUTO });
  });

  it.each([
    ['id fora do padrão', { id: 'ABC', criadoEm: '2026-11-25T15:00:00Z', expiraEm: '2026-11-25T17:00:00Z' }],
    ['id com ../', { id: `../${ID.slice(3)}`, criadoEm: '2026-11-25T15:00:00Z', expiraEm: '2026-11-25T17:00:00Z' }],
    ['data inválida', { id: ID, criadoEm: 'ontem', expiraEm: '2026-11-25T17:00:00Z' }],
    ['vence antes de nascer', { id: ID, criadoEm: '2026-11-25T17:00:00Z', expiraEm: '2026-11-25T15:00:00Z' }],
    ['dura mais de um dia', { id: ID, criadoEm: '2026-11-25T15:00:00Z', expiraEm: '2026-11-27T15:00:00Z' }],
  ])('recusa %s', (_caso, resposta) => {
    expect(espacoDaResposta(resposta, 0)).toBeNull();
  });
});

describe('lerEspacoSalvo', () => {
  it.each([
    ['ausente', null],
    ['JSON quebrado', '{'],
    ['texto', '"abc"'],
    ['sem expiraEm', JSON.stringify({ id: ID })],
    ['id maiúsculo', JSON.stringify({ id: ID.toUpperCase(), expiraEm: 1 })],
    ['id com quebra de linha', JSON.stringify({ id: `${ID}\n`, expiraEm: 1 })],
    ['expiraEm texto', JSON.stringify({ id: ID, expiraEm: '1' })],
  ])('descarta %s', (_caso, texto) => {
    expect(lerEspacoSalvo(texto)).toBeNull();
  });
});

describe('SessaoEspaco', () => {
  it('começa ausente, ativa, grava e esquece', () => {
    const armazenamento = armazenamentoFalso();
    const sessao = new SessaoEspaco({ armazenamento });
    expect(sessao.obter()).toEqual({ tipo: 'ausente' });
    expect(sessao.idAtual()).toBeNull();

    sessao.ativar({ id: ID, expiraEm: Date.now() + 120 * MINUTO });
    expect(sessao.idAtual()).toBe(ID);
    expect(lerEspacoSalvo(armazenamento.getItem(CHAVE_ARMAZENAMENTO_ESPACO))?.id).toBe(ID);

    sessao.esquecer();
    expect(sessao.obter()).toEqual({ tipo: 'ausente' });
    expect(armazenamento.dados.size).toBe(0);
  });

  it('retoma o espaço salvo por outra página', () => {
    const armazenamento = armazenamentoFalso({
      [CHAVE_ARMAZENAMENTO_ESPACO]: JSON.stringify({ id: ID, expiraEm: Date.now() + 30 * MINUTO }),
    });
    expect(new SessaoEspaco({ armazenamento }).idAtual()).toBe(ID);
  });

  it('vence sozinho na hora e avisa quem assina', () => {
    const sessao = new SessaoEspaco({ armazenamento: armazenamentoFalso() });
    const ouvinte = vi.fn();
    sessao.assinar(ouvinte);
    sessao.ativar({ id: ID, expiraEm: Date.now() + 10 * MINUTO });
    expect(ouvinte).toHaveBeenCalledTimes(1);

    vi.advanceTimersByTime(10 * MINUTO - 1);
    expect(sessao.obter().tipo).toBe('ativo');
    vi.advanceTimersByTime(1);
    expect(sessao.obter()).toEqual({ tipo: 'expirado' });
    expect(ouvinte).toHaveBeenCalledTimes(2);
  });

  it('não manda um id vencido mesmo se o relógio do navegador atrasar o aviso', () => {
    const sessao = new SessaoEspaco({ armazenamento: armazenamentoFalso() });
    sessao.ativar({ id: ID, expiraEm: Date.now() + MINUTO });
    // Aba suspensa: a hora andou, mas o timer ainda não disparou.
    vi.setSystemTime(Date.now() + 2 * MINUTO);
    expect(sessao.idAtual()).toBeNull();
    expect(sessao.obter()).toEqual({ tipo: 'expirado' });
  });

  it('apaga o espaço vencido ao abrir', () => {
    const armazenamento = armazenamentoFalso({
      [CHAVE_ARMAZENAMENTO_ESPACO]: JSON.stringify({ id: ID, expiraEm: Date.now() - 1 }),
    });
    const sessao = new SessaoEspaco({ armazenamento });
    expect(sessao.obter()).toEqual({ tipo: 'expirado' });
    expect(armazenamento.dados.size).toBe(0);
  });

  it.each([
    ['fora do formato', '{"id":"x"}'],
    ['validade alterada à mão', JSON.stringify({ id: ID, expiraEm: Date.parse('2027-01-01T00:00:00Z') })],
  ])('descarta e apaga valor salvo %s', (_caso, valor) => {
    const armazenamento = armazenamentoFalso({ [CHAVE_ARMAZENAMENTO_ESPACO]: valor });
    const sessao = new SessaoEspaco({ armazenamento });
    expect(sessao.obter()).toEqual({ tipo: 'ausente' });
    expect(armazenamento.dados.size).toBe(0);
  });

  it('acompanha outra aba que esqueceu o espaço', () => {
    const armazenamento = armazenamentoFalso();
    const sessao = new SessaoEspaco({ armazenamento });
    sessao.ativar({ id: ID, expiraEm: Date.now() + MINUTO });
    armazenamento.dados.clear();
    sessao.recarregar();
    expect(sessao.obter()).toEqual({ tipo: 'ausente' });
  });

  it('funciona sem armazenamento (navegação privada), só na memória', () => {
    const quebrado: Armazenamento = {
      getItem: () => {
        throw new Error('bloqueado');
      },
      setItem: () => {
        throw new Error('bloqueado');
      },
      removeItem: () => {
        throw new Error('bloqueado');
      },
    };
    const sessao = new SessaoEspaco({ armazenamento: quebrado });
    sessao.ativar({ id: ID, expiraEm: Date.now() + MINUTO });
    expect(sessao.idAtual()).toBe(ID);
  });
});
