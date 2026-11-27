# ADR 0016: telas de entrada, a conta na tela e a demonstração para quem tem conta (C2)

- Status: aceito (C2a; C2b e C2c nas seções do fim)
- Data: 2026-11-26
- Etapa: C2 do [plano v2.1](../plano-v2.1.md), dividida em três PRs pelo usuário
- Código da C2a:
  - `frontend/src/sessao/conta.ts` (`SessaoConta`), `middleware.ts`, `acoes.ts` (`carregarSessao`), `instancias.ts`;
  - `frontend/src/api/rotas.ts` (`ROTAS_DA_CONTA`, `ROTAS_DE_ENTRADA`, `DELETE` no `ChaveRota`);
  - `frontend/src/dados/empresa.ts` (`useOrigemDosDados`, `useGravacao`);
  - `frontend/src/shell/` (`rotas.ts`, `Shell.tsx`, `demonstracao.tsx`, `paginas.tsx`, `StatusSessao.tsx`, `Rodape.tsx`, `navegacao.tsx` com a `Ancora`);
  - `frontend/src/telas/` (`Inicio.tsx`, `Termos.tsx`, `Privacidade.tsx`, `TextoLegal.tsx`, `legal.ts`, `publicas.css`).
- Código da C2b:
  - `frontend/src/telas/` (`CriarConta.tsx`, `Entrar.tsx`, `Conta.tsx`, `SegundoFator.tsx`, `QrCode.tsx`, `forcaDaSenha.tsx`, `formulario.tsx`, `regrasDeEntrada.ts`, `PortaDaConta.tsx`, `conta.css`);
  - `frontend/src/shell/MenuDaConta.tsx`, e as rotas `/entrar`, `/criar-conta` e `/conta` em `shell/rotas.ts`;
  - `frontend/src/sessao/conta.ts` (as ações da conta na `SessaoConta`);
  - backend: a entrada numa conta pendente, o tipo `/problemas/conta-bloqueada` e o nome da organização (revisões da C2b no [ADR 0015](0015-contas.md)).
- Código da C2c:
  - `frontend/src/dados/notasDeExemplo.ts` e a seção das notas de exemplo em `frontend/src/telas/Notas.tsx`;
  - `frontend/src/shell/navegacao.tsx` (`ArquivoParaBaixar`);
  - `frontend/vite.config.ts` (`server.fs.allow` e `build.assetsInlineLimit`).

## Contexto

A C1 ([ADR 0015](0015-contas.md)) criou as contas no backend: a sessão é um cookie `HttpOnly`, e a API abre o banco da organização quando o pedido traz o cookie e nenhum espaço. A tela ainda não sabia que havia conta. O mapeamento da C2 achou:

1. **Com o cookie e sem espaço, a API abre o banco da organização**, vazio até a C3. A tela pediria o CNPJ fixo da demonstração e receberia 404.
2. **Uma sessão vencida responde 401 em qualquer rota.** O middleware da tela só tratava o 401 de um pedido com o token da demo.
3. **No modo mock, as rotas de conta respondem 501.**
4. **O `ChaveRota` só aceitava GET e POST**, mas sair usa DELETE.
5. **`/` era o Painel.**

Decisões do usuário (plano v2.1, C2): a página inicial em `/` e o Painel em `/painel`; quem tem conta vê a demonstração compartilhada como todo mundo, com os pedidos de dados sem o cookie; quem responde pelos dados é "Equipe ContaAI", sem e-mail; a C2 em três PRs.

## Fontes lidas (2026-11-26)

| Fonte | O que foi usado |
|---|---|
| LGPD (Lei nº 13.709/2018), planalto.gov.br | Art. 5º (dado pessoal, controlador, encarregado, tratamento); art. 7º, V (execução de contrato a pedido do titular), a base citada na privacidade; art. 9º (o que informar, inclusive a identificação e o contato do controlador, incisos III e IV); art. 18 (direitos); art. 41, § 1º (identidade e contato do encarregado divulgados publicamente) |
| ANPD, "Guia orientativo: cookies e proteção de dados pessoais", out/2022 (PDF no gov.br, lido em texto) | p. 10: cookies necessários; p. 20: o consentimento não é a base apropriada para os estritamente necessários; p. 24: o legítimo interesse pode ser; p. 28-29: a política de cookies pode ser uma seção da política de privacidade, com finalidade, retenção e compartilhamento |
| `backend/app/contas/` e `backend/app/api/dependencias.py` | As regras que os termos citam (senha, código, espera, bloqueio, sessão, passe, cadastro pendente) e os nomes dos cookies |

