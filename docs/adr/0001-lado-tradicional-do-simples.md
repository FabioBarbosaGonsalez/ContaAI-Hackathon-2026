# ADR 0001 — Lado "Simples tradicional" da decisão de regime

- Status: aceito
- Data: 2026-11-24
- Etapa: E0-04 (investigação do motor do Simples Nacional)
- Motor: `calculadora-rtc-simples-nacional` tag `1.0.2` (commit `f90b6525e6d5823e784baecfc6fef0ad2f04b74f`), banco `V0073` gerado pela tag `1.7.2` do Regime Regular

## Contexto

O plano v2.0 deixou três caminhos para o lado tradicional da comparação Simples tradicional × híbrido (M5):

- (a) o motor devolve CBS/IBS do Simples por item → usar no lado tradicional;
- (b) o motor só lista atividades e percentuais → usar o percentual da 1ª faixa como preset da premissa;
- (c) não deu tempo → a parcela de CBS/IBS dentro do DAS vira premissa digitada, com rótulo.

O README do motor não documenta o formato de entrada e saída do cálculo, e os exemplos do repositório são cópia dos do Regime Regular. A investigação leu o código-fonte na tag fixada e executou o motor.

## O que foi verificado

Fontes: código na tag `1.0.2` e chamadas ao motor em execução (`docker compose up`).

1. **O endpoint citado no plano está obsoleto.** O Javadoc de `SimplesNacionalController` marca `POST /calculadora/observabilidade/simples-nacional` (alíquotas por item) como "OBSOLETO, com contrato e resultados inalterados". O cálculo atual é `POST /calculadora/observabilidade/simples-nacional/nao-assistido`.
2. **O não assistido calcula por item.** A entrada (`OperacaoSimplesNaoAssistidaInput`) leva `data`, `tpDoc`, `CRT`, a linha de alíquotas efetivas do contribuinte em `aliquotasEfetivas` (`anexoI.pCBSSN` e `anexoI.pIBSSN`, em pontos percentuais) e os itens (`cAtivSN`, `cClassTrib`, `ncm`, `baseCalculo`, `valorImpostoSeletivo`). A saída traz, por item, `vCBSSN`, `vIBSSN`, `totalItem`, `estadoItem` e `memoriaCalculo` (`cbs`, `ibs`). Gravado em `backend/tests/golden/sn-nao-assistido-anexo-i.resposta.json`.
3. **As alíquotas efetivas são entrada, não resultado.** No não assistido, `aliquotasEfetivas` é obrigatória (erro `VSN-039` quando falta). No modo assistido, a linha vem da "Tabela de Alíquotas Efetivas do Simples Nacional", alimentada pelo PGDAS por CNPJ e período (CHANGELOG 1.0.0), o que não existe no perfil offline (`OrigemLinhaAliquotasEnum`: `REQUISICAO` ou `TABELA_ALIQUOTAS_EFETIVAS`).
4. **O preset por anexo e faixa não está na API nem no banco.** O `ROADMAP.md` do motor marca como concluída a "disponibilização de percentuais pré-carregados de IBS e CBS, por anexo e ano, aplicáveis à primeira faixa do Simples Nacional" (é provavelmente a origem do caminho (b) no plano). Na tag `1.0.2`, porém: a palavra "faixa" só aparece no ROADMAP (nem no código, nem nos 75 scripts SQL que geram o banco); a tabela `ANEXO` do banco trata dos anexos da LC 214/2025 (texto legal, sem alíquotas); `GET /calculadora/simples-nacional/atividades` devolve código, descrição, anexo e compatibilidades, sem alíquota; e o endpoint clássico também recebe `pCBSSN`/`pIBSSN` como entrada. Os percentuais podem estar num componente não publicado (a configuração de CORS do motor cita um front Angular) ou na instalação online; isso não foi verificado. Para nós, o caminho (b) não está disponível. O mesmo item do ROADMAP cita "componentes executáveis (JAR e Docker)", mas não há Dockerfile em nenhum dos dois repositórios.
5. **Sem aviso de simulação.** Com data de 2027 e alíquotas informadas, os itens saem `CALCULADO` e a resposta não traz `x-warning-dados-simulados`. Quem rotula a premissa é o nosso produto (P8).
6. **Erro equivalente ao REG-011.** NCM não vinculada à cClassTrib volta como `VSN-047` ("NCM não aplicável"), com `pointer`. A descrição oficial sai de `GET /calculadora/observabilidade/simples-nacional/erros?codigo=VSN-047`.
7. **Atividade da distribuidora.** Em 2027-03-15, com `anexos=I`, `tpDoc=55` e `cClassTrib=000001`, a atividade `01` ("Revenda de mercadorias, venda de mercadorias industrializadas pelo contribuinte") está disponível.

## Decisão

Caminho **(a) com alíquotas como premissa**:

- O lado tradicional chama `POST /calculadora/observabilidade/simples-nacional/nao-assistido`. O valor de CBS/IBS de cada item, que é também o crédito que o cliente do regime regular pode aproveitar (LC 214/2025, art. 47, §9, II), vem do motor (`vCBSSN + vIBSSN`), com a memória de cálculo do motor.
- `pCBSSN` e `pIBSSN` do anexo são **premissas digitadas pelo usuário**, impressas junto do resultado e sem valor pré-preenchido (P8). Os valores reais saem da apuração do Simples do contribuinte; onde o empresário os encontra na prática é pergunta para o contador (não verificado).
- O endpoint clássico (obsoleto) não é usado. `fonteTradicional` no contrato da API passa a ser sempre `motor`, e a premissa fica em `premissas`.

## Consequências

- O lado tradicional segue o P1: nenhum código nosso multiplica alíquota por base.
- A tela de decisão precisa de um campo obrigatório de alíquotas efetivas do anexo, com texto de ajuda. Sem ele, não há comparação.
- Os testes de referência usam `pCBSSN = 1.1612` e `pIBSSN = 0.0129`, que são os **exemplos do esquema OpenAPI do motor** (`AliquotasEfetivasInput.AnexoParUnicoInput`), e não alíquotas de nenhum contribuinte. Nunca mostrar esses números como valor real.

## Pontos em aberto (validar com contador antes da demo)

- Para o arroz (`NCM 10063021`, `cClassTrib 200003`), o motor do Regime Regular aplica redução de 100%, e o do Simples aplica a alíquota efetiva cheia sobre a receita bruta (`tpRBSN 1`). O produto mostra o que o motor devolve; a interpretação jurídica não foi feita.
- O tratamento do crédito das compras no Simples tradicional (não aproveitado) continua sendo a hipótese dos guias citados no plano.
