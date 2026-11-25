# ADR 0004 — Núcleo de cálculo: clientes dos motores e carrinho real

- Status: aceito
- Data: 2026-11-24
- Etapa: E1-01 (clientes tipados) e E1-02 (`POST /carrinho/calcular` real)
- Código: `backend/app/motores/` (modelos, cliente, conversão), `backend/app/precificacao/carrinho.py`, `backend/app/cenarios/premissas.py`

## Contexto

Na Etapa 0 todas as rotas respondiam com mocks gerados por `scripts/gerar_mocks.py`. A E1 troca isso por código de produção, começando pelo carrinho. O aceite do plano para estas duas tarefas é:
- E1-01: os clientes tipados validam as respostas gravadas;
- E1-02: o carrinho bate com a referência e trata os estados dos itens.

## Decisões

### Clientes tipados (E1-01)

- `app/motores/modelos.py` descreve em Pydantic só os campos que o ContaAI lê. O resto é ignorado (`extra="ignore"`), para que um campo novo do motor não derrube o cálculo. Um campo lido com tipo errado ou um estado desconhecido derruba, e vira `RespostaInvalida`.
- `ClienteMotores` (httpx assíncrono) chama só os endpoints de observabilidade (P4) e transforma as falhas em três exceções, que a API devolve com o corpo `FalhaMotorResposta` (desde o ADR 0009, `ProblemaMotor`, no formato da RFC 9457):

| Situação no motor | Exceção | Resposta da API |
|---|---|---|
| Conexão recusada, tempo esgotado ou 5xx | `MotorIndisponivel` | 503 |
| 422 com a lista `errors` (a operação inteira foi recusada) | `OperacaoRecusada` | 422 com os erros do motor (código, título, campo, detalhe) |
| 400, outro status, corpo fora do modelo, itens diferentes dos enviados | `RespostaInvalida` | 502 |

- Nenhuma resposta repassa URL, host ou corpo do motor. O campo `type` dos erros do motor traz o host interno (`http://127.0.0.1/...`) e é descartado. O cliente guarda só os headers de simulação e de versão.
- `trust_env=False`: as chamadas aos motores não passam por proxy configurado no ambiente.
- Serviço vai ao motor RR com `nbs` em vez de `ncm`, como no exemplo oficial. Antes ia com `ncm` vazio.

### Carrinho real (E1-02)

- `CONTAAI_MODO=real` liga o cálculo real em `/carrinho/calcular`. As rotas que ainda não calculam respondem 501 no modo real, para que um número de mock nunca apareça como resultado da entrada do usuário. O modo mock continua o padrão, e é o que o CI usa. (Desde a E4 todas as rotas calculam no modo real; o 501 ficou só para as rotas que mudam o estado no modo mock, [ADR 0008](0008-nfe-historico-e-alertas.md).)
- Fórmulas de preço, custo e margem: as do ADR 0003, sem mudança. O valor da linha (quantidade × valor unitário) é arredondado ao centavo com `ROUND_HALF_UP`.
- **Crédito das compras no tradicional.** Com `creditoCompraUnitario` (da NF-e), o custo efetivo é (custo + crédito) × quantidade. Sem ele, há uma chamada ao motor RR, em lote, sobre o custo da linha, na data e com as alíquotas da operação. A hipótese de fornecedor no regime regular aparece nas premissas com os itens afetados. No híbrido, o crédito não entra no custo.
- **Premissas e aviso de simulação** são montados a partir da requisição (`app/cenarios/premissas.py`), e não do cenário de demonstração. O resultado é `simulado` quando há DAS (tradicional), alíquotas nominais, o header `x-warning-dados-simulados` do motor RR ou item em `CALCULO_SIMULADO`.
- **O que o tradicional ainda recusa (422 claro, em vez de número errado):**
  - serviço (NBS), porque enviamos ao motor SN uma NF-e de mercadorias (`tpDoc 55`);
  - Imposto Seletivo com incidência (CST do IS diferente de 200), porque falta decidir como o IS entra na margem do tradicional.

  A revenda com IS 200007 funciona. Os ids dos itens precisam ser únicos.
- `versoes` traz só os motores que foram chamados naquele cálculo.

## Verificado nos motores em execução (RR 1.7.2, SN 1.0.2, banco V0073)

| Entrada | Resposta |
|---|---|
| RR, 2026, sem alíquotas | 200, `CALCULADO`, CBS 0,90% e IBS UF 0,10% da base do motor, **sem** header de simulação |
| RR, 2027, sem alíquotas | 200, item `INCONSISTENCIA_ENTRADA` com `REG-037` (o contrato já recusa antes) |
| RR, NCM sujeita ao IS sem alíquota de IS / sem grupo IS | 200, item com `REG-035` / `REG-013` |
| RR, CST incompatível com a cClassTrib / NCM inexistente | 200, item com `REG-006` / `REG-002` |
| RR, número inválido / lista de itens vazia | 400 sem lista de erros / 422 com `VAL-003` |
| RR, serviço com `ncm` nulo ou com quantidade e unidade | aceita; educação dá vCBS 42,24 e vIBS 0,48, como no exemplo oficial |
| RR, IS tributado com `baseCalculo` no item | vBC 165,00 (150 + IS 15,00), como no exemplo oficial, que não manda a base |
| SN, 2026 | **422 com `VSN-015`**: "Tipo de documento não suportado pelo cálculo do Simples Nacional, recebido: '55'". O tradicional de 2026 não é calculado pelo motor. |
| SN, sem `aliquotasEfetivas` | 422 com `VSN-039` |
| SN, `cAtivSN` inexistente | 200, item `NAO_CALCULADO` com `motivoEstado` |
| SN, base inválida / IS sem valor | 200, item com `VSN-002` / `VSN-003` |

