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
ruff check .            # lint Python
make golden             # testes de referência contra os motores (quando existirem)
cd frontend && npm run lint && npm test   # quando o frontend existir
```

## Princípios que a revisão cobra

- Nenhum código nosso calcula alíquota, base ou tributo: os valores vêm dos motores oficiais (P1).
- A IA não faz aritmética e não decide classificação fiscal sozinha (P2, P3).
- Resultados de 2027 em diante mostram as premissas e o aviso de simulação (P6).
- Nada de segredos no código: chaves ficam no `.env`, que está no `.gitignore`. Só dados fictícios (P10).

## Labels

`frente:*` diz a frente, `tipo:*` diz o tipo do trabalho, `prioridade:alta` e `bloqueado` ajudam a triagem. Os milestones são as etapas E0 a E6 do plano.

## Releases

Uma tag `vX.Y.Z` na `main` cria a release com notas geradas a partir dos PRs, agrupadas pelos labels `tipo:*`.
