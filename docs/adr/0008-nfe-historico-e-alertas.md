# ADR 0008: NF-e de compra, histórico de custo, alertas de margem e painel do contador

- Status: aceito
- Data: 2026-11-25
- Etapa: E4 (E4-01, E4-02, E4-04 e E4-05; a E4-03, telas de importar nota e do painel, passa para a E5)
- Código: `backend/app/nfe/` (leitor, importação e consultas), `backend/app/persistencia/` (banco, migrações, repositório e sementes), `backend/app/empresa.py`, as rotas de notas em `backend/app/main.py` e a ferramenta `listar_alertas` em `backend/app/agente/ferramentas.py`

## Contexto

A E4 do plano (seções 6 e 11.3) tem três partes:
1. `POST /nfe/importar`: ler o XML da NF-e de compra, casar os itens com o catálogo e atualizar o custo com histórico.
2. Recalcular a margem pela API e gerar o alerta com o preço-alvo.
3. Desejável D1: painel do contador com 3 CNPJs fictícios.

Critério de saída: subir o XML de demonstração gera o alerta com o preço sugerido em menos de 5 s.

Até a E3 o backend não guardava estado: tudo vinha na requisição. `POST /nfe/importar` e `GET /alertas` serviam o mock da referência e respondiam 501 no modo real. A E4 é a primeira etapa que precisa de memória. O ADR 0004 (item 5 da revisão) já tinha deixado uma decisão para cá: SQLite, com o CNPJ do contribuinte em toda tabela.

Decisões do usuário em 2026-11-25:

1. **Estado: SQLite persistente com migrações versionadas e repositório (opção B), estado global por CNPJ, rotas que mudam o estado protegidas pelo token da demo e restauração das sementes (opção 1).** O pedido foi de um projeto "formal e bem estruturado". O espaço por visitante (opção 2) fica registrado como evolução.
2. **Rotas além das do contrato:** `GET /catalogo` e `POST /alertas/{id}/aplicar`.
3. **D1: o backend na E4 e a tela na E5**, com as empresas novas usando só os itens já verificados.
4. **XML com a biblioteca padrão**, recusando DTD e entidades, e **"mais proteção em todas as frentes"**. As ferramentas de CI (auditoria de dependências e varredura de segredos) vão num PR `chore` separado.
5. **A banca precisa conseguir acessar e testar o projeto por completo** (lembrete do usuário). Isso levou a três coisas:
   - a restauração ao alcance de quem tem o token;
   - o XML com item sem par em `data/demo/notas/`;
   - a subida que carrega as sementes sozinha quando o banco está vazio.

## Decisão

### Estado (`app/persistencia/`)

- **Migrações:** arquivos `migracoes/NNNN_nome.sql`, aplicados em ordem, cada um numa transação, com o SHA-256 gravado em `schema_migrations`.
  - Se um arquivo já aplicado muda, o backend não sobe (`MigracaoAlterada`): mudança de esquema é sempre uma migração nova.
  - O modo real migra na subida.
  - O `executescript` do `sqlite3` não serve, porque faz COMMIT antes de rodar. Os comandos são separados com `sqlite3.complete_statement`.
- **Esquema (`0001_inicial.sql`):** empresas, itens, códigos do fornecedor, notas, custos, alertas e preços.
  - Tabelas `STRICT`, com o CNPJ em todas e chaves estrangeiras ligadas.
  - Dinheiro e quantidades como texto decimal, nunca `REAL`, para não ter erro de ponto flutuante.
  - Datas em ISO 8601 com fuso, conforme a convenção do ADR 0003 (revisada no pacote A, abaixo): instantes do sistema em UTC; data de emissão da nota com o fuso dela, ordenada por `julianday()`, que converte o fuso. Uma nota de outro fuso (Amazonas, Acre) não troca a ordem. Um `CHECK` recusa data inválida.
