# Como contribuir

## Fluxo

1. Pegue uma issue do backlog (ou crie uma com o modelo **Tarefa do backlog**).
2. Crie uma branch a partir da `main`: `tipo/etapa-descricao-curta`, por exemplo `feat/e1-preco-alvo` ou `fix/e4-leitor-nfe`.
3. Commits pequenos, no padrão [Conventional Commits](https://www.conventionalcommits.org/pt-br/): `feat:`, `fix:`, `docs:`, `test:`, `chore:`, `ci:`, `refactor:`.
4. Abra um Pull Request para a `main` preenchendo o modelo e ligando a issue (`Fecha #123`).
5. O PR só entra com o check **CI** verde, **1 aprovação de outra pessoa** e todos os comentários resolvidos.

## Regras da `main`

- Ninguém faz push direto: tudo entra por PR.
- Quem abriu o PR não aprova o próprio PR, e um novo push depois da aprovação invalida a aprovação.
- Force push e exclusão da `main` são bloqueados.

## Antes de abrir o PR

```bash
uv run --project backend ruff check . && uv run --project backend ruff format --check .   # lint (na raiz)
cd backend && uv run mypy                                     # tipos
cd backend && uv run coverage run -m pytest && uv run coverage report   # testes do CI + cobertura (mínimo 90%)
cd frontend && npm run lint && npm test    # quando o frontend existir
```

Se mexeu na integração com os motores, rode também os testes de referência com os motores de pé:

```bash
docker compose up -d
cd backend && uv run pytest -m golden
```

No Linux e no macOS, `make lint`, `make tipos`, `make test`, `make cobertura`, `make auditoria` e `make golden` fazem o mesmo. O CI também roda o pip-audit (dependências) e o gitleaks (segredos no histórico); ver [docs/seguranca.md](docs/seguranca.md). No Windows sem `make`, use os comandos acima.

No GitHub, o workflow **Golden** roda os mesmos testes de referência: sozinho nos PRs que mexem em `motores/`, `backend/app/motores/`, `backend/app/precificacao/`, `backend/app/cenarios/`, `backend/scripts/`, `backend/tests/golden/` ou `data/demo/`, e à mão em Actions → Golden → Run workflow. Ele não é exigido pela proteção da `main`, porque o build dos motores leva alguns minutos; confira o resultado antes de aprovar.

## Mudou o contrato ou os dados de demonstração?

- **Contrato** (`backend/app/contrato.py`): reexporte com `cd backend && uv run python scripts/exportar_openapi.py`. O teste `test_openapi_exportado_esta_atualizado` falha se o arquivo `docs/contrato/openapi.json` ficar para trás. Registre a mudança no [ADR 0003](docs/adr/0003-contrato-da-api.md).
- **Dados de demonstração** (`data/demo/`): com os motores de pé, regere as notas (`scripts/gerar_notas_demo.py`) e os mocks (`scripts/gerar_mocks.py`), e revise a diferença. Os testes `golden` exigem que notas e mocks sejam reproduzíveis a partir dos motores: nenhum número dos mocks é digitado à mão.

## Trocar a versão de um motor

1. Atualize `*_TAG` e `*_SHA` no Dockerfile do motor (o SHA é o commit para onde a tag aponta; o build falha se não bater).
2. Suba com `docker compose up -d --build` e regrave as respostas: `cd backend && uv run python scripts/gravar_golden.py`.
3. Revise a diferença dos arquivos em `backend/tests/golden/` e abra um PR só com essa troca (P5).

## Princípios que a revisão cobra

- Nenhum código nosso calcula alíquota, base ou tributo: os valores vêm dos motores oficiais (P1).
- A IA não faz aritmética e não decide classificação fiscal sozinha (P2, P3).
- Resultados de 2027 em diante mostram as premissas e o aviso de simulação (P6).
- Versões dos motores só mudam em PR próprio, com os testes de referência verdes (P5).
- Nada de segredos no repositório, que é público: chaves de API (inclusive a do LLM) ficam só no `.env`, que está no `.gitignore`, e nunca vão para código, issue, PR ou captura de tela. Só dados fictícios (P10).

## Labels

`frente:*` diz a frente, `tipo:*` diz o tipo do trabalho, `prioridade:alta` e `bloqueado` ajudam a triagem. Os milestones são as etapas E0 a E6 do plano.

## Releases

Uma tag `vX.Y.Z` na `main` cria a release com notas geradas a partir dos PRs, agrupadas pelos labels `tipo:*`.
