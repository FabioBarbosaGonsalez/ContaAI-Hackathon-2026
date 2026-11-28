# ADR 0018: as telas da empresa própria, a primeira vez e o cadastro da empresa (C3a)

- Status: aceito (C3a; a C3b entra em seções do fim: as etapas 1 a 5 estão feitas, as 6 a 9 vêm na C3b2)
- Data: 2026-11-27
- Etapa: C3a do [plano v2.1](../plano-v2.1.md), depois do backend da C3-B ([ADR 0017](0017-empresa-propria.md))
- Código:
  - `frontend/src/dados/empresa.ts` (`useEmpresaDaTela`, `useCnpjDaTela`, `catalogoVazio`, a origem e a gravação na conta, `useNotas(pedir)`);
  - `frontend/src/api/rotas.ts` (`ROTAS_DA_EMPRESA`) e `frontend/src/sessao/middleware.ts`;
  - `frontend/src/sessao/conta.ts` (`SessaoConta.cadastrarEmpresa`);
  - `frontend/src/telas/CadastroDaEmpresa.tsx`, `regrasDeEntrada.ts` (CNPJ e razão social), `formulario.tsx` (`CampoDeLista` e `GrupoDeOpcoes`), `empresa.css`, `PortaDaConta.tsx` (`paraQue`);
  - `frontend/src/shell/` (`rotas.ts` com `/empresa/nova`, `paginas.tsx` com a `PrimeiraVez`, `Shell.tsx`);
  - `frontend/src/telas/Painel.tsx`, `Catalogo.tsx`, `Notas.tsx`, `Dialogos.tsx`, `Explicacao.tsx` e `Privacidade.tsx`;
  - `frontend/src/api/cliente.ts` (o tempo limite que não depende da cópia da `Request`);
  - C3b, etapas 3 a 5: `frontend/src/telas/ConfiguracoesDaEmpresa.tsx`, `camposDaEmpresa.tsx` (os campos divididos com o cadastro), `Conta.tsx` (baixar os dados), `regrasDeEntrada.ts` (a alíquota do DAS e o CNPJ da confirmação), `frontend/src/sessao/conta.ts` (`excluirEmpresa`, `baixarDados`, `nomeDoArquivo`), `frontend/src/api/cliente.ts` (`chamarComCabecalhos`), `frontend/src/shell/` (`/empresa`, o menu da conta e a `acao` da `Pagina`) e `Painel.tsx`;
  - testes: `frontend/src/telas/empresa.test.tsx` e as fixtures `*-empresa-nova.json`, `empresa-cadastrada.json`, `erro-empresa-*.json`, `erro-nota-outro-destinatario.json` e `referencias-*.json`.

## Contexto

A C3-B deixou a conta cadastrar a empresa pela API. A tela ainda mostrava, na conta, o estado vazio da C2 ("o cadastro da empresa ainda não está disponível"), e as telas do app pediam sempre o CNPJ fixo da Serra Azul. A C3a troca o estado vazio pelo cadastro e faz as telas mostrarem a empresa da conta.

O mapa, gravado no plano antes do código, achou:

1. **O CNPJ fixo** estava em `useCatalogo`, `useAlertasAbertos` e `useNotas`, na explicação e nos diálogos de preço e de classificação.
2. **O catálogo vazio:** o `POST /carrinho/calcular` exige pelo menos um item (`minItems: 1`). A empresa recém-cadastrada não tem itens, e a tela pediria um cálculo que volta 422.
3. **O cookie:** quem tem conta e está vendo a demonstração manda os pedidos sem o cookie. Um `POST /empresas` dali receberia 401 com a sessão aberta.
4. **As notas de exemplo** apareciam na conta, e a API recusa a nota de outro destinatário (422, conferido na API real e gravado em `erro-nota-outro-destinatario.json`).
5. **A Privacidade** listava só os dados da conta.

## Conferido antes do código (2026-11-27)