- **Lançamentos só de acréscimo:** custo e preço são lançamentos, e gatilhos impedem `UPDATE`.
  - O custo atual é o da nota mais recente pela data de emissão. Uma nota antiga importada depois entra no histórico sem mudar o custo (`atualizaCusto: false`).
  - O preço atual é o último lançado (ordem de registro). Nenhum código apaga: a restauração substitui o banco inteiro (pacote A).
- **Repositório:** as rotas e os serviços falam com `Repositorio` e `Sessao`, nunca com SQL.
  - Uma sessão é uma unidade de trabalho: tudo entra junto ou nada entra.
  - Só consultas parametrizadas. Trocar o SQLite por outro banco é trocar esta implementação.
- **Arquivo:** `backend/.dados/contaai.db`, fora do git (`.gitignore`), configurável por `CONTAAI_BANCO_CAMINHO`. Os testes usam um banco temporário por teste (`banco_isolado` no `conftest`).
- **Sementes (`data/demo/sementes.json`):** as três empresas e as notas iniciais.
  - A restauração monta um banco temporário ao lado do principal: carrega as empresas e o preço de cada item (lançamento "semente") e importa as notas iniciais pelo mesmo código do `POST /nfe/importar`. Só se tudo der certo o conteúdo substitui o do principal, numa operação só (pacote A). Rodar de novo dá o mesmo estado.
  - A pasta das sementes é configurável (`CONTAAI_PASTA_DEMO`, padrão `data/demo`), para o container do deploy. Sem sementes legíveis, a resposta é 503, sem o caminho da pasta.
  - Formas de restaurar: `POST /demo/restaurar` (com o token, quando configurado), `make sementes` / `uv run python -m app.persistencia.sementes` ou a própria subida com o banco vazio (`CONTAAI_SEMEAR_AO_SUBIR`, padrão `true`). Se os motores não estiverem de pé, o backend sobe assim mesmo e avisa no log.
  - Ficam de fora das sementes a nota 2 da Serra Azul (a demonstração ao vivo) e a do item sem par.

### Leitor da NF-e (`app/nfe/leitor.py`)

**Fonte da proteção:** documentação do Python 3.12, "XML vulnerabilities", lida em 2026-11-25 em docs.python.org/3.12/library/xml.html. Para o `xml.etree.ElementTree`, a tabela marca como vulneráveis o "billion laughs", o "quadratic blowup" e os "large tokens". As notas da página dizem:
- "Expat 2.4.1 and newer is not vulnerable to the 'billion laughs' and 'quadratic blowup' vulnerabilities";
- "Expat 2.6.0 and newer is not vulnerable to denial of service through quadratic runtime caused by parsing large tokens";
- o ElementTree "doesn't expand external entities and raises a ParseError when an entity occurs".

A mesma página recomenda o `defusedxml` "for any server code that parses untrusted XML data".

**Decisão (usuário):** biblioteca padrão, numa forma mais estrita que o `defusedxml`:
- o parser é o expat direto, alimentando um `TreeBuilder`;
- qualquer DOCTYPE, declaração de entidade, entidade não analisada ou referência externa é recusada antes de montar a árvore. O `defusedxml`, por padrão, ainda aceita um DOCTYPE sem entidades;
- o expat mínimo é o **2.6.0**, conferido na importação do módulo, ou seja, na subida. Na máquina de desenvolvimento ele é o 2.8.3.

Na conversa de mapeamento eu tinha citado 2.4.1: corrigido para 2.6.0, por causa dos "large tokens".

**Por que não o `defusedxml`:** a última versão estável no PyPI é a 0.7.1, de 2021-03-08 (licença PSFL); as candidatas 0.8.0rc1 e rc2 são de setembro de 2023. Para trocar, basta trocar a função `_arvore`.

**Limites:**
- profundidade 16;
- até 100.000 elementos;
- até 990 itens, o teto do leiaute da NF-e 4.00 (nItem de 1 a 990);
- o tamanho do arquivo, que a rota já limitava (middleware + leitura de no máximo o limite + 1 byte).

