# ADR 0005 — Preço-alvo, cache e premissas de 2027

- Status: aceito
- Data: 2026-11-24
- Etapa: E1-03 (preço-alvo afim + bisseção, com cache) e E1-04 (premissas de 2027 e simulado)
- Código: `backend/app/precificacao/preco_alvo.py`, `backend/app/motores/cache.py`, `backend/app/cenarios/presets.py`, `backend/app/cenarios/premissas.py`

## Contexto

O critério de saída da E1 é a tabela da distribuidora vir da API (E1-02, ADR 0004) e o preço-alvo convergir em até 3 chamadas nos itens lineares. O ADR 0003 deixou em aberto a tolerância do preço-alvo. O plano (11.5) pede presets rotulados para as alíquotas de 2027, e o M2 pede a carga atual informada como número de comparação.

## Decisões

### Preço-alvo (`POST /item/preco-alvo`, modo real)

- **Método.** É o ajuste afim do plano 11.1, com as fórmulas do ADR 0003 nos dois regimes.
  - Duas avaliações, em x₁ = custo e x₂ = 2 × custo (R$ 1 e R$ 2 quando o custo é zero), dão a reta T(x) = α + βx.
  - O preço sai em fórmula fechada, arredondado ao centavo **acima**, e uma terceira avaliação confirma.
  - Cada avaliação usa um lote de 100 unidades.
- **Critério de aceite.** O preço é o **menor valor em centavos com margem ≥ alvo**, o que significa erro menor que R$ 0,01 (M4). Isso resolve a pendência do ADR 0003: a tolerância de 0,01 p.p. do código da seção 11.1 é inatingível com centavos em itens baratos.
- **Confirmação.** Exige três coisas:
  1. item calculado;
  2. margem ≥ alvo;
  3. tributo da 3ª avaliação igual ao previsto pela reta, com folga de R$ 0,001 por unidade para o arredondamento ao centavo do motor.

  A condição 3 não está no plano. Sem ela, um tributo não linear pode passar na confirmação com um preço que não é o menor centavo, e só uma 4ª chamada perceberia.
- **Bisseção de reserva.** Busca o menor centavo com margem ≥ alvo, partindo do custo e de um teto que dobra até atingir o alvo, no máximo 25 avaliações. Supõe a margem crescente no preço, como o plano.
- **Recusas.** Respondem 422 com `RecusaCalculo` (`detail` mais os erros do motor quando existem):
  - margem impossível (denominador da fórmula ≤ 0);
  - item que o motor não calcula já no primeiro ponto (ex.: REG-011, VSN-047);
  - falta de convergência.
- **`chamadas`** conta as avaliações do método, inclusive as respondidas pelo cache, para ser determinístico. A chamada ao motor RR que calcula o crédito da compra (no tradicional, sem crédito informado) não entra na conta e aparece nas premissas.
- No tradicional, valem as mesmas recusas do carrinho: serviço (NBS) e IS com incidência. O DAS passou a ser obrigatório também aqui, o que faltava no contrato.

### Cache das respostas dos motores

- LRU em memória, por processo, compartilhado entre as requisições, com 512 entradas por padrão (`CONTAAI_CACHE_MOTORES_ITENS`; 0 desliga).
- Chave: motor + operação em JSON canônico. Guarda só respostas 200 que passaram no modelo.
- Sem invalidação: a versão do motor é fixa (P5) e o cache some quando o processo reinicia, que é como se troca de versão.
- Privacidade: não vai a disco nem a log. Uma pessoa nunca recebe o dado de outra; só é reaproveitada a resposta do motor para uma operação idêntica.

### Premissas de 2027 (E1-04)

- **`GET /cenarios/presets`.** Igual nos dois modos e sem chamar motor. Os campos da tela começam vazios; o preset só preenche o que tem fonte:

