# ADR 0011: contrato para a tela da E5 e proteções do navegador

- Status: aceito
- Data: 2026-11-25
- Etapa: antes da E5 (PR 1 dos três aprovados: o contrato do backend)
- Código: `backend/app/contrato.py`, `backend/app/nfe/consultas.py`, `backend/app/api/rotas/notas.py`, `backend/app/api/rotas/explicacao.py`, `backend/app/api/middlewares.py`, `backend/app/main.py`, `backend/app/persistencia/` (migração 0002, repositório e sementes), `backend/app/precificacao/lote.py` e `data/demo/sementes.json`

## Contexto

O mapeamento da E5 comparou o que as telas do inventário (`.taste-skill/app/inventario.md`) precisam com o que a API entrega e com as ferramentas do frontend. Ele achou onze lacunas e inconsistências (L1 a L11).

Em 2026-11-25, o usuário aprovou as quatro decisões recomendadas. Ele também pediu duas coisas antes da E5: corrigir todas as lacunas e verificar a segurança, com proteção contra XSS e testes de segurança.

### Decisões do usuário

1. **Frontend em Vite + React, como páginas estáticas, no lugar do Next.js do plano.**
   - Pela documentação oficial do Next.js, uma CSP estrita sem `unsafe-inline` exige um destes dois caminhos:
     - nonce, que obriga a renderização dinâmica num servidor Node;
     - hashes SRI, um recurso ainda experimental.
   - No export estático, rewrites, redirects e headers dão erro até no `next dev`.
   - Com Vite, o build só gera arquivos `.js` externos. A CSP `script-src 'self'` basta, e não há servidor Node em produção.
   - Os React Server Components tiveram uma falha crítica de execução remota, já corrigida (CVE-2025-55182, nota 10, GHSA-fv66-9v8q-g76r).
   - Fontes: nextjs.org/docs/app/guides/content-security-policy, nextjs.org/docs/app/guides/static-exports e o aviso GHSA-9qr9-h5gf-34mp do repositório vercel/next.js.
2. **Preço e classificação gravados pela tela, só no espaço ou com o token**, como lançamentos de acréscimo (migração 0002). Um item novo cadastrado pelo chat fica só na tela.
3. **A linha do tempo 2026 × 2027 (D2) e a exportação (D3) ficam fora da E5.** São os itens 1 e 2 da ordem de corte do plano.
4. **A E5 vai em três PRs:** este contrato, a fundação do frontend e as telas com o portão da skill.

## Decisão: o que mudou

### L1 e L2: o cenário e os clientes B2B saem pelo catálogo

- `GET /catalogo` passou a trazer:
  - `cenario`: a `operacao` da empresa (data, UF, município, alíquotas e premissas do DAS, com a fonte), a descrição e a carga atual;
  - `clientesB2B`: os clientes empresa, cada um com a compra mensal;
  - `loteReferencia`.
- O cenário é o mesmo que as margens dos alertas usam (`app.empresa.operacao_da_empresa`). A tela não repete nenhuma alíquota no próprio código (P6).
- Os clientes B2B entram nas sementes pelo manifesto. `clientesB2B` em `sementes.json` liga cada cliente ao CNPJ da empresa que vende para ele.
  - A restauração recusa um cliente de empresa que não está nas sementes, um cliente repetido ou igual à empresa, e uma compra com item fora do catálogo.
  - Os clientes ficam na tabela `clientes_b2b` (migração 0002).
- **Verificado:**
  - a margem da cerveja que a tela refaz só com o catálogo é a do alerta da nota 2: 11,19%, contra os motores (`tests/test_tela_golden.py`);
  - a venda ao Mercado Bom Preço montada pelo catálogo dá o `valorVenda` esperado.

### L3: `GET /explicar/{itemId}` lê o estado