## Decisão

### 1. Rotas públicas e rotas do app

- **Públicas:** `/` (início), `/termos` e `/privacidade`. Têm uma barra própria, com a marca e "Explorar a demonstração" (ou "Minha conta", que a C2b renomeou para "Ir ao Painel"), sem os destinos do app e sem a faixa. Não pedem dados da empresa.
- **Do app:** `/painel`, `/catalogo`, `/regime`, `/notas` e `/contador`. A barra mostra só estas.
- `/entrar` e `/criar-conta` entram na C2b. Até lá, nenhuma tela leva a uma página que ainda não existe. **Feito na C2b** (seção no fim).
- O `ChaveRota` aceita `DELETE`.

### 2. A conta na tela (`SessaoConta`)

- Estados: `desligada` (mock), `carregando`, `anonima`, `conectada` (com `naDemo`), `encerrada` e `erro`.
- **A tela só sabe da conta pelo `GET /conta`**, pedido ao abrir e só no modo real. Nada da conta vai ao armazenamento do navegador nem ao endereço (testado).
- **A conta fica "carregando" desde antes do `/saude`** (`aguardar`), e nenhum dado é pedido até a tela saber se há conta. O teste da tela achou o defeito: no intervalo entre o `/saude` e o `/conta`, o Painel já pedia o catálogo.
- `erro` (rede ou 5xx no `/conta`) segue como quem não tem conta, com "Tentar de novo" na faixa.

### 3. O cookie só vai aonde precisa (middleware da sessão)

| Pedido | Na conta | Fora da conta (sem conta, ou com a conta vendo a demonstração) |
|---|---|---|
| Rotas da conta (tag `contas` do contrato) | cookie | cookie |
| Rotas de dados | cookie, sem espaço e sem token | `credentials: 'omit'`, com o espaço e o token como antes |

- Na conta, o id do espaço não vai: para a API, o espaço do header vence o cookie.
- **401 com o cookie, sem token e fora das rotas de entrada** (`POST /contas/ativar`, `/sessoes`, `/sessoes/codigo` e `/conta/excluir`, onde o 401 quer dizer senha ou código errado): a sessão acabou, e a faixa diz "Sua sessão terminou, e você voltou à demonstração".
- As listas `ROTAS_DA_CONTA` e `ROTAS_DE_ENTRADA` são conferidas com o contrato (`rotas.test.ts`).
- **Conferido no Chrome** (build no `vite preview`, API real): o cookie é `__Host-`, `HttpOnly`, `Secure`, `SameSite=Strict` e `Path=/`, e o `document.cookie` não o mostra; a conta sem empresa não pede dados da empresa em 1440, 768 e 390 px; na demonstração, os pedidos de dados saem sem o cookie; o `POST /espacos` sem cookie passa pela conferência de CSRF e cria o espaço; depois de sair em todos os aparelhos, a página volta à demonstração; nenhum erro no console.

### 4. A conta sem empresa

Na conta, as páginas do app dão lugar a um estado vazio com o título da página: "A sua organização ainda não tem empresa cadastrada, e o cadastro da empresa ainda não está disponível", com o botão "Explorar a demonstração". A origem dos dados é `null` na conta: nenhum pedido com o CNPJ da demonstração vai ao banco da organização. A C3 troca este estado pelo cadastro (feito na C3a: a primeira vez e `/empresa/nova`, [ADR 0018](0018-telas-da-empresa-propria.md)).

### 5. Página inicial

- O que é o ContaAI (as palavras do README), a frase de simulação (P6) e "Explorar a demonstração" como primeiro botão, sem cadastro.
- Ao lado, o que cada tela da demonstração responde (as perguntas do inventário da skill) e como gravar (espaço próprio, ou só leitura no mock).
- Nenhum número da demonstração fica escrito na página.

