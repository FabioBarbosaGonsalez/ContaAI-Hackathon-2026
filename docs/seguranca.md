# Segurança do ContaAI

Resumo do que o projeto protege, como protege e o que continua em aberto. Os detalhes e as fontes estão nos ADRs citados. Este documento não acrescenta decisões: quando um ADR muda, ele é atualizado junto.

Para relatar uma vulnerabilidade, veja o [SECURITY.md](../SECURITY.md).

## O que existe para proteger

| Ativo | Por que importa |
|---|---|
| Motores oficiais da Receita (RR e SN) | Não têm autenticação (`anyRequest().permitAll()` no código oficial). Quem alcança o motor usa a CPU dele à vontade |
| Crédito do provedor de IA | Cada mensagem do chat custa dinheiro quando uma IA real é ligada |
| Estado da demonstração (SQLite) | Notas, custos, alertas e preços aplicados das empresas fictícias, compartilhados por quem usa a demo |
| Contas (`contas.db`, [ADR 0015](adr/0015-contas.md)) | E-mail, hash da senha, segredo do segundo fator, sessões e o aceite dos termos (versão e data) de quem tem conta: o primeiro dado pessoal do projeto |
| Estado de cada organização (`organizacoes/<id>.db`) | Desde a C3-B ([ADR 0017](adr/0017-empresa-propria.md)): a empresa, o catálogo, as notas e os preços de uma empresa real. Não pode chegar a outra organização |
| Chave do provedor de IA e token da demo | Segredos do servidor |
| Confiança no número mostrado | O produto mostra tributo e margem: um número inventado ou adulterado é o pior defeito possível |

Os dados do repositório e dos testes são sintéticos (P10): empresas, CNPJs, notas e e-mails fictícios. Desde a C1, o servidor guarda o e-mail de quem cria uma conta, num banco fora do git (`*.db` no `.gitignore`). Desde a C3-B, o P10 vale para a demonstração e os espaços. A empresa da conta guarda os dados reais que a pessoa cadastra, também fora do git.

## Ameaças e proteções

### Acesso aos motores ([ADR 0002](adr/0002-motores-em-containers.md))

- As portas dos motores só abrem em `127.0.0.1` no `docker-compose.yml`. As portas de gestão não são publicadas.
- As imagens rodam com usuário sem privilégios, e o banco dos motores é aberto só para leitura.
- O build baixa o código da Receita pelo commit verificado (SHA), não pela tag, que já foi republicada uma vez.
- A JVM roda com `-XX:-UseBASE64Intrinsics`, a mitigação indicada nos CHANGELOGs oficiais.
- O backend chama os motores com `trust_env=False`, sem passar por proxy configurado no ambiente.

### Abuso da API pública ([ADR 0006](adr/0006-agente.md), [ADR 0008](adr/0008-nfe-historico-e-alertas.md))

- **Limite por IP** (janela de 60 s, em memória):
  - 10 por minuto no `/chat`;
  - 120 por minuto nas rotas que chamam os motores ou mudam o estado;
  - mais 20 por minuto na busca de NCM.

  A tabela de IPs tem no máximo 10 mil entradas.
- **Token da demo** (`CONTAAI_TOKEN_DEMO`) no `/chat` e nas rotas que mudam o estado (inclusive preço e classificação pela tela, fora do espaço), comparado em tempo constante.
- **Teto por mensagem do agente:** 6 rodadas, 16 ferramentas, 1.024 tokens de saída por rodada e 90 s.
- **Cache das respostas dos motores:** pedidos repetidos não chegam ao motor.

### Entrada não confiável ([ADR 0008](adr/0008-nfe-historico-e-alertas.md))

- **XML da NF-e:**
  - expat ≥ 2.6.0, conferido na subida;
  - DOCTYPE, entidades e referências externas recusados antes de montar a árvore;
  - limites de profundidade, de elementos e de itens;
  - números só em notação decimal simples (NaN e infinito recusados).
- **Upload:**
  - sem `Content-Length`, 411;
  - acima do limite, 413, antes de o corpo ser lido;
  - leitura de no máximo o limite + 1 byte;
  - só tipos de XML (415).
