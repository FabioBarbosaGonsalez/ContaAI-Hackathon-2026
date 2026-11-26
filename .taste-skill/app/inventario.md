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
  - 5 itens no catálogo, 2 notas de compra e 1 cliente B2B;
  - venda mensal de R$ 19.898,65;
  - preços de R$ 3,79 (lata) a R$ 39,90 (kg) e margens de 11,19% a 28,97%;
  - CBS/IBS por 100 unidades de R$ 0,00 (arroz no híbrido, redução de 100%) a R$ 53,31 (chocolate no híbrido).
  - Valores pequenos ficam pequenos: R$ 0,05 de IBS é R$ 0,05.
  - O tamanho real do catálogo de uma distribuidora pequena não foi medido; as telas não podem depender de 5 itens.
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

**Um fato, uma variável.** A margem da cerveja (11,19%) aparece no catálogo e no alerta, e o preço sugerido (R$ 3,97) aparece no alerta e no preço-alvo. Nos mocks, os dois saem do mesmo cálculo e já foram conferidos iguais. Na E5, cada um deve vir de um só campo. Desde a E4, o preço e o custo atuais de cada item vêm do `GET /catalogo` (estado no SQLite, ADR 0008): o preço atual do alerta é o do catálogo, e o custo novo do alerta é o custo atual do catálogo (teste em `test_contrato.py`).

**Antes da E5 (ADR 0011)**, o `GET /catalogo` passou a trazer tudo de que as telas precisam para montar os pedidos. A tela usa estes campos e não guarda cópia de nenhum valor:
- `cenario.operacao`: data, UF, município, alíquotas e premissas do DAS, com a fonte. Vai em todo carrinho, preço-alvo, comparação, explicação e contexto do chat. Nenhuma alíquota fica escrita no código da tela (P6).
- `loteReferencia` (100): a quantidade de cada linha do catálogo ("CBS/IBS a cada 100 unidades"). É o mesmo lote da explicação e do preço-alvo.
- `clientesB2B[].compraMensal`: a venda que a decisão de regime compara.

Conferido nos testes (`test_tela.py` e `test_tela_golden.py`): a margem da cerveja refeita com o catálogo é a do alerta (11,19% contra os motores). A memória da explicação é a conta da linha do catálogo: no tradicional, o arroz dá R$ 32,40 + R$ 0,36 = R$ 32,76 a cada 100 unidades.

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
  - pendências de cadastro: "Carne bovina: NCM não combina com a classificação", com "Corrigir". Corrigir mostra as candidatas oficiais (200003, alimentação humana, e 000001, tributação integral, conferidas nos motores) e grava a escolhida com `POST /catalogo/{itemId}/classificacao` (ADR 0011). Gravada, a pendência some e o item volta a calcular.

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
- **Achado:** no híbrido o Mercado Bom Preço leva R$ 1.626,26 de crédito por mês, contra R$ 233,63 no tradicional; em troca, a distribuidora paga R$ 125,79 a mais de imposto por mês. Isso vale para estas premissas. (Até a E3 a cesta tinha arroz, e o achado dependia da premissa da redução dentro do DAS; ADR 0007.)
- **Tarefa:** levar ao contador. A tela nunca diz "opte pelo híbrido" (seção 10 do plano).
- **Blocos:**
  - a régua do crédito (elemento-assinatura, seção 3 abaixo), que é o maior bloco;
  - o caixa da empresa: débito − crédito das compras contra o tributo no DAS;
  - premissas e simplificações, sempre visíveis;
  - desde a E3 (ADR 0007), a API traz ainda as linhas por item, com a origem do crédito das compras (`fonteCredito`), e o preço de empate com um concorrente do regime regular (`empateTradicional`: R$ 18.489,49 na demo, ou R$ 1.409,16 a menos). É um bloco secundário, abaixo da régua. A tela é construída na E5.

### Importar nota (detail: a NF-e)
- **Pergunta:** o que mudou no custo com esta nota?
- **Achado:** cerveja +17,31% (de R$ 2,60 para R$ 3,05) e margem para 11,19%; chocolate sem mudança.
- **Tarefa:** importar a próxima nota; aplicar o preço sugerido (`POST /alertas/{id}/aplicar`, desde a E4).
- **Blocos:**
  - itens casados, com custo antigo e novo e a variação; uma nota mais antiga que o custo atual aparece como "entrou no histórico, custo mantido" (`atualizaCusto`);
  - o crédito lido da nota (fonte: grupo IBSCBS) ou calculado pelo motor;
  - itens sem par, como pergunta, com o motivo que a API devolve (código sem cadastro, NCM ou unidade diferente);
  - a mesma nota de novo: "já importada", com o recibo da primeira vez (`jaImportada`);
  - alertas gerados.

