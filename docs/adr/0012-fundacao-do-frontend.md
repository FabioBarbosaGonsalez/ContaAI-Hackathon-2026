# ADR 0012: fundação do frontend

- Status: aceito
- Data: 2026-11-25
- Etapa: E5 (PR 2 dos três aprovados no ADR 0011: a fundação do frontend)
- Código: `frontend/` (projeto, `csp.ts`, `scripts/checar-seguranca.mjs`, `src/api/`, `src/sessao/`, `src/estilo/` e `src/shell/`), `.github/workflows/ci.yml`, `.github/dependabot.yml`, `Makefile` e `backend/tests/test_contrato.py`

## Contexto

O ADR 0011 dividiu a E5 em três PRs: o contrato do backend (feito), esta fundação e as telas com o portão da skill. A fundação foi feita em sete segmentos: projeto e CI, contrato tipado e cliente, espaço e modo, tokens e fontes, shell, segurança da tela e esta documentação.

Ela entrega tudo de que as telas precisam, menos as telas: as páginas mostram só o título e a frase "Esta tela entra na próxima etapa da interface".

### Decisões do usuário (2026-11-25)

1. **O ESLint fica na 9, por enquanto.**
   - A 9 está em fim de vida desde 2026-08-06 e não recebe mais correção de segurança (eslint.org/version-support).
   - Na 10, o `eslint-plugin-react` 7.37.5 e o `eslint-plugin-jsx-a11y` 6.10.2 não funcionam: os dois declaram aceitar o ESLint só até a 9.
   - O substituto das regras de React, `@eslint-react/eslint-plugin`, aceita a 10 e tem as regras de XSS.
   - A única cópia do jsx-a11y que aceita a 10 (`eslint-plugin-jsx-a11y-x` 0.2.0) traz uma dependência com vulnerabilidade moderada (GHSA-g3hv-75wg-m249) e reprovaria o `npm audit` do CI.
   - O ESLint só roda no desenvolvimento e no CI, nunca no navegador, e o `npm audit` acusa se aparecer vulnerabilidade nele. Migrar quando o jsx-a11y aceitar a 10.
2. **As mensagens de validação do backend vão ser traduzidas no backend, num PR separado, depois deste.** Hoje o `detail` do 422 vem em inglês, do Pydantic (ex.: "String should have at least 2 characters"). A tela mostra o `detail` como texto e destaca o campo pela lista `campos`, então não depende da tradução.
3. **Os sete segmentos vão num commit só.**

## Decisão

### S1: projeto e CI

- **Vite 8.3.8, React 19.3.1, TypeScript 5.9.3** (L8 do ADR 0011), Vitest 5.1.1, jsdom 31.0.1 e Testing Library, com TypeScript estrito (`noUncheckedIndexedAccess`, `exactOptionalPropertyTypes`).
- **A tela roda em `127.0.0.1:3000`**, com `strictPort`, a origem liberada no CORS do backend.
- **`frontend/.npmrc`:**
  - `min-release-age=7`: só instala versões publicadas há mais de 7 dias, inclusive as transitivas. A opção foi conferida no código do npm 11 (`@npmcli/config`).
  - `save-exact`, `ignore-scripts` e `engine-strict`. Nenhum pacote do lock tem script de instalação.
  - Node `^24.15.0`, pelo jsdom.
- **O job `frontend` do CI roda:**
  - `npm ci` e `npm audit --audit-level=low`;
  - `npm audit signatures`, que confere a assinatura do registro de cada pacote;
  - a checagem dos tipos do contrato, lint, `tsc`, Vitest, build e a checagem de segurança (S6).

  O CodeQL de JavaScript, que já existia, passou a rodar.
- **O Dependabot ganhou o bloco do npm com `cooldown` de 7 dias.** O suporte do npm a `cooldown.default-days` foi conferido na tabela da documentação do GitHub ("NPM and Yarn").

### S2: contrato tipado e cliente

- **`src/api/esquema.gen.ts` é gerado de `docs/contrato/openapi.json`** pelo `openapi-typescript` 7.13.0 (`npm run contrato`).
  - O CI roda `npm run contrato:checar` (`--check`) e falha se os tipos ficarem atrás do contrato.
  - O gerador rodou com toda a rede do Node bloqueada e não tentou nenhuma conexão.