**Campos:**
- aceita só o leiaute 4.00 (raiz `NFe` ou `nfeProc`), modelo 55 e `tpNF` 1 (saída do emitente);
- emitente e destinatário com CNPJ;
- `dhEmi` com fuso;
- números só em notação decimal simples. `Decimal("NaN")` é aceito pelo Python, então NaN, infinito, expoente e sinal são recusados por expressão regular;
- textos com tamanho máximo e sem caracteres de controle;
- `vProd` precisa bater com `qCom × vUnCom` (tolerância de R$ 0,01, escolha nossa, para o arredondamento).

**Erros:** dizem só qual campo falhou, sem repetir trecho do XML (422).

### Importação e alertas (`app/nfe/importacao.py`)

1. **Destinatário:** precisa ser uma empresa cadastrada. Senão, 422 antes de qualquer gravação, sem ecoar o CNPJ e sem log. **Dado real nunca entra no banco.**
2. **Idempotência:** a chave é destinatário + emitente + série + número.
   - Mesmo arquivo (SHA-256): volta o recibo gravado, com `jaImportada: true`.
   - Outro conteúdo: 409.
   - Duas importações simultâneas da mesma nota: a segunda bate na restrição `UNIQUE` e devolve o recibo da primeira.
3. **Casamento:** pelo CNPJ do emitente + `cProd`. O plano fala em "NCM + código do fornecedor", mas o código só é único dentro de um fornecedor; o catálogo ganhou `cnpjFornecedor`. Viram item sem par, com o motivo:
   - código sem cadastro;
   - NCM diferente da do cadastro;
   - unidade diferente (não há conversão de caixa para unidade);
   - produto repetido na nota;
   - tributação monofásica (`gIBSCBSMono`).
4. **Crédito da compra por unidade:**
   - do grupo IBSCBS do item: (vCBS + vIBS) ÷ qCom, como no ADR 0003;
   - sem o subgrupo de valores: zero;
   - sem o grupo: do motor RR sobre o custo, na data da nota e com as alíquotas do cenário da empresa, com a premissa impressa.
5. **Margem antes e depois:**
   - no regime atual da empresa, ao preço atual e na data do cenário dela;
   - pelo carrinho real da E1, com lote de 100 unidades, o mesmo lote do preço-alvo;
   - "antes" usa o custo e o crédito do lançamento anterior.
6. **Alerta:** sai quando a margem caiu **e** ficou abaixo do alvo do item.
   - Traz o preço-alvo da E1 com o custo novo. Se a margem-alvo for impossível, `precoSugerido` vem vazio, com o motivo.
   - Também traz `simulado`, `avisoSimulacao` e as premissas (do preço-alvo, mais "Margem do alerta").
   - O id é um resumo SHA-256 de empresa, nota e item: determinístico e opaco.
7. **Gravação:** nota, lançamentos de custo, alertas e o recibo entram numa transação só (`BEGIN IMMEDIATE`). As chamadas aos motores acontecem antes, fora da transação de escrita.
   - Por isso a gravação confere, já dentro da transação, se o custo e o preço de cada item ainda são os lidos (checagem otimista). Se outra nota ou um preço aplicado entrou no meio, a importação é refeita uma vez do começo. Se mudar de novo, a resposta é 409 e nada é gravado.
   - O acesso ao SQLite, que é síncrono, roda numa thread (`asyncio.to_thread`), para não travar o servidor.

### Rotas

| Rota | O que faz | Token | Limite por IP |
|---|---|---|---|
| `POST /nfe/importar` | Lê, casa, grava e gera os alertas | sim (modo real) | sim |
| `GET /alertas?cnpj=&abertos=` | Alertas, do mais recente para o mais antigo | não | não |
| `POST /alertas/{id}/aplicar` | Lança o preço sugerido como preço de venda; 409 se já aplicado ou sem preço | sim | sim |
| `GET /catalogo?cnpj=` | Itens com o preço e o custo atuais e o histórico (até 10). Não chama os motores: a margem sai do `POST /carrinho/calcular` com estes valores | não | não |
| `GET /contador/painel` | Empresas com os alertas abertos, a mais urgente primeiro (D1) | não | não |
| `POST /demo/restaurar` | Volta o estado às sementes | sim | sim |

