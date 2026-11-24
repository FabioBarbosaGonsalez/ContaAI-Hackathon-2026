# ContaAI

Copiloto de preço e margem para a pequena empresa na reforma tributária (Hackathon 2026, Trilha 05: Pagamentos e finanças).

O dono de uma ME do Simples conversa com o copiloto sobre o que vende. O ContaAI mostra quanto de CBS, IBS e IS incide em cada item, que preço mantém a margem, se vale ir para o Simples híbrido para vender a empresas e o que mudou quando chega uma nota de compra. **Toda conta vem das calculadoras oficiais da Receita Federal; a IA só interpreta e explica.**

> Estimativa baseada nas calculadoras oficiais. Não é parecer fiscal e não substitui o contador.

## Documentos

- [Plano de desenvolvimento (PDF)](docs/plano-de-desenvolvimento.pdf): escopo, arquitetura, etapas E0 a E6, backlog e roteiro da demo
- [Pesquisa de base](wiki/research/2026-11-24-copiloto-tributario-pequenos-negocios.md): o que as APIs oficiais impõem e as fontes
- [Como contribuir](CONTRIBUTING.md): fluxo de branches, PRs e revisão

## Arquitetura (resumo)

| Peça | Papel |
|---|---|
| Motor Regime Regular 1.7.2 (Receita, Java 25) | CBS, IBS e IS por item, dados abertos e memória de cálculo |
| Motor Simples Nacional 1.0.2 (Receita, Java 25) | Lado "Simples tradicional" da decisão de regime |
| Backend (FastAPI) | Orquestra, preço-alvo, comparação de regimes, leitura de NF-e e alertas |
| Agente (LLM com ferramentas) | Só chama as ferramentas do backend; não faz conta |
| Frontend (Next.js) | Telas construídas com a skill design-taste-frontend |

## Status

Etapa 0 (fundação) em andamento. Os motores, o backend e o frontend entram nos próximos PRs.

## Créditos

As calculadoras da Reforma Tributária do Consumo são da Receita Federal do Brasil, publicadas sob licença MIT (Portaria Cotec nº 342/2026).