| Preset | Valores | Fonte |
|---|---|---|
| Exemplo da documentação | CBS 8,8%, IBS 0,05% + 0,05%, IS 10% | Entradas do exemplo oficial (`docs/exemplos.md` da calculadora RR 1.7.2). Não são alíquotas oficiais. |
| Referência TCU 2027, pendente do Senado | CBS 11,3%; IBS em branco | [Portal do TCU, 28/10/2026](https://portal.tcu.gov.br/imprensa/noticias/tcu-calcula-aliquota-de-referencia-de-113-para-novo-tributo-sobre-consumo), processo TC 006.529/2026-7: "TCU aprovou alíquota de referência de 11,3% para a CBS"; "não corresponde, necessariamente, ao percentual que será efetivamente cobrado". O Senado fixa a alíquota por resolução. |

- **Campo `fonte`** (opcional, até 200 caracteres) em `aliquotasNominais` e `premissasDas`. O rótulo do preset escolhido sai impresso na premissa, sempre seguido do aviso padrão ("Não são alíquotas oficiais").
- **`cargaAtualPct`** (opcional) no carrinho. Volta na resposta e numa premissa "Carga atual informada", sem entrar em nenhuma conta. A comparação fica para a tela. Não calculamos um "% de carga" por item, para não chegar perto de calcular alíquota (P1).
- **Simulação.** Carrinho e preço-alvo usam as mesmas funções de premissas e de aviso. Em 2026 sem premissa, o resultado não é simulado (ADR 0004).

## O que foi verificado, e onde

- O valor de 11,3% e as ressalvas: Portal do TCU (texto literal) e [Agência Senado](https://www12.senado.leg.br/noticias/materias/2026/10/28/reforma-tributaria-tcu-calcula-aliquota-da-cbs-em-11-3-para-2027), em 24/11/2026.
- **Não usado, por divergência ou falta de leitura:**
  - o prazo do Senado (o TCU diz 15/12; a Agência Senado diz 22/12);
  - o valor sem arredondamento (11,3468%), que só apareceu num resumo da página do TCU, não em texto lido;
  - o redutor de compras públicas (44,2% no TCU, 44,16% no Senado);
  - o número do acórdão (a página traz só "Acórdão xxxxx").
- Não há referência de IBS para 2027 nas fontes lidas: o preset do TCU deixa o IBS em branco.

## Testes

- CI, com motores falsos (`tests/test_preco_alvo.py`, `tests/test_cenarios.py`):
  - 3 avaliações e o menor centavo, conferido por força bruta, nos dois regimes;
  - bisseção com tributo não linear (degrau), também no menor centavo;
  - limite de 25 avaliações;
  - recusas: margem impossível, REG-011 com os erros, DAS ausente, IS tributado;
  - cache sem nova chamada ao motor;
  - presets, rótulo da premissa e carga atual.
- `golden` (`tests/test_preco_alvo_golden.py`):
  - arroz, cerveja e chocolate convergem pelo ajuste afim em **exatamente 3 chamadas nos dois regimes** (critério de saída da E1);
  - a cerveja real é igual ao mock;
  - a carne é recusada com REG-011 (híbrido) ou VSN-047 (tradicional).

## Segurança e custo

- Nada pago e nenhuma dependência nova (o cache é feito na mão).
- **Amplificação:** um pedido de preço-alvo faz até 26 chamadas aos motores (25 avaliações + crédito). Com o cache, os pedidos repetidos não chegam ao motor. Na demo pública, é preciso limitar requisições (já registrado para a E2/E4/E6 no ADR 0004).
- O texto de `fonte` volta para a tela: o frontend deve exibi-lo como texto, nunca como HTML.

## Consequências

- A E1 está completa: carrinho, preço-alvo e premissas de 2027 reais, com o mesmo contrato dos mocks.
- `scripts/gerar_mocks.py` segue como referência para as rotas das etapas E3 e E4 (comparação de regimes, NF-e, alertas). Para a entrada da demonstração, o preço-alvo real é igual ao mock.
