# ADR 0003 — Contrato da API do backend

- Status: aceito
- Data: 2026-11-24
- Etapa: E0-05 (contrato e mocks) e E0-06 (dados de demonstração)
- Código: `backend/app/contrato.py` · contrato exportado: `docs/contrato/openapi.json` · mocks: `backend/app/mocks/`

## Contexto

O plano (seção 9) lista as rotas e os campos principais, mas não define o significado de preço, custo e margem em cada regime, e foi escrito antes de conhecermos as respostas reais dos motores. Frontend e agente precisam de um contrato fechado para trabalhar com mocks desde já.

## Decisão

O contrato é o conjunto de modelos Pydantic em `app/contrato.py`. O OpenAPI é exportado para `docs/contrato/openapi.json`, e um teste falha quando o contrato muda sem reexportar. As rotas da seção 9 existem todas. Na Etapa 0 elas respondem com mocks (`CONTAAI_MODO=mock`, header `X-ContaAI-Mock: 1`), e o modo real devolve 501 até a Etapa 1. `GET /saude` já é real.

### Mudanças em relação à seção 9 do plano

| # | Plano | Contrato | Motivo |
|---|---|---|---|
| 1 | Sem regime | `regime`: `simples_tradicional` ou `simples_hibrido` em carrinho e preço-alvo | No tradicional a CBS/IBS está dentro do DAS e vem do motor SN; no híbrido é cobrada por fora e vem do motor RR. A cliente da demo é do Simples. |
| 2 | `ano` | `data` | Os dois motores pedem a data do fato gerador, que rege as vigências. |
| 3 | "premissas do DAS" sem formato | `premissasDas` (anexo, `cAtivSN`, `pCBSSN`, `pIBSSN`) | Formato do modo não assistido (ADR 0001). Obrigatório no tradicional e na comparação. |
| 4 | 5 estados | 6 estados | O motor SN tem também `NAO_CALCULADO`. |
| 5 | `is` | `impostoSeletivo` | Mais claro, e `is` é palavra reservada em Python. |
| 6 | `aliquotaEfetiva` | `cbs`, `ibsUF`, `ibsMun` (RR) ou `cbs`, `ibs` (SN) | Como o motor publica. Somar alíquotas seria calcular alíquota (P1). |
| 7 | `modo (margem\|prateleira)` | Removido | O plano não define "prateleira". Volta quando alguém definir. |
| 8 | Comparação sem critério | `criterio: mesmo_preco_total_ao_cliente` | As fórmulas do plano (custo líquido = V − D) só fecham se V for o preço total ao cliente e D for calculado sobre a base B tal que B + D = V. |
| 9 | `fonteTradicional (motor\|premissa)` | Sempre `motor` | ADR 0001: o motor SN calcula; a premissa é a alíquota efetiva, impressa em `premissas`. |
| 10 | `GET /busca/ncm` devolve `cClassTrib[]` | Candidatas = específicas do produto + `000001` | Ver "Achados", item 1. |
| 11 | `/saude` com `/versao/status` | Rotas locais de versão dos motores | ADR 0002: o `/versao/status` do SN dá falso "desatualizado" e consulta a internet. |

### Significado dos campos (fórmulas)

Todos os tributos vêm dos motores. O backend só soma, subtrai e divide esses valores (P1). Valores de linha = quantidade × valor unitário.

**Preço e custo por regime.** `valorUnitario` é o valor do produto por unidade, como o `vUnCom` da NF-e.

| | Simples tradicional | Simples híbrido |
|---|---|---|
| Tributo da venda (T) | `vCBSSN + vIBSSN` do motor SN, sobre o valor dos produtos | `vCBS + vIBS` do motor RR, por fora |
| Preço ao cliente | valor dos produtos | valor dos produtos + T (+ IS) |
| Custo efetivo | custo + CBS/IBS da compra (crédito não aproveitado, hipótese dos guias) | custo (a CBS/IBS da compra vira crédito) |
| Margem | (valor − T − custo efetivo) ÷ valor | (valor − custo) ÷ preço ao cliente (plano 11.1) |

As duas margens são a mesma fórmula do plano, m = (b − c) ÷ (b + T), com b = receita líquida de CBS/IBS. O que muda é sobre qual valor o motor calcula o tributo.

**Crédito da compra.** Vem do grupo IBSCBS da NF-e (`vCBS + vIBS` do item ÷ quantidade). Sem grupo, o motor RR calcula sobre o custo, sob a hipótese exibida de fornecedor no regime regular (plano, E3).

