# ContaAI

Copiloto de preço e margem para a pequena empresa na reforma tributária (Hackathon 2026, Trilha 05: Pagamentos e finanças).

O dono de uma ME do Simples conversa com o copiloto sobre o que vende. O ContaAI mostra quanto de CBS, IBS e IS incide em cada item, que preço mantém a margem, se vale ir para o Simples híbrido para vender a empresas e o que mudou quando chega uma nota de compra. **Toda conta vem das calculadoras oficiais da Receita Federal; a IA só interpreta e explica.**

> Estimativa baseada nas calculadoras oficiais. Não é parecer fiscal e não substitui o contador.

## Como rodar

### Requisitos

- Docker com Compose (Docker Desktop no Windows e no macOS, Docker Engine no Linux). Não é preciso instalar Java nem Maven: os motores são compilados dentro dos containers.
- [uv](https://docs.astral.sh/uv/) para o backend; ele baixa o Python 3.12 se faltar. Também funciona com `pip`.
- [Node.js](https://nodejs.org/) 24 (a partir da 24.15) para a tela.

### Motores oficiais

```bash
docker compose up -d --build   # primeira vez: alguns minutos (dependências Maven e banco do Flyway)
docker compose ps              # esperar motor-rr e motor-sn com status "healthy"
```

| Motor | Versão fixada | API | Swagger |
|---|---|---|---|
| Regime Regular | 1.7.2 | `http://127.0.0.1:8080/api/calculadora` | `http://127.0.0.1:8080/api/swagger-ui.html` |
| Simples Nacional | 1.0.2 | `http://127.0.0.1:8082/api/calculadora` | `http://127.0.0.1:8082/api/swagger-ui.html` |

As portas só abrem em `127.0.0.1`, porque os motores não têm autenticação ([ADR 0002](docs/adr/0002-motores-em-containers.md)). Para parar: `docker compose down`.

### API

```bash
cd backend
uv sync --extra dev
uv run uvicorn app.main:app --reload   # documentação interativa em http://127.0.0.1:8000/docs
```

As rotas seguem o contrato ([docs/contrato/openapi.json](docs/contrato/openapi.json), [ADR 0003](docs/adr/0003-contrato-da-api.md)). Há dois modos:

- **mock** (padrão): as rotas de cálculo e de leitura da demonstração respondem com mocks gerados a partir dos motores oficiais, com o header `X-ContaAI-Mock: 1`. As que gravam, as das contas, as da empresa própria e as que dependem dos motores sem mock respondem 501, e o mock nunca cria banco. `tests/test_modo_mock.py` classifica cada rota do contrato.
- **real** (`CONTAAI_MODO=real`, motores de pé): `POST /carrinho/calcular` e `POST /item/preco-alvo` calculam pelos motores ([ADR 0004](docs/adr/0004-nucleo-de-calculo.md), [ADR 0005](docs/adr/0005-preco-alvo-e-premissas.md)); `GET /busca/ncm`, `GET`/`POST /explicar`, `GET /erros/{codigo}` e `POST /chat` também ([ADR 0006](docs/adr/0006-agente.md)), `POST /regime/comparar` ([ADR 0007](docs/adr/0007-comparacao-de-regimes.md)), e NF-e, alertas, catálogo e painel do contador ([ADR 0008](docs/adr/0008-nfe-historico-e-alertas.md)). Para a tela, o catálogo traz o cenário da empresa, os clientes B2B e o lote de referência, e a tela grava preço e classificação (`POST /catalogo/{itemId}/preco` e `/classificacao`, [ADR 0011](docs/adr/0011-contrato-da-tela-e-seguranca.md)). Todo erro sai no formato Problem Details da RFC 9457 (`application/problem+json`, com `type`, `title`, `status` e `detail`); `GET /problemas/{nome}` descreve cada tipo próprio ([ADR 0009](docs/adr/0009-camada-http-e-erros.md)). Falhas dos motores voltam como 422 (operação recusada, com os erros do motor), 502 ou 503, sem expor endereço interno.

### Testar a recorrência (NF-e → alerta)

No modo real o estado fica num SQLite local (`backend/.dados/contaai.db`, fora do git). Na primeira subida, com o banco vazio, o backend carrega as sementes de `data/demo/` sozinho: três empresas fictícias e as notas iniciais.

```bash
cd backend
CONTAAI_MODO=real uv run uvicorn app.main:app          # motores de pé (docker compose up -d)
curl -F "arquivo=@../data/demo/notas/nfe-compra-2.xml;type=text/xml" http://127.0.0.1:8000/nfe/importar
```

A nota 2 gera o alerta da cerveja: margem de 24,12% para 11,19%, alvo de 15%, preço sugerido R$ 3,97 (simulação de 2027 com premissas impressas). Também dá para testar:

- `data/demo/notas/nfe-item-sem-par.xml`: um código sem cadastro e um com NCM diferente da do cadastro;
- a mesma nota de novo: volta o recibo da primeira importação (`jaImportada`), sem gravar nada;
- `GET /catalogo?cnpj=36817420000113`, `GET /notas?cnpj=36817420000113`, o recibo de uma nota já importada (`GET /notas/71604258000156/1/1001?cnpj=36817420000113`), `GET /alertas`, `POST /alertas/{id}/aplicar` e `GET /contador/painel`;
- `POST /demo/restaurar`: volta tudo às sementes (pela documentação em `/docs` também).

**Espaço de avaliação (para a banca testar tudo sem afetar ninguém).** `POST /espacos` cria uma cópia própria dos dados fictícios e devolve um `id`. Enviado no header `X-ContaAI-Espaco`, ele faz as rotas de notas, alertas, catálogo, painel, restauração e chat usarem só aquele espaço. Dentro do espaço, importar, aplicar e restaurar não pedem o token da demo. O espaço vale 2 horas desde a criação (`CONTAAI_ESPACO_VALIDADE_MIN`), e o servidor guarda no máximo 50 ao mesmo tempo (`CONTAAI_ESPACOS_MAX`) ([ADR 0010](docs/adr/0010-espacos-de-avaliacao.md)).

```bash
ID=$(curl -s -X POST http://127.0.0.1:8000/espacos | python -c "import json,sys; print(json.load(sys.stdin)['id'])")
curl -H "X-ContaAI-Espaco: $ID" -F "arquivo=@../data/demo/notas/nfe-compra-2.xml;type=text/xml" http://127.0.0.1:8000/nfe/importar
```

Com `CONTAAI_TOKEN_DEMO` definido, as rotas que mudam a demonstração compartilhada (importar, aplicar e restaurar sem o header do espaço) e o `/chat` pedem o header `X-ContaAI-Token`. Uma nota cujo destinatário não é uma das empresas fictícias é recusada antes de gravar qualquer coisa: dado real não entra no banco.

**Contas (C1, [ADR 0015](docs/adr/0015-contas.md)), só no modo real.** `POST /contas` cria a conta, com o aceite da versão atual dos termos de uso (`termosAceitos`), e devolve o segredo do segundo fator (TOTP, para qualquer aplicativo autenticador). `POST /contas/ativar` confirma o primeiro código e devolve 10 códigos de recuperação. Para entrar, use `POST /sessoes` (e-mail e senha) e depois `POST /sessoes/codigo`. A sessão anda num cookie `HttpOnly` de mesma origem, por isso a tela fala com a API em `/api`, pelo proxy do Vite. Com a sessão, as rotas de estado leem o banco da organização da pessoa, e a demonstração segue aberta para quem não entrou. Uma conta bloqueada depois de 100 tentativas erradas só volta pelo servidor: `uv run python -m app.contas desbloquear <e-mail>`.

**Empresa própria (C3-B, [ADR 0017](docs/adr/0017-empresa-propria.md)), só no modo real.** Com a sessão, `POST /empresas` cadastra a empresa da conta. O CNPJ pode ser numérico ou alfanumérico, sempre com o dígito verificador certo. A UF, o município e a atividade do Simples vêm de `GET /referencias/ufs`, `/municipios?uf=` e `/atividades`, que leem os motores. `PATCH /empresas/{cnpj}` muda as configurações, inclusive as alíquotas efetivas do Simples da empresa. O catálogo ganhou `POST /catalogo/itens`, `PATCH /catalogo/{item_id}` e `POST /catalogo/{item_id}/arquivar`. Os clientes B2B (a venda que a comparação de regimes usa) ganharam `POST /clientes`, `PATCH /clientes/{cnpj_cliente}` e `POST /clientes/{cnpj_cliente}/excluir`; um item na compra de um cliente não é arquivado (409). Com `daNota` (série, número e nItem), o item nasce de uma linha sem par de uma nota já importada, com o custo dessa nota (C3b). Só o dono cadastra, configura e exclui a empresa; o dono e o membro editam o catálogo e os clientes. Com a senha de novo, `POST /conta/dados` devolve o arquivo JSON com os dados da conta e das empresas (LGPD, art. 18 V), e `POST /empresas/{cnpj}/excluir` (também com o CNPJ digitado) exclui a empresa sem excluir a conta. Ao subir, a API apaga os bancos de organizações que não existem mais, e o log de acesso grava a rota-modelo, sem o IP nem o CNPJ. Na demonstração e nos espaços, os CNPJs fictícios continuam valendo.

`GET /cenarios/presets` (valores de 2027 com fonte) e `GET /saude` (estado e versões dos motores) são reais nos dois modos. O CORS libera só `http://localhost:3000` e `http://127.0.0.1:3000`; para outra origem, use `CONTAAI_CORS_ORIGENS='["http://..."]'`.

### Tela

```bash
cd frontend
npm ci        # dependências travadas no package-lock.json, sem scripts de instalação
npm run dev   # http://127.0.0.1:3000; a tela chama /api, e o Vite repassa para http://127.0.0.1:8000
```

Com a API em outro endereço: `CONTAAI_API_ALVO=http://127.0.0.1:8010 npm run dev` (vale também para o `vite preview`). Essa variável fica no servidor do Vite. Toda variável `VITE_*` vai para o navegador; nunca ponha segredo nela. `VITE_CONTAAI_API` aponta a tela direto para outra origem, mas aí a conta não funciona, porque o cookie da sessão só anda na mesma origem.

A barra mostra o modo da API. No modo real, "Criar meu espaço" cria um espaço de avaliação, e o id fica só no navegador. O rodapé traz o aviso legal e as versões dos motores.

A fundação está pronta: cliente tipado do contrato, sessão, tokens do estilo, shell e segurança ([ADR 0012](docs/adr/0012-fundacao-do-frontend.md)). Painel, Catálogo e a explicação lateral estão prontos ([ADR 0013](docs/adr/0013-telas-painel-e-catalogo.md)), e Notas e Regime também ([ADR 0014](docs/adr/0014-telas-notas-e-regime.md)); Contador entra no 3c. Desde a C2a ([ADR 0016](docs/adr/0016-telas-de-entrada.md)), `/` é a página inicial, com "Explorar a demonstração" sem cadastro; o Painel fica em `/painel`, e os termos de uso e a privacidade (rascunhos sem revisão jurídica) em `/termos` e `/privacidade`. Desde a C2b, no modo real, `/criar-conta` cria a conta em três passos (dados, aplicativo autenticador pelo QR code e os 10 códigos de recuperação), `/entrar` pede e-mail, senha e o código, e o menu com o e-mail, na barra, leva a `/conta` (dados, sessão, baixar os dados e excluir a conta). Quem entrou com uma conta vê a própria organização e pode ver a demonstração como todo mundo. Desde a C3a ([ADR 0018](docs/adr/0018-telas-da-empresa-propria.md)), a conta sem empresa é levada a `/empresa/nova`, que cadastra a empresa com o CNPJ (numérico ou alfanumérico), o regime no Simples, a UF, o município e a atividade, nas listas dos motores; depois, o Painel, o Catálogo, o Regime e as Notas mostram a empresa da conta. Desde a C3b (etapas 1 a 5), `/empresa` muda os dados e as alíquotas do DAS da empresa e a exclui (pelo menu da conta ou pelo Painel), e Sua conta baixa o arquivo com os seus dados. Os itens e os clientes pela tela vêm na C3b2. Para importar uma nota pela tela, crie seu espaço e use um XML fictício de [data/demo/notas](data/demo/notas). Desde a C2c, a tela de Notas oferece esses arquivos para baixar. Para ver o build com a CSP e os cabeçalhos de segurança: `npx vite build && npx vite preview`.

**Agente.** O padrão é o provedor `roteiro`: responde às frases do roteiro da demo sem IA, sem chave e sem custo. Para ligar uma IA, escreva o adaptador em `backend/app/agente/provedores/` e configure no `backend/.env` (fora do git) `CONTAAI_LLM_PROVEDOR`, `CONTAAI_LLM_MODELO` e `CONTAAI_LLM_CHAVE` ([ADR 0006](docs/adr/0006-agente.md)). Na demo pública, defina `CONTAAI_TOKEN_DEMO`: o `/chat` e as rotas que mudam o estado passam a exigir o header `X-ContaAI-Token`. Há limite de requisições por IP (`CONTAAI_LIMITE_CHAT_POR_MINUTO`, `CONTAAI_LIMITE_GERAL_POR_MINUTO`, `CONTAAI_LIMITE_BUSCA_POR_MINUTO`).

### Testes

```bash
cd backend
uv sync --locked --extra dev   # dependências travadas no uv.lock (as mesmas do CI)
uv run pytest              # testes que não precisam dos motores (os mesmos do CI)
uv run mypy                # tipos
uv run coverage run -m pytest && uv run coverage report   # cobertura (o CI exige 90% no app/)
uv run pytest -m golden    # testes de referência contra os motores em execução
uv run pytest -m llm       # as 20 perguntas com o provedor de IA do .env (GASTA crédito)

cd frontend
npm run lint && npm run typecheck && npm test   # lint, tipos e testes da tela
npx vite build && npm run seguranca             # build e checagem de segurança (CSP, script embutido, terceiros)
```

No GitHub, o workflow **Golden** sobe os motores e roda os testes de referência: à mão (Actions → Golden → Run workflow) e sozinho nos PRs que mexem nos motores, no cliente, nos geradores ou nos dados de demonstração.

No Linux e no macOS, o [Makefile](Makefile) tem atalhos para os mesmos comandos: `make motores`, `make api`, `make real`, `make sementes`, `make test`, `make golden`, `make llm`, `make indice`, `make lint`, `make tela` e `make tela-checar`.

## Arquitetura (resumo)

| Peça | Papel |
|---|---|
| Motor Regime Regular 1.7.2 (Receita, Java 25) | CBS e IBS por item, dados abertos e memória de cálculo. O IS sai de valor ou alíquota informados: as regras de cálculo do IS estão previstas para a Release 16 do motor |
| Motor Simples Nacional 1.0.2 (Receita, Java 25) | Lado "Simples tradicional" da decisão de regime: CBS e IBS por item a partir das alíquotas efetivas informadas ([ADR 0001](docs/adr/0001-lado-tradicional-do-simples.md)) |
| Backend (FastAPI) | Orquestra, preço-alvo, comparação de regimes, leitura de NF-e e alertas |
| Agente (tool use, provedor de IA trocável) | Só chama as ferramentas do backend; não faz conta. Toda resposta passa pelo verificador de números |
| Frontend (Vite + React, páginas estáticas; E5) | Telas construídas com a skill design-taste-frontend. Troca do Next.js do plano aprovada pelo usuário: CSP estrita sem servidor Node ([ADR 0011](docs/adr/0011-contrato-da-tela-e-seguranca.md)). Fundação: cliente tipado do contrato, espaço de avaliação, tokens do estilo, shell, CSP com Trusted Types ([ADR 0012](docs/adr/0012-fundacao-do-frontend.md)) |

## Princípios

- **P1.** Nenhum código nosso calcula alíquota, base ou tributo. O backend só soma e subtrai valores devolvidos pelos motores e premissas rotuladas.
- **P2.** A IA não faz aritmética tributária: chama ferramentas e explica o que voltou.
- **P3.** A IA nunca decide a classificação fiscal sozinha: propõe candidatos e o usuário confirma.
- **P4.** Para calcular, só os endpoints de observabilidade dos dois motores.
- **P5.** Versões fixadas (Regime Regular 1.7.2, Simples Nacional 1.0.2). Atualizar exige PR próprio e testes de referência verdes.
- **P6.** De 2027 em diante, as alíquotas são premissas do usuário, e a tela mostra que é simulação. 8,8% e 11,3% nunca aparecem como alíquota oficial.
- **P7.** O Imposto Seletivo é premissa informada.
- **P8.** O que o motor do Simples não entrega, como a alíquota efetiva do anexo, vira premissa rotulada e nunca é reimplementado.
- **P9.** O aviso "estimativa, não é parecer fiscal" fica visível em todas as telas e é dito no vídeo.
- **P10.** Só dados sintéticos: empresas, CNPJs e notas fictícios.
- **P11.** A interface passa pelo portão da skill design-taste-frontend: zero FAIL em 1440, 768 e 390 px.

## Documentos

- [Como contribuir](CONTRIBUTING.md): fluxo de branches, PRs e revisão
- [Plano v2.1](docs/plano-v2.1.md): a ordem das etapas (3b, C1 e C2 feitas; C3, a empresa própria, em andamento; depois 3c e entrega), com as decisões do usuário
- [ADR 0001](docs/adr/0001-lado-tradicional-do-simples.md): lado "Simples tradicional" da decisão de regime
- [ADR 0002](docs/adr/0002-motores-em-containers.md): motores em containers, segurança e custos
- [ADR 0003](docs/adr/0003-contrato-da-api.md): contrato da API, fórmulas de preço, margem e regimes, e achados da investigação
- [ADR 0004](docs/adr/0004-nucleo-de-calculo.md): clientes dos motores, carrinho real, comportamento verificado dos motores e revisão da arquitetura
- [ADR 0005](docs/adr/0005-preco-alvo-e-premissas.md): preço-alvo (afim + bisseção), cache e premissas de 2027 com presets de fonte verificada
- [ADR 0006](docs/adr/0006-agente.md): agente com IA trocável, ferramentas, verificador anti-alucinação, busca de NCM e proteção da demo
- [ADR 0007](docs/adr/0007-comparacao-de-regimes.md): comparação Simples tradicional × híbrido, crédito das compras e preço de empate
- [ADR 0008](docs/adr/0008-nfe-historico-e-alertas.md): NF-e de compra, estado em SQLite com migrações, alertas de margem, painel do contador e proteções
- [ADR 0009](docs/adr/0009-camada-http-e-erros.md): camada HTTP em routers, erros no formato da RFC 9457 e ordem dos middlewares
- [ADR 0010](docs/adr/0010-espacos-de-avaliacao.md): espaço de avaliação por visitante (um SQLite por espaço, cópia do banco-modelo, validade e teto)
- [ADR 0011](docs/adr/0011-contrato-da-tela-e-seguranca.md): contrato para a tela da E5 (cenário, clientes B2B, lote, preço e classificação pela tela), proteções do navegador (XSS, CSRF, DNS rebinding) e testes de segurança
- [ADR 0012](docs/adr/0012-fundacao-do-frontend.md): fundação do frontend (Vite + React, cliente tipado, espaço e token na tela, tokens do estilo, shell, CSP com Trusted Types e testes de ataque no navegador)
- [ADR 0013](docs/adr/0013-telas-painel-e-catalogo.md): telas do Painel e do Catálogo e explicação lateral (PR 3a), com correção da classificação e troca de preço pela tela
- [ADR 0014](docs/adr/0014-telas-notas-e-regime.md): telas de Notas (envio do XML, recibo e notas importadas) e de Regime (régua do crédito, caixa, empate e premissas), PR 3b
- [ADR 0015](docs/adr/0015-contas.md): contas com segundo fator (TOTP), sessão em cookie, tentativas, CSRF, um banco de estado por organização e o CNPJ como permissão, C1
- [ADR 0016](docs/adr/0016-telas-de-entrada.md): telas de entrada, a conta na tela, o cookie só onde precisa, a demonstração para quem tem conta, termos e privacidade, C2
- [ADR 0017](docs/adr/0017-empresa-propria.md): a empresa própria no backend, o CNPJ alfanumérico, as referências dos motores, o catálogo e os clientes B2B editáveis, C3-B
- [ADR 0018](docs/adr/0018-telas-da-empresa-propria.md): as telas da empresa própria, a primeira vez, o cadastro da empresa e a empresa da conta nas telas, C3a; as configurações, a exclusão da empresa e o arquivo dos dados, C3b
- [Segurança](docs/seguranca.md): o que o projeto protege, como, e o que está em aberto; para relatar uma vulnerabilidade, [SECURITY.md](SECURITY.md)
- [Contrato OpenAPI](docs/contrato/openapi.json): o que frontend e agente consomem
- [Dados de demonstração](data/demo/README.md): distribuidora, carteira do contador, cliente B2B, notas de compra fictícias e sementes do estado
- [Direção visual](.taste-skill/app/inventario.md): inventário, a pergunta de cada tela e o estilo sorteado pela skill design-taste-frontend
- [Respostas de referência](backend/tests/golden/README.md): o que está gravado e quando regravar
- [Validação com contadores](docs/validacao.md)

## Status

Etapa 0 (fundação) concluída: motores oficiais em containers, testes de referência, decisão sobre o lado tradicional do Simples, contrato da API com mocks, dados de demonstração e direção visual. Pendente fora do código: o envio da mensagem aos contadores (E0-08).

Etapa 1 (núcleo de cálculo) concluída: clientes tipados dos motores, carrinho real, preço-alvo em 3 chamadas com bisseção de reserva e cache, e premissas de 2027 com presets de fonte verificada.

Etapa 2 (agente) concluída: loop de tool use independente do provedor, provedor `roteiro` sem IA, cadastro por chat com confirmação, correção do REG-011 e do VSN-047, explicação pela memória de cálculo e pela lei, busca de NCM nos dados abertos e verificador anti-alucinação (20 perguntas, 0 número fora do JSON). Pendente: o adaptador do provedor de IA (o Claude como principal e o Gemini como reserva, se o nível gratuito for confirmado; decisão de 2026-11-26 no [plano v2.1](docs/plano-v2.1.md)).

Etapa 3 (diferencial B2B) concluída no backend: `POST /regime/comparar` real, com os três números (diferença de caixa, crédito que o cliente leva e custo líquido do cliente), o crédito das compras por item (NF-e ou motor), o detalhamento por linha, o preço de empate com um concorrente do regime regular e a ferramenta `comparar_regimes` do agente. A tela de decisão passou para a Etapa 5 (decisão do usuário, ADR 0007).

Etapa 4 (recorrência) concluída no backend: leitor seguro da NF-e, casamento com o catálogo, histórico de custo em SQLite com migrações versionadas, alerta de margem com o preço-alvo (24,12% → 11,19%, R$ 3,97, em menos de 5 s), aplicar preço, catálogo com o estado atual, painel do contador com três CNPJs fictícios (D1) e a ferramenta `listar_alertas` do agente. As telas (importar nota, painel e contador) ficam para a Etapa 5, como na E3 (ADR 0008).

Antes da Etapa 5: espaço de avaliação por visitante (ADR 0010) e o contrato para a tela, com as proteções do navegador e os testes de segurança (ADR 0011).

Etapa 5 (interface) em andamento: a fundação do frontend está pronta (ADR 0012): projeto e CI, cliente tipado do contrato, espaço de avaliação e modo, tokens e fontes, shell e segurança da tela. PR 3a (Painel, Catálogo e explicação lateral) pronto ([ADR 0013](docs/adr/0013-telas-painel-e-catalogo.md)), e PR 3b (Notas e Regime) também ([ADR 0014](docs/adr/0014-telas-notas-e-regime.md)). Contas no backend (C1) prontas ([ADR 0015](docs/adr/0015-contas.md)). Telas de entrada (C2) prontas: a C2a (página inicial, rotas, a conta na tela, termos e privacidade), a C2b (criar conta, entrar, o menu da conta e Sua conta) e a C2c (notas de exemplo para baixar na tela de Notas) ([ADR 0016](docs/adr/0016-telas-de-entrada.md)). A C3 (dados da própria empresa) está em andamento: o backend está pronto (C3-B, [ADR 0017](docs/adr/0017-empresa-propria.md)): o cadastro, as configurações, o catálogo e os clientes B2B editáveis, os papéis, o arquivo dos dados e a exclusão da empresa, os logs sem dado pessoal e o erro 500 com os cabeçalhos de segurança. A C3a está pronta: a primeira vez, o cadastro da empresa pela tela e a empresa da conta no Painel, no Catálogo, no Regime e nas Notas ([ADR 0018](docs/adr/0018-telas-da-empresa-propria.md)). Da C3b, as etapas 1 a 5 estão prontas: o item a partir da nota no backend, as configurações da empresa, a exclusão da empresa e o arquivo dos dados. Faltam as etapas 6 a 9 (o catálogo, o par da nota e os clientes pela tela), pelo [plano v2.1](docs/plano-v2.1.md).

## Créditos e licenças

As calculadoras da Reforma Tributária do Consumo são da Receita Federal do Brasil e estão no GitHub sob licença MIT ([regime regular](https://github.com/ReceitaFederal/calculadora-rtc-regime-regular), [Simples Nacional](https://github.com/ReceitaFederal/calculadora-rtc-simples-nacional)). A publicação foi autorizada pela Portaria Cotec nº 342, de 12 de novembro de 2026 ([notícia da Receita Federal](https://www.gov.br/receitafederal/pt-br/assuntos/noticias/2026/novembro/receita-federal-publica-primeiro-codigo-fonte-aberto-no-github-e-amplia-transparencia-da-reforma-tributaria)). O ContaAI não altera os motores: o build baixa o commit oficial da versão fixada, conferido pelo SHA (a tag 1.7.2 do regime regular foi republicada em 2026-11-25; [ADR 0002](docs/adr/0002-motores-em-containers.md)).

O código do ContaAI está sob a [licença MIT](LICENSE). As licenças das bibliotecas que vão no navegador saem com o build da tela, no arquivo `licencas.md`, montado pelo Vite com o que entra no build.