| O quê | Onde | Resultado |
|---|---|---|
| A ordem das empresas no `GET /conta` | `backend/app/contas/servico.py` | `ORDER BY cnpj`: até o seletor do 3c, a tela abre a primeira |
| O que vai às calculadoras | `backend/app/motores/requisicoes.py` | os itens, a data, a UF, o município, o anexo e a atividade. Nunca o CNPJ nem a razão social |
| As referências | API real com os motores RR 1.7.2 e SN 1.0.2 | 27 UFs (sem o "EX"), com o nome em maiúsculas; 646 municípios em SP e 497 no RS; 4 atividades (01 e 02 no anexo I, 03 e 04 no anexo II), na data do cenário (16/03/2027) |
| A definição do híbrido | [ADR 0003](0003-contrato-da-api.md), item 1 e a opção pelo regime regular | no tradicional, a CBS e o IBS ficam dentro do DAS; no híbrido, são cobrados por fora (LC 214/2025, art. 41, §3º) |
| O dígito do CNPJ | [ADR 0017](0017-empresa-propria.md), seção 1 (manual do Serpro) | o mesmo cálculo na tela, com o exemplo do manual (12ABC34501DE35) e o CNPJ numérico do teste do backend |
| O que a empresa guarda | `backend/app/persistencia/migracoes` e `app/dados_demo.py` | a empresa e o cenário; os itens, os custos, os preços, as classificações e os alertas; das notas, o emitente, a série, o número, a data, o sha256 e o recibo (sem o XML); dos clientes, o CNPJ, a razão social, o regime, a UF, o município e a compra mensal |

## Decisão

### 1. A empresa da tela (`useEmpresaDaTela`)

- **Uma fonte só** para o CNPJ de todo pedido de dados:
  - `demonstracao`: a demonstração compartilhada, um espaço ou a conta vendo a demonstração, com o CNPJ da Serra Azul;
  - `conta`: a primeira empresa do `GET /conta`;
  - `sem-empresa`, com o papel: nenhum dado é pedido;
  - `esperando`: a API ou a conta ainda não responderam.
- **A origem dos dados** na conta é `conta:<id da organização>`, e a chave de todo dado leva também o CNPJ. Trocar de conta, de espaço ou de empresa nunca mostra o dado da anterior.
- **A gravação na conta:** o dono e o membro gravam, como no backend ([ADR 0017](0017-empresa-propria.md), etapa 8).
- **Os diálogos e a explicação:** a classificação usa o CNPJ do próprio catálogo aberto; o preço e a explicação usam o CNPJ da tela.

### 2. O cookie nas rotas da empresa

- `ROTAS_DA_EMPRESA` (`POST /empresas`, `GET` e `PATCH /empresas/{cnpj}` e `POST /empresas/{cnpj}/excluir`) sempre leva o cookie, também com a conta vendo a demonstração, e nunca o espaço nem o token. O teste compara a lista com os caminhos `/empresas` do contrato.
- **`POST /empresas/{cnpj}/excluir` entra nas rotas de entrada:** o 401 dela é a senha errada e não encerra a sessão na tela. A regra do teste mudou de "rotas da conta que declaram 401" para "rotas que sempre levam o cookie e declaram 401". A tela da exclusão é da C3b, mas a lista já fica certa, porque uma rota com o cookie fora das de entrada encerraria a sessão no 401.
- `/referencias/` é pública: leva o cookie só quando a tela está na conta, como as outras rotas de dados.

### 3. A primeira vez

- Na conta sem empresa, as páginas do app mantêm o título e mostram, no lugar dos dados, "Cadastre a empresa para começar". A frase diz o que o ContaAI faz e o que ele precisa, com o botão "Cadastrar a empresa" e o caminho para a demonstração.
- **O membro** (que só existe com os convites do 3c) lê que só o dono cadastra a empresa.

### 4. A página "Cadastrar a empresa" (`/empresa/nova`)

- Fica no app, fora dos destinos, como `/conta`. Quem não entrou vê "Entre para cadastrar a sua empresa". No modo mock, as contas não existem.
- **Quem estava vendo a demonstração** volta aos dados da conta ao abrir a página.
- **Uma empresa por conta até o seletor do 3c:** com uma empresa, a página leva ao Painel. Uma segunda ficaria invisível sem o seletor. O teto do backend (10) não muda.
- **Os campos:**
  - CNPJ com ou sem a pontuação. Vai sem ela e em maiúsculas, e o dígito é conferido na tela, com a frase do backend;
  - razão social sem os espaços das pontas, até 150 caracteres contados como o backend conta, sem caractere de controle;
  - o regime em duas opções, com a definição do ADR 0003. A ajuda diz que o MEI e o lucro presumido ou real não são atendidos;
  - UF e município em listas da API, com a fonte impressa. O município espera a UF;
  - a atividade em opções da API, com o código, o anexo e a fonte.
