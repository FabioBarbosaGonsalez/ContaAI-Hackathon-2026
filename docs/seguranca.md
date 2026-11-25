# Segurança do ContaAI

Resumo do que o projeto protege, como protege e o que continua em aberto. Os detalhes e as fontes estão nos ADRs citados. Este documento não acrescenta decisões: quando um ADR muda, ele é atualizado junto.

Para relatar uma vulnerabilidade, veja o [SECURITY.md](../SECURITY.md).

## O que existe para proteger

| Ativo | Por que importa |
|---|---|
| Motores oficiais da Receita (RR e SN) | Não têm autenticação (`anyRequest().permitAll()` no código oficial). Quem alcança o motor usa a CPU dele à vontade |
| Crédito do provedor de IA | Cada mensagem do chat custa dinheiro quando uma IA real é ligada |
| Estado da demonstração (SQLite) | Notas, custos, alertas e preços aplicados das empresas fictícias, compartilhados por quem usa a demo |
| Chave do provedor de IA e token da demo | Segredos do servidor |
| Confiança no número mostrado | O produto mostra tributo e margem: um número inventado ou adulterado é o pior defeito possível |

Todos os dados são sintéticos (P10): empresas, CNPJs e notas fictícios. Não há dado pessoal nem fiscal real no repositório nem nos testes.

## Ameaças e proteções

### Acesso aos motores ([ADR 0002](adr/0002-motores-em-containers.md))

- As portas dos motores só abrem em `127.0.0.1` no `docker-compose.yml`. As portas de gestão não são publicadas.
- As imagens rodam com usuário sem privilégios, e o banco dos motores é aberto só para leitura.
- O build baixa o código da Receita pelo commit verificado (SHA), não pela tag, que já foi republicada uma vez.
- A JVM roda com `-XX:-UseBASE64Intrinsics`, a mitigação indicada nos CHANGELOGs oficiais.
- O backend chama os motores com `trust_env=False`, sem passar por proxy configurado no ambiente.

### Abuso da API pública ([ADR 0006](adr/0006-agente.md), [ADR 0008](adr/0008-nfe-historico-e-alertas.md))

- **Limite por IP** (janela de 60 s, em memória):
  - 10 por minuto no `/chat`;
  - 120 por minuto nas rotas que chamam os motores ou mudam o estado;
  - mais 20 por minuto na busca de NCM.

  A tabela de IPs tem no máximo 10 mil entradas.
- **Token da demo** (`CONTAAI_TOKEN_DEMO`) no `/chat` e nas rotas que mudam o estado, comparado em tempo constante.
- **Teto por mensagem do agente:** 6 rodadas, 16 ferramentas, 1.024 tokens de saída por rodada e 90 s.
- **Cache das respostas dos motores:** pedidos repetidos não chegam ao motor.

### Entrada não confiável ([ADR 0008](adr/0008-nfe-historico-e-alertas.md))

- **XML da NF-e:**
  - expat ≥ 2.6.0, conferido na subida;
  - DOCTYPE, entidades e referências externas recusados antes de montar a árvore;
  - limites de profundidade, de elementos e de itens;
  - números só em notação decimal simples (NaN e infinito recusados).
- **Upload:**
  - sem `Content-Length`, 411;
  - acima do limite, 413, antes de o corpo ser lido;
  - leitura de no máximo o limite + 1 byte;
  - só tipos de XML (415).
- **Contrato:** todo modelo recusa campo desconhecido. CNPJ, id do alerta e código de erro têm padrão fixo. O texto do produto vindo da nota (`xProd`) é tratado como dado, nunca como instrução ao agente.
- **Estado:** a nota só entra se o destinatário for uma empresa cadastrada. Reimportar a mesma nota é idempotente (SHA-256). Os lançamentos de custo só aceitam acréscimo (gatilhos bloqueiam UPDATE). A restauração é atômica.

### Vazamento de informação ([ADR 0009](adr/0009-camada-http-e-erros.md))

- **Erros no formato da RFC 9457.**
  - Nenhum traz pilha, URL ou host dos motores, caminho do servidor ou corpo de terceiros.
  - O erro não tratado vai para o log e o cliente recebe só "Erro interno".
  - A validação não devolve o valor enviado.