- Antes, a rota lia o arquivo da semente. Ela usava o preço antigo depois de um preço aplicado e só servia para a Serra Azul.
- Agora ela lê o item no estado (preço atual e classificação atual), com o cenário da empresa, no lote de referência.
- Parâmetros novos: `cnpj` (sem ele, vale a distribuidora da demo) e o header `X-ContaAI-Espaco`.
- **A memória de cálculo da explicação agora é a mesma conta da linha do catálogo.** No tradicional, o arroz dá R$ 32,40 + R$ 0,36 = R$ 32,76 a cada 100 unidades, o número do inventário. O mock `explicar.json` foi regerado pelos motores.

### L4: preço e classificação pela tela

| Rota | O que faz |
|---|---|
| `POST /catalogo/{itemId}/preco` | Lança o preço escolhido (origem `tela`). Recusa com 409 o preço igual ao atual. Não fecha alertas: eles fecham só pelo `POST /alertas/{id}/aplicar` |
| `POST /catalogo/{itemId}/classificacao` | Grava a classificação confirmada (P3). Só aceita uma candidata válida para a NCM nos dados abertos do motor RR, na data do cenário, e o CST vem da fundamentação oficial, não da tela. Tem checagem otimista (409 se o item mudar no meio) |

- As duas respondem 501 no modo mock e exigem o token fora do espaço.
- A classificação atual de um item é a do último lançamento. Toda leitura de item do repositório a aplica, então catálogo, importação de nota, alertas e explicação usam a nova.
- O texto da fonte da correção é montado só com dados oficiais e datas, nunca com texto digitado.
- **Verificado contra os motores** (`tests/test_tela_golden.py`):
  - a carne bovina (NCM 02013000, cClassTrib 200035) volta com REG-011;
  - as candidatas oficiais são 200003 (CST 200) e 000001 (CST 000);
  - corrigida para 200003, ela fica CALCULO_SIMULADO no híbrido e CALCULADO no tradicional. É o critério M3 do plano.

**Migração 0002 (`0002_tela.sql`):**
- a tabela `precos` é refeita com a origem `tela` (o SQLite não altera um CHECK), com o mesmo conteúdo, índice e gatilho de imutabilidade, e com uma regra nova: só o preço de origem `alerta` tem `alerta_id`;
- as tabelas `classificacoes` (com gatilho de imutabilidade) e `clientes_b2b` são novas;
- um espaço copiado por um processo da versão anterior recebe a migração ao ser aberto (`abrir_estado` passa por `banco()`, que migra uma vez por processo).

### L5 e L6: CORS e lote

- **L5.** O CORS expõe `Retry-After` e `X-ContaAI-Mock`. Sem isso, o JavaScript de outra origem não lê esses dois headers, porque eles estão fora da lista de headers que o padrão Fetch libera.
- **L6.** O lote de 100 unidades fica num lugar só (`app/precificacao/lote.py`). O preço-alvo, as margens dos alertas, a explicação e o gerador de mocks usam esse valor, e a tela recebe `loteReferencia` pela API.

### L7 a L11: registrados para os PRs da interface

| # | Registro |
|---|---|
| L7 | O inventário ganhou a seção do chat lateral: pergunta, achado, blocos e regras |
| L8 | Usar o TypeScript **5.9.3**. O 7.0.2, mais recente no npm, é incompatível com o typescript-eslint 8.74.0 (que exige `typescript >=4.8.4 <6.1.0`, inclusive pelo eslint-config) e com o openapi-typescript 7.13.0 (que exige `^5.x`). Conferido no registro do npm em 2026-11-25 |
| L9 | A skill design-taste-frontend não declara licença para `assets/app.css` e `assets/charts.js`, e o repositório é público e MIT. Esses arquivos não são copiados: o CSS e os SVG (barra de margem contra o alvo e régua do crédito) são escritos no projeto, e a skill entra só como referência e como portão, rodando da pasta dela |
| L10 | Números em Geist Mono é a "cara" do estilo achromatic-ledger. O plano (§12) diz "sem fonte monoespaçada fora de código", mas a skill permite mono em todos os números como decisão do estilo (`app-screens.md` §13). No modo app, o inspetor só avisa (WARN `mono`, acima de 15% do texto), não falha. A justificativa vai no relatório da E5 |
| L11 | `/catalogo` e `/contador` existem como rota da tela e da API. Na mesma origem, colidiriam. O endereço da API é configurável no frontend desde já, e no deploy (E6) a API fica em `/api` no proxy |

