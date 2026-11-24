# Direção visual do ContaAI (E0-07)

Roteiro de telas de app da skill design-taste-frontend (`references/app-screens.md`, §2.1 a §2.3). A construção das telas é a Etapa 5; este arquivo é o que ela segue. A folha sorteada está em `direction.json` (reimprimir com `node <skill>/scripts/draw.mjs --show`).

## 1. Inventário de dados e tarefas (§2.1)

- **Objetos e campos** (unidades entre parênteses):
  - **Item do catálogo:** descrição, NCM, cClassTrib, CST, IS (classificação), unidade (UN, KG), código do fornecedor, preço de venda (R$/un), margem-alvo (%).
  - **Item calculado:** estado (6 estados dos motores), CBS e IBS (R$), IS (R$), redução (%), alíquota efetiva (%), preço ao cliente (R$), custo efetivo (R$), margem (%), memória de cálculo (texto), erros (código e texto oficial).
  - **NF-e de compra:** número, emissão (data e hora), emitente, itens (código, NCM, quantidade, R$/un, R$ da linha) e, quando houver, o grupo IBSCBS (R$).
  - **Alerta:** item, margem antes e depois (%), alvo (%), preço atual e sugerido (R$/un), nota de origem.
  - **Comparação de regimes:** venda (R$), tributo, crédito do cliente e custo líquido do cliente em cada regime (R$), crédito das compras (R$), diferença de caixa (R$/mês).
  - **Premissas:** nome, valor e fonte, impressas junto de todo resultado simulado.
- **Magnitudes da demonstração** (dos dados em `data/demo/` e dos mocks):
  - 4 itens no catálogo, 2 notas de compra e 1 cliente B2B;
  - venda mensal de R$ 19.901,00;
  - preços de R$ 3,79 (lata) a R$ 39,90 (kg) e margens de 11,19% a 28,97%;
  - CBS/IBS por 100 unidades de R$ 0,00 (arroz no híbrido, redução de 100%) a R$ 53,31 (chocolate no híbrido).
  - Valores pequenos ficam pequenos: R$ 0,05 de IBS é R$ 0,05.
  - O tamanho real do catálogo de uma distribuidora pequena não foi medido; as telas não podem depender de 4 itens.
- **Pessoas:**
  - **Dono(a) da distribuidora:** abre o app quando chega uma nota de compra (algumas vezes por semana) e antes de mexer em preço; usa o computador do escritório, e o celular para ver um alerta.
  - **Contador:** abre o painel com vários CNPJs uma vez por mês, no computador (D1).
- **Tarefas, da mais frequente para a menos:**
  1. Aplicar o preço sugerido depois de uma nota.
  2. Importar a nota de compra.
  3. Confirmar ou corrigir a classificação de um item (REG-011 ou VSN-047).
  4. Decidir o regime para vender a um cliente empresa (opção semestral, em setembro e março, LC 123 art. 13 §10; a janela de 1º a 31 de março de 2027 vale para o semestre de julho a dezembro, segundo o Portal do Simples; ver ADR 0003).
  5. Levar a decisão ao contador.
- **Coisas do próprio produto:**
  - nome e marca ContaAI no topo;
  - o escopo é a empresa (Distribuidora Serra Azul ME, fictícia), que vira um seletor de CNPJ quando o contador usa;
  - o cliente B2B (Mercado Bom Preço, fictício);
  - a NF-e do fornecedor;
  - os produtos, identificados por nome e NCM (não há fotos dos produtos; nada de ilustração no lugar);
  - a frase de simulação no título e o aviso legal no rodapé.

### Onde estão os dados e o que eles garantem

O arquivo de dados das telas é a **API em modo mock** (`backend/app/mocks/*.json`, servida por `uv run uvicorn app.main:app`). Todo valor de tributo veio dos motores oficiais.

As asserções que a skill pede estão nos testes do backend (`backend/tests/test_contrato.py`):
- os totais saem das linhas;
- débito − crédito das compras = tributo líquido;
- diferença de caixa = tributo tradicional − tributo líquido híbrido;
- mesmo preço total nos dois regimes, a menos de centavos.

**Um fato, uma variável.** A margem da cerveja (11,19%) aparece no catálogo e no alerta, e o preço sugerido (R$ 3,97) aparece no alerta e no preço-alvo. Nos mocks, os dois saem do mesmo cálculo e já foram conferidos iguais. Na E5, cada um deve vir de um só campo.

## 2. Uma pergunta e um achado por tela (§2.2)

Valores do cenário de demonstração (simulação de março de 2027, premissas rotuladas). A tela mostra o que a API devolver; os números abaixo são os dos mocks.

### Painel do negócio (overview)
- **Pergunta:** qual item está perdendo margem e o que eu faço?
- **Achado:** a margem da cerveja caiu de 24,12% para 11,19% depois da nota 1002, de 16/03/2027, abaixo do alvo de 15%. Preço sugerido: R$ 3,97.
- **Tarefa mais frequente, a um clique:** "Aplicar R$ 3,97" no próprio alerta (o único botão preto da tela).
- **Blocos**, cada um responde a uma pergunta seguinte:
  - o alerta, que é o maior bloco e vem primeiro;
  - a margem de cada item contra o alvo: uma barra por item com um traço no alvo (`Charts.bullet`); só a que quebra leva cor;
  - a última nota importada, com "Importar nota";
  - pendências de cadastro: "Carne bovina: NCM não combina com a classificação", com "Corrigir".

