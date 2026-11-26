// Página inicial (C2, T3; ADR 0016): o que é o ContaAI, a frase de simulação e o caminho para a demonstração.
//
// - "Explorar a demonstração" é o primeiro botão e não pede cadastro (plano v2.1, decisão 1).
// - Os textos dizem o que as telas fazem com as palavras do inventário (.taste-skill/app/inventario.md §2) e do
//   README. Nenhum número da demonstração fica escrito aqui: eles vêm da API, nas telas.
// - Entrar e Criar conta entram na C2b.

import { useConta, useModo } from '../sessao/ganchos.ts';
import { BotaoDemonstracao, BotaoMinhaConta } from '../shell/demonstracao.tsx';
import { Pagina } from '../shell/Pagina.tsx';
import { DESCRICAO_ESPACO } from '../shell/StatusSessao.tsx';
import './publicas.css';
import './telas.css';

const TELAS = [
  { nome: 'Painel', texto: 'Qual item está perdendo margem e o preço que a recupera.' },
  { nome: 'Catálogo', texto: 'Quanto de CBS e IBS cada item carrega, no Simples tradicional e no híbrido.' },
  { nome: 'Regime', texto: 'Tradicional ou híbrido para vender a um cliente empresa: o crédito que ele leva e o custo no caixa.' },
  { nome: 'Notas', texto: 'O que mudou no custo e na margem quando chega uma nota de compra.' },
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
      A demonstração compartilhada é igual para todos e só serve para ver. Para mudar preços e importar notas, crie
      o seu espaço na barra da demonstração. {DESCRICAO_ESPACO}
    </p>
  );
}

export function Inicio() {
  const conta = useConta();
  return (
    <Pagina titulo="Preço e margem na reforma tributária">
      <div className="inicio">
        <div className="inicio__texto">
          <p className="inicio__lide">
            O ContaAI mostra à pequena empresa do Simples quanto de CBS, IBS e Imposto Seletivo incide em cada item,
            que preço mantém a margem, se vale ir para o Simples híbrido para vender a empresas e o que mudou quando
            chega uma nota de compra.
          </p>
          <p>
            Toda conta vem das calculadoras oficiais da Receita Federal. De 2027 em diante, as alíquotas são
            premissas, e cada resultado mostra que é simulação.
          </p>
          <div className="inicio__acoes">
            <BotaoDemonstracao className="botao-principal" />
            {conta.tipo === 'conectada' && <BotaoMinhaConta className="botao-secundario" />}
          </div>
          <p className="texto-suave">
            Sem cadastro. A demonstração usa uma distribuidora fictícia, com catálogo, notas de compra e um cliente
            empresa.
          </p>
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