### Proteções do navegador

| Ameaça | Proteção | Onde |
|---|---|---|
| XSS | A API nunca responde HTML: só JSON e Problem Details, com `nosniff` e `Content-Security-Policy: default-src 'none'` em toda resposta, inclusive nos erros. O teste percorre todas as rotas do contrato com payload de XSS, nos dois modos. A única página HTML é o `/docs`, desligável (`CONTAAI_DOCS_PUBLICA=false`), porque o Swagger carrega scripts de uma CDN e, na mesma origem da tela, alcançaria o que a tela guarda no navegador. Na tela, as regras estão em `docs/seguranca.md` | `middlewares.py`, `main.py` |
| CSRF | POST com `Origin` fora de `CONTAAI_CORS_ORIGENS` → 403, inclusive `Origin: null`. O navegador sempre manda Origin num POST de outra origem, até num formulário simples, que não passa pelo preflight. Sem Origin (curl, scripts), segue. Corpo `text/plain` ou de formulário não é lido como JSON (422). Reforçado na C1 ([ADR 0015](0015-contas.md)): também no DELETE, `Sec-Fetch-Site: cross-site` → 403 e cookie da sessão sem Origin → 403 | `verificar_origem` |
| DNS rebinding | Só os hosts de `CONTAAI_HOSTS_PERMITIDOS` (padrão: `127.0.0.1` e `localhost`) → senão 400. Uma página de outro domínio que passe a resolver para 127.0.0.1 chega com o Host dela | `verificar_host` |
| Corpo gigante | JSON acima de `CONTAAI_TAMANHO_MAX_JSON_BYTES` (1 MB) → 413 antes de ser lido. Corpo em pedaços (sem Content-Length) → 411. Antes, só a NF-e tinha limite | `limitar_corpo` |
| Número extremo | **Achado e corrigido:** `"1e999999"` ou 35 dígitos no valor derrubavam o cálculo com erro 500, e `"1e-999999"` ia ao motor. Agora valores aceitam até 10 casas (como o leitor da NF-e), quantidades e percentuais até 4, com teto de R$ 1 bilhão por unidade e 1 bilhão de unidades. O teto é escolha de projeto, não regra fiscal | `contrato.py` |
| Abuso | As rotas novas entram no limite por IP. Os ids de item seguem um padrão fixo (`^[a-z0-9][a-z0-9-]{0,63}$`), validado também nas sementes | `middlewares.py`, `dados_demo.py` |
| Leitura por outro site | `Cross-Origin-Resource-Policy: same-origin` (era `same-site`): uma `<img>` ou um `<script>` de outro site não lê a resposta. Não afeta o `fetch` em modo CORS da tela (MDN e padrão Fetch) | `middlewares.py` |
| Asserts | `assert` some com `python -O`. Os 5 do app viraram checagens explícitas: no leitor da NF-e, um campo ausente viraria erro 500 | `leitor.py` e outros |

A ordem dos middlewares, de fora para dentro: cabeçalhos de segurança, Host, CORS, Origin, limite por IP e tamanho do corpo. O OpenAPI documenta as recusas novas (400 em toda rota; 403, 411 e 413 em todo POST).

## Testes de segurança (2026-11-25)

| Teste | Resultado |
|---|---|
| `tests/test_seguranca_api.py` (CI) | 41 testes: XSS em todas as rotas (mock e real), texto como dado JSON, `/docs` desligável, Host, Origin, corpo não JSON, CORS, 413 e 411, injeção de SQL e de caminho, guarda contra SQL montado com texto, números extremos sem chamar o motor e cabeçalhos nos erros |
| `tests/test_tela.py` (CI) e `tests/test_tela_golden.py` (motores) | 31 e 2 testes do contrato novo |
| Regras de segurança do ruff (`S`, as do bandit), agora no CI | App limpo depois das correções. Os XML lidos nos scripts são os da demo e o do motor local, marcados no código |
| Ao vivo, uvicorn no modo real com `curl` | 11 verificações iguais às do CI (Host, Origin, preflight, headers expostos, 411, 413, número extremo, injeção, rotas da tela no espaço) |
| pip-audit 2.10.1 no `uv.lock` | Nenhuma vulnerabilidade conhecida |
| gitleaks 8.30.1 (histórico com 33 commits e pasta de trabalho) | Nenhum segredo |
| OWASP ZAP 2.17.0 (varredura ativa da API pelo OpenAPI, imagem oficial `ghcr.io/zaproxy/zaproxy`, Apache-2.0) | 0 FAIL, 119 PASS e 1 WARN (CORP), corrigido. Detalhes na seção abaixo |