- **Cabeçalhos em toda resposta:** `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `X-Frame-Options: DENY` e `Cross-Origin-Resource-Policy: same-site`. Fora de `/docs`, também `Content-Security-Policy: default-src 'none'` e `Cache-Control: no-store`.
- **CORS** só para as origens configuradas (`CONTAAI_CORS_ORIGENS`), sem credenciais.
- **Segredos:**
  - a chave da IA e o token são `SecretStr`, ausentes de `repr` e de `model_dump_json` (testado);
  - ficam só no `backend/.env`, fora do git.

### Número inventado ([ADR 0006](adr/0006-agente.md))

- Nenhum tributo é calculado pelo backend: todos vêm dos motores oficiais (P1).
- O verificador do agente recusa a resposta que cita um número ausente do JSON das ferramentas e troca por uma resposta segura.
- O agente só propõe ações; aplicar um preço exige o clique do usuário (P3).

## Cadeia de suprimentos e CI

| Verificação | Onde | Ferramenta (licença) |
|---|---|---|
| Dependências travadas | CI, `uv sync --locked` | uv (MIT OR Apache-2.0) |
| Vulnerabilidades conhecidas nas dependências travadas | CI, job "Dependências" | pip-audit 2.10.1 (Apache-2.0), banco do PyPI, sem conta |
| Segredos no histórico inteiro | CI, job "Segredos" | gitleaks 8.30.1 (MIT), binário conferido pelo SHA-256 da release |
| Segredos no push e no repositório | GitHub, ligado nas configurações | varredura de segredos e proteção no push (gratuitas em repositório público) |
| Análise estática | CI, CodeQL (Python e JavaScript) | CodeQL (gratuito em repositório público) |
| Tipos | CI, `mypy` com o plugin do Pydantic | mypy (MIT) |
| Cobertura mínima de 90% no `app/` | CI | coverage.py (Apache-2.0) |
| Atualizações | Dependabot semanal (Actions, uv, imagens dos motores) e alertas de segurança | GitHub |
| Relato privado de vulnerabilidades | GitHub, ligado nas configurações (ver [SECURITY.md](../SECURITY.md)) | GitHub (recurso de repositório público) |

**Relato privado (ligado em 2026-11-25).** Segundo a documentação do GitHub ("Configuring private vulnerability reporting for a repository" e "Managing privately reported security vulnerabilities"):
- o relato não fica público;
- o GitHub avisa só os **administradores e gerentes de segurança** do repositório, e só se eles acompanham o repositório (todas as atividades ou "Security alerts") com as notificações ligadas;
- quem tem só permissão de escrita **não é avisado**: para o time acompanhar, cada pessoa precisa ser administradora ou ser adicionada ao aviso de segurança;
- aceito, o relato vira um rascunho de aviso de segurança, ainda privado.

As páginas lidas não falam de custo. O recurso é oferecido aos donos de repositórios públicos, e ligá-lo não exigiu contratar nada: o repositório não tem GitHub Advanced Security.

Não usamos a `gitleaks-action`: desde a v2 ela deixou de ser MIT e exige chave de licença para organizações.

## Em aberto

- **Sem usuário nem autorização por CNPJ.** O CNPJ é filtro, não permissão. Há um token só para toda a demo. Login fica para depois do hackathon ([ADR 0008](adr/0008-nfe-historico-e-alertas.md)).
- **Estado compartilhado:** vários avaliadores ao mesmo tempo mexem nos mesmos dados. O espaço de avaliação por visitante é o próximo PR.
- **Atrás de proxy, o limite por IP vira global.** Ler `X-Forwarded-For` só de um proxy nosso fica para o deploy (E6).
- **Deploy (E6):** volume para o SQLite, container sem root e com sistema de arquivos só de leitura, limite de corpo no proxy e `/docs` desligado ou protegido.
- **Erro 500 sem os cabeçalhos de segurança e de CORS**, porque o Starlette o monta por fora dos middlewares. O corpo não traz nada interno ([ADR 0009](adr/0009-camada-http-e-erros.md)).
- **Custo da IA real** ainda não verificado. Precisa ser conferido na página oficial do provedor antes de ligar a chave ([ADR 0006](adr/0006-agente.md)).