- **Contrato:**
  - todo modelo recusa campo desconhecido;
  - CNPJ, id do alerta, id do item do catálogo e código de erro têm padrão fixo;
  - o texto do produto vindo da nota (`xProd`) é tratado como dado, nunca como instrução ao agente.
- **Corpo das rotas JSON** ([ADR 0011](adr/0011-contrato-da-tela-e-seguranca.md)):
  - acima de 1 MB (`CONTAAI_TAMANHO_MAX_JSON_BYTES`), 413 antes de ser lido;
  - em pedaços, sem `Content-Length`, 411.
- **Números de entrada:**
  - valores com até 10 casas, quantidades e percentuais com até 4;
  - teto de R$ 1 bilhão por unidade e 1 bilhão de unidades;
  - NaN e infinito recusados.

  Antes, `1e999999` no valor dava erro 500, e `1e-999999` ia ao motor.
- **Preço e classificação pela tela:**
  - a classificação só é aceita se for candidata válida para a NCM nos dados abertos do motor;
  - o CST vem da fundamentação oficial, não da tela;
  - o texto da fonte é montado só com dados oficiais;
  - os dois são lançamentos de acréscimo (gatilhos bloqueiam UPDATE).
- **Espaços de avaliação** ([ADR 0010](adr/0010-espacos-de-avaliacao.md)):
  - o id é sorteado pelo servidor (128 bits) e vai num header, não na URL, e por isso não aparece no log de acesso;
  - só vira nome de arquivo depois de conferido pelo padrão de 32 hexadecimais;
  - criar tem limite próprio por IP (5 por minuto) e teto de espaços ao mesmo tempo;
  - o espaço vence num tempo fixo e é apagado na limpeza.
- **Estado:** a nota só entra se o destinatário for uma empresa cadastrada. Reimportar a mesma nota é idempotente (SHA-256). Os lançamentos de custo só aceitam acréscimo (gatilhos bloqueiam UPDATE). A restauração é atômica.

### Contas e sessão ([ADR 0015](adr/0015-contas.md))

- **Senha:** de 8 a 128 caracteres, sem regra de composição (NIST SP 800-63B-4, §3.1.1.2). O mínimo de 8 vale porque o segundo fator é obrigatório.
  - Recusa as 46.483 senhas comuns da lista do NCSC (SecLists, MIT), o e-mail e o nome do produto.
  - Hash Argon2id (argon2-cffi, MIT) com 19 MiB, 2 passes e paralelismo 1 (OWASP).
- **Segundo fator obrigatório:** TOTP (RFC 6238) com a biblioteca padrão, sem SMS.
  - Segredo de 160 bits, 6 dígitos, passo de 30 s, um passo de tolerância e cada código aceito uma vez.
  - 10 códigos de recuperação de 65 bits, guardados só como hash, de uso único e com aviso quando um é usado.
  - Conta pendente com o passe vencido: entrar com a senha certa troca o segredo e dá um passe novo de ativação. A senha errada responde como qualquer outra (revisão da C2b no ADR 0015).
- **Sessão:**
  - cookie `__Host-contaai_sessao`, `HttpOnly`, `Secure`, `SameSite=Strict`, sem `Domain`;
  - token de 256 bits, só o hash no banco, token novo a cada entrada;
  - 30 min sem uso e 8 h no total;
  - sair apaga a sessão no servidor.
- **Tentativas:** contador de falhas seguidas por conta, que soma senha, código e código de recuperação.
  - Espera crescente da 5ª falha em diante (30 s até 1 h).
  - Bloqueio em 100 falhas (NIST §3.2.2), com desbloqueio só pelo administrador no servidor. O 429 do bloqueio tem o tipo próprio `/problemas/conta-bloqueada`, e a tela não mostra contagem para ele; as outras esperas saem como `about:blank` (revisão da etapa 8 da C2b no ADR 0015).
  - Um e-mail sem conta tem o mesmo contador e o mesmo trabalho: a entrada não revela se a conta existe.
  - O cadastro revela, porque sem confirmação de e-mail não há como esconder (achado do ADR 0015).