- No modo mock, importar, alertas, catálogo e painel servem os mocks. Aplicar e restaurar respondem 501, porque o mock nunca finge uma gravação.
- O `responder_mock` (501 no modo real) foi removido: nenhuma rota precisa mais dele.

### Painel do contador (D1)

- Três empresas fictícias com CNPJ de dígito verificador inválido:
  - Distribuidora Serra Azul ME (tradicional);
  - Mercearia Vale Verde ME (tradicional);
  - Empório Lagoa EPP (híbrido).
- As novas só reaproveitam itens já verificados, com a mesma classificação, a mesma fonte e o mesmo código do fornecedor (um teste confere). Preço e margem-alvo são fictícios. Nenhuma classificação nova precisou de verificação.
- As notas da carteira foram geradas pelo `scripts/gerar_notas_demo.py`, com os grupos validados no XSD oficial do motor RR.
- As NCMs do XML com item sem par (22021000 e 19059090) foram conferidas no índice oficial (dados abertos do motor RR 1.7.2, banco V0073).

### Agente (E4-05)

- `listar_alertas(abertos=true)` lê o estado.
  - Usa a empresa do contexto do chat (`contexto.cnpj`, campo novo e opcional) ou todas, sem CNPJ.
  - O resultado tem `descricaoItem`, que vem do cadastro. O texto da nota (`xProd`) não entra no resultado da ferramenta, porque é dado não confiável (regra 7 do ADR 0006).
- O `roteiro` cita só números do resultado (margens, alvo, preço atual e sugerido) e termina com "Aplicar o preço é com você, na tela" (P3).
- O verificador aprova; teste em `tests/test_nfe.py`.

### Proteções desta etapa ("todas as frentes")

- **XML:** ver "Leitor".
- **Estado compartilhado:**
  - token nas rotas que mudam o estado;
  - limite por IP nelas;
  - destinatário obrigatório entre as empresas cadastradas;
  - idempotência por SHA-256.
- **Cabeçalhos em toda resposta:** `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `X-Frame-Options: DENY` e `Cross-Origin-Resource-Policy: same-site`. Fora da documentação (`/docs`, que carrega o Swagger da CDN do FastAPI), também `Content-Security-Policy: default-src 'none'; frame-ancestors 'none'` e `Cache-Control: no-store`.
- **Upload:** só tipos de XML (`text/xml`, `application/xml` ou sem tipo); outro tipo dá 415.
- **Entradas:**
  - CNPJ nas consultas com padrão de 14 dígitos;
  - id do alerta com padrão `alerta-` + 16 hexadecimais;
  - caminhos do manifesto das sementes presos à pasta `data/demo`.
- **Configuração:** `CONTAAI_BANCO_CAMINHO` vazio é recusado, porque viraria o caminho ".".

### Pacote A: revisão antes do commit (decisão do usuário, 2026-11-25)

Revisão estrutural feita antes do primeiro commit da E4. Todos os itens foram aprovados pelo usuário.

| # | Ponto | O que mudou | Teste |
|---|---|---|---|
| A1 | SQLite síncrono dentro de rotas assíncronas travava o servidor durante a consulta | Leitura e gravação da importação, a restauração e as contagens rodam em `asyncio.to_thread`. As rotas de leitura (`def`) já rodavam numa thread | Suíte inteira |
| A2 | Restauração não atômica: com um motor caindo no meio, sobravam empresas sem as notas iniciais | Banco temporário ao lado do principal e cópia de uma vez só (`Connection.backup`). O `apagar_tudo` saiu | `test_restauracao_com_motor_caindo_no_meio_nao_muda_o_estado` |
| A3 | Duas notas do mesmo item ao mesmo tempo liam o mesmo custo anterior | Checagem otimista dentro da transação de escrita, uma nova tentativa e, depois, 409 | `test_nota_concorrente_no_meio_refaz_a_importacao_com_o_custo_novo` e `test_estado_que_muda_nas_duas_tentativas_da_409_sem_gravar` |
| A4 | A pasta `data/demo` dependia do layout do código-fonte: no container, as sementes não seriam achadas | `CONTAAI_PASTA_DEMO`; 503 sem o caminho quando faltam sementes; manifesto preso à pasta | `test_pasta_das_sementes_configuravel_e_erro_sem_caminho` e `test_manifesto_nao_sai_da_pasta_de_dados` |
| A5 | 3 `# type: ignore` na importação | `fonte` tipada como `FonteCredito`; a chamada ao motor usa o item do contrato (`item_base`) | mypy à parte (ver Consequências) |
| A6 | Datas com convenções diferentes (UTC, -03:00, hora real × 2027) | Convenção no ADR 0003 e em `app/contrato.py`; data da nota gravada com o fuso dela e ordenada pelo instante; relógio dos mocks em UTC | `test_datas_de_fusos_diferentes_ficam_na_ordem_do_instante` |

