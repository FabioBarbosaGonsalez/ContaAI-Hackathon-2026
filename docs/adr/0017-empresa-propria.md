# ADR 0017: a empresa própria no backend, o CNPJ alfanumérico, o catálogo e os clientes editáveis (C3-B)

- Status: aceito (etapas 1 a 10 da C3-B; as etapas 1 a 5 no PR #26, as 6 a 10 no PR #27; revisão da C3b, o item a partir da nota, e a da C3b2, o fornecedor no catálogo e o recibo de uma nota gravada, no fim)
- Data: 2026-11-27
- Etapa: C3-B do plano v2.1 (as telas vêm na C3a e na C3b)
- Código: `backend/app/cnpj.py`, `backend/app/cadastro.py`, `backend/app/api/rotas/empresa.py`, `backend/app/persistencia/migracoes/0003_empresa_propria.sql`, `backend/app/persistencia/banco.py` (`migrar`), `backend/app/persistencia/repositorio.py` (`trocar_recibo`, C3b), `backend/app/nfe/importacao.py` (`creditos_pelo_motor` e as linhas sem par, C3b), `backend/app/motores/dados_abertos.py` (UF, município e atividade), `backend/app/empresa.py` (rótulos das premissas), `backend/app/contas/servico.py` (`vincular_empresa`), `backend/app/api/middlewares.py`, `frontend/src/dados/formatar.ts`, `frontend/src/api/rotas.ts`, `backend/app/dados_da_conta.py`, `backend/app/api/registro.py`, `backend/app/api/dependencias.py` (papéis), `backend/app/api/problemas.py` (o 500), `backend/tests/test_cnpj.py`, `test_migracao_0003.py`, `test_clientes_b2b.py`, `test_empresa_propria.py`, `test_empresa_golden.py`, `test_exclusao_e_dados.py`, `test_papeis.py`, `test_erro_interno.py`, `test_modo_mock.py`, `test_par_da_nota.py` (C3b) e `test_recibo_da_nota.py` (C3b2); `backend/app/nfe/consultas.py` (`recibo_da_nota`, C3b2)

## Contexto

Desde a C1, quem entra com a conta lê e grava no banco da própria organização, que nasce vazio. A C3 deixa a conta cadastrar a empresa dela. A saída da C3 é esta: uma conta nova cadastra a empresa, importa uma nota e vê o alerta, sem tocar nos dados da demonstração.

O usuário decidiu antes do código (plano v2.1, C3):
1. **P10:** "só dados fictícios" vale para a demonstração e os espaços. No ambiente próprio, cada pessoa põe os dados reais dela.
2. **O dígito verificador do CNPJ** é exigido nas empresas reais. A demonstração continua aceitando os CNPJs dela, que têm dígito inválido de propósito ([ADR 0008](0008-nfe-historico-e-alertas.md)).
3. **As notas de exemplo** da tela somem fora da demonstração (C3a).
4. **A exclusão da conta** é imediata e definitiva, com os dados para baixar antes (etapa 7).
5. **Validadas no mapa da C3-B:**
   - o CNPJ alfanumérico entra já;
   - o cenário da empresa real usa as premissas rotuladas da simulação;
   - quem não é do Simples é recusado no cadastro;
   - o item é arquivado em vez de apagado;
   - o mesmo CNPJ pode estar em duas contas.

## Fontes lidas (2026-11-27)

| Fonte | O que foi usado |
|---|---|
| Receita Federal, página "CNPJ Alfanumérico" (gov.br) | "O CNPJ Alfanumérico será atribuído, a partir de Julho de 2026, exclusivamente a novas inscrições"; "Os números de CNPJ já existentes não sofrerão nenhuma alteração"; o primeiro em 31/07/2026 |
| Receita Federal, perguntas e respostas do CNPJ alfanumérico (PDF) | 14 posições, "AA.AAA.AAA/AAAA-DV"; "Poderá ser numerais de 0 a 9 e letras maiúsculas de A até Z"; DV pelo módulo 11; a máscara é "exatamente igual" à do numérico; a raiz e a ordem (12 primeiras posições) podem ter letras |
| Serpro, "Cálculo dos dígitos verificadores de CNPJ alfanumérico" (PDF da Receita) | Valor de cada caractere = ASCII menos 48; pesos de 2 a 9 da direita para a esquerda, recomeçando depois do oitavo; resto 0 ou 1 dá 0, senão 11 menos o resto; exemplo 12.ABC.345/01DE-35 |
| NT 2026.004 v1.01 da NF-e (Portal Nacional da NF-e), junho de 2026 | `emit/CNPJ` (C02), `dest/CNPJ` (E02) e a chave de acesso passam de numéricos para alfanuméricos (tipo C, 14 e 44 posições); produção em 01/07/2026 |
| Documentação do SQLite: `lang_altertable.html` e `lang_droptable.html` | O procedimento para mudar o esquema de uma tabela: chaves estrangeiras desligadas antes da transação, tabela nova com outro nome, cópia, DROP, RENAME e `PRAGMA foreign_key_check`. Com elas ligadas, o DROP faz um DELETE implícito que "does cause any configured foreign key actions to take place". O `PRAGMA foreign_keys` "is a no-op within a transaction" |
| LGPD, art. 16 (caput e incisos), art. 18 V e VI (planalto.gov.br) | Eliminação ao fim do tratamento, salvo obrigação legal do controlador; portabilidade; eliminação a pedido. Para as etapas 6 a 10 |
| Ajuste SINIEF 07/05, cláusula décima (CONFAZ) | "O emitente deverá manter a NF-e em arquivo digital, sob sua guarda e responsabilidade"; o §2º estende ao destinatário. A guarda é do contribuinte, não do ContaAI |
| CTN, art. 173 I e art. 195, parágrafo único (planalto.gov.br) | Os 5 anos da Fazenda e a guarda dos comprovantes "até que ocorra a prescrição": também obrigações do contribuinte |
| Motores fixados, RR 1.7.2 e SN 1.0.2 (rodando no docker) | `GET /calculadora/dados-abertos/ufs`, `/ufs/municipios?siglaUf=` e `GET /calculadora/simples-nacional/atividades?data=&tpDoc=55`, com o formato conferido nas respostas |

## Decisão

### 1. O CNPJ numérico e o alfanumérico (`app/cnpj.py`)

- **Um padrão só (`PADRAO_CNPJ`):** `^[0-9A-Z]{12}[0-9]{2}$`. Ele substitui o `^[0-9]{14}$` no contrato, nos dados da demo, nas sementes, nas rotas, no leitor da NF-e e nas mensagens.
- **Só letras maiúsculas.** A Receita fala só em maiúsculas. A tela converte o que a pessoa digita.
- **`cnpj_valido`** confere o formato e os dois dígitos verificadores, pelo cálculo do Serpro. O CNPJ numérico é o mesmo cálculo.
- **Onde o dígito é exigido:** no cadastro da empresa e no CNPJ do fornecedor de um item, só na empresa da conta. Na demonstração e nos espaços, os CNPJs fictícios continuam aceitos.
- **O leitor da NF-e** confere só o formato: o destinatário ainda precisa ser uma empresa de quem chama.

### 2. A migração 0003 e o `migrar`

- **Duas tabelas reconstruídas:** `empresas` e `clientes_b2b` ganham o CHECK do formato oficial.
- **Item arquivado:** `itens` ganha `arquivado_em`.
- **Achado:** com as chaves estrangeiras ligadas, a reconstrução de `empresas` apagava em cascata os itens e as notas. Isso foi conferido num rascunho com a própria 0003.
- **Conserto no `Banco.migrar`:** ele passou a seguir o procedimento da documentação. Desliga as chaves fora da transação, roda `foreign_key_check` antes do COMMIT e as religa no fim. Uma migração que quebre uma chave estrangeira é recusada e desfeita.
- **PostgreSQL:** o GLOB é do SQLite. No PostgreSQL, o mesmo CHECK é `~ '^[0-9A-Z]{12}[0-9]{2}$'`, registrado no comentário da migração.

### 3. Referências oficiais

- **`GET /referencias/ufs` e `GET /referencias/municipios?uf=`:** vêm dos dados abertos do motor RR, com o código do IBGE.
  - Os dados abertos trazem "EX" (EXTERIOR, município 9999999), o código das operações com o exterior. Ele não é UF onde a empresa fica e sai da lista.
- **`GET /referencias/atividades`:** vem do motor SN na data do cenário e mostra só as atividades que o ContaAI calcula:
  - admissíveis na NF-e (`tpDoc=55`) e disponíveis;
  - com anexo;
  - sem fator R, que depende da folha de salários, um dado que o ContaAI não recebe.
- **No motor 1.0.2 sobram quatro atividades:** 01 e 02 (anexo I) e 03 e 04 (anexo II).
- Nenhuma lista é copiada para o código.

### 4. A empresa da conta (`/empresas`)

- **`POST /empresas`:**
  - pede sessão e papel de dono;
  - o nome do município e o anexo vêm dos motores, nunca da tela;
  - o cenário é o de `data/demo`, com `origem: empresa_propria`, o anexo da atividade e a carga atual vazia.
- **`GET /empresas/{cnpj}`:** dono e membro leem.
- **`PATCH /empresas/{cnpj}`:**
  - muda só o enviado, e o CNPJ não muda;
  - `premissasDas` com os valores da apuração da empresa (P8) passa a valer em todo cálculo, com o rótulo "Configurações da empresa";
  - `premissasDas: null` volta à simulação.
- **Os rótulos impressos nas premissas** mudam com a origem. A demonstração mantém "Cenário de demonstração (data/demo)", e a empresa da conta recebe "Simulação do ContaAI". Os números de referência (golden) não mudaram.
- **Dois bancos:** a empresa é gravada no banco da organização e depois recebe o acesso no `contas.db`. Se o acesso falhar, a empresa sai do banco da organização. O acesso que sobrar de uma falha não trava o recadastro (`ON CONFLICT DO NOTHING`).
- **O mesmo CNPJ em duas contas** é aceito, cada uma com a sua cópia. Sem prova de quem é o dono, um CNPJ único deixaria alguém bloquear a empresa de outra pessoa.
- **O header do espaço não vale nestas rotas.** O espaço é uma cópia da demonstração.
- **Aviso das respostas:** na empresa da conta, o catálogo, as notas e o painel trocam o aviso de dados fictícios por um de simulação: "Dados cadastrados pela sua empresa…". A demonstração e os espaços continuam com o aviso de dados fictícios.

### 5. O catálogo editável

- **`POST /catalogo/itens`:**
  - a NCM é conferida nos dados abertos na data do cenário;
  - a classificação precisa ser uma das válidas para a NCM, e o CST é o da fundamentação oficial, como na correção (P3);
  - a fonte é montada pelo backend, sem texto da pessoa;
  - o primeiro preço é um lançamento de origem `tela`.
- **Itens com Imposto Seletivo ficam para depois.** A classificação do IS e os litros por unidade não têm, hoje, uma fonte oficial que o ContaAI consulte, e o ContaAI não inventa.
- **`PATCH /catalogo/{item_id}`:**
  - muda a descrição, a margem-alvo ou o fornecedor (o CNPJ e o código juntos);
  - NCM e unidade não mudam, porque o histórico de custo é dessa NCM e dessa unidade;
  - a alteração regrava o cadastro e não a classificação dos lançamentos.
- **`POST /catalogo/{item_id}/arquivar`:**
  - o item sai do catálogo, das listas de alertas, do painel e das contagens das notas;
  - aplicar um alerta dele responde 409;
  - o código do fornecedor fica livre para outro item;
  - custos, preços, classificações e alertas ficam no banco, como histórico.
- **Ids de item:** `item-` mais 12 caracteres aleatórios, sem dado da pessoa, e nunca reaproveitados.
- **Tetos de produto, não regra fiscal:** 10 empresas por conta e 500 itens por empresa.

### 6. Segurança

- **Achado:** o limite de corpo valia só para o POST, e o limite por IP só para GET e POST. Os dois passaram a valer para o PATCH. O CORS passou a aceitar o PATCH.
- **`/empresas` e `/referencias/`** têm limite por IP, porque consultam os motores.
- **CSRF:** o PATCH já passava pela defesa dos métodos que mudam o estado. Os testes cobrem PATCH sem Origin, de outra origem e com `Sec-Fetch-Site: cross-site`.
- **Achado no guarda de SQL** (`test_o_sql_do_repositorio_nunca_e_montado_com_texto`): uma f-string na linha seguinte ao `execute(` escapava dele.
  - A consulta de alertas desta etapa caía nisso. Ela virou uma consulta literal, com o CNPJ opcional como parâmetro.
  - O guarda passou a olhar a linha seguinte.
- **As recusas por dado** (`Recusado`, 422) têm frase fixa, sem repetir o que foi enviado.

## Consequências

- **A saída da C3 no backend** está coberta por um teste e foi conferida no modo real com os motores oficiais, num banco temporário:
  - a conta nova cadastra a empresa com CNPJ alfanumérico;
  - cria o item, importa duas notas e vê o alerta;
  - o carrinho sai com as premissas da empresa;
  - a demonstração não muda.
- **Testes:** backend com 586 testes no CI (eram 500) e 54 golden (eram 52), com 97% de cobertura; na tela, 491.
- **A tela ainda não usa as rotas novas** (C3a e C3b; a C3a, com o cadastro da empresa e o cookie nas rotas `/empresas`, está no [ADR 0018](0018-telas-da-empresa-propria.md)):
  - o cliente da tela ainda não manda o cookie da sessão para `/empresas` nem para `/referencias/`;
  - as notas de exemplo ainda aparecem fora da demonstração.
- **Fica para as etapas 7 a 10 da C3-B:** a exclusão e os dados para baixar (LGPD), a limpeza dos bancos órfãos ao subir, a exclusão da empresa sem excluir a conta e o erro 500 sem os cabeçalhos de segurança ([ADR 0009](0009-camada-http-e-erros.md)).

## Etapa 6: os clientes B2B editáveis (2026-11-27)

O cliente B2B é o cliente empresa e a compra mensal dele: a venda que a comparação de regimes usa (`GET /catalogo`, `clientesB2B`). Até aqui, ele só existia nas sementes da demonstração. A tabela `clientes_b2b` já tinha o formato oficial do CNPJ desde a 0003, então a etapa não tem migração.

**Decisões do usuário, validadas antes do código:**
1. Arquivar um item que está na compra mensal de um cliente responde 409, com a lista dos clientes.
2. No máximo 50 clientes por empresa. É um teto de produto, sem fonte fiscal, como os de empresas e itens.
3. Só cliente do regime regular. Um cliente do Simples Nacional é recusado com 422.
4. O cliente é excluído de vez, sem histórico, por `POST /clientes/{cnpj_cliente}/excluir`.
5. A razão social do cliente pode ser dado pessoal (o nome de um empresário individual) e entra nos dados para baixar da etapa 7.

**Rotas:** são rotas do estado, como as do catálogo (espaço, conta ou demonstração com o token).
- **`POST /clientes`:**
  - a empresa que vende (`cnpj`), o CNPJ do cliente, a razão social, o regime, a UF, o município e a compra mensal;
  - o dígito do CNPJ do cliente é exigido só na empresa da conta, como o do fornecedor;
  - o cliente não pode ser a própria empresa;
  - o município é conferido na UF nos dados abertos do motor RR. A consulta fica fora da transação;
  - cada item da compra precisa estar no catálogo da empresa, sem os arquivados, e entra uma vez só;
  - a compra cabe numa comparação: até 200 itens, o mesmo teto do `POST /regime/comparar`;
  - a descrição da compra é um texto fixo do backend. Uma compra igual reenviada guarda a descrição que já tinha (a das sementes, na demonstração).
- **`PATCH /clientes/{cnpj_cliente}`:**
  - muda a razão social, o local (UF e município juntos) ou a compra;
  - o CNPJ do cliente não muda, porque é a chave: outro CNPJ é outro cliente;
  - o regime também não muda, porque só o regular é aceito.
- **`POST /clientes/{cnpj_cliente}/excluir`:** apaga a linha. Nenhuma outra tabela aponta para o cliente.

**A trava do item arquivado:**
- **Achado:** na etapa 5, arquivar o biscoito no espaço deixava a compra do Mercado Bom Preço apontando para um item fora do catálogo. A tela mostrava "não há venda para comparar" (`pedidoDeRegime` devolve null).
- **Conserto:** `POST /catalogo/{item_id}/arquivar` confere os clientes na mesma transação de escrita (`BEGIN IMMEDIATE`) que arquiva. Um cliente gravado ao mesmo tempo não escapa da trava.
- **A resposta** tem um tipo próprio, `409 /problemas/item-em-uso` (RFC 9457), com o membro `clientes` (CNPJ e nome de cada um). A tela pode levar a pessoa até eles. A frase do `detail` é fixa.

**Segurança:**
- **Achado:** `/clientes` não estava na lista das rotas com limite por IP. Ela entrou, porque as rotas gravam e consultam o motor.
- **Achado no contrato:** o OpenAPI listava as recusas dos middlewares (403, 411 e 413) só no POST. O PATCH passa pelas mesmas defesas desde a etapa 5 e agora aparece com elas.
- **Testes:** cobrem a outra conta (404), o token da demonstração, o CSRF (outra origem e o cookie sem `Origin`), o limite de corpo e o por IP, e os erros que não repetem o que foi enviado.

**Verificação:**
- backend com 625 testes no CI (eram 586; 38 em `test_clientes_b2b.py`), 97% de cobertura, e os 54 golden;
- na tela, a lista das rotas com o header do espaço e com o token ganhou as três rotas (`rotas.test.ts` compara com o contrato);
- **no modo real com os motores oficiais**, num banco temporário apagado no fim:
  - a conta cadastra a empresa, o item e a nota, e depois o cliente com CNPJ alfanumérico;
  - o Simples, o dígito errado e o município fora da UF são recusados;
  - a comparação de regimes com a compra do cliente, montada como a tela monta, responde 200;
  - arquivar o item dá 409 com o cliente;
  - alterar e excluir funcionam, e o item sai depois da exclusão;
  - a demonstração não muda.

## Etapa 7: exclusão e dados, LGPD (2026-11-27)

**Fontes lidas:**
- **LGPD, art. 19** (Planalto, texto literal): o acesso aos dados é fornecido "em formato simplificado, imediatamente" (inciso I), "por meio eletrônico, seguro e idôneo para esse fim" (§2º, I) e, quando o tratamento vem do contrato, como "cópia eletrônica integral de seus dados pessoais [...] em formato que permita a sua utilização subsequente" (§3º).
- **Arts. 16, 18 V e VI**, já lidos no mapa da C3 (plano v2.1).
- **Starlette 1.10** (`starlette/middleware/errors.py`): depois de montar o 500, o `ServerErrorMiddleware` relança a exceção. O uvicorn 0.54 a grava em "Exception in ASGI application" com a pilha inteira, mensagem incluída.

**Decisões do usuário, validadas antes do código:**
1. O log de acesso do uvicorn sai e entra um nosso, sem o IP. A Privacidade deixa de dizer que o log grava o IP.
2. Baixar os dados pede a senha de novo (`POST /conta/dados`).
3. Excluir a empresa pede a senha e o CNPJ digitado.
4. O membro também baixa os dados das empresas da organização, e ninguém recebe o e-mail de outro integrante.
5. As etapas 6 a 10 vão num PR só.

**`POST /conta/dados`:**
- só no modo real e com a sessão da conta; sem ela, 401, com ou sem o header do espaço;
- a senha errada conta como falha de entrada (`Contas.conferir_senha`, a mesma da exclusão da conta): a espera da 5ª falha e o bloqueio da 100ª valem aqui;
- a resposta sai com `Content-Disposition: attachment; filename="contaai-dados-AAAA-MM-DD.json"` e `Cache-Control: no-store`;
- **o arquivo (`ContaDadosResposta`, formato `contaai-dados-1`):**
  - a pessoa: o e-mail, a criação, a situação, os termos aceitos, a confirmação do segundo fator, quantos códigos de recuperação restam, as falhas seguidas (se houver), todos os eventos de segurança e as sessões (início, último uso, vencimento e qual é a atual);
  - cada organização da pessoa, com o papel e a data de entrada, e as empresas dela;
  - de cada empresa, como está gravado: a empresa e o cenário, os itens (inclusive os arquivados), os códigos de fornecedor, as notas (chave, sha256 e recibo), os custos, os preços, os alertas, as classificações e os clientes B2B com a razão social;
  - `naoIncluido` diz no próprio arquivo o que fica de fora e por quê: a senha, o segredo do segundo fator, os hashes de código e de token, os passes, o XML das notas e os outros integrantes.
- **Acréscimo ao mapa:** as falhas seguidas de entrada entram no arquivo. Elas são um dado da pessoa, e o mapa não as listava.
- Os documentos JSON gravados (`empresa_json`, `item_json`, `cliente_json`, `alerta_json`, `recibo_json`) saem sem transformação: o arquivo é a cópia do que o ContaAI guarda.
- O banco de uma organização sem empresa não é aberto, porque abrir criaria o arquivo.

**`POST /empresas/{cnpj}/excluir` (204):**
- a ordem dos testes:
  1. sem sessão, 401;
  2. o membro recebe 403;
  3. a empresa de outra conta recebe 404;
  4. o CNPJ digitado diferente recebe 422, sem gastar uma tentativa de senha;
  5. a senha errada recebe 401 e conta como falha de entrada.
- **a ordem da exclusão** (`cadastro.excluir_empresa`):
  1. a empresa sai do banco da organização, e tudo dela vai em cascata (itens, códigos de fornecedor, notas, custos, preços, alertas, classificações e clientes);
  2. depois sai o acesso no `contas.db`, e o contador deixa de alcançá-la.
- uma falha entre os dois deixa só o acesso, sem dado. O recadastro já aceitava esse caso, e a exclusão de novo também o limpa (testado).
- a conta e as outras empresas continuam, e o mesmo CNPJ pode ser cadastrado de novo, do zero.

**Consertos:**
- **Exclusão da conta:** `Contas.excluir` devolvia só a organização da sessão. Agora devolve todas as organizações em que a pessoa era a única integrante, e a rota apaga o banco de cada uma. Hoje não havia caso real, porque ainda não há convites; com a 3c, passaria a haver.
- **Bancos órfãos:** na subida, `limpar_bancos_orfaos` apaga `organizacoes/<id>.db` (e o `-wal`, o `-shm` e o `-journal`) quando o id não existe mais no `contas.db`. Um nome fora do padrão não é apagado e aparece no log só pelo nome. A pasta é lida antes das organizações: a linha da organização nasce antes do arquivo dela, então um arquivo visto nunca é de uma organização ainda não lida.

**Logs sem dado pessoal (`app/api/registro.py`):**
- o log de acesso do uvicorn fica desligado no próprio código (`uvicorn.access` desativado), sem depender de como o servidor é chamado;
- o nosso grava, por fora de todos os middlewares, o método, a rota-modelo, o status e a duração. Uma rota-modelo é, por exemplo, `/empresas/{cnpj}`. Um caminho que não é rota sai como `-`;
- as recusas dos middlewares (403, 411, 413 e 429) também entram. Elas acontecem antes do roteamento, então a rota-modelo sai da comparação com as rotas incluídas. No FastAPI 0.165, essas rotas ficam dentro de um `_IncludedRouter`;
- **erro não tratado:**
  - o nosso 500 grava só o tipo da exceção e os últimos quadros da pilha (arquivo:linha em função), sem a mensagem;
  - o mesmo filtro vale para o logger `uvicorn.error`, que grava a exceção relançada pelo Starlette;
- o logger `contaai` passou a ter uma saída própria em INFO. Antes, sem handler, só WARNING ou mais aparecia (`logging.lastResort`).

**Na tela:**
- `POST /conta/dados` entrou nas rotas da conta e nas de entrada (`rotas.ts`). O 401 dela quer dizer "senha incorreta", e não "a sessão acabou";
- `POST /empresas/{cnpj}/excluir` fica para a C3b, junto com o cookie da sessão em `/empresas`. A lista das rotas de entrada só aceita rotas da conta (`rotas.test.ts`);
- a Privacidade diz o que o log técnico grava (atualizada em 27/11/2026). Baixar os dados e excluir a empresa entram na seção dos direitos quando a tela delas existir (C3b).

**Verificação:**
- backend com 649 testes (eram 625; 24 em `test_exclusao_e_dados.py`) e 97% de cobertura. `registro.py` e `dados_da_conta.py` têm 100%;
- tela com 492 testes, lint, tipos, build e `npm run seguranca` ok; `rotas.test.ts` confere a rota nova contra o contrato;
- `pip-audit` (como no CI) e `npm audit` sem vulnerabilidades. Nenhuma dependência nova;
- **no modo real com os motores oficiais** (RR 1.7.2 e SN 1.0.2), num banco temporário apagado no fim, 34 conferências:
  - a conta cadastra a empresa, o item, duas notas (com o alerta) e um cliente com CNPJ alfanumérico;
  - baixa o arquivo com a senha (a errada dá 401 e aparece nas falhas seguidas), sem o segredo, a senha ou um hash;
  - exclui a empresa (o CNPJ digitado errado dá 422) e depois a conta, e o banco da organização sai;
  - um banco órfão posto na pasta sai na subida seguinte;
  - a demonstração não muda;
  - a saída real do uvicorn tem só as linhas do nosso log de acesso (`POST /empresas/{cnpj}/excluir 204 49 ms`), sem o IP, sem o CNPJ e sem o e-mail.

## Etapa 8: os papéis na organização (2026-11-27)

**Onde estava:** o plano dava a etapa 8 por feita, porque o 403 do dono já existia no cadastro, nas configurações e na exclusão da empresa. A conferência no código achou quatro lacunas:
- **a edição não conferia o papel.** O catálogo, os clientes, as notas, os preços, os alertas e as classificações aceitavam qualquer sessão da organização. Hoje só existem o dono e o membro (o CHECK de `membros`), e os dois editam; mas um papel novo, como o contador do 3c, passaria a editar sem ninguém decidir. Isso contraria a decisão de que o contador só sugere;
- **a regra do dono estava em dois lugares,** com o teste do papel escrito à mão em cada um;
- **nenhum teste tinha um membro de verdade.** Os testes rebaixavam a própria dona a membro, e nenhum conferia que o membro edita;
- **o contrato:**
  - o `GET /empresas/{cnpj}` declarava um 403 que nunca acontece;
  - nas rotas da empresa, o 403 do dono escondia o 403 do CSRF;
  - o `DELETE /sessoes` e o `DELETE /sessoes/atual` passam pela defesa contra CSRF, mas não declaravam o 403;
  - o 403 da restauração com a sessão não aparecia.

**Decisão:**
- **as listas dizem quem pode, nunca quem não pode** (`app/api/dependencias.py`):
  - `PAPEIS_QUE_EDITAM = {dono, membro}`: o catálogo, os clientes B2B, as notas, os preços, os alertas e as classificações;
  - `PAPEIS_QUE_ADMINISTRAM = {dono}`: cadastrar, configurar e excluir a empresa;
  - ler vale para todo integrante: a empresa, o catálogo, os alertas, as notas, a explicação e o chat;
  - um papel que não está numa lista recebe 403, e o 3c precisa pôr o contador nelas de propósito.
- **um ponto só para a edição:** `exigir_permissao_para_mudar` (antes `exigir_token_fora_do_espaco`), chamado por toda rota de edição:
  - na demonstração compartilhada, pede o token;
  - no espaço de avaliação, nada a mais;
  - no banco da organização, confere o papel.
- **a ordem das recusas:**
  - o 403 do papel vem antes de olhar a empresa, o item ou a senha;
  - por isso o membro recebe o mesmo 403 para um CNPJ que existe e para um que não existe, e a senha não é gasta.
- **o papel vale a cada pedido.** A sessão lê o papel em `membros` a cada pedido (já era assim desde a C1). Rebaixar ou promover alguém vale na hora, e quem sai da organização recebe 401.
- **no OpenAPI:**
  - o 403 de cada rota se soma ao do CSRF (`problemas._somar_csrf`);
  - todo método que muda o estado declara o 403 do CSRF. A lista `METODOS_INSEGUROS` passou para `app/seguranca.py`, de onde o middleware e o OpenAPI a leem;
  - as rotas de edição declaram o 403 do papel (`respostas.PAPEL`);
  - o `GET /empresas/{cnpj}` não declara mais o 403.

**Testes (`tests/test_papeis.py`, 8):**
- o membro, com a conta dele e a sessão levada à organização da dona, faz cada edição. A dona vê o que ele mudou;
- o membro lê a empresa, mas não a cadastra, não a configura e não a exclui. O 403 não gasta uma tentativa de senha;
- o papel muda no meio da sessão (rebaixar, promover e tirar da organização);
- com a lista de edição vazia, as 10 rotas de edição recusam a própria dona e nada muda. A demonstração e os espaços não dependem do papel. A conferência no negativo: tirar a checagem do papel faz este teste falhar;
- com a lista de administração vazia, as 3 rotas da empresa recusam;
- **o inventário:** toda rota que muda o estado está numa das três listas (edição, administração, fora do banco da organização). Uma rota nova do 3c falha o teste até ser classificada;
- o contrato declara o 403 de cada papel, junto com o do CSRF.

**Verificação:**
- backend com 657 testes (eram 649) e 97% de cobertura; 54 golden; ruff, format e mypy ok;
- tela com 492 testes, lint, build, `npm run seguranca` e `contrato:checar` ok. Os tipos foram gerados de novo, e só mudaram as descrições;
- `pip-audit` (como no CI) e `npm audit` sem vulnerabilidades. Nenhuma dependência nova;
- **no modo real com os motores oficiais** (RR 1.7.2 e SN 1.0.2), num banco temporário apagado no fim, 30 conferências:
  - a Bia entra como membro na organização da Ana;
  - ela cria o item, importa duas notas, aplica o alerta, lança o preço e cria, altera e exclui um cliente com CNPJ alfanumérico;
  - ela recebe 403 ao cadastrar, configurar e excluir a empresa;
  - promovida a dona, configura na hora; tirada da organização, recebe 401;
  - a demonstração não muda;
  - o log grava `PATCH /empresas/{cnpj} 403` sem o CNPJ, os e-mails e o IP.

**Para o 3c:**
- os convites, o seletor de organização e a troca de papel;
- o contador entra nas listas de papéis só onde a decisão 3 deixa (ele sugere, não aplica);
- tirar alguém da organização também deve apagar as sessões dele naquela organização. Hoje a sessão só deixa de valer (401), e a linha fica até a limpeza das sessões vencidas (`Contas._limpar`: 30 min sem uso ou 8 h no total).

## Etapa 9: as proteções e o erro 500 (2026-11-27)

**Fontes lidas** (o código instalado, no `backend/.venv`):
- **Starlette 1.10** (`starlette/middleware/errors.py`): o `ServerErrorMiddleware` usa o tratador de `Exception` registrado, manda a resposta se ela ainda não começou e relança a exceção "para os servidores registrarem o erro".
- **FastAPI 0.165** (`fastapi/applications.py`, `build_middleware_stack`): a ordem da pilha é `ServerErrorMiddleware`, `ExceptionTelemetryMiddleware`, `AppBodyLimitMiddleware`, os nossos middlewares, `ExceptionMiddleware` e `AsyncExitStackMiddleware`. O tratador de `Exception` vai para o primeiro, por fora de todos os nossos.
- **FastAPI 0.165, telemetria** (`fastapi/telemetry/_api.py`, `_asgi.py` e `_runtime.py`):
  - a opção `logs` diz, na documentação do próprio pacote: "Record validation failures and unhandled exceptions, including exception messages and stack traces. Defaults to `True`";
  - `TelemetryData.body` guarda "the body read by FastAPI";
  - ela só liga com um provedor do OpenTelemetry configurado. A exportação automática pede `FASTAPI_OTEL_AUTO_CONFIGURE=true` e os pacotes de SDK e de exportador;
  - no projeto só está o `opentelemetry-api` 1.45.2, que é dependência do FastAPI. Hoje, portanto, nada é gravado nem enviado.

**Reproduzido antes do conserto:** uma rota que levanta `RuntimeError` dava 500 com `application/problem+json`, mas sem `nosniff`, sem CSP, sem `X-Frame-Options`, sem `Cache-Control: no-store` e sem `Access-Control-Allow-Origin`. A tela de outra origem nem conseguia ler o erro. O corpo e o log já estavam sem a mensagem (etapa 7).

**Decisão:**
- **`ErroNaoTratado`** (`app/api/middlewares.py`) é um middleware ASGI puro e o primeiro a ser adicionado, portanto o mais de dentro:
  - a exceção da rota vira o 500 ali mesmo (`problemas.erro_interno`), e a resposta volta pelos outros middlewares como qualquer outra. Ela recebe os cabeçalhos de segurança, o CORS da origem permitida e a linha do log de acesso;
  - a exceção não segue para o servidor. O registro é só o nosso (o tipo e os quadros da pilha, sem a mensagem), e o uvicorn deixa de gravar "Exception in ASGI application";
  - se a resposta já tinha começado, ela não pode ser trocada, e a exceção segue para o Starlette.
- **A falha dentro de um middleware** é pega no `cabecalhos_de_seguranca`, que monta o mesmo 500 com os cabeçalhos. O CORS fica de fora nesse caso, porque a exceção atravessa o middleware dele.
- **O tratador antigo** (`_inesperado`, no `ServerErrorMiddleware`) fica como último recurso, para uma falha no próprio log de acesso ou nos cabeçalhos.
- **A frase do 500** passou a ser "Erro interno. Tente de novo em instantes.". A anterior dizia "avise a equipe", mas o ContaAI não publica um contato (decisão 4 da C2).
- **A telemetria do FastAPI fica desligada no código** (`FastAPI(telemetry=...)`, com tracing, métricas, logs, spans de operação e configuração automática em `False`). Nem a variável `FASTAPI_OTEL_AUTO_CONFIGURE` nem um SDK instalado depois a ligam. Ligar observabilidade na E6 é decisão nova, e o que ela grava precisa de filtro.
- **O `GET /saude` entrou no limite geral por IP** (120 por minuto). Ele consulta a versão dos dois motores a cada pedido, e a regra do [ADR 0006](0006-agente.md) é "rotas que chamam os motores: 120 por minuto". A tela o chama uma vez por carga.
- **O contrato** declara o 500 em toda rota (`problemas.ERRO_INTERNO`).

**Testes (`tests/test_erro_interno.py`, 8):**
- o 500 da rota sai com os cabeçalhos e o CORS, mesmo com o `TestClient` repassando exceções (o padrão). O log tem uma linha do erro, sem a mensagem, e nada do `uvicorn.error`;
- uma origem fora da lista não recebe o CORS no 500;
- o 500 de um middleware sai com os cabeçalhos;
- a resposta já começada não é trocada;
- o 500 está no contrato de toda rota;
- a telemetria está desligada;
- **o inventário:** toda rota tem limite por IP ou está em `SEM_LIMITE` com o motivo (lê o banco ou dados fixos, sem motor nem IA, ou só encerra a sessão da pessoa);
- o `/saude` dá 429 depois do limite.
- **Conferência no negativo:** sem o `ErroNaoTratado`, o teste do 500 da rota falha; sem a rede no dos cabeçalhos, o teste do middleware falha.
- **Três testes antigos dependiam do comportamento velho:**
  - dois esperavam a exceção passar ao `TestClient` e agora conferem o 500 tratado;
  - um usava o `/saude` como exemplo de rota sem limite e agora usa o `GET /cenarios/presets`;
  - o teste do 500 em `test_problemas.py` deixava a rota de teste no app até o fim da bateria. No FastAPI 0.165, o `include_router` a embrulha, e a limpeza pelo caminho não a achava. A rota agora entra direto no roteador.

**Verificação:**
- backend com 665 testes (eram 657) e 97% de cobertura; 54 golden; ruff, format e mypy ok;
- tela com 492 testes, lint, build, `npm run seguranca` e `contrato:checar` ok. Os tipos foram gerados de novo, e só entrou o 500;
- `pip-audit` (como no CI) e `npm audit` sem vulnerabilidades. Nenhuma dependência nova;
- **no uvicorn real, com os motores oficiais** (RR 1.7.2 e SN 1.0.2), 25 conferências. A rota que falha de propósito foi posta só pelo roteiro, fora do repositório:
  - o 500 sai com os seis cabeçalhos de segurança, `problem+json` e o CORS da tela, e a outra origem não recebe o CORS;
  - o corpo sai sem a mensagem;
  - o `/saude` responde `ok` nos motores e dá 429 no 4º pedido com o limite em 3;
  - o log tem o 500, o tipo e o lugar do erro, e nenhuma linha "Exception in ASGI application", nem o e-mail, o CNPJ, o caminho do arquivo ou o IP.
- **Ambiente:** no Windows, o console grava o log em cp1252, e o "não" sai trocado ao ler em UTF-8. Não é defeito do código. A codificação do log no container da E6 não foi conferida (a conferir no deploy).

## Etapa 10: o contrato, o mock e o fechamento da C3-B (2026-11-27)

**Conferências:**
- **o contrato:** o `docs/contrato/openapi.json` reexportado bate com o código (`test_openapi_exportado_esta_atualizado`), e os tipos da tela também (`npm run contrato:checar`);
- **o mock, rota por rota:** com o modo padrão, 12 rotas respondem com os mocks (com `X-ContaAI-Mock: 1`), 3 são fixas (a saúde, os tipos de problema e as premissas da simulação) e 29 só existem no modo real e respondem 501. Até aqui, o 501 das rotas novas estava em testes avulsos, um por arquivo, e algumas (`PATCH /empresas/{cnpj}`, `PATCH /catalogo/{item_id}`, `POST /catalogo/{item_id}/arquivar`, `POST /conta/dados`, `GET /referencias/municipios`) não tinham nenhum.

**Decisão:** `tests/test_modo_mock.py` (32 testes) põe cada rota do contrato num dos três grupos:
- uma rota nova, fora dos grupos, faz o inventário falhar até alguém decidir onde ela entra, e uma rota apagada também;
- só as rotas do modo real declaram o 501 no OpenAPI;
- cada rota do modo real recebe um pedido válido, porque o 501 vem depois da validação do FastAPI e um corpo inválido daria 422. Ela responde 501 em `application/problem+json`, sem cookie e sem o marcador do mock;
- nenhum método que muda o estado responde 2xx no mock sem o marcador. Os cinco POST servidos pelo mock calculam ou leem, sem gravar.
- **Conferência no negativo:** sem o `so_no_modo_real` em `POST /conta/dados`, o teste falha (a rota responde 401 no mock).

**Achados na varredura do projeto:**
- o README dizia que, no modo mock, "todas as rotas respondem com mocks". Não é assim: as que gravam, as das contas e as da empresa própria respondem 501;
- o README e o `backend/README.md` paravam na etapa 6: sem o arquivo dos dados, a exclusão da empresa, os papéis e os logs. A tabela do `backend/README.md` não tinha `app/contas/` (desde a C1), `app/cnpj.py` e `app/cadastro.py` (desde o #26), `app/dados_da_conta.py` e `app/api/registro.py`;
- o cabeçalho deste ADR ainda dizia "etapas 1 a 6", e o "Onde estamos" do plano não tinha as etapas 8 a 10.

**Verificação da C3-B inteira, no código final:**
- backend com 697 testes (eram 665) e 97% de cobertura; 54 golden; ruff, format e mypy ok;
- tela com 492 testes, lint, tipos, build, `npm run seguranca` e `contrato:checar` ok;
- `pip-audit` (como no CI) e `npm audit` sem vulnerabilidades. Nenhuma dependência nova na C3-B;
- **no modo real, com os motores oficiais** (RR 1.7.2 e SN 1.0.2), os roteiros das etapas rodaram de novo, num banco temporário: as etapas 1 a 5 (a empresa, o item, as notas, o alerta e o carrinho com as premissas da empresa), a 6 (o cliente, a comparação e o 409), a 7 (34 conferências), a 8 (30) e a 9 (25). A demonstração não mudou;
- **o mock no uvicorn real:** as 29 rotas do modo real respondem 501 com os cabeçalhos de segurança e o CORS da tela, `GET /alertas` sai marcado, e nenhum banco é criado.

**Consequências:**
- a C3-B está fechada. As telas da C3a e da C3b usam as rotas daqui, com o que ficou anotado no [plano v2.1](../plano-v2.1.md) ("Para a C3a e a C3b");
- uma rota nova precisa de lugar no inventário do mock, do limite por IP (etapa 9) e dos papéis (etapa 8).

## Revisão da C3b: o item a partir da nota (2026-11-28)

Ficou do 3b cadastrar o par de um item sem par a partir da nota. O mapa da C3b achou dois problemas no backend: o item sem par do recibo não trazia a unidade (`uCom`), que o item novo exige e que o casamento confere; e cadastrar o item depois não pegava o custo daquela nota, porque reimportar a mesma nota devolve o recibo antigo (`jaImportada`) e o XML não fica guardado. O usuário escolheu que o item nasça com o custo da nota (decisão b1, no [plano v2.1](../plano-v2.1.md), "C3b").

**Decisão:**
- **O recibo guarda o que o par precisa:** cada `ItemNotaSemPar` passa a ter a causa (`semCadastro`, `repetido`, `ncm`, `unidade` ou `monofasico`), a unidade (em maiúsculas, como o casamento compara), a quantidade, o custo, o valor (`vProd`) e o crédito do grupo IBSCBS da linha. Nos recibos anteriores, esses campos ficam vazios.
- **`POST /catalogo/itens` aceita `daNota`** (série, número e nItem). A nota é procurada pelo fornecedor do item (`cnpjFornecedor`): uma nota de outro fornecedor, ou de outra empresa, responde como inexistente (404). Só a linha de código sem cadastro vira item, e o código, a NCM e a unidade precisam ser os da linha (422). Uma linha já cadastrada dá 409. Um código que aparece mais de uma vez na nota é recusado (422), como a importação faz com o item que já existe.
- **O crédito:** o da nota, quando a linha tem o grupo IBSCBS; sem o grupo, o do motor RR sobre o custo, na data da nota e com as alíquotas do cenário da empresa (`creditos_pelo_motor`, a mesma função da importação agora). O motor recebe a classificação escolhida no cadastro do item.
- **Uma transação:** o item, o preço, o custo e a linha do recibo marcada com o item (`itemCadastrado`). O recibo é trocado só se ainda é o lido (`Sessao.trocar_recibo`, uma troca conferida no próprio `UPDATE`); se outro cadastro a partir da mesma nota entrou no meio, nada é gravado (409).
- **Sem custo anterior, não há alerta:** o custo da nota é o primeiro do item. O alerta vem com a nota seguinte do fornecedor, se a margem cair.
- **`GET /notas`** conta, em `itensSemPar`, só as linhas que ainda não viraram item.
- **A linha monofásica sem cadastro** diz agora a causa certa (`monofasico`); antes dizia "código sem cadastro", e cadastrar o item não faria a nota casar.

**Consequências:**
- `tests/test_par_da_nota.py` (18): o recibo novo, o custo da nota e o alerta na nota seguinte, o crédito pelo motor na data da nota, as recusas, a nota de outro fornecedor, a linha já cadastrada, a de outra causa, a monofásica, o código repetido, o recibo anterior à C3b, a troca do recibo (com o método trocado e direto no banco) e o espaço de avaliação. Backend com 715 testes e 97% de cobertura, 54 golden.
- **Conferências no negativo:** sem a conferência da unidade e sem a troca conferida do recibo, um teste falha. A primeira versão do teste da troca trocava o próprio método e não pegava a falta da conferência; o teste direto no banco foi escrito por isso.
- **No modo real, com os motores oficiais:** a linha guarda o crédito da nota (0,3649 por unidade na nota de exemplo); o item nasce com o custo de 3,50 e esse crédito; a nota seguinte (4,10) gera o alerta; a linha cadastrada não entra de novo; e, sem o grupo IBSCBS, o crédito vem do motor RR (0,3115).
- Frases dos padrões novos (série e número da nota) em `mensagens.py`, o OpenAPI reexportado e os tipos da tela. No modo mock, a rota continua 501 (inventário da etapa 10), com o mesmo limite por IP e os mesmos papéis.
- A tela usa `daNota` na etapa 8 da C3b (feito na C3b2, seção da C3b2 no [ADR 0018](0018-telas-da-empresa-propria.md)).

## Revisão da C3b2: o fornecedor no catálogo e o recibo de uma nota gravada (2026-11-28)

O mapa das etapas 6 a 9 da C3b (as telas do catálogo, do par da nota e dos clientes) achou dois buracos no backend. O usuário escolheu fechar os dois antes das telas (A1 e B1, no [plano v2.1](../plano-v2.1.md), "C3b").

**Os achados:**
- **o `GET /catalogo` não dizia o fornecedor do item.** O `PATCH /catalogo/{item_id}` muda o CNPJ e o código do fornecedor, mas a resposta do item não os trazia (eles ficam em `codigos_fornecedor`). A tela de alterar não teria o valor atual para mostrar;
- **o recibo de uma nota antiga só voltava com o XML.** O `GET /notas` traz as contagens, não as linhas. Cadastrar uma linha sem par depois dependia de a pessoa ter guardado o arquivo e importá-lo de novo (o recibo volta com `jaImportada`).

**Decisão:**
- **`fornecedor` em cada item** (`ItemCatalogoEstado.fornecedor`, com `cnpj` e `codigo`): no `GET /catalogo` e em toda resposta que traz o item (criar, alterar, corrigir a classificação). Na demonstração, os fornecedores e os códigos são os fictícios das sementes.
- **`GET /notas/{cnpj_emitente}/{serie}/{numero}?cnpj=`** devolve `importadaEm` e o recibo gravado (`NfeImportarResposta`), sem chamar os motores e sem gravar. As linhas sem par que já viraram item citam o item (`itemCadastrado`). Os alertas vêm com o `aplicadoEm` atual, porque o recibo gravado guarda o estado do momento da importação. O `jaImportada` fica como foi gravado (falso): a leitura não é uma importação.
- **Quem lê:** as mesmas regras do `GET /notas`. Uma nota de outra empresa, de outro fornecedor, de outra série ou de outra conta recebe o 404 de uma nota que não existe. Uma nota ainda sem recibo fica de fora, como na lista. Os padrões da série e do número são os do `daNota`.
- **Os inventários:** sem limite por IP (lê o banco, como o `GET /notas`, com o motivo em `test_erro_interno.py`); servida pelo mock (`test_modo_mock.py`), com o recibo de cada nota do `notas.json` em `notas-recibos.json`, gerado pelos motores (`gerar_mocks.py`). A tela a declara entre as rotas com o header do espaço.

**Consequências:**
- `tests/test_recibo_da_nota.py` (19): o recibo igual ao da importação, os alertas no estado atual, as linhas sem par de uma nota antiga, a linha cadastrada a partir da leitura (sem o XML), os 404 (nota que não existe, outra série, outro emitente, outra empresa, outro espaço e outra conta), os 422 do caminho, o mock (cada nota da lista tem o recibo, e o da nota mais recente é o do mock da importação) e o fornecedor no catálogo (das sementes, e o alterado pelo `PATCH`). Backend com 734 testes (eram 715) e 97% de cobertura; tela com 556; ruff, format, mypy, `contrato:checar`, lint, build e `npm run seguranca` ok. Nenhuma dependência nova.
- Os mocks gerados de novo pelos motores: muda só o `catalogo.json` (o fornecedor) e entra o `notas-recibos.json`; os outros saem iguais byte a byte (golden 54).
- **No modo real, com os motores oficiais (uvicorn):** o recibo lido da nota 2 é igual ao da importação; depois de aplicar o alerta, a leitura traz o `aplicadoEm`; a nota que não existe e a de outra empresa dão 404; a resposta sai com `no-store`, `nosniff` e o CORS da tela; o catálogo traz o fornecedor dos cinco itens.
- O OpenAPI reexportado e os tipos da tela. A fixture `catalogo.json` da tela ganhou só o campo novo (o resto confere byte a byte com o da gravação), com os mesmos valores do mock.
