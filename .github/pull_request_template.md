## O que muda

<!-- Uma ou duas frases. Ligue a issue: "Fecha #123". -->

## Etapa e frente

- Etapa: <!-- E0 a E6 -->
- Frente: <!-- F1 motores · F2 backend · F3 agente · F4 interface · F5 pitch -->

## Como testar

<!-- Passos para quem revisa reproduzir. -->

## Checklist

- [ ] O CI passou (lint, tipos, testes com cobertura, dependências e segredos)
- [ ] Nenhum código nosso calcula alíquota, base ou tributo; os valores vêm dos motores oficiais (P1)
- [ ] A IA não faz aritmética nem decide a classificação fiscal sozinha (P2, P3)
- [ ] Premissas e aviso de simulação aparecem quando o resultado é de 2027 em diante (P6)
- [ ] Sem segredos no código (`.env` fora do git) e só dados fictícios (P10)
- [ ] Telas: passou no `inspect.mjs --app` sem FAIL (P11), se mexeu na interface
- [ ] `make golden` verde, se mexeu na integração com os motores