A migração `0001_inicial.sql` foi editada no pacote A (datas, `CHECK` e índice por `julianday`). Isso só é aceitável porque ela nunca foi aplicada fora de bancos temporários: a E4 ainda não tinha commit. Depois do merge, qualquer mudança é uma migração nova, e o hash em `schema_migrations` impede a edição.

## Conferência

- **Gerador de mocks:** importação, alertas, catálogo e painel saem do código de produção, num banco temporário com as sementes e relógio fixo.
  - A importação da nota 2 de referência da E0 continua como conferência: se os alertas ou os itens casados divergirem, nenhum mock é gravado (`Divergencia`). Não houve divergência.
  - Os demais mocks (carrinho, preço-alvo, comparação, explicação) não mudaram nenhum byte, o que confere a troca de `requisicao_demo` para `operacao_da_empresa`.
  - As notas 1 e 2 regeradas ficaram iguais byte a byte.
- **Golden (`tests/test_nfe_golden.py`, motores reais):**

| Caso | Resultado |
|---|---|
| Serra Azul, nota 2, cerveja (preço R$ 3,79, alvo 15%) | margem de 24,12% para 11,19%, preço sugerido R$ 3,97, em menos de 5 s (0,1 a 0,2 s medidos) |
| Vale Verde, nota 2002, biscoito | 26,84% → 12,91%, sugerido R$ 5,12 |
| Vale Verde, nota 2002, chocolate | sugerido R$ 6,77 |
| Item sem par | o chocolate casa, com crédito pelo motor (R$ 0,3649/un), e os outros dois viram pergunta |
| Rota real × mock | iguais, menos o `criadoEm` |

- **CI (`tests/test_nfe.py`, motores falsos; 265 testes no CI ao todo):**
  - **leitor:** DTD, entidade interna e externa, aninhamento, NaN, infinito, sinal, expoente, `vProd`, modelo 65, `tpNF` 0, leiaute, NCM, fuso, CPF, caractere de controle sem eco e mais de 990 itens;
  - **migrações:** aplica uma vez, trava alteração, não fica pela metade;
  - **banco:** gatilho de imutabilidade;
  - **rotas:** restauração idempotente, alerta, recibo repetido, conflito 409, destinatário alheio sem gravação, sem par, nota antiga, aplicar uma vez só, painel ordenado e tempo;
  - **proteções:** token, 415, cabeçalhos, CNPJ inválido;
  - **agente.**

### Inconsistências corrigidas nesta etapa