- **Autorização por empresa:**
  - cada organização tem o próprio banco de estado;
  - toda rota só enxerga os CNPJs de quem chama, e um CNPJ alheio responde o mesmo 404 de um que não existe;
  - os três vazamentos do mapeamento (alertas sem `cnpj`, painel do contador e aplicar alerta) foram fechados;
  - restaurar a demonstração com a sessão de uma conta é recusado.
- **Excluir a conta** pede a senha de novo e apaga a pessoa e todas as organizações em que ela era a única integrante, com o arquivo de estado de cada uma (LGPD, art. 18 VI). Antes da etapa 7 da C3-B, só a organização da sessão saía.
- **Bancos órfãos:** na subida, a API apaga o banco de uma organização que não existe mais no `contas.db`. Um arquivo fora do padrão fica no disco e aparece no log só pelo nome.

### Empresa própria ([ADR 0017](adr/0017-empresa-propria.md))

- **CNPJ:**
  - o formato oficial com o alfanumérico (`^[0-9A-Z]{12}[0-9]{2}$`) no contrato, no leitor da NF-e e num CHECK do banco;
  - o dígito verificador é exigido na empresa da conta e no fornecedor dos itens dela.
- **Dados oficiais vêm dos motores, nunca da tela:**
  - o nome do município;
  - o anexo da atividade;
  - a descrição da NCM;
  - a classificação válida e o CST.
- **Isolamento:**
  - a empresa fica no banco da organização, e o acesso no `contas.db`;
  - outra conta recebe o mesmo 404 de uma empresa que não existe;
  - o mesmo CNPJ em duas contas são duas cópias separadas;
  - o header do espaço não cadastra empresa.
- **Papéis (etapa 8):**
  - só o dono cadastra, configura e exclui a empresa; o dono e o membro mudam o catálogo, os clientes B2B, as notas, os preços, os alertas e as classificações; todo integrante lê;
  - as listas (`PAPEIS_QUE_EDITAM`, `PAPEIS_QUE_ADMINISTRAM`) dizem quem pode: um papel fora delas, como o contador do 3c, recebe 403 até entrar de propósito;
  - o 403 do papel vem antes de olhar a empresa e a senha (não diz se o CNPJ existe nem gasta tentativa), e o papel é lido a cada pedido;
  - um teste de inventário obriga toda rota nova que muda o estado a ser classificada.
- **Métodos:**
  - o PATCH passa pelo limite de corpo, pelo limite por IP e pela defesa contra CSRF;
  - antes da C3-B, os dois limites só valiam para o POST (e o GET, no caso do limite por IP);
  - o OpenAPI passou a listar no PATCH as recusas dos middlewares (403, 411 e 413), que antes só apareciam no POST;
  - desde a etapa 8, todo método que muda o estado (o DELETE das sessões também) declara o 403 do CSRF, somado ao 403 próprio da rota em vez de escondido por ele.
- **Clientes B2B (etapa 6):** `/clientes` tem limite por IP, porque grava e consulta o motor. O dígito do CNPJ do cliente é exigido na empresa da conta, e outra conta recebe o 404 de uma empresa que não existe.
- **Migrações:**
  - chaves estrangeiras desligadas durante a migração e `foreign_key_check` antes do COMMIT, como manda a documentação do SQLite;
  - com elas ligadas, a 0003 apagaria em cascata os itens e as notas.
- **SQL:** o guarda contra SQL montado com texto passou a olhar a linha seguinte ao `execute(`, onde uma f-string escapava dele.
- **Erros:** as recusas por dado (422) têm frase fixa, sem repetir o que foi enviado.
- **Dados e exclusão (etapa 7):**
  - `POST /conta/dados` e `POST /empresas/{cnpj}/excluir` pedem a senha de novo, contam a senha errada como falha de entrada e têm o limite por IP da entrada;
  - excluir a empresa é só do dono e pede o CNPJ digitado; o CNPJ errado é recusado antes da senha;
  - o arquivo dos dados sai como anexo e sem cache, e não leva a senha, o segredo do segundo fator nem nenhum hash (testado contra os valores gravados);
  - o membro baixa as empresas da organização, sem o e-mail dos outros integrantes.
