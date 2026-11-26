# ADR 0015: contas, segundo fator, sessão e autorização por empresa (C1)

- Status: aceito
- Data: 2026-11-26
- Etapa: C1 do [plano v2.1](../plano-v2.1.md) (as telas de entrada vêm na C2)
- Código: `backend/app/contas/` (`servico.py`, `senha.py`, `totp.py`, `migracoes/0001_contas.sql`, `__main__.py`), `backend/app/api/rotas/contas.py`, `backend/app/api/dependencias.py` (`abrir_estado`, `Estado`), `backend/app/api/middlewares.py` (`verificar_origem`), `frontend/vite.config.ts` (proxy `/api`), `frontend/src/api/` (`config.ts`, `cliente.ts`), `backend/tests/test_contas.py`

## Contexto

O usuário pediu um ContaAI pronto para o mercado: cada pessoa entra com a própria conta e cadastra a própria empresa, e a banca continua entrando sem cadastro nos dados fictícios (plano v2.1, decisões 1 e 2). Até aqui:
- não havia usuário: só um token para toda a demonstração;
- o CNPJ era filtro, e não permissão (ADR 0008);
- o cliente da tela mandava `credentials: 'omit'` e chamava a API em outra origem (ADR 0012).

O mapeamento achou três pontos que mudam o desenho:
1. **O `POST /demo/restaurar` substitui o banco principal inteiro** pela cópia das sementes (`Banco.copiar_para`). Dados reais não podem morar nele.
2. **Três rotas atravessavam empresas:** o `GET /alertas` sem `cnpj`, o `GET /contador/painel` e o `POST /alertas/{id}/aplicar`, que não conferia a empresa do alerta.
3. **Sem recuperação de senha** (decisão 2 do plano), o bloqueio em 100 falhas que o NIST exige trancaria a conta para sempre.

## Fontes lidas (2026-11-26)

| Fonte | O que foi usado |
|---|---|
| NIST SP 800-63B-4, §3.1.1.2 (pages.nist.gov) | Senha de no mínimo 15 caracteres quando usada sozinha; "MAY allow passwords that are only used as part of multi-factor authentication processes to be shorter but SHALL require them to be a minimum of eight characters"; pelo menos 64 aceitos (SHOULD); sem regra de composição (SHALL NOT); a senha inteira comparada com uma lista de senhas comuns (SHALL) |
| NIST SP 800-63B-4, §3.1.4 | Segredo de pelo menos 112 bits; saída de pelo menos 6 dígitos; passo de no máximo 2 minutos; validade pelo desvio do relógio; "accept a given OTP only once while it is valid"; o OTP não é resistente a phishing |
| NIST SP 800-63B-4, §3.2.2 | Até 100 falhas seguidas por conta, desabilitando o autenticador (SHALL); espera crescente, "30 seconds up to an hour", como técnica complementar (MAY); zerar as falhas depois de entrar (SHOULD) |
| NIST SP 800-63B-4, §2.2 e §4.2 | AAL2: senha mais um autenticador físico (o OTP de software no celular é um deles); oferecer ao menos uma opção resistente a phishing. Código de recuperação: pelo menos 64 bits, guardado como hash, uso único, trocado por outro e com aviso à pessoa |
| RFC 6238 (TOTP) e RFC 4226 (HOTP), rfc-editor.org | O algoritmo; os vetores do Apêndice B (SHA-1) e do Apêndice D; "We RECOMMEND a default time-step size of 30 seconds"; "at most one time step is allowed as the network delay" |
| OWASP Password Storage, Authentication, Session Management e CSRF Prevention Cheat Sheets | Argon2id com 19 MiB, 2 passes e paralelismo 1; mensagem que não revela se a conta existe; token de pelo menos 128 bits, trocado a cada entrada; `HttpOnly`, `Secure`, `SameSite=Strict`; 15 a 30 min sem uso e 4 a 8 h no total; Fetch Metadata além do SameSite |
| LGPD (Lei 13.709/2018), planalto.gov.br, texto original com as notas de alteração | Art. 18 VI: eliminação dos dados "exceto nas hipóteses previstas no art. 16"; art. 16 I: conservação para obrigação legal; art. 46: medidas de segurança |
| SecLists, LICENSE (MIT) | A lista `Passwords/Common-Credentials/100k-most-used-passwords-NCSC.txt` |

## Decisão

### 1. Um banco de contas próprio, e um banco de estado por organização

