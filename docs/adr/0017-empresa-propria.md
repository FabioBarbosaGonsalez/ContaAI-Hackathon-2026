# ADR 0017: a empresa própria no backend, o CNPJ alfanumérico e o catálogo editável (C3-B)

- Status: aceito (etapas 1 a 5 da C3-B; as etapas 6 a 10 seguem no [plano v2.1](../plano-v2.1.md))
- Data: 2026-11-27
- Etapa: C3-B do plano v2.1 (as telas vêm na C3a e na C3b)
- Código: `backend/app/cnpj.py`, `backend/app/cadastro.py`, `backend/app/api/rotas/empresa.py`, `backend/app/persistencia/migracoes/0003_empresa_propria.sql`, `backend/app/persistencia/banco.py` (`migrar`), `backend/app/persistencia/repositorio.py`, `backend/app/motores/dados_abertos.py` (UF, município e atividade), `backend/app/empresa.py` (rótulos das premissas), `backend/app/contas/servico.py` (`vincular_empresa`), `backend/app/api/middlewares.py`, `frontend/src/dados/formatar.ts`, `frontend/src/api/rotas.ts`, `backend/tests/test_cnpj.py`, `test_migracao_0003.py`, `test_empresa_propria.py` e `test_empresa_golden.py`

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
- **A tela ainda não usa as rotas novas** (C3a e C3b):
  - o cliente da tela ainda não manda o cookie da sessão para `/empresas` nem para `/referencias/`;
  - as notas de exemplo ainda aparecem fora da demonstração.
- **Fica para as etapas 6 a 10 da C3-B:** os clientes B2B editáveis, a exclusão e os dados para baixar (LGPD), a limpeza dos bancos órfãos ao subir, a exclusão da empresa sem excluir a conta e o erro 500 sem os cabeçalhos de segurança ([ADR 0009](0009-camada-http-e-erros.md)).