**Preço-alvo.** É o ajuste afim do plano (11.1): duas chamadas dão T(x) = α + βx e uma terceira confirma.
- Híbrido (x = valor dos produtos): b* = (c + mα) ÷ (1 − m(1 + β)).
- Tradicional (x = preço, porque o tributo incide sobre ele): p* = (c + α) ÷ (1 − β − m).
- O resultado é arredondado ao centavo **acima**, para garantir margem ≥ alvo, e confirmado no motor.
- As chamadas usam um lote de 100 unidades (`loteReferencia`): o motor arredonda cada valor ao centavo, e numa unidade de R$ 3,79 isso distorce a reta (T sai 0,04 em vez de 0,0445).

**Comparação de regimes** (mesmo preço total V ao cliente):
- Tradicional: tributo e crédito do cliente = `vCBSSN + vIBSSN` sobre V; custo líquido do cliente = V − crédito.
- Híbrido: base B com B + D(B) = V, achada pelo mesmo ajuste afim (pode sobrar diferença de centavos). O crédito do cliente é igual a D, e o custo líquido do cliente é B.
- Crédito das compras Cc: crédito por unidade da última nota de cada item × quantidade vendida. Tributo líquido = D − Cc.
- `diferencaCaixa` = tributo tradicional − tributo líquido híbrido. Positivo: o híbrido deixa mais dinheiro com a empresa.

## Achados da investigação que viram regra

1. **`ncm-aplicavel` não lista a classificação do produto.** Para qualquer NCM, inclusive máquinas industriais, cerca de 127 classificações respondem `valido: true`, inclusive algumas com redução (ex.: 200001, 200002), porque muitas reduções dependem da operação ou de quem compra. Por isso, candidata "específica do produto" = válida para a NCM **e** inválida para a NCM neutra `84381000` (máquina industrial). Somam-se a ela a `000001` (tributação integral). Resultado nos dados oficiais: arroz → 200003, 200038, 515001 e 000001; carne bovina desossada → 200003 e 000001; chocolate e cerveja → só 000001. A escolha é sempre do usuário (P3).
2. **Imposto Seletivo na revenda.** O IS incide uma única vez sobre o bem (CF, art. 153, §6º, II, incluído pela EC 132/2023). O catálogo oficial do IS tem a classificação `200007` ("Venda de bem ou serviço tributado pelo IS em operação anterior", CST 200, sem cálculo). A cerveja da distribuidora usa essa classificação e o motor devolve `vIS 0.00`. O motor RR ainda exige uma alíquota de IS para NCM sujeita ao IS (erro `REG-035`, "ainda não foi definida em lei"), mesmo sem efeito no resultado.
3. **Sem busca textual de NCM no motor.** Existem só a consulta por código (`/dados-abertos/ncm?ncm=`) e a lista de vigentes (`/ncm/vigentes`, com a descrição do último nível). A busca "arroz" → NCM precisa de um índice local com a hierarquia (E2). Nos mocks, a busca resolve pelo catálogo de demonstração.

## Pontos em aberto para as próximas etapas

- **E1-03:** o critério de aceite do M4 ("erro menor que R$ 0,01") e a tolerância do código da seção 11.1 (0,01 p.p. na margem) não são compatíveis. Com preço em centavos, 0,01 p.p. é inatingível em itens baratos: 1 centavo sobre R$ 3,79 vale 0,26 p.p. Proposta: o preço-alvo é o menor preço em centavos com margem ≥ alvo.
- **E2:** a alíquota de IS que o RR exige na revenda é premissa sem efeito. Falta decidir se o usuário precisa digitá-la ou se o backend envia a premissa rotulada ("exigida pelo motor, sem efeito na revenda").
- **E4:** ler o XML de upload com proteção contra XML malicioso (por exemplo, `defusedxml`; verificar licença e manutenção na hora) e manter o limite de tamanho, que já existe na rota.
- O teste avisa que o Starlette depreciou o uso de `httpx` no `TestClient` e sugere um pacote chamado "httpx2". Investigar antes de trocar qualquer dependência.
- Continuam abertos do ADR 0001: arroz sem redução no motor SN e crédito das compras no tradicional. Os dois devem ser validados com contador.

## Consequências

- Frontend e agente trabalham sobre `docs/contrato/openapi.json` e sobre a API em modo mock (`uv run uvicorn app.main:app --reload`, documentação em `/docs`).
- Os mocks e as notas são reproduzíveis: os testes `golden` regeram tudo a partir dos motores e exigem igualdade byte a byte, o que prova que nenhum número foi digitado.
- As etapas E1 a E4 substituem o gerador de mocks (`scripts/gerar_mocks.py`) pelo código de produção. As fórmulas acima são o critério de aceite desse código.