- **`contas.db`**, ao lado do banco da demo e fora dele, com migrações próprias (`app/contas/migracoes/`). Restaurar a demo não toca nas contas.
- **SQL portável para o PostgreSQL** (decisão 5 do plano):
  - ids em texto (128 bits de `secrets.token_hex`);
  - datas ISO 8601 em UTC, sempre no mesmo formato, comparadas como texto;
  - sem `STRICT`, `GLOB` nem `julianday`;
  - a organização em toda tabela que guarda dado de uma organização;
  - `ON DELETE CASCADE` para apagar junto.
- **O estado de cada organização** (notas, catálogo, alertas e preços) fica num SQLite próprio, em `organizacoes/<id>.db`, com as mesmas migrações do banco da demo, como os espaços de avaliação (ADR 0010). A fronteira entre clientes é o arquivo. O conjunto de CNPJs (abaixo) fica como segunda camada.
- **Revisar depois:**
  - na troca para o PostgreSQL, o estado vira uma coluna `organizacao_id` ou um schema por organização;
  - o 3c (o contador que vê empresas de várias organizações) lê mais de um banco.

### 2. Senha (S2)

- **De 8 a 128 caracteres, sem regra de composição.** O mínimo de 8 vale porque toda conta real tem segundo fator (§3.1.1.2). Sem ele, o mínimo seria 15.
- **Normalização NFKC antes do hash**, para que o mesmo texto digitado em teclados diferentes dê o mesmo hash.
- **Lista de senhas comuns:** a do NCSC que está no SecLists (MIT). Ela guarda as 46.483 senhas de 8 caracteres ou mais, em NFKC e minúsculas, em `app/contas/senhas_comuns.txt.gz` (origem e SHA-256 em `app/contas/LEIA-ME.md`).
  - A comparação é com a senha inteira, sem diferenciar maiúsculas.
  - Também são recusados o e-mail, a parte antes do @, o nome do produto e um caractere repetido.
  - Nenhum dado sai do servidor.
- **Hash Argon2id** pelo argon2-cffi 25.1.0 (MIT; dependências argon2-cffi-bindings MIT, cffi MIT-0, pycparser BSD-3-Clause), com os parâmetros mínimos do OWASP. O hash é refeito numa entrada certa se os parâmetros mudarem.

### 3. Segundo fator obrigatório: TOTP (S3b)

- **RFC 6238 escrita com a biblioteca padrão** (`hmac`, `hashlib`, `struct`, `secrets`), sem dependência nova e sem SMS. O teste confere os 6 vetores SHA-1 do Apêndice B.
- **Parâmetros:** HMAC-SHA1, 6 dígitos e passo de 30 s, o padrão dos aplicativos autenticadores. O segredo tem 160 bits e é guardado no `contas.db`, que só o backend lê.
- **Tolerância de um passo para cada lado**, a recomendação da RFC 6238 (§5.2).
- **Uso único:** o passo do último código aceito fica gravado, e só vale um passo maior. Conferir e gravar acontecem na mesma transação de escrita, para que duas requisições com o mesmo código não passem as duas.
- **Ativação:** o `POST /contas` cria a conta pendente e devolve o endereço `otpauth://` (o QR code é desenhado na C2) e o segredo em texto. A conta só vale depois do `POST /contas/ativar` com o primeiro código, até 5 minutos depois do cadastro. Um cadastro pendente vence em 30 minutos, e o e-mail fica livre de novo.
- **Códigos de recuperação:** 10, cada um com 65 bits sorteados (13 caracteres de base32 em 3 grupos), guardados só como SHA-256. Usar um apaga o código, cria outro no lugar (devolvido uma vez só, na resposta) e grava um evento que o `GET /conta` mostra. Eles substituem a recuperação de senha que a C1 não tem.

### 4. Entrada e sessão (S3)

- **Duas etapas:** o `POST /sessoes` confere e-mail e senha e grava um passe de 5 minutos. O `POST /sessoes/codigo` confere o código (ou um código de recuperação) e abre a sessão.
- **Tokens:** a sessão e o passe têm 256 bits (`secrets.token_urlsafe(32)`), e só o SHA-256 vai ao banco. Nenhum token aparece no corpo de uma resposta.
- **Cookies:** `__Host-contaai_sessao` e `__Host-contaai_passe`, com `HttpOnly`, `Secure`, `SameSite=Strict`, `Path=/` e sem `Domain`.
  - **Conferido no Chrome 158** (headless, pelo DevTools Protocol, roteiro no scratchpad da sessão) em `http://127.0.0.1:3002` e em `http://localhost:3002`:
    - o navegador guardou os dois cookies com o prefixo `__Host-`;
    - mandou a sessão de volta pelo proxy `/api`;
    - o `document.cookie` ficou vazio;
    - sair apagou o cookie.

    Isso resolve o ponto que o plano deixou "a conferir": a MDN fala em "página segura", e o Chrome trata o endereço local como seguro também para o prefixo.
