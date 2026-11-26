# Crítica das telas do PR 3a (E5-02)

Painel, Catálogo e a explicação lateral, julgados pelas capturas do `inspect.mjs --app` em 1440, 768 e 390 px e pelas perguntas de `references/app-screens.md` §2.7. Dados: modo real, motores RR 1.7.2 e SN 1.0.2, nota 2 da demonstração importada.

## Portão

| Tela | Rodada 1 | Rodada 2 | Rodada 3 |
|---|---|---|---|
| Painel | 0 FAIL, 2 WARN (`panel-void` 329 px nas margens; contraste 4,2:1 no botão desligado) | 0 FAIL, 1 WARN (`panel-void` 155 e 144 px) | 0 FAIL, 0 WARN |
| Catálogo | 0 FAIL, 1 WARN (contraste 4,2:1 no seletor) | 0 FAIL, 0 WARN | — |

`lint.mjs --app frontend/src`: 0 FAIL e 6 WARN, todos defensáveis:
- `mono` (4): todo número em Geist Mono é a cara escolhida no inventário §3;
- `shadow` (1): só o diálogo e a lateral, que flutuam;
- `numbering` (1): o "01" é o código de atividade do Simples num teste.

## As perguntas do §2.7, na última rodada

1. **A pergunta é respondida pelo maior bloco, lido primeiro?** Sim. No Painel, o alerta abre a grade, com a frase do achado e o preço sugerido a 30 px, o maior número da tela. No Catálogo, a frase do achado fica acima da tabela.
2. **Os blocos dividem as bordas?** Sim. A grade de 12 colunas fecha a conta (570 + 12 + 570 = 1152), e não há vão de mais de 40 px dentro de nenhum cartão.
3. **A cor só no dado?** Sim. A única cor de dado é a margem abaixo do alvo, em `--negativo`. O botão principal é quase preto e o cromo é cinza.
4. **Os números fecham?** Sim, nos três casos:
   - a margem da cerveja na lista é a do alerta (11,19%), que vem do mesmo cálculo (teste do backend e `telas.test.tsx`);
   - a carga do achado soma os dois valores exibidos (R$ 32,40 + R$ 0,36 = R$ 32,76);
   - os totais vêm do backend.
5. **Zero é zero e ausente é traço?** Sim. O arroz no híbrido mostra R$ 0,00; a carne sem cálculo mostra traço e o motivo em palavras.
6. **Legendas?** Não há legenda: a barra é a margem, e o traço é o alvo, com nome acessível.
7. **No celular?** A navegação vai para o menu, a tabela do catálogo vira lista de duas linhas, e a faixa do alerta vira lista de rótulo e valor.

## O que ainda fica aquém

- A barra preta e o símbolo de quadrado com "C" foram pedidos pelo usuário (ADR 0013), contra a folha (barra no fundo da página) e contra o §3.2 do capítulo (que desaconselha quadrado preto com letra). O inspetor seguiu em 0 FAIL e 0 WARN nas duas telas depois da troca.
- Sem espaço próprio nem token, o "Aplicar" do Painel aparece desligado na demonstração compartilhada. Ele diz por quê e aponta para "Criar meu espaço". A demonstração em si é só leitura de propósito (ADR 0010).
- A explicação lateral repete as premissas inteiras. Num item simples, isso deixa a lateral longa.