### 6. Termos de uso e privacidade

- **Rascunho marcado "sem revisão jurídica"** no alto de cada página.
- **Cada regra citada vem do código.** `REGRAS_DA_CONTA` e `COOKIES` (`telas/legal.ts`) são conferidos com o backend por `legal.test.ts`, que lê os arquivos Python. A versão dos termos é o tipo gerado do contrato (o enum de `termosAceitos`) e também é conferida com `termos.py`.
- **Privacidade:** o que fica guardado (das migrações do `contas.db`), a base legal (art. 7º, V), os dois cookies em tabela, com finalidade e duração, e a razão de não pedir consentimento (guia da ANPD), o id do espaço no `localStorage`, os registros técnicos (o IP fica só na memória do limitador e no log do servidor, nunca no banco), o compartilhamento (nenhum), os prazos e os direitos.
- **Quem responde: "Equipe ContaAI"**, sem e-mail e sem nome (decisão 4).
- O índice de cada página sai da mesma lista das seções. As âncoras usam a `Ancora` de `shell/navegacao.tsx`, que só monta `#id` com um id em minúsculas e hífen. A regra do lint (item 2) continua valendo fora desse arquivo.

## Consequências

- **Risco confirmado na leitura da lei:** o art. 9º, III e IV, e o art. 41, § 1º, pedem o contato do controlador e do encarregado. A página mostra só "Equipe ContaAI", por decisão do usuário. Fica registrado no plano para rever antes da E6.
- **A privacidade cita o menu da conta** (ver os dados e excluir a conta), que entra na C2b. A C2a não tem caminho na tela para criar conta, então ninguém chega a uma conta pela tela antes da C2b. **Resolvido na C2b:** a privacidade aponta para "Sua conta", no menu da conta.
- **Ficam para a E6:**
  - o prazo de guarda do log do servidor;
  - o provedor de hospedagem, que seria um operador (art. 5º, VII) e mudaria a seção de compartilhamento;
  - as cópias de segurança, que mudariam o "apaga na hora" da exclusão.
- **Fica para o 3c:** o chat com um provedor de IA real manda o texto da conversa a terceiros, e a privacidade precisa dizer isso antes.
- **Testes:** 293 na tela (eram 265), com o estado da conta, o cookie por rota, o 401 da sessão, as páginas públicas, o índice e as regras conferidas com o backend. Também foi corrigida uma corrida antiga no teste do tempo limite (`cliente.test.ts`): com a máquina carregada, o sinal já chegava abortado.
- **Portão da skill:** `inspect.mjs --app` com 0 FAIL e 0 WARN no início, nos termos, na privacidade e no Painel com a faixa, em 1440, 768 e 390 px; a crítica está em `.taste-skill/app/critica-c2a.md`.

## C2b: criar conta, entrar e o menu da conta (2026-11-27)

Feita em 10 etapas, validadas pelo usuário; o detalhe de cada uma, com o que foi conferido, está no [plano v2.1](../plano-v2.1.md) (C2b).

### Decisões