- **Proteções (etapa 9):**
  - o erro 500 sai com os cabeçalhos de segurança e com o CORS da tela, pela mesma pilha de middlewares das outras respostas; antes, o Starlette o montava por fora de todos;
  - o 500 tem frase fixa, sem a mensagem da exceção, e o uvicorn deixa de gravar a pilha: o registro é só o nosso, com o tipo e o lugar;
  - a telemetria do FastAPI fica desligada no código, e nem `FASTAPI_OTEL_AUTO_CONFIGURE` nem um SDK instalado depois a ligam;
  - o `GET /saude`, que consulta os dois motores, entrou no limite por IP; um teste de inventário obriga toda rota nova a ter limite ou um motivo escrito para não ter.
- **O item a partir da nota (revisão da C3b):** a nota é procurada pelo fornecedor do item, e uma nota de outro fornecedor ou de outra empresa responde como inexistente. A troca do recibo é conferida no próprio `UPDATE` (o recibo lido), e o item, o custo e o recibo entram na mesma transação: um cadastro concorrente a partir da mesma nota dá 409 sem gravar nada (testado direto no banco).
- **Modo mock (etapa 10):** um teste de inventário (`tests/test_modo_mock.py`) põe cada rota do contrato num de três grupos: servida pelo mock (com `X-ContaAI-Mock: 1`), fixa ou só do modo real (501). As do modo real recebem um pedido válido, para o 501 não ser um 422 da validação, e respondem sem cookie e sem o marcador; nenhum método que muda o estado responde 2xx no mock sem o marcador. No uvicorn real, o 501 sai com os cabeçalhos de segurança e o CORS, e o mock não cria banco.

### Navegador: XSS, CSRF e DNS rebinding ([ADR 0011](adr/0011-contrato-da-tela-e-seguranca.md))

- **A API nunca responde HTML.**
  - Toda resposta é JSON ou Problem Details, com `nosniff` e `Content-Security-Policy: default-src 'none'`, inclusive as de erro.
  - O texto do usuário volta como string JSON, nunca como página: o backend não o escapa nem o remove, porque é dado.
  - O teste percorre todas as rotas do contrato com payload de XSS, nos modos mock e real.
- **`/docs` é a única página HTML** e é desligável (`CONTAAI_DOCS_PUBLICA=false`). O Swagger carrega scripts de uma CDN. Na mesma origem da tela, eles alcançariam o que a tela guarda no navegador. No deploy, fica desligado.
- **CSRF** (nos métodos POST, PUT, PATCH e DELETE):
  - `Origin` fora de `CONTAAI_CORS_ORIGENS` recebe 403, inclusive com `Origin: null`;
  - `Sec-Fetch-Site: cross-site` recebe 403, e uma requisição com o cookie da sessão e sem `Origin` também ([ADR 0015](adr/0015-contas.md));
  - o cookie da sessão é `SameSite=Strict`, e o CORS não aceita credenciais: o cookie só anda na mesma origem (proxy `/api`);
  - corpo `text/plain` ou de formulário não é lido como JSON;
  - as rotas que mudam o estado também exigem um header próprio (token ou espaço), que força o preflight do CORS.
- **DNS rebinding:** só os hosts de `CONTAAI_HOSTS_PERMITIDOS` são aceitos (padrão: `127.0.0.1` e `localhost`). Os outros recebem 400.
- **CORS:** expõe só `Retry-After` e `X-ContaAI-Mock`, que a tela precisa ler.

### Regras para a interface (E5, [ADR 0012](adr/0012-fundacao-do-frontend.md))

A tela é a próxima camada exposta a XSS. A fundação do frontend (PR 2 da E5) traz estas regras, cada uma com lint, teste ou checagem no CI:

1. **Todo texto vindo da API é exibido como texto.** Isso vale para:
   - a descrição da nota (`xProd`, escrita pelo fornecedor);
   - a resposta do chat;
   - a memória de cálculo;
   - as premissas e a fonte;
   - o `detail` dos erros;
   - os nomes das empresas.

   O React escapa texto por padrão. São proibidos `dangerouslySetInnerHTML`, `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write`, `srcDoc` e `eval`/`new Function`:
   - pelo lint (`react/no-danger` e `no-restricted-syntax` em `frontend/eslint.config.js`);
   - pela busca no código do `npm run seguranca` no CI (`frontend/scripts/checar-seguranca.mjs`).

   Um corpo de erro fora do formato da RFC 9457 (HTML de um proxy, texto) nunca chega à tela, e o teste confere que um `detail` com `<img onerror>` aparece como texto.