1. **Alerta sem premissas:** o contrato do alerta não tinha `simulado` nem premissas, mas o alerta sai de números simulados de 2027, e a definição de pronto exige o aviso. `Alerta` e `NfeImportarResposta` passaram a herdar `_Simulacao` (mudança aditiva; não há frontend consumindo).
2. **"Importar nota" como ação do agente:** o ADR 0004 (item 7) previa essa ação para a E4, mas o agente não recebe arquivo. O upload é da tela; o agente lista e explica os alertas e propõe aplicar o preço (ação da E2).
3. **Exemplo do plano × demo:** o "18% para 11%" do plano (seção 6, E4) é ilustrativo. A demo dá 24,12% → 11,19%, que é o que a API devolve. O plano fica como está; vale o número da API.
4. **Inventário:** o painel do contador dizia "depende de 3 CNPJs fictícios, que entram na E4" e "nada foi inventado". Agora tem o achado real (ver `.taste-skill/app/inventario.md`).
5. **Casamento só por NCM + código:** o código do fornecedor só é único dentro dele. O catálogo ganhou `cnpjFornecedor`.
6. **Preço aplicado × data simulada:** com o preço atual ordenado pela data de vigência, o preço da semente (01/03/2027, data simulada) vencia um preço aplicado hoje (2026). Achado no teste de ponta a ponta. O preço atual passou a ser o último lançado.
7. **Testes no banco do desenvolvedor:** o primeiro teste do chat com a ferramenta real gravou em `backend/.dados/`. Agora cada teste tem um banco temporário (`banco_isolado`).
8. **Expat mínimo:** de 2.4.1 (o que eu disse no mapeamento) para 2.6.0 (doc oficial, "large tokens").

## Consequências

- A E4 está completa no backend. O modo real importa notas, gera e aplica alertas e mantém o histórico. O modo mock serve a saída real da demo.
- O contrato mudou de forma aditiva:
  - `Alerta`: `cnpj`, `custoAnterior`, `custoNovo`, `motivoSemPreco`, `aplicadoEm` e a simulação; `precoSugerido` passou a aceitar vazio;
  - `NfeImportarResposta`: `jaImportada` e a simulação;
  - `NotaResumo`: `serie`, `destinatario` e `homologacao`;
  - itens da nota: `nItem`, `atualizaCusto` e `motivo`;
  - `ContextoChat`: `cnpj`;
  - rotas novas.
- **Abertos:**
  - **Espaço por visitante (opção 2 da decisão 1):** se a URL pública for aberta a qualquer pessoa, vários jurados ao mesmo tempo mexem no mesmo estado. Hoje há o token e a restauração.
  - **Sem usuário nem autorização por CNPJ:** o CNPJ é filtro, não permissão. O token é um só para a demo. Login e autorização ficam para depois do hackathon.
  - **"Margem antes" ao preço atual:** se o preço mudou entre as notas, o "antes" não é a margem histórica, e sim a do preço atual com o custo anterior. É rotulado na premissa "Margem do alerta".
  - **`criadoEm` com a hora real (2026)**, enquanto as datas da demo são de 2027. É verdadeiro e fica: a tela distingue "emitida em" de "criado em" (convenção no ADR 0003). Os mocks usam a hora da nota 2, em UTC.
  - **Tipos:** um mypy rodado à parte (sem entrar no projeto) acusa 16 erros no backend, todos da mesma causa: o protocolo `ItemClassificado` (`app/motores/requisicoes.py`, E1) declara atributos mutáveis, e nenhum modelo do contrato se encaixa nele. Na E4 sobra um, na chamada ao motor RR para o crédito. A correção (atributos só de leitura no protocolo) vai no PR `chore`, junto com a checagem de tipos no CI.
  - **Casos sem suporte:** unidade diferente (conversão de embalagem), produto repetido na nota e tributação monofásica voltam como itens sem par.
  - **Notas de produção (`tpAmb` 1) são aceitas.** O destinatário precisa estar cadastrado, então só as empresas fictícias recebem nota.
  - **Deploy (E6):**
    - volume para o SQLite;
    - container do backend sem root e com sistema de arquivos só de leitura, exceto o banco;
    - limite de corpo no proxy;
    - `/docs` desligado ou protegido;
    - IP real só de um proxy nosso;
    - CSP do frontend na E5.
  - **PR `chore` separado:** auditoria de vulnerabilidades das dependências e varredura de segredos no CI. Licença, gratuidade e manutenção de cada ferramenta serão conferidas antes de adotar.
