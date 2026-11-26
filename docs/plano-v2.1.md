# Plano v2.1: as próximas etapas

- Data: 2026-11-26
- Substitui: a ordem da E5 e da E6 no plano v2.0 (`docs/plano-de-desenvolvimento.pdf`, de 2026-11-24, fora do git). As etapas E0 a E4 e os princípios P1 a P11 continuam valendo.
- Atualizar: ao fim de cada etapa, marcando o que foi feito e o que mudou.

## Por que o plano mudou

O usuário pediu que o ContaAI saia do hackathon **profissional e pronto para o mercado**: cada pessoa entra com a própria conta e cadastra a própria empresa. A demonstração continua: a banca entra **sem cadastro**, nos dados fictícios.

Por isso entram três etapas de contas (C1 a C3) entre o 3b e o 3c. O 3c depende delas, porque o contador convida empresas e o seletor troca entre elas.

## Decisões do usuário (2026-11-26)

1. **"Explorar a demonstração" sem cadastro é obrigatório.** A conta demo é o espaço de avaliação de hoje ([ADR 0010](adr/0010-espacos-de-avaliacao.md)).
2. **Sem confirmação de e-mail e sem recuperação de senha no começo.** Quem perdeu o aplicativo do segundo fator entra com um código de recuperação (C1); quem perdeu a senha volta por convite.
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
| 3b: Notas e Regime (e o Painel sem alerta) | PR #20, ADR 0014 |

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
- proxy `/api` no Vite. A tela e a API ficam na mesma origem, o que o cookie precisa (antes da C1, o cliente mandava `credentials: 'omit'`, ADR 0012).

**Decisões do usuário (2026-11-26):**
- **Senha:** Argon2id, com o argon2-cffi (25.1.0, licença MIT, gratuito). É a primeira escolha do OWASP (Password Storage Cheat Sheet): 19 MiB de memória, 2 passes, paralelismo 1.
- **Segundo fator obrigatório na conta real:** TOTP (RFC 6238), escrito com a biblioteca padrão do Python (`hmac`, `hashlib`, `secrets`), sem dependência nova e sem SMS. O código sai de qualquer aplicativo autenticador gratuito. A demonstração segue sem cadastro e sem segundo fator.
- **Tamanho da senha:** no mínimo 8 caracteres, sem regra de composição, e pelo menos 64 aceitos. O NIST SP 800-63B-4 (§3.1.1.2) exige 15 para a senha usada sozinha e permite 8 só quando ela faz parte de uma autenticação de múltiplos fatores. Por isso o mínimo de 8 depende do TOTP.
- **Senhas comuns:** a lista `100k-most-used-passwords-NCSC.txt` do SecLists (licença MIT, lida em 2026-11-26), guardada no repositório só com as senhas de 8 caracteres ou mais, mais as palavras do produto e o e-mail de quem se cadastra. A senha inteira é comparada, não pedaços (§3.1.1.2). Nenhum dado sai do servidor. **Não verificado:** os termos do próprio NCSC sobre a lista (o endereço do NCSC respondeu 404).
- **Tentativas de entrada:** espera crescente a partir da 5ª falha seguida e bloqueio da conta em 100 falhas, o teto do NIST (§3.2.2: "no more than 100"; a espera de "30 seconds up to an hour" é técnica complementar). A conta bloqueada só volta por um comando de administrador no servidor. Entrar com sucesso zera as falhas.
- **Excluir a conta:** se a pessoa é a única dona, a organização e os dados dela são apagados junto. Se há outros membros, ela passa a posse antes. A C1 não tem obrigação legal de guardar esses dados (LGPD, art. 16 I; o art. 18 VI garante a eliminação "exceto nas hipóteses previstas no art. 16").
- **Papéis:** dono (gerencia membros e apaga a organização) e membro (importa notas e grava preços). O contador entra no 3c.