### Explicação (painel lateral)
- **Pergunta:** por que este item paga isso?
- **Achado** (arroz, híbrido): alíquota zero da cesta básica, Art. 125 da LC 214/2025, com a memória de cálculo do motor a um clique.
- **Regras:** de 3 a 6 frases (seção 11.6 do plano), terminando com o aviso de estimativa.
- **Dados:** `GET /explicar/{itemId}?cnpj=` (desde o ADR 0011, lê o item como está no estado, no lote de referência) ou, para um item que só existe na tela, `POST /explicar`.

### Chat lateral (M1, M3 e o preço-alvo conversado)
- **Pergunta:** o que o copiloto propõe, e o que eu confirmo?
- **Achado** (provedor `roteiro`, sem IA): "Vendo arroz, cerveja e chocolate" gera três cartões de classificação para confirmar, sem nenhum cálculo antes da confirmação (P3).
- **Tarefa:** confirmar uma classificação, corrigir o item com REG-011 ou aplicar o preço sugerido.
- **Blocos:**
  - a conversa, como texto (nunca HTML: a resposta e a descrição dos itens são dados, `docs/seguranca.md`);
  - os cartões das ações propostas (`acoesPropostas`), montados pelo backend a partir das ferramentas e nunca do texto da IA:
    - `confirmar_classificacao`: até 3 candidatas visíveis e um "ver todas" (o arroz tem 4; ADR 0006). O item confirmado fica só na tela, como lista de trabalho calculada pelo carrinho (decisão do usuário, ADR 0011);
    - `corrigir_classificacao`: grava com `POST /catalogo/{itemId}/classificacao`;
    - `aplicar_preco`: grava com `POST /catalogo/{itemId}/preco`, só com o clique;
  - a frase de simulação e as premissas quando `simulado` (P6), e o aviso curto no fim;
  - quem respondeu (`provedor`: "roteiro, sem IA" ou o provedor de IA). Com uma IA externa, a tela diz que a conversa vai ao provedor (ADR 0006).
- **Estados:**
  - `verificacao: resposta_segura`: o verificador trocou uma resposta com número fora das ferramentas; a tela mostra a resposta segura, sem alarme;
  - 401: o chat exige o token da demo, que a pessoa digita num campo e fica só na memória da aba;
  - 429: espera, com o tempo de `Retry-After`.
- **No celular:** o chat abre em tela cheia, sobre a tela de onde veio, e volta para ela ao fechar.

### Painel do contador (inbox, D1)
- **Pergunta:** qual cliente meu precisa de atenção este mês?
- **Achado** (sementes da E4, ADR 0008): a Mercearia Vale Verde ME (fictícia) tem 2 alertas abertos depois da nota 2002, de 15/03/2027: biscoito de 26,84% para 12,91% (sugerido R$ 5,12) e chocolate (sugerido R$ 6,77). A Serra Azul ganha o alerta da cerveja quando a nota 1002 é importada; o Empório Lagoa (Simples híbrido) não tem alerta.
- **Tarefa:** abrir a empresa com mais alertas; o seletor de CNPJ da barra superior leva ao painel dela.
- **Dados:** `GET /contador/painel` (empresas ordenadas por alertas abertos, com o alerta mais recente de cada uma).

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
- **Base técnica (decisões do usuário, ADR 0011):**
  - Vite + React como páginas estáticas, no lugar do Next.js do plano;
  - TypeScript 5.9.3, porque o 7 é incompatível com o typescript-eslint e com o openapi-typescript;
  - a tela roda na porta 3000, a origem que o CORS já libera;
  - o endereço da API é configurável, e na E6 a API fica em `/api`, para `/catalogo` e `/contador` não colidirem;
  - a linha do tempo 2026 × 2027 (D2) e a exportação (D3) ficam fora da E5.
- **Fundação feita ([ADR 0012](../../docs/adr/0012-fundacao-do-frontend.md)):**
  - tokens deste estilo em `frontend/src/estilo/tokens.css`, com o fundo `#f2f4f7` (a troca que a folha sugere para um livro-caixa) e `--borda-campo` `#8a8a8a` (3:1 na borda de campo, WCAG 1.4.11);
  - o shell sem barra lateral, com o rodapé do aviso legal e das versões dos motores;
  - as páginas ainda sem conteúdo, à espera do PR 3.
- **Arquivos da skill:** `assets/app.css` e `assets/charts.js` não declaram licença e não são copiados para o repositório (público, MIT). O CSS e os SVG (a barra de margem contra o alvo e a régua) são escritos no projeto, seguindo as regras do capítulo. A skill entra como referência e como portão, rodando da pasta dela.