- **Validade:** 30 minutos sem uso e 8 horas no total. O último uso é gravado no máximo uma vez por minuto. Um token novo nasce a cada entrada, contra sessão fixada.
- **Sair:** o `DELETE /sessoes/atual` apaga a sessão no servidor, e não só o cookie. O `DELETE /sessoes` apaga as sessões de todos os aparelhos.
- **Cookie vencido ou desconhecido** em qualquer rota: 401, e a resposta apaga o cookie.

### 5. Tentativas (S4)

- **Um contador de falhas seguidas por conta**, no banco (o OWASP liga o contador à conta, e não ao IP). Ele soma a senha, o código e o código de recuperação.
- **Espera crescente da 5ª falha em diante:** 30 s, dobrando, até 1 h. Durante a espera, nem a senha certa é conferida, e a resposta é 429 com `Retry-After`.
- **Na 100ª falha, a conta é bloqueada** (§3.2.2), e só o administrador desbloqueia, no servidor: `uv run python -m app.contas desbloquear <e-mail>`. Não há rota HTTP para isso. Com a espera, chegar a 100 falhas leva dezenas de horas.
- **Entrar com sucesso zera as falhas.**
- **Um e-mail sem conta tem o mesmo contador**, em memória e com teto de 10.000 e-mails, e passa por um Argon2id de mentira. A resposta e o tempo não dizem se a conta existe.
- **Limite por IP próprio** nas rotas de entrada (`CONTAAI_LIMITE_ENTRADA_POR_MINUTO`, padrão 10), além do contador da conta.

### 6. CSRF (S5)

Nos métodos que mudam o estado (POST, PUT, PATCH e DELETE):
- `Sec-Fetch-Site: cross-site` recebe 403 (Fetch Metadata, recomendado pelo OWASP além do SameSite);
- um `Origin` fora da lista recebe 403, como antes, agora também no DELETE;
- **com o cookie da sessão e sem `Origin`, 403.** Um navegador manda `Origin` nesses métodos. Sem cookie e sem `Origin` (curl, scripts), segue valendo como antes.

O CORS continua sem credenciais (`allow_credentials=False`): o cookie só anda na mesma origem.

### 7. Autorização por empresa (S6)

- **Quem chama é resolvido em `abrir_estado`, nesta ordem:**
  1. o espaço do header `X-ContaAI-Espaco` (escolha explícita, também para quem tem conta: assim a pessoa que entrou ainda pode avaliar a demonstração);
  2. a sessão do cookie, que leva ao banco da organização;
  3. sem os dois, a demonstração compartilhada.
- **`Estado.cnpjs`** é o conjunto de empresas que quem chama alcança:
  - na demonstração e no espaço, as empresas do banco, todas fictícias (P10);
  - na conta, as da tabela `acessos_empresa`, que a C3 preenche.
- **Toda rota com `cnpj`** confere o conjunto. Um CNPJ fora dele responde o mesmo 404 de um CNPJ que não existe ("Empresa não cadastrada."), para não revelar quais existem.
- **Os três vazamentos foram fechados:**
  - o `GET /alertas` sem `cnpj` filtra pelo conjunto;
  - o `GET /contador/painel` mostra só as empresas do conjunto;
  - o `POST /alertas/{id}/aplicar` responde "Alerta não encontrado." para alerta de outra empresa.
- **O `POST /nfe/importar`** recusa, com a mesma frase de destinatário desconhecido, a nota de uma empresa fora do conjunto. O chat lê o banco de quem chama.
- **O token da demo** vale só para a demonstração compartilhada. No espaço e na conta, a mudança de estado não o exige (o chat continua exigindo, porque protege o crédito da IA).
- **O `POST /demo/restaurar` com sessão e sem espaço:** 403. Os dados de uma organização nunca são trocados pelas sementes.

### 8. Excluir a conta (S7)

- **`POST /conta/excluir` com a senha de novo** (em vez do `DELETE /conta` do plano): pedir a senha protege contra uma sessão roubada, e o corpo de um DELETE é mal suportado.
- **Apaga a pessoa, as sessões, os passes, o segundo fator, os códigos e as tentativas.** Se ela era a única integrante, apaga também a organização e o arquivo de estado dela.
- **A única dona de uma organização com outros membros** recebe 409 e precisa passar a posse antes. Não há obrigação legal de guardar esses dados na C1 (LGPD, art. 16 I). Os convites de membros vêm no 3c.