- **O erro de cada campo some quando a pessoa o corrige.** O primeiro campo com erro recebe o foco.
- **O quadro ao lado** diz só o que foi conferido no código:
  - o CNPJ é conferido pelos dígitos e não é consultado na Receita;
  - o mesmo CNPJ pode estar em outra conta;
  - as listas vêm das calculadoras, e a atividade define o anexo;
  - os cálculos começam com as premissas da simulação, na data do cenário;
  - as calculadoras recebem os itens, a data, a UF, o município e a atividade, nunca o CNPJ nem a razão social.
- **Depois do 201,** a conta passa a ter o CNPJ da resposta, sem outro `GET /conta`. Um `GET /conta` antigo que chega depois não o tira (o contador `versao`). A tela vai ao Painel com o endereço trocado.
- **O 409** (outra aba cadastrou) lê a conta de novo e oferece o Painel. O 429 mostra a espera, como nos formulários da conta.

### 5. As telas com a empresa nova

- **O Painel sem itens** diz "Nenhum item no catálogo ainda" no lugar das margens. Mostra a empresa cadastrada (razão social, CNPJ, regime, município e cenário) e a última nota. O subtítulo é a descrição do cenário, como no Regime antes da resposta.
- **O Catálogo sem itens** diz o mesmo, sem a troca de regime, sem as premissas e sem pedir o cálculo.
- **O Regime** já dizia "Nenhum cliente empresa cadastrado".
- **As Notas** liberam a importação na conta, e as notas de exemplo aparecem só na demonstração e nos espaços.
- Nenhuma frase promete os itens e os clientes, que entram pela C3b.

### 6. A Privacidade

- **O que fica guardado** da empresa, no espaço da organização: a empresa, o catálogo e o histórico, os clientes e, das notas, o emitente, a série, o número, a data, o resumo e o recibo. A página avisa que o XML não é guardado e que o ContaAI não é o arquivo fiscal (a frase da C3, decisão da exclusão).
- **Com quem é compartilhado:** as calculadoras recebem os itens e a operação, nunca o CNPJ, a razão social ou um dado pessoal.
- **Por quanto tempo:** enquanto a organização existir. A exclusão da conta da única pessoa apaga tudo.
- **Baixar os dados e excluir a empresa** entram nos direitos quando as telas deles existirem (C3b).

## Achados durante o código

- **O Painel dizia "Nenhuma nota importada ainda" depois de uma nota toda sem par.** O bloco tira a última nota do custo dos itens, e sem item casado não há custo. Conferido no Chrome com a API real. Isso vinha do 3a e valia para qualquer empresa cujas notas não casaram.
  - Agora, quando nenhum item tem custo de nota, o bloco pede a lista (`GET /notas`) e diz quantos itens casaram e quantos ficaram sem par.
  - Na demonstração, o catálogo tem o custo, e o Painel não faz o pedido a mais (testado).
- **O teste do tempo limite do cliente falhava às vezes com a máquina carregada** (2 de 6 baterias completas).
  - Num rascunho com o coletor de lixo forçado (`node --expose-gc`), o Node 24.21 perdeu o abort da cópia da `Request` em 5 de 5 rodadas. Um ouvinte no próprio sinal combinado o recebeu em 10 de 10.
  - O Chrome 158 não perde: 5 de 5 com o coletor forçado pelo DevTools Protocol.
  - **Conserto no `criarCliente`:** a promessa também termina pelo sinal combinado. No navegador, o resultado é o mesmo de antes.
  - Dois testes novos usam um fetch que nunca vê o sinal. Sem o conserto, os dois falham; com ele, a bateria completa passou 3 vezes seguidas.
- **Os erros do formulário ficavam vermelhos** depois de a pessoa corrigir o campo, até o próximo envio. Isso foi visto nas capturas. Agora o erro do campo some na mudança.

## Consequências

- **Testes:** tela com 531 (eram 492), lint, tipos, build, `npm run seguranca`, `contrato:checar` e `npm audit` ok. O backend não mudou: 697 testes e 54 golden.
- **Conferências no negativo:**
  - sem a regra do cookie, sem a conferência do catálogo vazio, sem a das notas de exemplo e sem o conserto do tempo limite, os testes falham;
  - os arquivos voltaram depois de cada conferência.