Ao todo: 389 testes do CI (antes, 317), 52 golden (antes, 50), cobertura de 96% no `app/`, mypy e ruff limpos.

### Varredura do OWASP ZAP

**Como rodou:**
- `zap-api-scan.py` do ZAP 2.17.0, com a varredura ativa (fuzz), a partir do `openapi.json`, com as 37 URLs do contrato;
- contra uma instância só para ela: modo real com os motores oficiais, banco próprio, limites por IP desligados (senão o scanner só veria 429) e `host.docker.internal` liberado.

**Resultado:**
- **0 FAIL, 119 PASS e 1 WARN.** Entre os PASS estão XSS refletido, persistente e de DOM, injeção de SQL (inclusive por tempo), injeção de comando do sistema, injeção de template, XXE, Billion Laughs, travessia de caminho, CRLF, Log4Shell, Spring4Shell, React2Shell, metadados de nuvem e vazamento de `.env`.
- No log da API: cerca de 6.900 requisições, nenhum 500 e nenhuma exceção. Quase todas deram 422, a validação do contrato.

**O WARN e a correção:**
- O aviso foi `Cross-Origin-Resource-Policy` com `same-site`, que o ZAP considera fraco: a solução dele é `same-origin`.
- Pelo MDN e pelo padrão Fetch, o CORP só vale para requisições `no-cors`. A tela chama a API com `fetch` em modo CORS, então o valor passou para `same-origin` sem afetá-la.

**Avisos informativos, sem risco:**
- os 404, 405 e 422 do fuzz;
- o `Cache-Control: no-store`, que é proposital.

## Consequências

- **Contrato, só com acréscimos:**
  - `CatalogoResposta` ganhou `cenario`, `clientesB2B` e `loteReferencia`;
  - rotas novas para preço e classificação;
  - `cnpj` e o espaço em `GET /explicar/{itemId}`;
  - limites numéricos nas entradas;
  - novas recusas documentadas.

  `docs/contrato/openapi.json` foi reexportado. Ainda não há frontend consumindo.
- **O que muda para quem já usava:**
  - `GET /explicar/{itemId}` no modo real devolve 404 se o banco não tiver a empresa (antes, lia o arquivo);
  - a memória dele passou a ser do lote de 100 unidades.
- **Configuração nova:** `CONTAAI_HOSTS_PERMITIDOS`, `CONTAAI_DOCS_PUBLICA`, `CONTAAI_TAMANHO_MAX_JSON_BYTES` e a origem `http://127.0.0.1:3000` no CORS (a tela roda na porta 3000).
- O workflow Golden passou a rodar também quando muda `backend/app/dados_demo.py`.

### Em aberto

- **Deploy (E6):**
  - o domínio público em `CONTAAI_HOSTS_PERMITIDOS` e em `CONTAAI_CORS_ORIGENS`;
  - `CONTAAI_DOCS_PUBLICA=false`;
  - HSTS e a API em `/api` no proxy.
- **Na fundação do frontend** (resolvido no [ADR 0012](0012-fundacao-do-frontend.md)):
  - a CSP da tela e o Trusted Types: conferidos no Chrome, funcionam com o React;
  - as regras de exibição de texto em `docs/seguranca.md`, com lint, teste e checagem no CI.
- O erro 500 segue sem os cabeçalhos de segurança ([ADR 0009](0009-camada-http-e-erros.md)). Na bateria nova, nenhuma rota chegou a 500.
