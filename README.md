# ContaAI

Copiloto de preço e margem para a pequena empresa na reforma tributária (Hackathon 2026, Trilha 05: Pagamentos e finanças).

O dono de uma ME do Simples conversa com o copiloto sobre o que vende. O ContaAI mostra quanto de CBS, IBS e IS incide em cada item, que preço mantém a margem, se vale ir para o Simples híbrido para vender a empresas e o que mudou quando chega uma nota de compra. **Toda conta vem das calculadoras oficiais da Receita Federal; a IA só interpreta e explica.**

> Estimativa baseada nas calculadoras oficiais. Não é parecer fiscal e não substitui o contador.

## Como rodar

### Requisitos

- Docker com Compose (Docker Desktop no Windows e no macOS, Docker Engine no Linux). Não é preciso instalar Java nem Maven: os motores são compilados dentro dos containers.
- [uv](https://docs.astral.sh/uv/) para o backend; ele baixa o Python 3.12 se faltar. Também funciona com `pip`.

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

### Testes

```bash
cd backend
uv sync --extra dev        # dependências (alternativa: pip install -e ".[dev]")
uv run pytest              # testes que não precisam dos motores (os mesmos do CI)
uv run pytest -m golden    # testes de referência contra os motores em execução
```

No Linux e no macOS, o [Makefile](Makefile) tem atalhos para os mesmos comandos: `make motores`, `make test`, `make golden` e `make lint`.

## Arquitetura (resumo)

| Peça | Papel |
|---|---|
| Motor Regime Regular 1.7.2 (Receita, Java 25) | CBS e IBS por item, dados abertos e memória de cálculo. O IS sai de valor ou alíquota informados: as regras de cálculo do IS estão previstas para a Release 16 do motor |
| Motor Simples Nacional 1.0.2 (Receita, Java 25) | Lado "Simples tradicional" da decisão de regime: CBS e IBS por item a partir das alíquotas efetivas informadas ([ADR 0001](docs/adr/0001-lado-tradicional-do-simples.md)) |
| Backend (FastAPI) | Orquestra, preço-alvo, comparação de regimes, leitura de NF-e e alertas |
| Agente (LLM com ferramentas) | Só chama as ferramentas do backend; não faz conta |
| Frontend (Next.js) | Telas construídas com a skill design-taste-frontend |

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
- [ADR 0001](docs/adr/0001-lado-tradicional-do-simples.md): lado "Simples tradicional" da decisão de regime
- [ADR 0002](docs/adr/0002-motores-em-containers.md): motores em containers, segurança e custos
- [Respostas de referência](backend/tests/golden/README.md): o que está gravado e quando regravar
- [Validação com contadores](docs/validacao.md)

## Status

Etapa 0 (fundação): motores oficiais em containers, testes de referência e decisão sobre o lado tradicional do Simples prontos. Faltam o contrato da API com mocks, os dados de demonstração e a direção visual.

## Créditos e licenças

As calculadoras da Reforma Tributária do Consumo são da Receita Federal do Brasil e estão no GitHub sob licença MIT ([regime regular](https://github.com/ReceitaFederal/calculadora-rtc-regime-regular), [Simples Nacional](https://github.com/ReceitaFederal/calculadora-rtc-simples-nacional)). A publicação foi autorizada pela Portaria Cotec nº 342, de 12 de novembro de 2026 ([notícia da Receita Federal](https://www.gov.br/receitafederal/pt-br/assuntos/noticias/2026/novembro/receita-federal-publica-primeiro-codigo-fonte-aberto-no-github-e-amplia-transparencia-da-reforma-tributaria)). O ContaAI não altera os motores: o código é baixado das tags oficiais durante o build.

O código do ContaAI está sob a [licença MIT](LICENSE).