- **Fixtures gravadas da API real,** com os motores oficiais e um banco temporário. O roteiro está no rascunho da sessão, fora do repositório. O CNPJ é o exemplo do manual do Serpro, e o e-mail é do domínio reservado `.test`.
- **Conferido no Chrome 158**, com o build no `vite preview` (a CSP real) e a API real atrás do proxy `/api`:
  - a primeira vez;
  - o cadastro, com o envio vazio, o CNPJ com a máscara e em minúsculas, a UF, o município e a atividade;
  - o Painel, o Catálogo, o Regime e as Notas da empresa nova;
  - uma nota fictícia da empresa importada (3 itens sem par), e o Painel depois dela;
  - Sua conta com o CNPJ, e a volta à demonstração;
  - os pedidos da conta levam o cookie, e os da demonstração não;
  - nenhum pedido sai da origem, nenhuma violação da CSP, o armazenamento do navegador fica vazio e não há rolagem lateral em 1440, 768 e 390 px;
  - o único erro no console é o 401 do `GET /conta` antes de entrar.
- **O portão da skill:**
  - o inspetor dá 0 FAIL nas telas que abre sem cookie. O único aviso é o de `/empresa/nova` sem conta (o aviso curto centrado), o mesmo de `/conta` na C2b;
  - as telas da conta foram julgadas pelas capturas do roteiro;
  - o lint dá 0 FAIL e os mesmos 6 avisos de antes (a fonte mono é decisão do estilo).
- **Fica para a C3b:** os itens e os clientes (até lá, a empresa nova não tem como ver um alerta), as configurações, baixar os dados, excluir a empresa e o par de um item sem par a partir da nota.
- **Fica para o 3c:** o seletor de empresa (e, com ele, mais de uma empresa por conta) e o membro de verdade.
- **Para o usuário decidir:** os termos de uso não falam do cadastro da empresa. Uma regra como "cadastre só a empresa que você representa" muda os termos, pede uma versão nova (o contrato aceita só a versão atual) e um novo aceite.

## C3b, etapas 1 a 5: as configurações, a exclusão da empresa e o arquivo dos dados (2026-11-28)

O mapa e as decisões estão no [plano v2.1](../plano-v2.1.md) ("C3b"). O backend do item a partir da nota, que vai no mesmo PR, está na revisão do [ADR 0017](0017-empresa-propria.md).

**As configurações da empresa (`/empresa`):**
- **Onde:** fora da barra, como `/conta` e `/empresa/nova`. Os caminhos são o menu da conta (só com empresa) e um link abaixo do título do Painel (só na empresa da conta; a demonstração não tem configurações). A `Pagina` ganhou a prop `acao` para esse link.
- **A página é da conta:** quem estava vendo a demonstração volta aos dados da conta ao abri-la, como no cadastro. As rotas `/empresas` levam o cookie de qualquer forma (`ROTAS_DA_EMPRESA`).
- **Os campos** (regime, UF, município e atividade) saíram do cadastro para `camposDaEmpresa.tsx`, e as duas páginas usam os mesmos. As listas continuam vindo dos motores, com a fonte impressa.
- **O `PATCH` leva só o que mudou,** com a UF e o município juntos, como o contrato pede (`mudancasDosDados`). Salvar sem mudar nada diz "Nada mudou" e não chama a API. A resposta é a empresa nova: a página passa a mostrá-la, e os formulários recomeçam com os valores gravados.
- **As alíquotas do DAS** (`pCBSSN` e `pIBSSN`), com a origem à vista: os valores de exemplo da simulação, rotulados, ou os informados. "Voltar aos valores da simulação" manda `premissasDas: null`. O texto diz o que elas fazem (entram no Simples tradicional, também na comparação do Regime) e manda conferir com o contador; onde o empresário encontra os valores segue não verificado ([ADR 0001](0001-lado-tradicional-do-simples.md)).
- **Um "Salvar" por bloco,** no pé dele (app-screens §8.2: um modelo de gravação por tela).
- **O membro** vê os dados, sem formulários e sem a exclusão (a API recusa com 403 de qualquer forma). As alíquotas aparecem como foram informadas, sem arredondar.
- **A carga atual** (`cargaAtualPct`) fica de fora: nenhuma tela a mostra, e o carrinho da tela não a envia. Um campo sem efeito confundiria.

