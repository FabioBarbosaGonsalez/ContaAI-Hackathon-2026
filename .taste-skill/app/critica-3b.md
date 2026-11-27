# Crítica das telas do PR 3b (E5)

Notas e Regime, julgados pelas capturas do `inspect.mjs --app` em 1440, 768 e 390 px e pelas perguntas de `references/app-screens.md` §2.7. Dados: modo real, motores RR 1.7.2 e SN 1.0.2.

O inspetor abre a tela sem espaço, na demonstração compartilhada (só a nota 1). O recibo só existe depois de importar, e o inspetor não importa. Por isso, um roteiro de CDP (a biblioteca do próprio inspetor) cria o espaço pela tela, escolhe o XML da nota 2, importa, aplica o preço e mede o recibo e o Regime com as mesmas regras (`judge`, `judgeLayout` e `judgeApp`).

## Portão

As rodadas na ordem em que aconteceram:

| Rodada | O que mudou antes dela | Resultado |
|---|---|---|
| 1 | Primeira versão | Regime (compartilhada): 0 FAIL, 1 WARN (`panel-void` de 81 px no caixa). Notas (compartilhada): 0 FAIL, 2 WARN (`hero-void`; `panel-void` de 107 px na lista) |
| 2 | Caixa e lista com `align-self: start`; subtextos em palavras na fonte do texto | Recibo (espaço): 0 FAIL, 1 WARN (`numeric-align` em 390 px). Regime (espaço): 0 FAIL, 1 WARN (`ragged-row` de 81 px): sem esticar, o caixa terminava antes da régua |
| 3 | Caixa volta a esticar, com a diferença de caixa (o total) no pé; no celular, cada valor das tabelas do 3b numa linha, com o número à direita | Recibo: 0 WARN. Regime (compartilhada e espaço): `panel-void` de 94 px no caixa, porque o vão antes do total também conta. Notas: `hero-void` e `ragged-row` de 97 px. Painel (compartilhada, do 3a): `panel-void` de 231 px no cartão do alerta |
| 4 | O caixa ganha as duas barras do tributo do mês (R$ 233,63 no DAS e R$ 359,42 líquido no híbrido, os dois da API); em Notas, o envio e a lista viram faixas na linha inteira | Regime e Notas: 0 FAIL, 0 WARN. Recibo e Regime do espaço: 0 WARN. Painel: segue o `panel-void` de 231 px |
| 5 | No Painel sem alerta aberto, a resposta vai para o topo do bloco das margens, na linha inteira (ADR 0014) | Painel e Catálogo: 0 FAIL, 0 WARN |
| 6 | O achado do recibo junta o custo e a margem do mesmo item numa frase; o link do recibo na cor do texto | Painel, Catálogo, Regime e Notas: 0 FAIL, 0 WARN. Recibo: 0 FAIL, 1 WARN (`mono` em 390 px). Regime do espaço: 0 WARN |

`lint.mjs --app frontend/src`: 0 FAIL e 5 WARN, os mesmos do 3a (`mono` 4 e o "01" de um teste).

O WARN `mono` do recibo em 390 px (16% do texto) vem da cara escolhida no inventário §3: todo número em Geist Mono. O recibo é a tela com mais números por linha (quantidade, dois custos, variação e crédito).

## As perguntas do §2.7, na última rodada

1. **A pergunta é respondida pelo maior bloco, lido primeiro?** Sim.
   - Em Notas, o recibo abre a página com o achado em 20 px: o custo que subiu e a margem que caiu, na mesma frase.
   - No Regime, a régua abre a grade, com o achado acima dela.
2. **Os blocos dividem as bordas?** Sim. No Regime, (7 × 85 + 6 × 12) + 12 + (5 × 85 + 4 × 12) = 667 + 12 + 473 = 1152. Em Notas, três faixas na linha inteira. Não há vão de mais de 40 px dentro de nenhum cartão.
3. **A cor só no dado?** Sim.
   - O matiz (`#1d5fbf`) está só no crédito que o cliente leva: os dois segmentos da régua, o quadrado ao lado do rótulo e o valor.
   - A margem abaixo do alvo segue em `--negativo`.
   - As barras do tributo ficam em tinta, sem cor, porque o tributo não é o dado principal da tela.
4. **Os números fecham?** Sim. A tela não refaz conta nenhuma:
   - custo líquido + crédito = preço ao cliente, nos dois lados (19.665,02 + 233,63 = 19.898,65 e 18.272,42 + 1.626,26 = 19.898,68);
   - débito − crédito das compras = tributo líquido (1.626,26 − 1.266,84 = 359,42);
   - diferença de caixa = tributo no DAS − tributo líquido (233,63 − 359,42 = −125,79);
   - os R$ 0,03 entre os dois preços ao cliente vêm do arredondamento da base de cada linha, e a tela diz isso embaixo da barra;
   - os totais da venda por item são os dos lados da resposta.
5. **Zero é zero e ausente é traço?** Sim. Uma variação de 0,00% aparece como 0,00%, e um crédito ausente aparece como traço.
6. **Legendas?** A régua não tem legenda separada. Cada barra tem o nome, o preço e os dois valores logo abaixo, e o rótulo do crédito leva o quadrado do matiz. Cada SVG tem um nome acessível com os três números.
7. **No celular?** A régua empilha com a mesma escala. As tabelas viram listas de rótulo e valor, com os números à direita. O botão "Aplicar" do recibo ocupa a largura toda.

## O que ainda fica aquém

- **Itens sem par:** a tela explica o motivo e pede para conferir o cadastro, mas não há como cadastrar o par nela (C3).
- **A banca precisa de um XML para importar.** As notas fictícias estão no repositório (`data/demo/notas`), mas não na tela (C2). **Resolvido na C2c** (`critica-c2c.md`).
- **O achado do Regime é longo** (cinco linhas em 1440 px). Ele precisa dizer o crédito nos dois regimes, o custo no caixa e que vale para as premissas. Encurtar tiraria uma dessas três coisas.
- **A demonstração compartilhada mostra −R$ 173,90 de diferença de caixa, e não os −R$ 125,79 do plano.** Os R$ 125,79 dependem da nota 2 importada (ADR 0014). A tela mostra a origem do crédito em cada linha ("calculado pelo motor RR"), então a diferença tem explicação na própria tela.