### 9. Mesma origem (S8)

- **A tela chama a API em `/api`** também no desenvolvimento. O Vite faz o proxy no `dev` e no `preview` (`server.proxy` e `preview.proxy`, com `rewrite` que tira o `/api`). O alvo é `CONTAAI_API_ALVO` (padrão `http://127.0.0.1:8000`), uma variável que não é `VITE_*` e fica fora do navegador.
- **O cliente troca `credentials: 'omit'` por `'same-origin'`.** A CSP segue com `connect-src 'self'`. Com `VITE_CONTAAI_API` em outra origem, a demonstração funciona, e a conta não.

### 10. Só no modo real

As rotas de conta respondem 501 no modo mock, como as outras que mudam o estado. Elas não chamam os motores.

## Rotas novas

| Rota | O que faz |
|---|---|
| `POST /contas` | Cadastro (201): `otpauth`, `segredo` e `expiraEm`; o passe vai no cookie |
| `POST /contas/ativar` | Primeiro código: a conta vale, a sessão começa e saem os 10 códigos de recuperação |
| `POST /sessoes` | E-mail e senha: o passe vai no cookie |
| `POST /sessoes/codigo` | Código do aplicativo ou de recuperação: a sessão começa |
| `GET /conta` | E-mail, organização e papel, empresas, códigos restantes, eventos e fim da sessão |
| `DELETE /sessoes/atual` e `DELETE /sessoes` | Sair neste aparelho e em todos |
| `POST /conta/excluir` | Apaga a conta, com a senha |

## Consequências

- **Achado: o cadastro não consegue esconder que o e-mail já tem conta.** O plano pedia uma mensagem genérica, mas sem confirmação de e-mail (decisão 2) qualquer resposta falsa se denuncia: quem cadastra recebe um segredo, e a ativação falharia só para o e-mail que já existe. Por isso, o `POST /contas` responde 409 com uma frase clara, e o limite por IP reduz a varredura. A **entrada** esconde (mesma frase, mesmo trabalho e mesma espera para conta e para e-mail sem conta).
- **Qualquer pessoa pode criar uma conta com o e-mail de outra,** porque não há confirmação. O risco vai para os termos da C2.
- **A mensagem de conta bloqueada revela que a conta existe**, mas só depois de 100 falhas com espera crescente. Para quem tem a conta, a frase diz o que fazer.
- **O estado de uma organização começa vazio.** As empresas e o catálogo próprios entram na C3.
- **Verificado:**
  - testes de cada rota, com relógio de teste:
    - os vetores da RFC;
    - o código repetido;
    - a espera igual para conta e e-mail sem conta;
    - o bloqueio em 100 e o desbloqueio;
    - a sessão de 30 min e de 8 h;
    - sair e sair de todos;
    - os três casos de CSRF;
    - o isolamento da demo e entre organizações;
    - a exclusão, com e sem outros membros;
    - o banco guardando só hashes;
  - a sonda das mensagens em português passou também nas rotas novas;
  - o Chrome, nos dois endereços locais;
  - o OWASP ZAP (`zap-api-scan.py` da imagem `ghcr.io/zaproxy/zaproxy:stable`, com a varredura ativa a partir do `openapi.json` com as rotas novas, como no ADR 0011):
    - **0 FAIL, 0 WARN e 119 PASS**;
    - cerca de 19.600 requisições, nenhum 500 e nenhuma exceção no log da API;
    - os 429 vieram da espera por conta, que vale mesmo com o limite por IP desligado para a varredura.

## Implementação futura

- **Passkey (WebAuthn), a opção resistente a phishing.** O AAL2 completo pede oferecer "at least one phishing-resistant authentication option" (§2.2), e o TOTP não é resistente a phishing. Ela é gratuita, mas pede bastante trabalho no backend e na tela. Fica registrada no plano v2.1 como implementação futura, fora da C1.
- **Convites de membros, troca de papel e transferência de posse:** no 3c.

## Em aberto

- **Os termos do NCSC** sobre a lista de senhas não foram verificados (o endereço do NCSC respondeu 404). A licença MIT do SecLists foi lida.
- **O segredo do TOTP fica em texto no `contas.db`.** O NIST pede controle de acesso, e não cifra. Cifrar exigiria uma chave fora do banco e uma dependência, porque a biblioteca padrão não tem AES. Revisar no deploy (E6), com o volume e as permissões do container.
- **Atrás de proxy, o limite por IP vira global** (já registrado no ADR 0006). O contador por conta não depende do IP.