**Excluir a empresa:**
- a última seção da página, com a consequência em palavras (o catálogo, as notas, os custos, os preços, os alertas e os clientes empresa saem na hora e de vez) e o aviso "Guarde suas notas: o ContaAI não é o seu arquivo fiscal", com a fonte da guarda (Ajuste SINIEF 07/05, cláusula décima);
- a confirmação pede o CNPJ da empresa (com ou sem a pontuação, em minúsculas também) e a senha. A tela confere o CNPJ antes de enviar; o backend confere de novo;
- `SessaoConta.excluirEmpresa`: no 204, a conta deixa de ter o CNPJ sem esperar outro `GET /conta`, e as telas voltam à primeira vez. O 401 tanto é a senha errada quanto a sessão que acabou: a tela pergunta de novo quem entrou, como na exclusão da conta. O 404 também relê a conta (outra aba pode ter excluído).

**Baixar os seus dados (Sua conta):**
- a senha de novo; o texto do JSON é salvo como a API o mandou (`parseAs: 'text'`), sem reformatar, como `application/json`;
- o nome vem do `Content-Disposition` (`chamarComCabecalhos`), conferido por `nomeDoArquivo`: só letras, dígitos, ponto, hífen e sublinhado, terminando em `.json`. Fora disso, `contaai-dados.json`;
- o `Content-Disposition` não precisa ir ao `expose_headers` do CORS: o cookie da sessão só anda na mesma origem (`allow_credentials=False`), então esse pedido nunca é lido de outra origem.

**A Privacidade:** os direitos levam a baixar os dados (Sua conta) e a excluir a empresa (Configurações da empresa, só o dono); o que fica guardado inclui as alíquotas do DAS informadas; o prazo da empresa passou a ser "até o dono excluir a empresa, e no máximo enquanto a organização existir". A data da política (27/11/2026) não mudou: o texto anterior era do mesmo dia.

**Achados:**
- **a fonte das alíquotas terminava em ".."** quando o texto da API já tinha ponto. Achado pelo teste;
- **a alíquota aparecia duas vezes,** arredondada embaixo do campo ("1,16%" ao lado de "1,1612"). Achado nas capturas; agora aparece só no campo, e a visão do membro mostra o valor inteiro;
- **o link do Painel e um "Ir ao Painel" no pé das configurações** saíam no azul do navegador. O do Painel usa o link dos blocos; o outro saiu (repetia a barra).

**Consequências:**
- **Testes:** tela com 556 (eram 531): `configuracoes.test.tsx` (22) e as regras novas. Lint, tipos, build, `npm run seguranca`, `contrato:checar` e `npm audit` ok. Backend com 715 testes (eram 697) e 97% de cobertura, 54 golden, `pip-audit` sem vulnerabilidades. Nenhuma dependência nova.
- **Conferências no negativo:** sem o nome conferido do arquivo, sem o "Nada mudou", sem a UF com o município e sem a conta perder o CNPJ depois da exclusão, um teste falha em cada caso. Os arquivos voltaram depois de cada conferência.
- **Fixtures gravadas da API real** (motores oficiais, banco temporário, conta do domínio `.test`, CNPJ do exemplo do Serpro): `empresa-configurada.json`, `empresa-das-*.json`, `erro-empresa-municipio.json`, `erro-empresa-excluir-cnpj.json`, `erro-senha-errada.json` e `conta-dados.json`. `nfe-importar-empresa-nova.json` e `nfe-importar-sem-par.json` foram gravadas de novo com os campos novos das linhas sem par; fora esses campos, são iguais às de antes (conferido).
- **Conferido no Chrome 158**, com o build no `vite preview` (a CSP real) e a API real atrás do proxy `/api`, por um roteiro do DevTools Protocol que cria a conta e a empresa pela própria página: o link do Painel e do menu, salvar os dados, as alíquotas e a volta à simulação, baixar os dados (um download só, com o nome e o conteúdo da API e sem a senha), excluir a empresa e a primeira vez depois. Sem violação da CSP, sem rolagem lateral em 1440, 768 e 390 px e sem nada no armazenamento do navegador.
- **O portão da skill** (crítica em `.taste-skill/app/critica-c3b1.md`): o inspetor dá 0 FAIL; o único aviso é o aviso curto centrado das páginas da conta sem conta, o mesmo de antes. O lint dá 0 FAIL e os 6 avisos de antes.
- **Fica para a C3b2:** criar, alterar e arquivar itens, o par a partir da nota na tela de Notas e os clientes. Até lá, a empresa nova ainda não chega ao alerta pela tela.