2. **Nenhum texto da API vira `href`, `src`, `style` ou nome de atributo.**
   - Os links da tela são rotas fixas do próprio app: o `Link` só aceita o tipo `Caminho`, e o lint barra `href`/`src` montado de um valor em qualquer outro lugar.
   - Desde a C2a ([ADR 0016](adr/0016-telas-de-entrada.md)), a `Ancora`, no mesmo arquivo do `Link` (`src/shell/navegacao.tsx`), monta o `#id` do índice dos termos e da privacidade. Ela só aceita um id em minúsculas, dígitos e hífen, e a tela quebra com outro valor (testado com um esquema de script e com `//outro.site`).
   - Desde a C2c ([ADR 0016](adr/0016-telas-de-entrada.md)), a `ArquivoParaBaixar`, no mesmo arquivo, monta o link das notas de exemplo. Ela só aceita um caminho que começa com uma barra, na mesma origem, sem consulta nem fragmento e terminado no nome pedido, e um nome em minúsculas com hífen e `.xml`. Com outro valor, a tela quebra (testado com esquema de script, `data:`, `blob:`, `//outro.site`, outra origem, barra invertida e `..`).
   - O atributo `style` é proibido.
   - Os ids que vão no caminho da API só podem ter letras, dígitos e hífen. Um `..` trocaria a rota pedida.
3. **Sem script embutido na página gerada.** O `npm run seguranca` confere no `dist/` que não há `<script>` sem `src` próprio, `<style>`, atributo `style`, `on*=` ou mapa de código. A CSP da tela (`frontend/csp.ts`) é:

   ```
   default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; font-src 'self'; connect-src 'self';
   base-uri 'none'; form-action 'none'; require-trusted-types-for 'script'; trusted-types 'none'; frame-ancestors 'none'
   ```

   - **No build, ela vai num `<meta>`** logo depois do `charset`, antes de todo script e estilo. No `<meta>`, o navegador ignora `frame-ancestors`, que fica para o cabeçalho.
   - **O `vite preview`** a manda como cabeçalho, com `nosniff`, `Referrer-Policy` e `X-Frame-Options`. O proxy da E6 deve repetir esses cabeçalhos (`cabecalhosDeSeguranca`).
   - **`connect-src`** recebe a origem da API só se o build apontar para outra origem (`VITE_CONTAAI_API`).
   - **O servidor de desenvolvimento do Vite fica sem CSP**, porque injeta script (React Refresh) e estilo embutidos.
   - **Conferido no Chrome em 2026-11-25:**
     - Trusted Types e `style-src 'self'` funcionam com o React (nenhuma violação na carga);
     - `innerHTML`, `eval`, `<script>`, `<style>` injetados, `fetch` e imagem a terceiros e o iframe de outra origem foram bloqueados.

     A tabela completa está no ADR 0012.
4. **Segredos fora do código da tela.**
   - Toda variável de ambiente do Vite (`VITE_*`) vai para o navegador e é pública. Só `src/api/config.ts` lê o ambiente, e só o endereço da API; o lint barra o resto.
   - O token do chat só aparece num campo, quando a API responde 401, e fica só na memória da aba. Não vai ao armazenamento do navegador, a cookie nem ao endereço (testado).