1. **Criar conta em três passos** (`/criar-conta`): e-mail, senha, organização e o aceite dos termos; o QR code e o primeiro código, com a contagem do passe; os 10 códigos de recuperação, com copiar, baixar (`.txt` por `blob:`) e "Guardei os códigos". Os termos abrem em outra aba, sem perder o que foi digitado.
2. **Entrar em duas etapas** (`/entrar`): e-mail e senha, depois o código do aplicativo ou um de recuperação. O código de recuperação usado é trocado por um novo, mostrado uma vez. Passe vencido volta ao começo com o e-mail. **Conta pendente com a senha certa vai ao passo do QR** com um segredo novo (decisão 1 da C2b; mudança no backend).
3. **O QR code é SVG desenhado pela tela** a partir da matriz da `uqr` (um `<path>`, 4 px por módulo, borda de 4), nunca um serviço externo nem `innerHTML`: a CSP (`img-src 'self'`, Trusted Types `'none'`) fica igual. O segredo aparece em grupos de 4 para digitar.
4. **Senha:** mínimo de 8 (com o segundo fator obrigatório, ADR 0015), "Mostrar", `autocomplete` e `name` para o gerenciador de senhas, e um medidor de força (zxcvbn-ts, baixado só quando a pessoa digita) que só orienta, sem regra de composição (NIST SP 800-63B-4, §3.1.1.2).
5. **A conta bloqueada (100 falhas) tem tipo próprio** (`/problemas/conta-bloqueada`) e a tela não mostra contagem para ela; a espera crescente mostra "Aguarde N s". O e-mail sem conta recebe a mesma resposta.
6. **Menu da conta na barra** (decisão 2): um botão de mostrar e esconder com o e-mail (não um `role="menu"`), com a organização, "Sua conta" e "Sair". Aparece também na demonstração e nas páginas públicas. **Página Sua conta** (`/conta`): dados, segundo fator e códigos, avisos de segurança, sessão (sair e sair de todos) e excluir a conta com a senha e uma caixa de confirmação.
7. **Segredo, códigos e senha só na memória dos componentes**: nada no endereço nem no armazenamento do navegador (testado e conferido no Chrome).
8. **Os campos contam caracteres como o backend** (pontos de código) e não usam `maxLength`, que conta unidades UTF-16 e corta o texto colado sem avisar. Os padrões dos campos são conferidos com o `openapi.json` por teste.

### Verificação final (etapa 10, 2026-11-27)

- **Testes:** tela 463 e backend 500 (97% de cobertura), mais os 52 de referência; lint, tsc, build, `npm run seguranca`, `contrato:checar`, ruff, mypy e `npm audit` (0 vulnerabilidades).
- **Um teste instável consertado:** o foco no título do passo vem de um `useEffect`, e o teste conferia antes de ele rodar (com a máquina ocupada, falhou 2 vezes em 8 rodadas). As conferências de foco que dependem de uma resposta da API agora esperam (`waitFor`); 4 rodadas seguidas com carga em paralelo passaram.
- **No Chrome 158**, com o build, a CSP do cabeçalho e a API real, por três roteiros do DevTools Protocol no scratchpad da sessão (fora do repositório): criar conta, entrar (inclusive código de recuperação, conta pendente, espera e conta bloqueada) e o menu com Sua conta (sair, sair de todos e excluir). Nenhuma violação da CSP, nenhum pedido fora da API, só cookies `__Host-` com `HttpOnly`, `Secure` e `SameSite=Strict`, e nada no endereço nem no armazenamento.
- **Achado e consertado na verificação:** a barra pública rolava de lado em 390 px com um e-mail longo (o botão do menu não encolhia). Agora o e-mail é cortado com reticências (`shell.css`).
- **Portão da skill:** 0 FAIL nas dez telas, em três larguras; crítica em `.taste-skill/app/critica-c2b.md`.
- **O que entrou no navegador:** `uqr` e zxcvbn-ts, com duas dependências deste (revisão da C2b no [ADR 0012](0012-fundacao-do-frontend.md)).

### Consequências

- **Fica com o usuário, num Chrome comum e num celular:** o balão do gerenciador de senhas (Criar conta e Entrar) e a leitura do QR pela câmera de um aplicativo autenticador de verdade. O Chrome sem janela não mostra o balão, e o jsQR leu o print, não uma foto da tela.
- **O aviso de 3 códigos ou menos não aparece com o backend de hoje,** porque o código usado é trocado na hora e os restantes ficam em 10. Fica pronto e testado (decisão do usuário).
- **Sem recuperação de senha nem confirmação de e-mail** (decisões do plano v2.1); por isso o cadastro não esconde que um e-mail já existe (ADR 0015).

## C2c: notas de exemplo e o fechamento da C2 (2026-11-27)

Feita em 5 etapas, validadas pelo usuário; o detalhe está no [plano v2.1](../plano-v2.1.md) (C2c).

### Decisões

