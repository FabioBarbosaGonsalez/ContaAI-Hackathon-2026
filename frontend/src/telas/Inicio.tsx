// Página inicial (C2, T3; ADR 0016): o que é o ContaAI, a frase de simulação e o caminho para a demonstração.
//
// - "Explorar a demonstração" é o primeiro botão e não pede cadastro (plano v2.1, decisão 1).
// - Os textos dizem o que as telas fazem com as palavras do inventário (.taste-skill/app/inventario.md §2) e do
//   README. Nenhum número da demonstração fica escrito aqui: eles vêm da API, nas telas.
// - Criar conta e Entrar (C2b) vêm depois, e só quando as contas existem (modo real) e ninguém entrou.

import { useConta, useContasLigadas, useModo } from '../sessao/ganchos.ts';
import { BotaoDemonstracao, BotaoMinhaConta } from '../shell/demonstracao.tsx';
import { Link } from '../shell/navegacao.tsx';
import { Pagina } from '../shell/Pagina.tsx';
import { DESCRICAO_ESPACO } from '../shell/StatusSessao.tsx';
import './publicas.css';
import './telas.css';

const TELAS = [
  { nome: 'Painel', texto: 'Qual item está perdendo margem e o preço que a recupera.' },
  { nome: 'Catálogo', texto: 'A CBS e o IBS de cada item, no Simples tradicional e no híbrido.' },
  { nome: 'Regime', texto: 'Tradicional ou híbrido para vender a empresas: o crédito do cliente e o caixa.' },
  { nome: 'Notas', texto: 'O que a nota de compra mudou no custo e na margem.' },
] as const;

function ComoGravar() {
  const modo = useModo();
  if (modo.tipo !== 'pronto') {
    return null;
  }
  if (modo.saude.modo === 'mock') {
    return <p>Nesta instalação, a demonstração é só leitura: nada é gravado.</p>;
  }
  return (
    <p>
      A demonstração compartilhada é só para ver. Para mudar preços e importar notas, use “Criar meu espaço”, na
      barra. {DESCRICAO_ESPACO}
    </p>
  );
}

export function Inicio() {
  const conta = useConta();
  const contasLigadas = useContasLigadas();
  const oferecerConta =
    contasLigadas && (conta.tipo === 'anonima' || conta.tipo === 'encerrada' || conta.tipo === 'erro');
  return (
    <Pagina titulo="Preço e margem na reforma tributária">
      <div className="inicio">
        <div className="inicio__texto">
          <p className="inicio__lide">
            Para a pequena empresa do Simples: quanto de CBS, IBS e Imposto Seletivo cada item paga, que preço mantém a
            margem e se vale o Simples híbrido para vender a empresas.
          </p>
          <p>
            As contas vêm das calculadoras oficiais da Receita Federal. De 2027 em diante, as alíquotas são premissas,
            e cada resultado mostra que é simulação.
          </p>
          <div className="inicio__acoes">
            <BotaoDemonstracao className="botao-principal" />
            {conta.tipo === 'conectada' && <BotaoMinhaConta className="botao-secundario" />}
            {oferecerConta && (
              <>
                <Link para="/criar-conta" className="botao-secundario">
                  Criar conta
                </Link>
                <Link para="/entrar" className="botao-secundario">
                  Entrar
                </Link>
              </>
            )}
          </div>
          <p className="texto-suave">A demonstração não pede cadastro e usa uma distribuidora fictícia.</p>
        </div>

        <section className="bloco inicio__telas" aria-labelledby="inicio-telas">
          <h2 id="inicio-telas">O que a demonstração mostra</h2>
          <dl className="inicio__lista">
            {TELAS.map((tela) => (
              <div key={tela.nome} className="inicio__item">
                <dt>{tela.nome}</dt>
                <dd>{tela.texto}</dd>
              </div>
            ))}
          </dl>
          <ComoGravar />
        </section>
      </div>
    </Pagina>
  );
}