5. **A conta (C2a, [ADR 0016](adr/0016-telas-de-entrada.md)):**
   - a tela só sabe da conta pelo `GET /conta`; o cookie da sessão é `HttpOnly`, e nada da conta vai ao armazenamento do navegador nem ao endereço (testado);
   - o cookie só vai às rotas da conta e, quando a tela mostra a conta, às rotas de dados. Fora disso, o pedido sai com `credentials: 'omit'`; na conta, o espaço e o token não vão;
   - um 401 com o cookie, fora das rotas de entrada, encerra a sessão na tela;
   - o nome da organização é mostrado como texto (testado com `<img onerror>`).
   - **C2b:** o segredo do segundo fator e os códigos de recuperação voltam só a quem chamou a ação e ficam na memória do componente. Não entram no estado da sessão nem no armazenamento do navegador (testado);
   - uma resposta antiga do `GET /conta` que chega depois de entrar ou sair é descartada (testado);
   - **Criar conta (C2b, etapas 6 e 7):** cada passo leva os próprios dados embora quando acaba: a senha sai com o passo 1, e o QR e o segredo saem com o passo 2 (também quando o passe vence). O QR é desenhado na tela, sem serviço externo. O `.txt` dos códigos é um `Blob` na memória, baixado por um link `blob:` revogado logo depois, sem servidor. O envio é por `fetch`, e o `<form>` não tem `action` (a CSP tem `form-action 'none'`). Conferido no Chrome 158 com o build e a API real: nenhuma violação da CSP do começo ao fim, e o endereço e o armazenamento do navegador ficam vazios.
   - **A empresa da conta (C3a, [ADR 0018](adr/0018-telas-da-empresa-propria.md)):** as rotas `/empresas` (`ROTAS_DA_EMPRESA`) sempre levam o cookie, também com a conta vendo a demonstração, e nunca o espaço nem o token; o `POST /empresas/{cnpj}/excluir` é rota de entrada (o 401 é a senha). O CNPJ é conferido na tela (o formato e os dígitos do Serpro) e de novo no backend. As listas de UF, município e atividade vêm da API, e o que a pessoa digita e o que as listas trazem aparecem como texto. Conferido no Chrome 158 com o build e a API real: os pedidos da conta levam o cookie e os da demonstração não, nenhum pedido sai da origem, nenhuma violação da CSP e o armazenamento do navegador fica vazio.
   - **As configurações, a exclusão da empresa e o arquivo dos dados (C3b, [ADR 0018](adr/0018-telas-da-empresa-propria.md)):** o arquivo dos dados é salvo como a API o mandou, por um link `blob:` revogado logo depois, e o nome vem do `Content-Disposition` só no formato esperado (letras, dígitos, ponto, hífen e sublinhado, terminando em `.json`; fora disso, um nome fixo). A senha some do campo depois do envio, dê certo ou não. A exclusão confere o CNPJ digitado na tela e de novo no backend. Conferido no Chrome 158 com o build e a API real: um download só, sem a senha no arquivo, nenhuma violação da CSP e o armazenamento do navegador vazio.
   - **Medidor de força da senha (Criar conta):** a estimativa roda no navegador, com o zxcvbn-ts (`@zxcvbn-ts/core` 4.2.0 e `@zxcvbn-ts/language-common` 4.1.3, MIT, versões fixas, sem chamada de rede nem `eval` no código, `npm audit` 0). A senha não sai da página. A biblioteca é um arquivo à parte no build, baixado do próprio endereço só quando a pessoa digita a senha (conferido no Chrome: nenhum pedido a terceiros e nenhuma violação da CSP). O medidor só orienta; quem aceita ou recusa a senha é o backend.
6. **O id do espaço fica no navegador (`localStorage`), nunca no endereço da página.**
   - Só é aceito no padrão de 32 hexadecimais.
   - Vai só às rotas que declaram o header no contrato.
   - O espaço vence em 120 min, contados pela duração que o servidor informa.
   - Os dados são fictícios.
7. **Nenhuma requisição a terceiros:**
   - fontes Geist hospedadas junto do app (OFL-1.1); no Chrome, só os arquivos do alfabeto latino são baixados;
   - sem CDN, analytics ou rastreamento (LGPD);
   - o `npm run seguranca` recusa endereço absoluto no build, salvo os nomes de espaço XML e os links de erro do React, que são texto.
8. **Upload (`frontend/src/api/upload.ts`):**
   - o campo oferece só XML (`.xml`, `application/xml`, `text/xml`);
   - o tipo e o tamanho (1.000.000 bytes) são conferidos antes de enviar, e o teste do backend confere que são os mesmos dele;
   - o backend continua sendo quem decide (411, 413 e 415).
   - Desde o 3b ([ADR 0014](adr/0014-telas-notas-e-regime.md)), a tela de Notas usa estas conferências. Ela mostra a recusa do backend (409, 413, 415 e 422) pelo `detail`, como texto. O arquivo fica só na memória da aba até o envio e não vai ao armazenamento do navegador. O recibo mostra o texto da nota (emitente e `xProd`) como texto.
