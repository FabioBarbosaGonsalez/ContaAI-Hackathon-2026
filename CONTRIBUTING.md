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
ruff check . && ruff format --check .      # lint e formatação do Python (na raiz)
cd backend && uv run pytest                # testes sem os motores (os mesmos do CI)
cd frontend && npm run lint && npm test    # quando o frontend existir
```

Se mexeu na integração com os motores, rode também os testes de referência com os motores de pé:

```bash
docker compose up -d
cd backend && uv run pytest -m golden
```

No Linux e no macOS, `make lint`, `make test` e `make golden` fazem o mesmo. No Windows sem `make`, use os comandos acima.

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