- **O cliente é o `openapi-fetch` 0.17.0**, embrulhado em `src/api/cliente.ts`. Toda requisição:
  - sai sem credenciais (`credentials: 'omit'`), sem Referer e sem cache;
  - recusa redirecionamento (`redirect: 'error'`);
  - tem tempo limite de 30 s.
- **`chamar()` devolve `{ dados, mock }` ou lança `ErroApi`**, com o tipo: resposta, rede, tempo, cancelado, entrada ou formato.
  - O corpo de erro só é aproveitado se tiver o formato da RFC 9457 (`src/api/problema.ts`).
  - Um corpo fora do formato (HTML de proxy, texto) nunca chega à tela; em seu lugar vai uma frase em português pelo status.
- **O endereço da API (`src/api/config.ts`)** é `127.0.0.1:8000` no desenvolvimento e `/api` no build (L11 do ADR 0011), ou `VITE_CONTAAI_API`.
  - Recusa `//host`, usuário e senha embutidos, consulta, fragmento, `javascript:` e http fora da máquina local.

**Achados, todos corrigidos com teste:**
- **`..` como id trocava a rota:** `/api/explicar/..` virava `/api/`. Agora o cliente só aceita parâmetros de caminho com letras, dígitos e hífen, o mesmo padrão de todos os parâmetros do contrato.
- **Referer na cópia da requisição:** pelo padrão Fetch, copiar uma `Request` com opções zera o referrer e a política de referrer. A cópia feita para o tempo limite repõe os dois.
- **`Retry-After`:** o `Date.parse` aceitava `"-5"` e `"1.5"` como datas. Agora só valem segundos ou a data IMF-fixdate (RFC 9110).

### S3: espaço e modo

- **O modo vem de `GET /saude`.** O espaço de avaliação só é oferecido no modo real (no mock, `POST /espacos` dá 501).
- **O id do espaço fica no `localStorage`**, para que uma segunda aba aberta pela banca use o mesmo espaço; o evento `storage` mantém as abas iguais.
  - Ele nunca vai ao endereço da página (docs/seguranca.md, item 5).
  - Só é aceito no padrão `^[0-9a-f]{32}$`.
  - A validade usa a duração que o servidor dá (`expiraEm − criadoEm`), contada no relógio do navegador, porque a resposta não traz a hora do servidor e o CORS não expõe o header `Date`. Um relógio local errado não muda a conta.
  - Um espaço vencido deixa de ser enviado mesmo se a aba ficou suspensa.
- **O token da demo fica só na memória da aba.** Recusa quebra de linha (injeção de header), caractere fora do ASCII visível e mais de 512 caracteres. Um 401 com token o apaga, para a tela pedir de novo.
- **O id do espaço e o token só vão às rotas que os declaram no contrato** (`src/api/rotas.ts`; um teste compara as listas com o `openapi.json`).
- **No 404 `/problemas/espaco-inexistente`, o espaço é marcado como vencido**, só se o id enviado ainda for o atual. A resposta atrasada de um espaço antigo não apaga o novo: há teste de corrida, e o teste de mutação confirmou que sem a checagem ele falha.
- **Verificado contra a API no modo real**, com os motores e um token de teste:
  - criar, conferir e usar o espaço;
  - restaurar dentro dele sem token;
  - 401 fora dele;
  - chat exigindo o token mesmo no espaço;
  - espaço inexistente voltando à demonstração compartilhada.

### S4: tokens e fontes