**Achados do mapeamento:**
1. **As contas reais não podem morar no banco da demonstração.** O `POST /demo/restaurar` substitui o banco principal inteiro pela cópia das sementes (`Banco.copiar_para`). Contas e empresas reais ficam num banco próprio, `contas.db`, com migrações próprias. O banco da demo e os espaços continuam como estão.
2. **Rotas que atravessam empresas.** Com dados reais, elas vazariam dados de um cliente para outro:
   - o `GET /alertas` sem `cnpj` devolve os alertas de todas as empresas;
   - o `GET /contador/painel` lista todas as empresas do banco;
   - o `POST /alertas/{id}/aplicar` age pelo id do alerta, sem conferir a empresa.

   O `POST /nfe/importar` escolhe a empresa pelo destinatário da nota, e o chat lê o estado: os dois também passam pela conferência.
3. **CNPJ sem acesso responde 404, e não 403,** para não revelar quais CNPJs existem.
4. **Sem recuperação de senha, o bloqueio em 100 falhas trancaria a conta para sempre.** Daí o desbloqueio pelo administrador e os códigos de recuperação do segundo fator.

**Segmentos (um PR de backend):**

| # | Segmento | O que entra |
|---|---|---|
| S1 | Banco de contas | `contas.db` com usuários, sessões, organizações, membros, acesso a empresas, segundo fator e tentativas de entrada. SQL portável para o PostgreSQL (decisão 5): ids em texto, datas ISO em UTC, sem `STRICT`, `GLOB` nem `julianday`, e a organização em toda tabela |
| S2 | Cadastro e senha | `POST /contas` cria o usuário e a organização dele. Hash Argon2id, lista de senhas comuns e mensagem genérica, que não revela se o e-mail já tem conta (OWASP, Authentication Cheat Sheet) |
| S3 | Sessão | `POST /sessoes` (entrar), `DELETE /sessoes/atual` (sair), `DELETE /sessoes` (sair de todos os aparelhos) e `GET /conta`. Detalhes abaixo |
| S3b | Segundo fator | Ativação no cadastro, entrada em duas etapas e códigos de recuperação. Detalhes abaixo |
| S4 | Limite de tentativas | Contador de falhas por conta, no banco (o OWASP associa o contador à conta, e não ao IP), mais o limite por IP que já existe. Vale para a senha, o código e o código de recuperação. E-mail inexistente passa pelo mesmo caminho e pelo mesmo tempo (hash de mentira) |
| S5 | CSRF | A conferência de `Origin` que já existe (ADR 0011), mais: recusar POST com `Sec-Fetch-Site: cross-site` e exigir `Origin` em POST que traz o cookie. O OWASP diz que `SameSite` sozinho é defesa em profundidade, não a defesa |
| S6 | Autorização por empresa | Uma dependência resolve quem chama (sessão, espaço ou anônimo) e o conjunto de CNPJs permitido, em todas as rotas de estado, fechando os vazamentos acima. Anônimo e espaço veem só os CNPJs fictícios da demo (P10) |
| S7 | Excluir a conta | `DELETE /conta` apaga o usuário, as sessões, o segundo fator e o vínculo com a organização, e a organização quando a pessoa é a única dona (LGPD, art. 18 VI) |
| S8 | Mesma origem | Proxy `/api` no `dev` e no `preview` do Vite (a documentação confirma o `rewrite` e que o `preview.proxy` herda do `server.proxy`). O cliente troca `credentials: 'omit'` por `'same-origin'`. A CSP fica só com `connect-src 'self'` |
| S9 | Verificação e documentação | Contrato e OpenAPI regerados; testes de cada rota com cada tipo de quem chama; ataques (enumeração, sessão fixada, CSRF, força bruta, código repetido); cookie conferido no Chrome; ZAP (gratuito, já usado no ADR 0011); ADR 0015, `seguranca.md` e README |