1. **Uma fonte só, sem cópia:** a tela importa os XML de `data/demo/notas` (os mesmos das sementes e dos testes do backend) por `import.meta.glob` com `?url`. No build, o Vite copia cada arquivo para `dist/assets` com um hash no nome. Ficou fora uma rota nova no backend, que pediria contrato e não funcionaria no modo mock.
2. **O servidor de desenvolvimento abre só essa pasta.** Definir `server.fs.allow` troca a raiz padrão pela lista (lido no código do Vite 8.3.8: `raw?.fs?.allow ?? [workspaceRoot]`). Por isso a lista repete `searchForWorkspaceRoot` e soma só `data/demo/notas`, que tem apenas XML fictícios. A lista de `deny` padrão (`.env`, chaves, `.git`) continua valendo. O build e o preview não usam essa lista.
3. **O XML sai sempre como arquivo** (`build.assetsInlineLimit`): abaixo de 4 KB, o padrão do Vite, a nota 1 (2.394 bytes) e a nota sem par (1.769) iriam para dentro do código como `data:`.
4. **As três notas, na ordem de interesse:** a nota 2 (a cerveja sobe e gera o alerta de margem), a sem par e a nota 1, marcada como já presente na demonstração. Importar a nota 1 de novo devolve o recibo gravado (`jaImportada`). As frases vêm de `data/demo/README.md` e foram conferidas com os recibos gerados pela API (fixtures da tela).
5. **O link passa pela `ArquivoParaBaixar`,** no `navegacao.tsx`, o único arquivo que pode montar `href` (lint, item 2 de `docs/seguranca.md`). Ela só aceita um caminho que começa com uma barra, na mesma origem, sem consulta nem fragmento e terminado no nome pedido, e um nome em minúsculas com hífen e `.xml`. Com outro valor, a tela quebra. Há testes com esquema de script, `data:`, `blob:`, `//outro.site`, outra origem, barra invertida, `..`, consulta e fragmento.
6. **A seção aparece também na demonstração compartilhada e no modo mock,** onde ninguém importa: a pessoa baixa a nota e cria um espaço.

### Verificação (2026-11-27)

- **Testes:** tela 491 (eram 463), backend 500, mais os 52 de referência; lint, tsc, build, `npm run seguranca`, `contrato:checar`, ruff, format e mypy. Os testes marcados `llm` ficaram de fora porque gastam crédito.
- **Build:** os três XML saem em `dist/assets` com o sha256 igual ao do repositório. O `dist` não tem caminho local (nome de usuário, `C:/` nem `Users/`). Aparece só o caminho relativo do repositório, como chave do `import.meta.glob`.
- **Servidor de desenvolvimento:** as notas respondem 200. `data/demo/sementes.json` (também com `..` direto e codificado), o backend e o `.git` respondem 403. `frontend/src` segue 200, como antes.
- **No Chrome 158**, com o build, a CSP do cabeçalho e a API real, por roteiros do DevTools Protocol no scratchpad da sessão (fora do repositório):
  - os três downloads, pelo clique do mouse, em 1440, 768 e 390 px, com o nome certo e o sha256 igual ao do repositório, sem sair de `/notas` e sem rolagem lateral;
  - um espaço criado pela tela, onde os três arquivos baixados foram importados: o alerta da cerveja, os itens sem par e o aviso "já tinha sido importada";
  - **a saída da C2:** criar conta (QR, código TOTP calculado no roteiro e os 10 códigos), sair pelo menu (`GET /conta` com 401), entrar com o código da janela seguinte, ver a demonstração com a conta (com as notas de exemplo) e "Voltar à minha conta". A conta de teste foi excluída no fim;
  - nenhuma violação da CSP, nenhuma exceção, nenhum pedido fora da origem; nada da conta no armazenamento nem no endereço.
- **Portão da skill:** `inspect.mjs --app` em `/notas` com 0 FAIL e 0 WARN nas três larguras; crítica em `.taste-skill/app/critica-c2c.md`.

### Consequências

- **Fica para a C3:** as notas de exemplo são da Serra Azul. Na empresa própria, a API recusa a nota de outro destinatário (422), e falta decidir se a seção some fora da demonstração e do espaço.
- **Fica com o usuário:** a leitura do QR pela câmera de um aplicativo autenticador de verdade. O balão do gerenciador de senhas foi conferido pelo usuário num Chrome comum (2026-11-27).