9. **Dependências:**
   - `npm ci` com o lockfile;
   - `frontend/.npmrc`: só versões publicadas há mais de 7 dias, versões exatas e sem scripts de instalação;
   - `npm audit` e `npm audit signatures` no CI;
   - bloco npm no Dependabot, com espera de 7 dias;
   - CodeQL de JavaScript.

### Vazamento de informação ([ADR 0009](adr/0009-camada-http-e-erros.md))

- **Erros no formato da RFC 9457.**
  - Nenhum traz pilha, URL ou host dos motores, caminho do servidor ou corpo de terceiros.
  - O erro não tratado vai para o log e o cliente recebe só "Erro interno".
  - O log desse erro leva o tipo e o lugar no código, sem a mensagem, que pode repetir um valor enviado. O mesmo filtro vale para o log do uvicorn, que recebe a exceção relançada pelo Starlette (etapa 7 da C3-B, [ADR 0017](adr/0017-empresa-propria.md)).
- **Log de acesso sem dado pessoal:** o do uvicorn (com o IP e o caminho com o CNPJ) fica desligado no código. O nosso grava o método, a rota-modelo (`/empresas/{cnpj}`), o status e a duração.
  - A validação não devolve o valor enviado.
- **Cabeçalhos em toda resposta:** `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `X-Frame-Options: DENY` e `Cross-Origin-Resource-Policy: same-origin` (era `same-site` até o ADR 0011). Fora de `/docs`, também `Content-Security-Policy: default-src 'none'` e `Cache-Control: no-store`.
- **CORS** só para as origens configuradas (`CONTAAI_CORS_ORIGENS`), sem credenciais.
- **Segredos:**
  - a chave da IA e o token são `SecretStr`, ausentes de `repr` e de `model_dump_json` (testado);
  - ficam só no `backend/.env`, fora do git.

### Número inventado ([ADR 0006](adr/0006-agente.md))

- Nenhum tributo é calculado pelo backend: todos vêm dos motores oficiais (P1).
- O verificador do agente recusa a resposta que cita um número ausente do JSON das ferramentas e troca por uma resposta segura.
- O agente só propõe ações; aplicar um preço exige o clique do usuário (P3).

## Cadeia de suprimentos e CI

| Verificação | Onde | Ferramenta (licença) |
|---|---|---|
| Dependências travadas | CI, `uv sync --locked` | uv (MIT OR Apache-2.0) |
| Vulnerabilidades conhecidas nas dependências travadas | CI, job "Dependências" | pip-audit 2.10.1 (Apache-2.0), banco do PyPI, sem conta |
| Segredos no histórico inteiro | CI, job "Segredos" | gitleaks 8.30.1 (MIT), binário conferido pelo SHA-256 da release |
| Segredos no push e no repositório | GitHub, ligado nas configurações | varredura de segredos e proteção no push (gratuitas em repositório público) |
| Análise estática | CI, CodeQL (Python e JavaScript) | CodeQL (gratuito em repositório público) |
| Regras de segurança do bandit (`S`) | CI, no `ruff check` | ruff (MIT), já travado no `uv.lock`; sem dependência nova |
| Testes de segurança da API (XSS, CSRF, Host, corpo, números, injeção) | CI, `tests/test_seguranca_api.py` | pytest |
| Varredura dinâmica da API pelo OpenAPI | Local, antes de cada etapa (ADR 0011) | OWASP ZAP (Apache-2.0), imagem oficial `ghcr.io/zaproxy/zaproxy` |
| Tipos | CI, `mypy` com o plugin do Pydantic | mypy (MIT) |
| Cobertura mínima de 90% no `app/` | CI | coverage.py (Apache-2.0) |
| Dependências do frontend travadas, sem scripts de instalação e com 7 dias de publicação | CI, `npm ci`; `frontend/.npmrc` | npm (Artistic-2.0) |
| Vulnerabilidades e assinaturas das dependências do frontend | CI, job "Frontend": `npm audit --audit-level=low` e `npm audit signatures` | npm, banco do registro público, sem conta |
| Regras de segurança da tela (XSS, CSP, endereços, segredos) | CI, job "Frontend": ESLint e `npm run seguranca` | ESLint (MIT) e roteiro próprio |
| Atualizações | Dependabot semanal (Actions, uv, npm com espera de 7 dias, imagens dos motores) e alertas de segurança | GitHub |
| Relato privado de vulnerabilidades | GitHub, ligado nas configurações (ver [SECURITY.md](../SECURITY.md)) | GitHub (recurso de repositório público) |

**Relato privado (ligado em 2026-11-25).** Segundo a documentação do GitHub ("Configuring private vulnerability reporting for a repository" e "Managing privately reported security vulnerabilities"):
- o relato não fica público;
- o GitHub avisa só os **administradores e gerentes de segurança** do repositório, e só se eles acompanham o repositório (todas as atividades ou "Security alerts") com as notificações ligadas;
- quem tem só permissão de escrita **não é avisado**: para o time acompanhar, cada pessoa precisa ser administradora ou ser adicionada ao aviso de segurança;
- aceito, o relato vira um rascunho de aviso de segurança, ainda privado.

As páginas lidas não falam de custo. O recurso é oferecido aos donos de repositórios públicos, e ligá-lo não exigiu contratar nada: o repositório não tem GitHub Advanced Security.

Não usamos a `gitleaks-action`: desde a v2 ela deixou de ser MIT e exige chave de licença para organizações.

## Em aberto

- **Sem opção resistente a phishing.** O TOTP não é resistente a phishing, e o AAL2 completo do NIST pede oferecer uma (passkey). Fica como implementação futura ([ADR 0015](adr/0015-contas.md)).
- **O segredo do TOTP fica em texto no `contas.db`,** protegido pelo acesso ao arquivo. Cifrar fica para o deploy (E6).
- **Termos do NCSC** sobre a lista de senhas comuns não verificados (a licença MIT do SecLists foi lida).
- **Esgotar os espaços de avaliação:** criar um espaço não pede o token, para a banca testar sem combinar nada. Quem fizer muitos pedidos de IPs diferentes pode ocupar o teto (50, configurável) até eles vencerem. A demonstração compartilhada segue funcionando, e o 503 diz em quanto tempo abre vaga ([ADR 0010](adr/0010-espacos-de-avaliacao.md)).
- **Atrás de proxy, o limite por IP vira global.** Ler `X-Forwarded-For` só de um proxy nosso fica para o deploy (E6).
- **Deploy (E6):**
  - volume para o SQLite;
  - container sem root e com sistema de arquivos só de leitura;
  - limite de corpo no proxy;
  - `CONTAAI_DOCS_PUBLICA=false`;
  - o domínio público em `CONTAAI_HOSTS_PERMITIDOS` e em `CONTAAI_CORS_ORIGENS`;
  - HSTS e a API em `/api` no proxy;
  - o proxy repetir os cabeçalhos da tela (`cabecalhosDeSeguranca` em `frontend/csp.ts`), com a CSP e `frame-ancestors`.
  - o log de acesso do proxy também sem o IP e sem o caminho com o CNPJ, como o da API (etapa 7 da C3-B). Sem isso, a decisão "os logs não guardam dado pessoal" vale só para a API.
- **ESLint 9 em fim de vida** (desde 2026-08-06, sem correção de segurança). Fica por decisão do usuário até o `eslint-plugin-jsx-a11y` aceitar a 10; só roda no desenvolvimento e no CI ([ADR 0012](adr/0012-fundacao-do-frontend.md)).
- **Telemetria do FastAPI** (OpenTelemetry, no FastAPI 0.165): desligada no código. Ligar observabilidade na E6 é decisão nova, e a documentação dela diz que grava as mensagens das exceções, as pilhas e o corpo lido; sem filtro, isso contraria "os logs não guardam dado pessoal" ([ADR 0017](adr/0017-empresa-propria.md)).
- **Custo da IA real** ainda não verificado. Precisa ser conferido na página oficial do provedor antes de ligar a chave ([ADR 0006](adr/0006-agente.md)).