**A sessão (S3), pelo OWASP (Session Management Cheat Sheet):**
- token aleatório de 256 bits (o OWASP pede ao menos 128 bits, de preferência 160 ou mais), com só o hash guardado no banco;
- token novo a cada login, contra sessão fixada;
- cookie `HttpOnly`, `Secure`, `SameSite=Strict` (o preferido pelo OWASP), `Path=/` e sem `Domain`;
- 30 min sem uso e 8 h no total. O OWASP dá de 15 a 30 min sem uso para aplicação de baixo risco e 4 a 8 h como exemplo de limite total;
- sair invalida a sessão no servidor, e não só o cookie.

**O segundo fator (S3b), pelo NIST SP 800-63B-4:**
- a conta só vale depois de confirmar o primeiro código. A API devolve o endereço `otpauth://`, e o QR code é desenhado na C2;
- entrar tem duas etapas: a senha dá um passe curto (5 min, só para a segunda etapa), e a sessão só nasce depois do código;
- segredo de 160 bits (o mínimo é 112, §3.1.4.1), guardado no `contas.db` com acesso restrito (§3.1.4.2);
- código de 6 dígitos (o mínimo do §3.1.4.1), passo de 30 s e tolerância de um passo para cada lado, pelo desvio do relógio (§3.1.4.2);
- cada código é aceito uma vez só (§3.1.4.2: "accept a given OTP only once while it is valid");
- 10 códigos de recuperação, cada um com 64 bits ou mais, guardados só como hash e de uso único. Usar um invalida o código, gera outro e avisa a pessoa (§4.2). Eles substituem a recuperação de senha que a C1 não tem.

**Conferido nas fontes (2026-11-26):** NIST SP 800-63B-4, §2.2, §3.1.1.2, §3.1.4, §3.2.2 e §4.2 (pages.nist.gov); LGPD, art. 16, 18 e 46 (planalto.gov.br, texto original com as notas de alteração); licença MIT do SecLists.

**A conferir durante o código:**
- **O prefixo `__Host-` no `http://localhost`:** a MDN diz que esse cookie precisa ser criado "por uma página segura (HTTPS)". A exceção do localhost está escrita só para o `Secure`. Conferir no Chrome no S3, antes de fixar o nome do cookie.
- **O e-mail sem confirmação** (decisão 2): qualquer pessoa pode criar uma conta com o e-mail de outra. Registrar o risco no ADR e nos termos (C2).

**Implementação futura (fora da C1):**
- **Passkey (WebAuthn), a opção resistente a phishing.** Para o nível AAL2 completo, o NIST pede oferecer "at least one phishing-resistant authentication option" (§2.2), e o TOTP não é resistente a phishing (§3.1.4). É gratuita, mas pede bastante trabalho no backend e na tela. Até lá, a C1 fica com senha e TOTP, e a lacuna é registrada no ADR 0015.

**Custo:** nenhum serviço pago e nenhuma chamada externa. A única dependência nova é o argon2-cffi (MIT). O TOTP usa só a biblioteca padrão.

**Saída:** ADR novo; as rotas de estado respondem só a quem tem acesso à empresa; a demonstração sem cadastro segue igual.

**Feito (2026-11-26, [ADR 0015](adr/0015-contas.md)):**
- S1 a S9 entregues;
- o `__Host-` foi conferido no Chrome 158, em `http://127.0.0.1` e em `http://localhost`: o navegador aceita e devolve o cookie;
- o estado de cada organização fica num SQLite próprio, como os espaços: a fronteira entre clientes é o arquivo, e o conjunto de CNPJs é a segunda camada.

O que mudou em relação a este mapa:
- **O cadastro não esconde que o e-mail já tem conta:** sem confirmação de e-mail, uma resposta falsa se denunciaria na ativação. A entrada esconde.
- **Excluir a conta virou `POST /conta/excluir` com a senha,** no lugar do `DELETE /conta`.
- **Ficou para depois:**
  - convites de membros e transferência de posse (3c);
  - empresas da organização (C3);
  - cifrar o segredo do TOTP (E6).

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