Não observados nos motores reais: `NAO_IMPLEMENTADO` e `FALHA_TECNICA`. Eles são cobertos com motores falsos nos testes.

## Testes

- CI (sem motores): `tests/test_motores.py` cobre os modelos com as respostas gravadas, a montagem da requisição e cada falha do cliente. `tests/test_carrinho.py` usa motores falsos, com valores fictícios rotulados em `tests/conftest.py`, e cobre: os estados, as margens nos dois regimes, o crédito pelo motor, a simulação em 2026 e 2027, as recusas e as falhas sem vazamento.
- Marcador `golden` (`tests/test_carrinho_golden.py`):
  - a rota real reproduz o exemplo oficial (vCBS 42,24; total CBS 56,76; IBS 0,64; IS 15,00; REG-011) e a resposta gravada do SN (arroz 1,16 e 0,01; VSN-047);
  - repassa o VSN-015 de 2026;
  - com a entrada da demonstração, devolve os mesmos números dos mocks nos dois regimes.
- Correção encontrada no caminho: no Windows, os geradores gravavam CRLF e os testes de reprodutibilidade falhavam. Agora todos gravam LF, como o `.gitattributes`.

## Revisão externa da arquitetura (validada em 2026-11-24)

| # | Achado | Verificação | O que foi feito |
|---|---|---|---|
| 1 | Limite do upload de NF-e ignorável (`size is None`) | Em parte. O Starlette 1.10 cria o `UploadFile` com `size=0` e soma; o risco real é o arquivo inteiro ser recebido e gravado em disco antes da checagem, porque arquivo não tem limite de parte. | Middleware recusa `Content-Length` acima do limite (413) ou ausente (411) antes da leitura; a rota lê no máximo o limite + 1 byte. No deploy, o proxy também deve limitar o corpo (E6). |
| 2 | Testes golden e `ruff format --check` fora do CI | Válido. | `format --check` no CI. Workflow `Golden` (manual e em PR que mexe em motores, golden, cliente, geradores ou demo). Runners padrão são gratuitos em repositório público (docs.github.com, Billing → GitHub Actions); sem cache, para não usar a franquia. |
| 3 | CI verde sem nada testado | Exagerado. O job Python roda os testes; no frontend, os passos (e não o job) são pulados e passam a rodar quando existir `frontend/package.json`. | Nada. |
| 4 | Preço-alvo afim supõe tributo linear | Válido e já previsto no plano (11.1). | Bisseção de reserva na E1-03. |
| 5 | Sem persistência | Válido. O plano já prevê SQLite no backend. | Decisão para a E4: SQLite, com o CNPJ do contribuinte em toda tabela desde o início (painel do contador, D1). **E4:** feito, com migrações versionadas e repositório ([ADR 0008](0008-nfe-historico-e-alertas.md)). |
| 6 | `/chat` e `/nfe/importar` sem defesa | Válido (hoje são mocks). | Requisitos da E2/E4: texto da nota (`xProd`) tratado como dado não confiável no contexto do LLM; `defusedxml`; limite de requisições e token na demo pública, porque o LLM custa dinheiro. **E2:** limite por IP, token e regra de dado não confiável no prompt ([ADR 0006](0006-agente.md)); `defusedxml` segue para a E4. **E4:** leitor que recusa DTD e entidades, token e limite por IP nas rotas que mudam o estado ([ADR 0008](0008-nfe-historico-e-alertas.md)). |
| 7 | Poucas ações do agente no contrato | Válido. | Na E2: aplicar preço, corrigir classificação (REG-011/VSN-047) e importar nota, sempre com confirmação do usuário (P3). **E2:** aplicar preço e corrigir classificação entraram ([ADR 0006](0006-agente.md)); importar nota fica para a E4. **E4:** "importar nota" não vira ação do agente, porque ele não recebe arquivo; o upload é da tela, e o agente lista e explica os alertas ([ADR 0008](0008-nfe-historico-e-alertas.md)). |
| 8 | Deploy não pronto | Válido. | Na E6: Dockerfile do backend e imagens no GHCR. **A VM do deploy é paga** e precisa de aprovação do time antes. |
| 9 | `/saude` em sequência | Válido. | `asyncio.gather`. |
| 10 | CORS só para localhost | Já documentado (`CONTAAI_CORS_ORIGENS` no README). | Nada. |

Uma inconsistência na própria revisão: ela cita um "D4" (PDF para o contador). O plano tem D1 a D3, e exportar CSV/PDF é o D3.

## Pontos em aberto

- E1-03 e E1-04: resolvidos no [ADR 0005](0005-preco-alvo-e-premissas.md).
- IS com incidência no Simples tradicional: falta decidir com o contador como o IS entra na margem.
- O tradicional de 2026 não tem cálculo no motor SN (VSN-015). Falta decidir o que a tela mostra nesse caso. **Resolvido na E3** ([ADR 0007](0007-comparacao-de-regimes.md)): carrinho, preço-alvo e explicação recusam o tradicional antes de 2027 com mensagem clara, antes de chamar o motor; o híbrido de 2026 continua calculando.
- O teste avisa que o Starlette depreciou o `httpx` no `TestClient` (sugere "httpx2"). Continua em investigação; nenhuma dependência foi trocada.

## Consequências

- O frontend pode usar o carrinho real (`CONTAAI_MODO=real`, motores de pé) com o mesmo contrato dos mocks. Os números são iguais para a entrada da demonstração.
- `scripts/gerar_mocks.py` continua sendo a referência das rotas que ainda não foram para produção. A leitura das respostas é a mesma da produção (modelos tipados), e os mocks não mudaram.
