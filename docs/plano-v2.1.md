# Plano v2.1: as próximas etapas

- Data: 2026-11-26
- Substitui: a ordem da E5 e da E6 no plano v2.0 (`docs/plano-de-desenvolvimento.pdf`, de 2026-11-24, fora do git). As etapas E0 a E4 e os princípios P1 a P11 continuam valendo.
- Atualizar: ao fim de cada etapa, marcando o que foi feito e o que mudou.

## Por que o plano mudou

O usuário pediu que o ContaAI saia do hackathon **profissional e pronto para o mercado**: cada pessoa entra com a própria conta e cadastra a própria empresa. A demonstração continua: a banca entra **sem cadastro**, nos dados fictícios.

Por isso entram três etapas de contas (C1 a C3) entre o 3b e o 3c. O 3c depende delas, porque o contador convida empresas e o seletor troca entre elas.

## Decisões do usuário (2026-11-26)

1. **"Explorar a demonstração" sem cadastro é obrigatório.** A conta demo é o espaço de avaliação de hoje ([ADR 0010](adr/0010-espacos-de-avaliacao.md)).
2. **Sem confirmação de e-mail e sem recuperação de senha no começo.** Quem perdeu o acesso volta por convite.
3. **O contador só sugere.** Ele não aplica preço na empresa do cliente.
4. **O 3a entrou como estava** (CNPJ fixo da Serra Azul e a barra atual). Ele é refeito para o plano novo na C2 e na C3.
5. **Banco:** SQLite agora, com as tabelas novas já desenhadas para o PostgreSQL (tipos e SQL portáveis, a organização em todas as tabelas). Depois, é só trocar o banco.
6. **Prazo:** seguir o plano completo, sem corte por pressa.
7. **PR 3b:** o `GET /notas` entra num PR de backend separado e antes das telas (feito, #19); a venda do Regime é fixa (a venda de referência da demo); este plano é gravado na documentação do 3b.
8. **Chat com IA real** (decisão anterior, também de 2026-11-26): o Claude como principal (cerca de US$ 2 de crédito) e o Gemini como reserva, **se** o nível gratuito for confirmado, com troca automática quando o crédito do Claude acabar.

## Onde estamos

| Feito | Onde |
|---|---|
| E0 a E4: contrato, núcleo de cálculo, agente, regimes, NF-e, alertas e painel do contador no backend | PRs #1 a #6, ADRs 0001 a 0008 |
| Camada HTTP, qualidade do CI, espaço de avaliação, contrato da tela e mensagens em português | PRs #7 a #10 e #17, ADRs 0009 a 0011 |
| Fundação do frontend | PR #11, ADR 0012 |
| 3a: Painel, Catálogo e explicação lateral | PR #18, ADR 0013 |
| `GET /notas` (antes do 3b) | PR #19, revisão no ADR 0008 |
| 3b: Notas e Regime (e o Painel sem alerta) | este PR, ADR 0014 |

## A ordem

| # | Etapa | Entrega | Depende de |
|---|---|---|---|
| 1 | **3b** (feito) | Telas de Notas e de Regime | `GET /notas` (feito) |
| 2 | **C1** | Contas no backend | 3b |
| 3 | **C2** | Telas de entrada | C1 |
| 4 | **C3** | Dados da própria empresa | C1 e C2 |
| 5 | **3c** | Contador, seletor de empresa e chat | C1 a C3 |
| 6 | **E6** | Hospedagem, HTTPS, testes de ponta a ponta, vídeo e pitch | todas |

Cada etapa sai em um PR, ou em mais de um quando o backend vem antes da tela.

## 3b: Notas e Regime

**Pergunta das telas** ([inventário](../.taste-skill/app/inventario.md)): "o que mudou no custo com esta nota?" e "vale a pena o Simples híbrido para vender a este cliente?".

1. **Notas**
   - Envio do XML com o `upload.ts` que já existe (só XML, até 1 MB).
   - O recibo: itens casados (custo antigo, novo e variação; "entrou no histórico, custo mantido" quando a nota é antiga), crédito lido da nota ou calculado pelo motor, itens sem par como pergunta, nota repetida ("já importada") e alertas gerados, com caminho para aplicar o preço.
   - A lista das notas já importadas (`GET /notas`).
   - Erros com frase clara: nota repetida com outro conteúdo, destinatário fora das empresas cadastradas, 413 e 415.
   - Importar fica desligado sem espaço ou token, como o "Aplicar" do 3a.
2. **Regime**
   - O cliente B2B e a venda de referência vêm do `GET /catalogo` (`clientesB2B`); a tela não guarda cópia de preço nem de quantidade.
   - Tradicional × híbrido lado a lado: diferença de caixa, crédito do cliente (a **régua do crédito**, elemento-assinatura do estilo), preço de empate e premissas rotuladas.
   - Antes de 2027 a comparação não existe, e a tela diz por quê (VSN-015).
   - Números esperados na demo, já verificados nos motores: venda R$ 19.898,65, diferença de caixa −R$ 125,79 e empate R$ 18.489,49.
   - **Corrigido no 3b:** esses números pedem a nota 2 importada. Na demonstração recém-aberta (só a nota 1), a diferença de caixa é −R$ 173,90, com o crédito das compras calculado pelo motor ([ADR 0014](adr/0014-telas-notas-e-regime.md)).
3. **Portão:** `inspect.mjs --app` com 0 FAIL em 1440, 768 e 390 px; crítica em `.taste-skill/app/critica-3b.md`; Chrome com o build (CSP e Trusted Types); teclado e leitor de tela.
4. **Documentação:** ADR 0014, README e a varredura de inconsistências no projeto inteiro.

**Saída:** as cinco páginas da barra funcionam, exceto Contador; tela e API ficam abertas em localhost para o usuário conferir.

**Feito (2026-11-26, [ADR 0014](adr/0014-telas-notas-e-regime.md)):**
- portão da skill com 0 FAIL e 0 WARN nas quatro telas da barra; crítica em `.taste-skill/app/critica-3b.md`;
- Chrome com o build: 0 violações de CSP e 0 erros de JS no fluxo de importar e aplicar;
- o que mudou: o Painel sem alerta (achado da medição na demonstração compartilhada) e o crédito por unidade na comparação, que só vai quando veio da nota;
- ficou para depois: cadastrar o par de um item sem par (C3), oferecer as notas de exemplo na tela (C2) e rever o recibo de uma nota antiga (rota nova, sem etapa).

## C1: contas no backend

**Escopo:**
- usuários, sessões em cookie `HttpOnly`, organizações e membros com papéis;
- autorização por CNPJ: o CNPJ deixa de ser só filtro e passa a ser permissão (pendência do ADR 0008);
- a conta demo é o espaço de avaliação;
- proxy `/api` no Vite. A tela e a API ficam na mesma origem, o que o cookie precisa (hoje o cliente manda `credentials: 'omit'`, ADR 0012).

**A decidir e verificar antes do código:**
- como guardar a senha. A biblioteca ou a função da stdlib precisa ter licença e gratuidade conferidas;
- o limite de tentativas de entrada;
- a validade da sessão e a saída em todos os aparelhos;
- o CSRF com cookie: hoje há a conferência de `Origin` nos POST (ADR 0011). Falta decidir se basta junto com `SameSite`.

**Saída:** ADR novo; as rotas de estado respondem só a quem tem acesso à empresa; a demonstração sem cadastro segue igual.

## C2: telas de entrada

**Escopo:**
- página inicial, com "Explorar a demonstração" sem cadastro;
- entrar, criar conta e o menu da conta;
- a faixa que avisa que a pessoa está na demonstração;
- termos de uso e privacidade;
- a barra do 3a refeita para ter conta e demonstração.

**Cuidado:** o texto dos termos e da privacidade não é parecer jurídico. Ele precisa de revisão humana antes da publicação.

**Saída:** portão da skill nas telas novas; dá para entrar, sair e voltar à demonstração.

## C3: dados da própria empresa

**Escopo:**
- a primeira vez (estado vazio) e o cadastro da empresa (CNPJ, regime, UF e município);
- configurações;
- catálogo e clientes B2B editáveis;
- o CNPJ fixo do 3a passa a ser o da empresa da conta.

**Inconsistência registrada:** o P10 diz "só dados fictícios". Com a empresa própria, entram dados reais. Antes do código é preciso decidir:
- se o P10 passa a valer só para a demonstração;
- como guardar e apagar os dados de cada empresa;
- a validação do dígito verificador do CNPJ. Os CNPJs da demo têm dígito inválido de propósito ([ADR 0008](adr/0008-nfe-historico-e-alertas.md)) e continuam aceitos só nela.

**Saída:** uma conta nova cadastra a empresa, importa uma nota e vê o alerta, sem tocar nos dados da demo.

## 3c: contador, seletor de empresa e chat

**Escopo:**
- painel do contador (D1) com convites;
- seletor de empresa;
- chat lateral com a IA real e cota por usuário;
- crítica final das telas.

**Regras:**
- o contador só sugere (decisão 3);
- a IA não faz conta nem decide a classificação sozinha (P2 e P3).

**A verificar antes de ligar a IA:**
- o nível gratuito do Gemini: termos e uso dos dados;
- o erro da Anthropic quando o crédito acaba (é o sinal para a troca);
- o custo por pergunta, com as 20 perguntas do `pytest -m llm`.

**Saída:** um contador convida uma empresa, troca entre empresas e sugere um preço; o chat responde dentro da cota.

## E6: entrega

**Escopo:**
- hospedagem e HTTPS;
- backups e logs;
- testes de ponta a ponta com Playwright;
- vídeo de 3 minutos, com o aviso de simulação dito em voz, e pitch;
- o checklist de entrega do plano v2.0 (seção 21).

**Do deploy, já registrado em [segurança](seguranca.md):**
- volume para o banco;
- container sem root, com sistema de arquivos só de leitura;
- limite de corpo no proxy;
- `CONTAAI_DOCS_PUBLICA=false`;
- domínio em `CONTAAI_HOSTS_PERMITIDOS` e `CONTAAI_CORS_ORIGENS`;
- HSTS, a API em `/api` e o `index.html` para as rotas da tela;
- os cabeçalhos de `cabecalhosDeSeguranca`;
- `X-Forwarded-For` só do nosso proxy.

**Não verificado:** a hospedagem gratuita que aguenta os dois motores, a API e o banco. A VM do plano v2.0 é paga. A troca para o PostgreSQL também não tem custo verificado (RAM e operação no host, ou os limites de um provedor gerenciado).

**Saída:** URL pública estável; os testes de ponta a ponta passam nela; o checklist da seção 21 está completo.

## O que segue aberto fora da ordem

- **ESLint 10:** quando o `eslint-plugin-jsx-a11y` aceitar a versão ([ADR 0012](adr/0012-fundacao-do-frontend.md)).
- **Erro 500 sem os cabeçalhos de segurança** ([ADR 0009](adr/0009-camada-http-e-erros.md)).
- **Esgotar os espaços de avaliação** na demo pública ([ADR 0010](adr/0010-espacos-de-avaliacao.md)).
- **Respostas dos contadores** (E0-08): dependem do time.
- **Fora do escopo:** a linha do tempo 2026 × 2027 e a exportação (decisão D3 da E5).

## Como cada etapa é feita

1. **Antes do código:** verificar se cada ferramenta ou serviço é gratuito e sinalizar qualquer custo.
2. **Fontes:** nunca inventar informação; o que não foi verificado fica marcado assim.
3. **Ao fim:**
   - checar segurança e vazamento de dados;
   - varrer o projeto atrás de inconsistências entre o plano, o código e a documentação.
4. **Publicação:** commit sem coautoria, push e PR. A `main` exige o CI verde e a aprovação de outra pessoa do time.
5. **Etapas de tela:** a tela e a API ficam abertas em localhost para conferência.