- **`src/estilo/tokens.css` traz os valores do estilo `achromatic-ledger`** (`.taste-skill/app/direction.json`), com nomes em português. O `app.css` da skill não é copiado (L9 do ADR 0011).
- **Fundo `#f2f4f7` no lugar do `#f8f8f8` da folha:** é a troca que a própria folha sugere para um livro-caixa ("a blue-grey (#f2f4f7) for a ledger").
- **`--borda-campo: #8a8a8a`**, porque o `#d4d4d4` da folha dá cerca de 1,5:1 e a WCAG 2.2 (1.4.11) pede 3:1 na borda que identifica um campo.
- **O contraste é conferido em teste** pela fórmula da WCAG 2.2: texto 4,5:1; gráfico, foco e borda de campo 3:1. O par mais apertado é o texto suave no fundo elevado, com 4,59:1. Outro teste compara 33 tokens com o `direction.json`.
- **Geist e Geist Mono** (`@fontsource-variable` 5.3.0, SIL Open Font License 1.1, sem dependências) entram no build. Nada vem do Google Fonts ou de CDN.
  - Lidos com o fontTools: a Geist tem `tnum` (algarismos proporcionais por padrão), e a Geist Mono tem largura fixa de 600.
  - No Chrome, só os arquivos do alfabeto latino são baixados, e `tabular-nums` iguala "1111" e "0000" (33,61 px).
- **Os números vão em Geist Mono** (L10 do ADR 0011). O lint da skill dá 4 WARN `mono`, a decisão do estilo, e 0 FAIL.

### S5: shell

- **Shell sem barra lateral:**
  - barra de 48 px no fundo da página;
  - coluna centrada de 1152 px, com a marca na borda esquerda da coluna;
  - os destinos Painel, Catálogo, Regime, Notas e Contador;
  - à direita, o modo e o espaço.
- **Abaixo de 900 px**, os destinos e o estado da sessão vão para um `<dialog>` modal de tela cheia, com links de 44 px.
- **A navegação é própria, com a History API**, sem biblioteca de rotas. O tipo `Caminho` só aceita as cinco rotas fixas (docs/seguranca.md, item 2).
  - A cada navegação, o foco vai para o h1 e o título da aba muda (não na primeira página).
  - O voltar do navegador funciona, e Ctrl+clique abre nova aba.
- **"Pular para o conteúdo"** é o primeiro Tab, e o foco tem contorno visível em tinta.
- **O rodapé traz o aviso legal (P9) e as versões dos motores em execução**, avisando motor fora do ar ou versão diferente da fixada.
  - O aviso é o mesmo texto de `AVISO_LEGAL` do backend; `backend/tests/test_contrato.py` confere a igualdade.
  - O Vite não deixa o teste da tela ler arquivos fora de `frontend/` com `?raw`, e abrir essa permissão valeria também para o servidor de desenvolvimento.
- **A sessão chega aos componentes por contexto** (`src/sessao/contexto.tsx`), e os testes passam instâncias próprias com um fetch falso.

**Achados, corrigidos:**
- **O aviso de `POST /espacos` é escrito para quem integra a API** (fala do header e do token) e esticava a barra. A tela mostra no lugar uma frase do ADR 0010: "Uma cópia própria dos dados fictícios. O que você mudar nela não afeta a demonstração compartilhada." Ela fica só para leitor de tela na barra (ligada ao botão) e visível na folha do celular.
- **O rodapé preso ao fim da janela** (`min-height: 100vh`) criava um vão vazio que o inspetor da skill reprovava (FAIL `blank-gap`). Foi retirado.
- **O `display` da `.botao-secundario` deixava o botão Menu visível no desktop.** Foi corrigido por especificidade.

### S6: segurança da tela

- **`frontend/csp.ts` é a fonte única da CSP.** Ela é a de docs/seguranca.md, mais `trusted-types 'none'`: nenhuma política do Trusted Types pode ser criada, e o React não precisa de nenhuma.
  - **No build**, um plugin do `vite.config.ts` põe a CSP num `<meta>` logo depois do `charset`, antes de todo script e estilo, porque uma CSP em `<meta>` só vale para o que vem depois dela. Sem o charset no lugar, o build falha.
  - **`frame-ancestors`** só vale no cabeçalho, porque o navegador o ignora no `<meta>`.
  - **O `vite preview`** manda `Content-Security-Policy`, `X-Content-Type-Options`, `Referrer-Policy` e `X-Frame-Options`, os cabeçalhos que o proxy da E6 deve repetir (`cabecalhosDeSeguranca`).
  - **`connect-src`** é `'self'`, mais a origem de `VITE_CONTAAI_API` se ela for absoluta.
