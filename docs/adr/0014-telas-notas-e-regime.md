# ADR 0014: telas de Notas e de Regime (PR 3b)

- Status: aceito
- Data: 2026-11-26
- Etapa: E5 (PR 3b; o 3a está no [ADR 0013](0013-telas-painel-e-catalogo.md), e o 3c vem depois das contas C1 a C3, [plano v2.1](../plano-v2.1.md))
- Código: `frontend/src/telas/Notas.tsx`, `frontend/src/telas/Regime.tsx`, `frontend/src/dados/` (`pedidoDeRegime`, `useNotas`, `useComparacao`, `importarNota`), `frontend/src/teste/fixtures/`, `.taste-skill/app/critica-3b.md`

## Contexto

O 3a entregou o Painel e o Catálogo. Faltavam duas telas da barra (inventário §2):
- **Notas:** "o que mudou no custo com esta nota?";
- **Regime:** "para vender a este cliente, tradicional ou híbrido?".

O `GET /notas` entrou antes, num PR de backend separado (#19, revisão no ADR 0008). O contrato do backend não muda neste PR.

## Decisão

### Notas

- **Envio do XML.**
  - Usa o `conferirArquivoDaNota` que já existia: só `.xml`, não vazio, até 1 MB. Um arquivo recusado aqui não chega à API.
  - O corpo é um `FormData` com o campo `arquivo`. O `openapi-fetch` o envia como está, sem `Content-Type`, e o navegador põe o boundary do multipart.
  - Quem decide é o backend. A tela mostra o `detail` dele como texto: nota repetida com outro conteúdo (409), arquivo que não é NF-e ou destinatário fora das empresas cadastradas (422), 413 e 415. Um corpo de erro fora do formato da RFC 9457 vira a frase fixa do status (ADR 0009).
  - Importar fica desligado sem espaço ou token, e no modo mock, como o "Aplicar" do 3a. O botão diz por quê.
- **O recibo** é o maior bloco e só aparece depois de importar:
  - o achado: o custo que mudou e, na mesma frase, a margem que caiu abaixo do alvo ("O custo de cerveja de malte, lata 350 ml subiu 17,31% (de R$ 2,60 para R$ 3,05), e a margem caiu para 11,19%, abaixo do alvo de 15,00%. Os outros 2 itens ficaram com o mesmo custo.");
  - os itens casados, com o custo antigo e o novo, a variação e o crédito por unidade com as 4 casas que a API manda, e a origem dele ("da nota (grupo IBSCBS)" ou "calculado pelo motor RR");
  - "entrou no histórico, custo mantido" quando a nota é mais antiga que o custo atual (`atualizaCusto`);
  - os itens sem par, com o motivo que a API devolve;
  - "já importada", com o recibo da primeira vez (`jaImportada`);
  - os alertas, com "Aplicar". Um alerta só fecha quando o preço é aplicado (`aplicado_em`). Por isso, quando o alerta do recibo some dos alertas abertos, a tela diz "Preço sugerido já aplicado.";
  - as premissas do recibo.
- **A lista** vem do `GET /notas`, na ordem da API, com as contagens de itens e de alertas.

### Regime

- **A venda** é a compra mensal do cliente empresa do `GET /catalogo` (`clientesB2B[].compraMensal`), ao preço de venda atual e com o custo da última nota de cada item (decisão 7 do plano v2.1). As quantidades são fixas, e o preço não.
  - **Achado ao vivo:** com o preço da cerveja aplicado (R$ 3,97), a venda passa de R$ 19.898,65 para R$ 20.114,65.
- **O crédito por unidade só vai quando veio da nota.**
  - O contrato define `creditoCompraUnitario` como o crédito "lido do grupo IBSCBS da NF-e". Mas o `GET /catalogo` também guarda nesse campo o crédito que o motor calculou para uma nota sem o grupo (`fonteCredito: "motor"`).
  - **Achado:** com a nota 1003 importada, mandar esse crédito fazia a comparação responder `fonteCredito: "nfe"` para o chocolate, cujo crédito não veio de nota nenhuma.
  - Por isso a tela só manda o campo quando `custoAtual.fonteCredito` é `"nfe"`. Sem ele, o backend refaz o crédito no motor e diz que refez. A diferença medida foi de 1 centavo (R$ 255,43 contra R$ 255,44), porque o motor calcula sobre a linha inteira.
  - **O carrinho do 3a segue mandando o crédito guardado.** É assim que a margem refeita pela tela fica igual à do alerta ("um fato, uma variável", `test_tela.py`), e o carrinho não mostra a origem do crédito.
- **Os blocos:**
  - a **régua do crédito** (o elemento-assinatura do inventário §3): duas barras na mesma escala, com o custo líquido do cliente em tinta e o crédito que ele leva no matiz;
  - o **caixa da empresa**, com o tributo de cada regime em duas barras e as contas: débito − crédito das compras = tributo líquido, e a diferença de caixa;
  - a **venda por item**, com a origem do crédito das compras;
  - o **preço de empate** com um concorrente do regime regular;
  - as **premissas e simplificações**, sempre visíveis.
- **A tela não diz qual regime escolher** (plano, seção 10). O achado dá o crédito do cliente em cada regime, o custo no caixa e "Isso vale para as premissas abaixo." Um teste falha se o texto da página trouxer "opte", "recomend" ou "escolha o".
- **Antes de 2027**, a tela explica que a comparação não existe (VSN-015) e não chama a API.
- **Sem cliente empresa**, a tela diz que não há venda para comparar. Com dois ou mais, aparece um seletor.

### O Painel sem alerta (revisão do 3a)

- **Achado:** na demonstração compartilhada (só a nota 1, sem alerta aberto), o cartão do alerta do Painel ficava com uma frase e 231 px vazios ao lado da tabela das margens (`panel-void`). O 3a tinha sido medido com a nota 2 importada.
- Agora, sem alerta aberto, a resposta ("Nenhum item com a margem abaixo do alvo.") fica no topo do bloco das margens, e esse bloco ocupa a linha inteira. Com alerta, nada muda.

## Os números da demonstração dependem da nota 2

O plano v2.1 esperava venda de R$ 19.898,65, diferença de caixa de −R$ 125,79 e empate de R$ 18.489,49. Conferido ao vivo, nos motores RR 1.7.2 e SN 1.0.2:

| Estado | Venda | Diferença de caixa | Empate |
|---|---|---|---|
| Demonstração recém-aberta (só a nota 1, sem o grupo IBSCBS; crédito do motor) | R$ 19.898,65 | −R$ 173,90 | R$ 18.489,49 |
| Com a nota 2 importada (crédito do grupo IBSCBS) | R$ 19.898,65 | −R$ 125,79 | R$ 18.489,49 |

Os números do plano, do inventário e do teste de referência (`test_regime_golden.py`) são os da linha de baixo. Quem abrir a demonstração sem importar a nota 2 vê −R$ 173,90. Não é erro: é outro crédito das compras.

## Verificação

- **Frontend:** 252 testes (eram 214), tsc, ESLint, build, `npm run seguranca` (no build sem endereço local) e `contrato:checar`.
  - As respostas de `src/teste/fixtures/` foram gravadas da API real num espaço de avaliação. Elas não trazem o id do espaço.
  - **Limite do jsdom:** o `Request` do Node não lê o conteúdo de um `File` do jsdom (o corpo do multipart sai vazio, com o nome "blob"). O teste confere o que a tela põe no `FormData` e o `Content-Type` multipart. O envio real foi conferido no Chrome.
- **Portão da skill:** `inspect.mjs --app` com 0 FAIL e 0 WARN em 1440, 768 e 390 px nas quatro telas da barra (Painel, Catálogo, Regime e Notas), na demonstração compartilhada.
  - O recibo e o Regime do espaço, que o inspetor não alcança sozinho, foram medidos com as mesmas regras por um roteiro de CDP que importa a nota pela tela. Deram 0 FAIL e um WARN `mono` no recibo em 390 px, que é a cara escolhida no inventário (todo número em Geist Mono).
  - A crítica está em `.taste-skill/app/critica-3b.md`.
- **Lint da skill:** 0 FAIL e os 5 WARN do 3a (`mono` e um "01" de teste).
- **Chrome com o build e a CSP (Trusted Types):** criar o espaço, escolher o XML, importar, ver o recibo, aplicar o preço, abrir o Regime e o Painel. Resultado: 0 violações de CSP, 0 erros de JS.
- **Teclado:** com Tab, a ordem segue a tela, e todo foco é visível. O campo de arquivo e o botão de importar só entram no Tab quando estão ligados.
- **Leitor de tela:** conferido pela árvore de acessibilidade nos testes (nomes das regiões, das barras da régua e do tributo, `role="status"` e `role="alert"`). Não foi testado com um leitor de tela de verdade (NVDA ou VoiceOver).

## Consequências

- As quatro telas da barra funcionam nos modos mock e real. Contador segue provisória até o 3c.
- O contrato do backend não mudou.

### Em aberto

- **Itens sem par:** a tela mostra o motivo, mas não há rota para casar um item da nota com um do catálogo. Cadastrar o par fica para a C3 (catálogo editável).
- **Notas de exemplo:** a banca precisa de um XML para importar. As notas fictícias estão em `data/demo/notas`. Oferecê-las para baixar na tela fica para a C2, junto da página inicial da demonstração.
- **Recibo de uma nota antiga:** o `GET /notas` traz só o resumo. Rever o recibo inteiro de uma nota já importada exigiria uma rota nova.