### Catálogo e impacto (list)
- **Pergunta:** quanto de CBS/IBS cada item carrega e quanto sobra?
- **Achado:** no Simples tradicional, o arroz paga R$ 32,76 de CBS/IBS a cada 100 pacotes; no híbrido, R$ 0,00 (redução de 100% da cesta básica). É o que os motores devolvem; a interpretação fica para o contador (ADR 0001).
- **Tarefa:** trocar a visão entre tradicional e híbrido; editar o preço; corrigir a classificação na linha que precisa.
- **Blocos:**
  - uma tabela com item, classificação, estado em palavras do ofício, CBS, IBS, redução, preço ao cliente e margem;
  - a linha da carne mostra o erro oficial e a ação "Corrigir";
  - números alinhados à direita, ausências como traço.

### Decisão de regime (detail: a venda ao Mercado Bom Preço)
- **Pergunta:** para vender ao Bom Preço, tradicional ou híbrido?
- **Achado:** no híbrido o Mercado Bom Preço leva R$ 714,39 de crédito por mês, contra R$ 233,66 no tradicional; e a distribuidora fica com R$ 100,50 a mais de caixa por mês. Isso vale para estas premissas.
- **Tarefa:** levar ao contador. A tela nunca diz "opte pelo híbrido" (seção 10 do plano).
- **Blocos:**
  - a régua do crédito (elemento-assinatura, seção 3 abaixo), que é o maior bloco;
  - o caixa da empresa: débito − crédito das compras contra o tributo no DAS;
  - premissas e simplificações, sempre visíveis.

### Importar nota (detail: a NF-e)
- **Pergunta:** o que mudou no custo com esta nota?
- **Achado:** cerveja +17,31% (de R$ 2,60 para R$ 3,05) e margem para 11,19%; chocolate sem mudança.
- **Tarefa:** importar a próxima nota; aplicar o preço sugerido.
- **Blocos:**
  - itens casados, com custo antigo e novo e a variação;
  - o crédito lido da nota (fonte: grupo IBSCBS) ou calculado pelo motor;
  - itens sem par, como pergunta;
  - alertas gerados.

### Explicação (painel lateral)
- **Pergunta:** por que este item paga isso?
- **Achado** (arroz, híbrido): alíquota zero da cesta básica, Art. 125 da LC 214/2025, com a memória de cálculo do motor a um clique.
- **Regras:** de 3 a 6 frases (seção 11.6 do plano), terminando com o aviso de estimativa.

### Painel do contador (inbox, D1)
- **Pergunta:** qual cliente meu precisa de atenção este mês?
- **Achado:** depende de 3 CNPJs fictícios, que entram na E4 (E4-04). Não há dado para isso ainda e nada foi inventado.

## 3. Estilo, cara e elemento-assinatura (§2.3)

- **Estilo:** `achromatic-ledger` (seed 1986745741), escolhido entre 2 opções.
  - **Por quê:** é uma ferramenta de dinheiro, aberta a cada nota de compra e revisada pelo contador. A confiança vem de números em tinta, com cor só no dado principal e na margem que quebra.
  - O `pastel-consumer` codifica categorias e pessoas de um orçamento doméstico, que este produto não tem.
- **Shell:** sem barra lateral; barra superior de 46-48px sobre coluna centrada de 1088-1208px. Os destinos são poucos: Painel, Catálogo, Regime e Notas, mais Contador na D1.
- **Cara escolhida: todo número em Geist Mono.** Preços, margens e créditos leem como as colunas de um livro-caixa e da NF-e, que são a linguagem do contador, canal principal do produto. O texto fica em Geist.
  - O lint e o inspetor vão apontar a fonte mono. É decisão do estilo (permitida em §13 do capítulo) e vai justificada no relatório da E5.
  - O matiz do gráfico (`#1d5fbf`) fica no dado principal de cada tela (o crédito que o cliente leva; a margem do item em foco). A margem abaixo do alvo usa `--negative`.
- **Elemento-assinatura: a régua do crédito**, sugerida no plano (seção 12, passo 4).
  - Duas barras na mesma escala, uma por regime, cada uma com o preço total ao cliente. Em cada barra, o custo líquido do cliente vai em tinta e o crédito que ele leva no matiz.
  - Ao lado, o caixa da empresa em cada regime.
  - Mostra numa olhada o argumento de venda (o crédito) e o custo dele (o caixa). Só este produto tem.
- **Regras do plano que viram regra de tela:**
  - aviso de simulação como frase de estado no título (ex.: "Simulação de 2027 com CBS 8,8% assumida", texto que já vem da API);
  - aviso legal no rodapé, em texto normal;
  - estados em palavras do ofício ("NCM não combina com a classificação"), nunca selos genéricos;
  - versões dos motores no rodapé (checklist da seção 21).

## 4. Notas para a E5

- **Fonte sem rastreio:** a folha carrega Geist pelo Google Fonts. No produto, hospedar os arquivos junto com o app, sem CDN, para não enviar o IP dos usuários ao Google (LGPD). Geist e Geist Mono estão sob a SIL Open Font License 1.1 (repositório oficial `vercel/geist-font`), o que permite isso de graça.
- **Padrões da biblioteca:** só a *overview* tem padrão ("KPIs como abas do gráfico"). Catálogo, decisão e contador se compõem pelas regras do capítulo. Não copiar uma tela estudada.
- **Portão:** `inspect.mjs --app` com 0 FAIL em 1440, 768 e 390px (P11). No celular, a tabela do catálogo vira lista de duas linhas, e a régua do crédito fica empilhada, com a mesma escala.