- **O servidor de desenvolvimento do Vite fica sem CSP**, porque injeta script (React Refresh) e estilo embutidos.
- **O lint (`no-restricted-syntax`) barra:**
  - `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write` e `srcDoc`;
  - `href`/`src` montados de um valor (só o `Link` monta `href`);
  - o atributo `style`;
  - `import.meta.env` fora de `src/api/config.ts`.
- **`scripts/checar-seguranca.mjs` (`npm run seguranca`, no CI depois do build) busca os mesmos padrões no código e confere o `dist/`:**
  - a CSP do `<meta>` igual à de `csp.ts` e antes de todo recurso;
  - nenhum `<script>` sem `src` próprio, `<style>`, atributo `style` ou `on*=`;
  - nenhum mapa de código;
  - nenhum endereço absoluto além dos nomes de espaço XML e dos links de erro do React (texto, não requisição);
  - nenhum `127.0.0.1` ou `localhost` no build publicado.

  Pegou os 9 defeitos plantados para testá-lo.
- **Upload (item 7, `src/api/upload.ts`):** a tela confere antes de enviar.
  - Só `.xml`, com os tipos que `POST /nfe/importar` aceita, nem vazio nem acima de 1.000.000 bytes.
  - O backend continua decidindo (411, 413 e 415). O teste do backend confere que o limite e os tipos são os mesmos dele.

## Testes de segurança no navegador (2026-11-25)

O build foi servido pelo `vite preview` com os cabeçalhos e aberto no Chrome pelo protocolo DevTools. Na carga: nenhuma violação de CSP e nenhum erro no console, com as fontes e o CSS aplicados.

| Ataque | Resultado |
|---|---|
| `innerHTML` com `<img onerror>` | Bloqueado (Trusted Types, `TypeError`) |
| `insertAdjacentHTML`, `document.write` | Bloqueados |
| `<script>` com texto; `<script src>` de terceiro | Bloqueados |
| `eval`, `new Function`, `setTimeout` com texto | Bloqueados (`EvalError`/`TypeError`) |
| Criar uma política do Trusted Types | Bloqueado |
| Link `javascript:` | Não executou |
| `fetch` e imagem a um terceiro | Cancelados pela CSP antes de sair (`blockedReason: csp`) |
| `<style>` injetado | Não aplicado |
| Outra origem embutindo a tela num iframe | Recusado (`frame-ancestors 'none'`) |
| A API permitida (`connect-src`) | 200 |

O `eval` foi testado por um módulo da própria página, e não pelo console do DevTools, que o Chrome isenta da CSP. O iframe foi servido de outra origem de verdade (outra porta), e não de um `data:`.

## Consequências

- **No navegador vão** só React, React DOM, scheduler e openapi-fetch (MIT) e as fontes Geist (OFL-1.1). As outras dependências são de desenvolvimento, todas com licença livre (MIT, Apache-2.0, ISC, BSD, MPL-2.0, BlueOak e CC-BY-4.0, esta só para os dados do caniuse-lite).
- **Testes:**
  - frontend: 191 (Vitest);
  - backend: 391, com cobertura de 96%; os dois novos conferem o aviso legal, o limite de upload e os tipos da tela contra os do backend.
- **O inspetor da skill (`inspect.mjs --app`)** dá 0 FAIL e 1 WARN (`hero-void`), a área vazia das páginas provisórias.
- **No Chrome, em 1440, 768 e 390 px:**
  - a página não rola para o lado, e a marca e o conteúdo dividem a borda esquerda;
  - nenhuma requisição vai a terceiros;
  - um espaço criado pela tela não põe o id no endereço, no texto nem no título.

### Em aberto

- **E6 (deploy):**
  - o proxy repete os cabeçalhos de `cabecalhosDeSeguranca` e serve `index.html` para as rotas da tela;
  - a API fica em `/api`;
  - entra HSTS.
- **PR 3 da E5:** as telas, com o portão da skill (P11, zero FAIL nas três larguras) e as regras de exibição de texto em cada uma.
- **ESLint 10:** quando o `eslint-plugin-jsx-a11y` aceitar a 10.
- **Tradução das mensagens de validação no backend:** PR separado (decisão 2).
- **O aviso de `POST /espacos`** segue escrito para quem integra a API. A tela não o mostra.
