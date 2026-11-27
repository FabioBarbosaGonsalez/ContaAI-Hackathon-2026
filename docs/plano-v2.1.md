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
| C1: contas no backend | PR #21, ADR 0015 |
| B0: aceite dos termos (antes das telas da C2) | PR #22, revisão no ADR 0015 |
| C2a: página inicial, rotas, a conta na tela, termos e privacidade | PR #23, ADR 0016 |
| C2b: criar conta, entrar, o menu da conta e Sua conta | PR #24, seção da C2b no ADR 0016 |
| C2c: notas de exemplo e o fechamento da C2 | PR #25, seção da C2c no ADR 0016 |
| C3-B, etapas 1 a 5: CNPJ alfanumérico, migração 0003, referências, empresa da conta e catálogo editável | ADR 0017 |

## A ordem

| # | Etapa | Entrega | Depende de |
|---|---|---|---|
| 1 | **3b** (feito) | Telas de Notas e de Regime | `GET /notas` (feito) |
| 2 | **C1** (feito) | Contas no backend | 3b |
| 3 | **C2** (feito) | Telas de entrada | C1 |
| 4 | **C3** (em andamento) | Dados da própria empresa | C1 e C2 |
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
- ficou para depois: cadastrar o par de um item sem par (C3), oferecer as notas de exemplo na tela (C2; feito na C2c) e rever o recibo de uma nota antiga (rota nova, sem etapa).

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
- **O e-mail sem confirmação** (decisão 2): qualquer pessoa pode criar uma conta com o e-mail de outra. Registrar o risco no ADR e nos termos (C2; feito nos termos na C2a).

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

**Decisões do usuário (2026-11-26):**
1. **Endereços:** a página inicial fica em `/`, e o Painel passa para `/painel`.
2. **Quem tem conta vê a demonstração como todo mundo.** É a demonstração compartilhada, só para ver, com "Criar meu espaço" para gravar. A pessoa continua conectada, e uma faixa mostra "Voltar à minha conta".
   - Os pedidos da demonstração saem com `credentials: 'omit'`, sem o cookie da sessão: a API responde como a quem não tem conta, e o backend não muda.
   - Não depende de sobrar espaço (pendência do ADR 0010).
   - Fica fora: criar um espaço sozinho a cada visita, porque ele vence em 120 min e gasta os espaços da demo pública.
3. **QR code com a `uqr` 0.1.3**, desenhado como SVG de elementos React a partir da matriz.
   - Lido em 2026-11-26, no pacote do npm:
     - o `LICENSE` é MIT, "Copyright (c) Project Nayuki" e "Copyright (c) 2023 Anthony Fu";
     - não tem dependências;
     - o `dist` tem 73.079 bytes, e o pacote inteiro, 79.278 (`npm view uqr@0.1.3 dist.unpackedSize`, conferido na C2b; o mapa dizia 84 KB);
     - o `encode()` devolve `data: boolean[][]`.
   - Fica fora:
     - o `renderSVG()`, que devolve texto e pediria `dangerouslySetInnerHTML`;
     - a `qrcode-generator` 2.0.4, porque o `package.json` diz MIT, mas o pacote não traz o arquivo de licença.
   - **Conferido na C2b (2026-11-26):** a 0.1.3 foi publicada em 2026-04-03 (`npm view uqr time`). O README documenta o `encode()` (`data`, `version` e `size`) e credita o algoritmo ao Project Nayuki. O `dist` não tem chamada de rede, `eval`, DOM nem `innerHTML`, e o `npm audit` dá 0 vulnerabilidades.
4. **Quem responde pelos dados: "Equipe ContaAI", sem e-mail.**
   - A página mostra só "Equipe ContaAI": sem e-mail, sem nome e sem frase do tipo "contato a definir".
   - **Regra do usuário: o nome e o e-mail dos integrantes nunca vazam.** Eles não entram no repositório, que é público, nem no código, nos testes, nos mocks, nos logs, nos commits, nos PRs ou na página publicada.
   - **Sem e-mail, os direitos da LGPD são exercidos dentro do app:**
     - ver os próprios dados no menu da conta (T6);
     - excluir a conta (T6, art. 18 VI).
   - **Risco confirmado, a decidir antes da publicação (E6):** lido no Planalto em 2026-11-26 (C2a), a LGPD pede, no art. 9º, a identificação e as informações de contato do controlador (incisos III e IV) e, no art. 41, § 1º, que a identidade e o contato do encarregado sejam divulgados publicamente. A política sem canal de contato fica incompleta, e o usuário decide de novo (por exemplo, um e-mail só do projeto, configurado no servidor e fora do git).
5. **Aceite dos termos com registro:** uma caixa obrigatória no cadastro, com a versão aceita e a data gravadas.
   - A política de privacidade entra como link, para ler, e não como consentimento.
   - **Base legal (lida na C2a):** o art. 7º, V, a execução de contrato a pedido do titular. É a que a privacidade cita para os dados da conta.
6. **As notas de exemplo** (pendência do 3b) entram na C2. **Feito na C2c.**

**Achados do mapeamento:**
1. **Com o cookie da sessão e sem espaço, a API abre o banco da organização** (`abrir_estado`), que fica vazio até a C3. As telas pedem o CNPJ fixo da Serra Azul (`CNPJ_DEMONSTRACAO`) e dariam 404. Por isso, a conta sem empresa tem um estado vazio próprio (decisão 2 para a demonstração).
2. **Uma sessão vencida responde 401 em qualquer rota.** O middleware só trata o 401 de um pedido com o token da demo. O cookie é `HttpOnly`, então a tela só sabe da sessão pelo `GET /conta`.
3. **No modo mock, as rotas de conta respondem 501.** Lá, Entrar e Criar conta não aparecem.
4. **A CSP fecha o caminho do QR pronto:**
   - `img-src 'self'`, sem `data:`;
   - Trusted Types `'none'`;
   - `dangerouslySetInnerHTML` proibido.

   Também fica fora um serviço externo de QR: ele receberia o segredo do TOTP.
5. **O segredo e os códigos de recuperação** ficam só na memória do componente: nada vai ao `localStorage`, ao endereço ou ao log. Tudo é apagado quando o passo acaba.
6. **O `ChaveRota` só aceita GET e POST,** mas sair usa DELETE (`/sessoes/atual` e `/sessoes`).
7. **Hoje `/` é o Painel** (decisão 1).

**Segmentos:** um PR de backend (B0) e, depois, três PRs de tela (decisão do usuário de 2026-11-26): **C2a** (T1, T2, T3, T7 e T8), **C2b** (T4, T5 e T6) e **C2c** (T9 e T10). Cada um sai com os próprios testes e o portão da skill.

| # | Segmento | O que entra |
|---|---|---|
| B0 | Aceite dos termos (backend) | Migração 0002 do `contas.db`, com a versão dos termos e a data do aceite. Um campo novo no `POST /contas`, que recusa a falta do aceite e a versão errada. O `GET /conta` mostra a versão aceita. Testes, contrato e OpenAPI regerados, revisão no ADR 0015 |
| T1 | Rotas | Rotas públicas (`/`, `/entrar`, `/criar-conta`, `/termos` e `/privacidade`) separadas das do app (`/painel` e as outras). A barra mostra só as do app. O `ChaveRota` passa a aceitar DELETE |
| T2 | Estado da conta | `SessaoConta`: carregando, anônimo, conectado ou encerrada, a partir do `GET /conta` ao abrir, só no modo real. O 401 vira "sessão encerrada, entre de novo", e os dados recarregam. A origem dos dados e o `useGravacao` passam a considerar a conta |
| T3 | Página inicial | O que é o ContaAI e a frase de simulação. "Explorar a demonstração" é o primeiro botão e não pede cadastro (decisão 1 do plano). Depois vêm "Criar conta" e "Entrar" |
| T4 | Criar conta | Três passos: (1) e-mail, senha (mínimo de 8, sem regra de composição), organização e o aceite; (2) QR, segredo para digitar à mão e o primeiro código, com a contagem dos 5 min; (3) os 10 códigos de recuperação, mostrados uma vez, com copiar, baixar e "guardei". O 409 do e-mail repetido usa a frase da API |
| T5 | Entrar | Duas etapas: e-mail e senha, depois o código do aplicativo ou um código de recuperação. O 429 mostra a espera do `Retry-After`. O passe vencido volta ao começo. O código de recuperação novo aparece uma vez |
| T6 | Menu da conta | E-mail, organização, códigos restantes (com aviso quando estiverem acabando) e eventos ("código de recuperação usado"). Sair, sair de todos os aparelhos e excluir a conta com a senha (o 409 pede passar a posse antes) |
| T7 | Barra e faixa | `StatusSessao` refeito para a demonstração compartilhada, o espaço e a conta. A faixa da demonstração leva a Criar conta ou volta à conta. A conta sem empresa tem um estado vazio que diz que o cadastro da empresa entra na C3 |
| T8 | Termos e privacidade | Rascunho marcado "sem revisão jurídica". Cobre: o e-mail sem confirmação (ADR 0015), os dados fictícios da demonstração, o cookie de sessão, o segundo fator, a exclusão da conta (LGPD, art. 18 VI) e quem responde pelos dados (decisão 4) |
| T9 | Notas de exemplo | Baixar os três XML fictícios de `data/demo/notas/` na tela de Notas, com uma fonte só e sem cópia à mão |
| T10 | Verificação e documentação | Testes com fetch falso e TOTP calculado no teste. Portão `inspect.mjs --app` em 1440, 768 e 390 px. Chrome com o build: CSP, Trusted Types e o fluxo inteiro pelo DevTools Protocol. Teclado, leitor de tela e `autocomplete` (`username`, `new-password`, `current-password` e `one-time-code`). ADR 0016, este plano, o README e a varredura de inconsistências |

**A conferir durante o código:**
- ~~o README e a data da `uqr` 0.1.3~~: **conferidos na C2b** (decisão 3);
- ~~se baixar os códigos como `.txt` por `blob:` passa pela CSP atual, no Chrome~~: **conferido na C2b, etapa 7** (o arquivo baixou inteiro, sem violação);
- se os gerenciadores de senha funcionam com `form-action 'none'` (o envio é por `fetch`): **em parte, na C2b, etapa 6.** O envio não dá violação da CSP, e os campos têm `name` e `autocomplete`. O balão de salvar a senha não aparece no Chrome sem janela (headless). **Conferido pelo usuário num Chrome comum (2026-11-27):** o balão aparece;
- ~~se o `credentials: 'omit'` da demonstração passa pela conferência de CSRF~~: **conferido na C2a**, no Chrome. O `POST /espacos` sem cookie, com a conta aberta, criou o espaço;
- ~~a LGPD, art. 7º, 9º e 41, e o guia de cookies da ANPD~~: **lidos na C2a** (fontes no [ADR 0016](adr/0016-telas-de-entrada.md)).

**Custo:** nenhum serviço pago e nenhuma chamada externa. A única dependência nova é a `uqr` (MIT).

**Saída:** portão da skill nas telas novas; dá para criar a conta, entrar, sair e voltar à demonstração.

**Feito: B0 (2026-11-26, revisão no [ADR 0015](adr/0015-contas.md)):**
- o `POST /contas` exige `termosAceitos` com a versão atual (`2026-11-26`). Sem ele, ou com outra versão, responde 422 com a frase em português, e nada é criado;
- a versão tem uma fonte só (`app/contas/termos.py`), e o tipo gerado da tela só aceita ela;
- a migração 0002 grava a versão e a data, conferida também num `contas.db` de antes dela;
- o `GET /conta` mostra o aceite;
- 489 testes do backend e 252 da tela passam, com 97% de cobertura.

**Feito: C2a (2026-11-26, [ADR 0016](adr/0016-telas-de-entrada.md)):**
- **rotas:** `/` é a página inicial, e o Painel foi para `/painel`. `/termos` e `/privacidade` são públicas, com uma barra sem os destinos do app;
- **a conta na tela** (`SessaoConta`): o `GET /conta` ao abrir, só no modo real. Nenhum dado é pedido antes de a tela saber se há conta (defeito achado pelo teste e corrigido);
- **o cookie só vai aonde precisa:** às rotas da conta sempre, e às de dados só na conta. A demonstração vista com a conta sai com `credentials: 'omit'`. Um 401 com o cookie, fora das rotas de entrada, encerra a sessão na tela;
- **a conta sem empresa** mostra o estado vazio no lugar das páginas, sem pedir o CNPJ da demonstração;
- **a faixa da demonstração** diz que os dados são fictícios e, para quem tem conta, oferece "Voltar à minha conta";
- **termos e privacidade:** rascunhos marcados "sem revisão jurídica", com as regras conferidas com o backend por teste;
- **verificação:** 293 testes da tela; o portão da skill com 0 FAIL e 0 WARN em quatro páginas e três larguras; o fluxo da conta no Chrome pelo DevTools Protocol;
- **ficou para a C2b:** Entrar, Criar conta e o menu da conta. A privacidade já cita o menu (ver os dados e excluir a conta), que só passa a existir na tela com a C2b;
- **pendências achadas, para a E6 e o 3c:**
  - o prazo de guarda do log do servidor;
  - o provedor de hospedagem como operador;
  - as cópias de segurança e a exclusão "na hora";
  - o chat com IA real, que manda texto a terceiros e precisa entrar na privacidade antes (3c).

**C2b em 10 etapas (validado pelo usuário em 2026-11-26):**

| # | Etapa | O que entra |
|---|---|---|
| 1 | Conferências e dependência | README e data da `uqr` 0.1.3, licença no `node_modules`, `npm audit`, versão fixa |
| 2 | Rotas e links | `/entrar` e `/criar-conta` (públicas) e `/conta` (no app, fora dos destinos). Links na página inicial, na barra pública e na faixa. No mock, a página diz que as contas não existem. Quem já entrou e abre Entrar ou Criar conta vai ao Painel, com o endereço trocado |
| 3 | Peças de formulário | Campo com ajuda e erro ligados (aria-describedby), senha com "Mostrar", campos de código, aviso de falha que recebe o foco, contagem do passe e espera do 429 |
| 4 | Ações da conta | Cadastrar, ativar, entrar, código, sair, sair de todos e excluir na `SessaoConta`. Segredo e códigos só na memória do componente |
| 5 | QR code | SVG de elementos React a partir do `encode()`, fundo claro, segredo em grupos de 4 para digitar |
| 6 | Criar conta, passo 1 | E-mail, senha, organização e o aceite dos termos; gerenciador de senhas com `form-action 'none'` no Chrome |
| 7 | Criar conta, passos 2 e 3 | QR e primeiro código com a contagem; os 10 códigos com copiar, baixar (`blob:` no Chrome) e "guardei". A correção do achado abaixo foi adiantada para a etapa 4 |
| 8 | Entrar | Duas etapas; código do aplicativo ou de recuperação; espera do 429; passe vencido volta ao começo; conta pendente (`etapa: "ativacao"`) vai ao passo do QR |
| 9 | Menu da conta | Botão com o e-mail na barra (Sua conta e Sair) e a página `/conta` com os dados, os códigos restantes, os eventos e as ações |
| 10 | Verificação e documentação | Testes, portão da skill, fluxo no Chrome, ADR 0016, plano, README, varredura; o QR lido num aplicativo autenticador de verdade, pelo usuário |

**Etapa 5 feita (QR code):** `telas/QrCode.tsx` desenha um único `<path>` (um retângulo por trecho escuro de cada linha) a partir do `encode()`, com fundo branco e módulos pretos. A correção de erro é a M, que dá a versão 8 (49 módulos) para o endereço de um e-mail comum. Cada módulo tem 4 px inteiros, e o QR cresce com o endereço, até 157 módulos (628 px) no pior e-mail aceito: 254 caracteres acentuados, que o endereço triplica. Em tela estreita, o QR encolhe. A borda tem 4 módulos, o valor dos exemplos do Project Nayuki (lido em 2026-11-26); a página não diz que a norma exige 4, e a ISO/IEC 18004 **não foi lida**. O segredo aparece em grupos de 4, em linha, separados por margem e com `<wbr>` entre eles, para que o texto copiado saia inteiro. Os testes refazem a matriz a partir do desenho e a comparam com a do `encode()`.

**Conferido no Chrome 158 (2026-11-26)**, com o componente real e o CSS da tela, por um roteiro no scratchpad da sessão (fora do repositório). O print do QR foi lido pelo jsQR 1.4.0 (Apache-2.0, só no rascunho, fora do projeto) em 4 e-mails (comum, acentuado, 254 caracteres e o pior caso), em densidade 1, 2 e 3, em 360 px e com alto contraste emulado (`forced-colors: active`, que pintou a página de preto e manteve o QR branco e preto). Todos foram lidos e deram o endereço exato. A conferência mudou duas coisas:
- **o tamanho fixo de 224 px** deixava o e-mail longo com 2,64 px por módulo, e o print não era lido. Daí os 4 px por módulo;
- **os grupos do segredo em flex** levavam uma quebra de linha entre cada grupo na cópia (`Ctrl+C`): o teste do jsdom passava porque o jsdom não tem layout. Com os grupos em linha, a seleção e a área de transferência dão o segredo exato. Numa tela de 200 px, o segredo quebra em 2 linhas sem partir nenhum grupo.

**Ainda falta:** a leitura num aplicativo autenticador de verdade, pela câmera (etapa 10). O jsQR lê o print, não uma foto da tela.

**Revisão da etapa 5 (2026-11-26):**
- **CSP:** o QR e o segredo, servidos com os cabeçalhos de `cabecalhosDeSeguranca` (`csp.ts`) e o CSS como arquivo externo, não deram violação no Chrome 158. Um `<style>` embutido de controle foi barrado, o que prova que a política estava valendo. O QR foi lido igual;
- **o endereço do QR** confere com o Key Uri Format do Google Authenticator (wiki lido em 2026-11-26; o repositório está arquivado desde 2021): o rótulo aceita o `:` como `%3A`, e o emissor do rótulo é igual ao do parâmetro `issuer`;
- **achado, anterior a esta etapa (C1, backend):** a mesma página diz que o nome da conta não pode ter `:`, mas o padrão de e-mail do contrato (`[^@\s]{1,64}@...`) aceita, por exemplo, `a:b@x.com`. O `quote` do `totp.endereco` vira `%3A`, e um aplicativo pode separar o rótulo no lugar errado. **Resolvido na varredura de 2026-11-26 (decisão do usuário):** o padrão de e-mail recusa o `:` (`[^@\s:]`), no contrato e na tela (revisão da varredura no [ADR 0015](adr/0015-contas.md));
- **licenças no build:** o build da tela saía sem nenhum aviso de copyright (o código minificado não leva os comentários), e a MIT pede o aviso nas cópias. Isso já valia para o React e passaria a valer para a `uqr` (Project Nayuki e Anthony Fu). Agora o `build.license` do Vite gera `licencas.md` com o que entra no build, e o `npm run seguranca` falha sem ele. A lista bate com a do [ADR 0012](adr/0012-fundacao-do-frontend.md) (React, React DOM, scheduler, openapi-fetch e as fontes Geist). A `uqr` entra sozinha quando o QR for montado (etapa 7). **Feito na etapa 10:** revisão da C2b no ADR 0012.

**Etapas 6 e 7 feitas (Criar conta, 2026-11-26):**
- **passo 1** (`telas/CriarConta.tsx`): e-mail (`username`), senha (`new-password`, com "Mostrar"), organização (`organization`) e a caixa do aceite, com a versão de `legal.ts`. Os termos e a privacidade abrem em outra aba (`target="_blank"` e `rel="noopener noreferrer"`; o `Link` passou a aceitar), sem perder o que foi digitado. A tela confere tudo antes de enviar, aponta o erro em cada campo e põe o foco no primeiro. O 409 mostra a frase da API e o caminho para Entrar; o 422 e o 429 mostram a frase da API, e o 429 segura o botão pelo `Retry-After`;
- **passo 2** (`telas/SegundoFator.tsx`, `PassoDoQr`, que o Entrar vai usar na etapa 8): o QR, o segredo com "Copiar o segredo", o e-mail da conta e o primeiro código, com a contagem do passe. A contagem parte de quando a resposta chegou, com os 5 min do backend, e não do `expiraEm` contra o relógio do aparelho. Com o passe vencido, o QR e o segredo saem da tela e a página leva a Entrar (decisão 1);
- **passo 3** (`CodigosDeRecuperacao`): os 10 códigos, "Copiar os códigos", "Baixar (.txt)" e "Guardei os códigos", que vai ao Painel sem deixar o cadastro no voltar. Fechar a aba neste passo pede confirmação;
- **ao lado dos passos:** "Como a conta é protegida", com as regras de `legal.ts` e o que os termos já dizem (senha, segundo fator, recuperação e sessão);
- **a tela conta os caracteres como o backend** (pontos de código): os campos não têm `maxLength`, porque o do HTML conta unidades UTF-16 e corta o texto colado sem avisar;
- **achado e consertado no backend:** a organização só com espaços passava pelo contrato e nascia sem nome (revisão da etapa 6 no [ADR 0015](adr/0015-contas.md));
- **verificação:** 392 testes da tela e 498 do backend (97%); o portão da skill em `/criar-conta` com 0 FAIL e 0 WARN em 1440, 768 e 390 px; o cadastro inteiro no Chrome 158, com o build, a CSP do cabeçalho e a API real, por um roteiro no scratchpad da sessão (o código TOTP calculado no roteiro): nenhuma violação da CSP, os cookies `__Host-` com `HttpOnly`, `Secure` e `SameSite=Strict`, o segredo copiado igual, o `.txt` com os 10 códigos e nada no endereço nem no armazenamento do navegador;
- **ainda falta:** o QR lido pela câmera de um aplicativo autenticador de verdade e o balão do gerenciador de senhas, pelo usuário (etapa 10); a `uqr` entrou no build e no `licencas.md` (ADR 0012 atualizado na etapa 10).

**Pedido do usuário (2026-11-26): medidor de força da senha e menos texto na tela**
- **Medidor** (`telas/forcaDaSenha.tsx`): fraca com a barra em um terço e vermelha, média em dois terços e amarela, forte inteira e verde, com a palavra ao lado (a cor não é o único sinal).
  - **Fonte:** o NIST SP 800-63B-4, §3.1.1.2 (lido em 2026-11-26), diz "Verifiers SHALL offer guidance to the subscriber to help the subscriber choose a strong password" e proíbe regra de composição. O medidor só orienta e não exige mistura de caracteres.
  - **Estimativa:** zxcvbn-ts (`@zxcvbn-ts/core` 4.2.0 e `@zxcvbn-ts/language-common` 4.1.3, MIT), com versões de pelo menos duas semanas (a 4.3.0 do núcleo saiu em 2026-11-14). Ficou fora o `@zxcvbn-ts/language-pt-br`: o dicionário dele vem do OpenSubtitles (ODC-BY, que pede manter um aviso de atribuição) e de uma lista da Wikipédia sem licença declarada.
  - **Limites:** sem o dicionário em português, a estimativa é generosa com palavras da nossa língua ("minhacasa" leva nota 3). Por isso 0 a 2 = fraca, 3 = média e só 4 = forte; abaixo de 8 caracteres, é fraca sempre. O e-mail, a organização e as palavras do produto pesam contra a senha, como no backend.
  - **Cores:** tokens novos `--forca-fraca`, `--forca-media` (`#b58105`, 3,12:1 no fundo) e `--forca-forte`, com 3:1 conferido em `tokens.test.ts`.
  - **Peso:** a biblioteca é baixada só quando a pessoa digita a senha: 33 KB do núcleo e 428 KB do dicionário (224 KB comprimido). O arquivo principal cresceu 4 KB.
- **Menos texto:** regras e resultado na revisão de 2026-11-26 do [ADR 0014](adr/0014-telas-notas-e-regime.md). Palavras no conteúdo, medidas no Chrome antes e depois: Regime 775 → 522, Catálogo 542 → 366, Criar conta 191 → 121, Início 209 → 170 e Notas 107 → 82. Termos e privacidade ficaram inteiros: são o texto legal.
- **Verificação:** 419 testes da tela e 498 do backend (52 de referência); o portão com 0 FAIL e 0 WARN nas seis telas que mudaram; o medidor e o cadastro inteiro no Chrome 158, sem violação da CSP.

**Etapa 8 feita (Entrar, 2026-11-27):**
- **página** (`telas/Entrar.tsx`): duas etapas, e-mail e senha, depois o código do aplicativo ou de recuperação, com a contagem do passe.
  - Passe vencido: volta ao passo 1, com o e-mail e sem a senha, e diz por quê.
  - Conta pendente (`etapa: "ativacao"`): vai ao QR e aos 10 códigos. O `PassoDoQr` ganhou `aoRecomecar`, para não mostrar um link para a própria página.
  - Código de recuperação: a página mostra o código novo uma vez, com aviso ao fechar a aba.
  - Ao lado, "Sem acesso?", com as regras de `legal.ts` (as mesmas dos termos).
  - A página é curta: o título e o formulário ficam no meio da altura livre (o portão mediu 408 px vazios no pé, em 1440 px).
- **o 429 da conta bloqueada (o ponto "a conferir" abaixo), resolvido:** tipo próprio `/problemas/conta-bloqueada` no backend, e a tela não mostra contagem para ele (revisão da etapa 8 no [ADR 0015](adr/0015-contas.md)). O e-mail sem conta recebe a mesma resposta, então o tipo não revela se o e-mail existe;
- **achados no caminho, anteriores à etapa:**
  - em `POST /sessoes`, a descrição do 429 no contrato só citava o limite por IP (o dicionário do limite apagava a da rota). Corrigido e exportado de novo;
  - o `lint.mjs --app` da skill dava 8 FAIL das etapas 3 a 7: emojis em dados de teste (contam pontos de código) e o `nome@example.com` da frase do e-mail (domínio reservado para exemplos, RFC 2606). As linhas levam `taste-skill-ignore` com o motivo. Ficam 6 WARN: os 5 de antes e o `padStart` dos segundos da contagem ("4 min 05 s"), que é um relógio;
  - um teste do aviso ao fechar a aba falhava às vezes com a máquina ocupada (o ouvinte entra num efeito): `waitFor` no Entrar e no Criar conta;
- **verificação:**
  - testes: tela 439 e backend 500, com lint, tsc, build, `npm run seguranca`, `contrato:checar`, ruff e mypy;
  - portão da skill em `/entrar` e `/criar-conta`: 0 FAIL e 0 WARN em 1440, 768 e 390 px;
  - fluxo inteiro no Chrome 158, com o build, a CSP do cabeçalho e a API real, por um roteiro no scratchpad da sessão: campos vazios, senha errada, código errado, código certo, código de recuperação (o novo é diferente, copiar dá o código exato, o usado não vale de novo), conta pendente (segredo novo, ativação e 10 códigos), espera do 429 ("Aguarde 30 s") e conta bloqueada (frase da API, sem contagem). Nenhuma violação da CSP e nenhuma exceção; só cookies `__Host-` com `HttpOnly`, `Secure` e `SameSite=Strict`; nada no endereço nem no armazenamento do navegador. O bloqueio foi marcado direto no banco de teste, porque 100 falhas reais levariam horas por causa da espera. A API de teste subiu com o limite por IP em 100 por minuto, para o roteiro caber; o limite em si tem teste no backend;
- **falta, para a etapa 10:** o balão do gerenciador de senhas no Entrar (`current-password`), num Chrome comum, pelo usuário.

**Etapa 9 feita (menu da conta e Sua conta, 2026-11-27):**
- **menu na barra** (`shell/MenuDaConta.tsx`): um botão com o e-mail, cortado com reticências, que mostra e esconde a organização, "Sua conta" e "Sair".
  - É um botão de mostrar e esconder (`aria-expanded`), e não um `role="menu"`: só um link e um botão. Esc fecha e devolve o foco; clicar fora ou levar o foco para fora também fecha.
  - Aparece também na demonstração e nas páginas públicas, para sair de qualquer lugar. Na folha do celular, o conteúdo aparece aberto, com alvos de 44 px.
  - Sair que falha diz que a sessão pode continuar aberta, e a conta segue na tela.
- **"Minha conta" virou "Ir ao Painel"** (barra pública e página inicial): o link levava ao Painel, e o nome era quase igual ao da página "Sua conta", que leva a outro lugar;
- **página Sua conta** (`telas/Conta.tsx`): só o que o `GET /conta` já trouxe, sem pedir nada além dele.
  - Dados: e-mail, organização e papel, criada em, aceite dos termos e empresas.
  - Segundo fator e códigos de recuperação, com o aviso de 3 ou menos (decisão 3).
  - Avisos de segurança, com nome e momento no fuso do navegador (`instante`, em `dados/formatar.ts`).
  - Sessão, com Sair e Sair de todos os aparelhos.
  - Excluir a conta: a senha de novo e a caixa "Entendo que a exclusão não pode ser desfeita", com o botão vermelho (branco sobre `--negativo`, 5,78:1, em `tokens.test.ts`). Também mostra o 401 de senha errada, o 401 de sessão acabada, o 409 do dono com outros membros e o bloqueio sem contagem. A exclusão vem por último também no celular;
- **privacidade:** "ver os seus dados" e "excluir a conta" apontam para "Sua conta", no menu da conta, que agora existe;
- **achados:**
  - **o aviso de poucos códigos (decisão 3) não aparece com o backend de hoje.** O código de recuperação usado é trocado por outro na hora (NIST §4.2, ADR 0015), então `codigosRecuperacaoRestantes` fica sempre em 10. O aviso está pronto e testado, para quando houver outro caminho que gaste os códigos sem troca. **Decisão do usuário (2026-11-27): o aviso fica;**
  - o formulário de excluir tinha senha sem campo de usuário, e o Chrome recomendou um campo de usuário, que pode ser oculto, para o gerenciador de senhas. Entrou um campo oculto com o e-mail (`autocomplete="username"`), que não é enviado;
  - "10 de 10" e as datas saíam na fonte mono, no meio da frase (classe `num`). Agora a `num` fica só nos CNPJs;
- **portão:**
  - `inspect.mjs --app` com 0 FAIL e 0 WARN em `/`, `/painel`, `/entrar` e `/criar-conta`;
  - em `/conta`, 0 FAIL e 1 WARN (`hero-void`): o aviso de quem não entrou fica estreito e no centro, e o vazio simétrico é o descanso da tela. Os avisos curtos da porta passaram a ficar no meio da altura, como o Entrar (antes, 580 px vazios);
  - o inspetor não leva cookie, então a visão de quem entrou foi conferida pelo roteiro do Chrome nas três larguras, sem rolagem lateral;
  - `lint.mjs --app` com 0 FAIL e os 6 WARN de antes;
- **verificação:**
  - testes: tela 463 (22 novos em `suaConta.test.tsx`) e backend 500 (sem mudança), com lint, tsc, build, `npm run seguranca` e `contrato:checar`;
  - no Chrome 158, com o build, a CSP e a API real: o menu (abre, Esc, foco, cores no painel claro), a folha do celular e a página nas três larguras;
  - sair pelo menu e sair de todos: cookie apagado e `GET /conta` com 401;
  - excluir com senha errada ("Senha incorreta.") e depois certa ("A conta foi excluída", e a entrada passa a dar 401);
  - nenhuma violação da CSP e nada no endereço nem no armazenamento.

**Etapa 10 feita (verificação e documentação, 2026-11-27):**
- **testes:** tela 463 e backend 500 (97%), mais os 52 de referência, com lint, tsc, build, `npm run seguranca`, `contrato:checar`, ruff, mypy e `npm audit` (0 vulnerabilidades);
- **teste instável:** um teste do Entrar falhava às vezes com a máquina ocupada (2 vezes em 8 rodadas). O foco no título do passo vem de um `useEffect`, e o teste conferia antes. As conferências de foco depois de uma resposta da API passaram a esperar (`waitFor`) no Entrar, no Criar conta e em Sua conta, e o `irAoCodigo` espera o passo 2 aparecer; 4 rodadas com carga em paralelo, todas com 463 de 463;
- **no Chrome 158**, com o build, a CSP do cabeçalho e a API real, os três roteiros (criar conta, entrar e o menu com Sua conta) rodaram de novo sobre o build final: nenhuma violação da CSP, nenhum pedido fora da API, só cookies `__Host-` com `HttpOnly`, `Secure` e `SameSite=Strict`, nada no endereço nem no armazenamento;
- **achado e consertado:** em 390 px, a barra pública rolava de lado com um e-mail longo, no passo "Guarde o código novo" do Entrar (já com a sessão, a barra mostra o menu). O botão do menu não encolhia, e "Ir ao Painel" quebrava em duas linhas. Agora a barra encolhe e o e-mail é cortado com reticências (`shell.css`); em 1440 px, nada muda. A etapa 9 tinha conferido as larguras no app, com um e-mail curto;
- **portão da skill:** `inspect.mjs --app` com 0 FAIL e 0 WARN em nove telas e 1 WARN defensável em `/conta` (o mesmo da etapa 9); `lint.mjs --app` com 0 FAIL e os 6 WARN de antes. As telas de dados só passam com os motores de pé e as sementes no banco: com os motores fora do ar, o esqueleto de carregamento conta como vazio (`blank-gap`). Crítica em `.taste-skill/app/critica-c2b.md`;
- **docs:** seção da C2b no [ADR 0016](adr/0016-telas-de-entrada.md); revisão da C2b no [ADR 0012](adr/0012-fundacao-do-frontend.md), com a `uqr`, o zxcvbn-ts e duas dependências deste que estavam fora dos docs (`fastest-levenshtein` 1.0.16 e `@zxcvbn-ts/dictionary-compression` 3.0.1, MIT, sem dependências próprias; nenhuma das cinco tem `fetch`, `eval` ou parecido); README;
- **fica com o usuário:** o balão do gerenciador de senhas num Chrome comum (Criar conta e Entrar) e o QR lido pela câmera de um aplicativo autenticador de verdade. **O balão foi conferido pelo usuário em 2026-11-27** e aparece; falta o QR pela câmera.

**Achado do mapa da C2b:** o passe da ativação dura 5 min, mas a conta pendente só some em 30 min (`servico.py`, `PASSE` e `PENDENTE`). Quem deixa o passe vencer no passo do QR recebe 409 ao se cadastrar de novo ("Entre com a senha e o código"), e o `entrar` só aceita conta ativa: a pessoa fica sem saída por até 25 min.

**Decisões da C2b (2026-11-26):**
1. **Entrar numa conta pendente, com a senha certa, dá um passe novo de ativação** e volta ao passo do QR (mudança no backend, neste PR). Exige a senha, então ninguém de fora assume o cadastro. **Feito na etapa 4:** o segredo é trocado, só o último passe vale e o cadastro pendente ganha mais 30 min (revisão da C2b no [ADR 0015](adr/0015-contas.md));
2. menu curto na barra, mais a página `/conta` com os detalhes e as ações;
3. o aviso de códigos de recuperação acabando aparece com 3 ou menos.

**A conferir na C2b (resolvido na etapa 8):** o 429 da espera e o da conta bloqueada (100 falhas) chegam com o mesmo status, e o bloqueio manda `Retry-After` de 3600 s. A tela não deve mostrar "tente em 1 h" para uma conta que só o administrador desbloqueia (etapa 8).

**C2c: notas de exemplo e o fechamento da C2.** O mapa saiu de uma leitura do código em 2026-11-27, e o usuário validou as três recomendações:
1. a tela lê `data/demo/notas` pelo Vite, sem rota nova no backend;
2. oferece as três notas, com a nota 1 marcada como já presente na demonstração;
3. a lista fica no bloco de importar, em Notas.

Achados do mapa:
- até aqui, a tela não lia nada de fora de `frontend/`. Um comentário do `App.test.tsx` registrava que abrir o `server.fs.allow` valeria para o servidor de desenvolvimento;
- abaixo de 4 KB, o Vite embute o arquivo no código como `data:`, e duas das notas têm menos que isso;
- importar a nota 1 de novo não dá erro: a API devolve o recibo gravado (`jaImportada`).

| # | Etapa | O que entra |
|---|---|---|
| 1 | Conferências | `import.meta.glob` com `?url` fora da raiz, `server.fs.allow` e `assetsInlineLimit`, lidos no Vite 8.3.8 instalado |
| 2 | Fonte única | `dados/notasDeExemplo.ts`, com uma frase por arquivo e o teste que compara as frases com a pasta |
| 3 | Tela | A seção "Notas de exemplo para baixar (fictícias)" no bloco de importar, também na demonstração e no mock |
| 4 | Verificação | Testes, build, segurança, o servidor de desenvolvimento e o Chrome com o build (baixar, sha256 e importar), o portão da skill |
| 5 | Docs e fecho da C2 | ADRs 0014 e 0016, este plano, `docs/seguranca.md`, README, a saída da C2 no Chrome e a varredura |

**Feito: C2c (2026-11-27, seção da C2c no [ADR 0016](adr/0016-telas-de-entrada.md)):**
- **etapa 1:** lido no código do Vite 8.3.8 que definir `server.fs.allow` troca a raiz padrão (`raw?.fs?.allow ?? [workspaceRoot]`), que a lista de `deny` padrão continua valendo e que o `assetsInlineLimit` aceita uma função por arquivo;
- **etapas 2 e 3:** `dados/notasDeExemplo.ts` acha os XML por `import.meta.glob` com `?url`. O `vite.config.ts` libera só essa pasta para o servidor de desenvolvimento, junto com a raiz de antes, e não deixa o XML virar `data:`. O link passa pela `ArquivoParaBaixar` (`shell/navegacao.tsx`), que só aceita um arquivo da própria origem;
- **achado no caminho:** o lint de segurança barrou o `href` montado de um valor (item 2 de `docs/seguranca.md`). O conserto seguiu o padrão da `Ancora`: um componente no único arquivo que monta `href`, com testes de recusa;
- **etapa 4:**
  - testes: tela 491 (eram 463) e backend 500, mais os 52 de referência; lint, tsc, build, `npm run seguranca`, `contrato:checar`, ruff, format e mypy;
  - no build, os três XML têm o mesmo sha256 do repositório, e não aparece nenhum caminho local;
  - no servidor de desenvolvimento, só a pasta das notas se abriu: `sementes.json`, o backend e o `.git` respondem 403;
  - no Chrome, os três downloads e a importação dos arquivos baixados num espaço, nas três larguras, sem violação da CSP;
  - portão com 0 FAIL e 0 WARN em `/notas`;
- **etapa 5, a saída da C2 conferida no Chrome com o build:** criar conta, sair, entrar, ver a demonstração com a conta e voltar à conta, sem violação da CSP nem pedido fora da origem. A conta de teste foi excluída no fim;
- **ambiente:** a porta 8000 desta máquina está ocupada por outro container do Docker, de fora do projeto. A API de teste subiu na 8001, com o proxy do preview apontado para ela (`CONTAAI_API_ALVO`).

**C2 fechada.** Dá para criar a conta, entrar, sair e voltar à demonstração (a saída da C2). Continuam pendentes:
- o QR lido pela câmera de um aplicativo autenticador de verdade, pelo usuário;
- o risco do contato na LGPD, para a E6.

## C3: dados da própria empresa

**Escopo:**
- a primeira vez (estado vazio) e o cadastro da empresa (CNPJ, regime, UF e município);
- configurações;
- catálogo e clientes B2B editáveis;
- o CNPJ fixo do 3a passa a ser o da empresa da conta.

**Decisões do usuário (2026-11-27):**
1. O P10 ("só dados fictícios") vale para a demonstração e os espaços. No ambiente próprio, cada pessoa põe os dados reais dela.
2. O dígito verificador do CNPJ é exigido nas empresas reais. A demo continua aceitando os CNPJs dela, que têm dígito inválido de propósito ([ADR 0008](adr/0008-nfe-historico-e-alertas.md)).
3. As notas de exemplo da tela somem fora da demonstração (a API recusa, com 422, a nota de outro destinatário).
4. **Excluir a conta:**
   - a exclusão é imediata e definitiva;
   - antes dela, a pessoa pode baixar os dados em JSON (LGPD, art. 18 V);
   - ao subir, a API apaga os bancos de organização que não existem mais;
   - os logs não guardam dado pessoal;
   - o contador perde o acesso quando a empresa sai.
5. **Backups (E6):** um por dia, cifrados e fora do servidor, guardados por 30 dias, com restauração testada. Uma organização excluída nunca volta por um backup, e a Privacidade diz o prazo.
6. **Mapa da C3-B:**
   - o CNPJ alfanumérico entra já;
   - o cenário da empresa real usa as premissas rotuladas da simulação;
   - quem não é do Simples é recusado no cadastro;
   - o item é arquivado em vez de apagado;
   - o mesmo CNPJ pode estar em duas contas.

**Fontes da exclusão:**
- **LGPD, art. 16:** "Os dados pessoais serão eliminados após o término de seu tratamento". A exceção do inciso I é a "obrigação legal ou regulatória pelo controlador".
- **Ajuste SINIEF 07/05, cláusula décima:** "O emitente deverá manter a NF-e em arquivo digital, sob sua guarda e responsabilidade"; o §2º estende ao destinatário.
- **CTN:** o art. 195, parágrafo único, manda conservar os comprovantes "até que ocorra a prescrição".
- **Conclusão:** a guarda é do contribuinte. O ContaAI não guarda o XML (só o sha256 e o recibo), então a exclusão pode apagar tudo. A tela avisa: "Guarde suas notas: o ContaAI não é o seu arquivo fiscal".

**Divisão:** C3-B (backend), C3a (a primeira vez e o cadastro da empresa) e C3b (configurações, catálogo e clientes editáveis).

### C3-B: o backend, em 10 etapas

| # | Etapa | Situação |
|---|---|---|
| 1 | Conferências: leiaute da NF-e para o CNPJ alfanumérico, a fonte dos municípios e as atividades do Simples | feita |
| 2 | Validação do CNPJ numérico e alfanumérico (`app/cnpj.py`) | feita |
| 3 | Migração 0003: CNPJ com letras e item arquivado | feita |
| 4 | Empresa: `POST /empresas`, `GET` e `PATCH /empresas/{cnpj}` e as referências | feita |
| 5 | Catálogo editável: criar, alterar e arquivar o item | feita |
| 6 | Clientes B2B: criar, alterar e excluir, com o CNPJ validado | a fazer |
| 7 | Exclusão e dados (LGPD): `GET /conta/dados`, limpeza dos bancos órfãos ao subir, logs sem dado pessoal e excluir a empresa sem excluir a conta | a fazer |
| 8 | Papéis: só o dono cadastra, configura e exclui a empresa; dono e membro editam o catálogo e os clientes | feita nas rotas da empresa e do catálogo; falta a exclusão (etapa 7) |
| 9 | Proteções: limites, o erro 500 com os cabeçalhos de segurança ([ADR 0009](adr/0009-camada-http-e-erros.md)) | limites feitos; falta o 500 |
| 10 | Contrato, mock e documentação | contrato e documentação das etapas 1 a 5 feitos; fecha no fim |

**Feito nas etapas 1 a 5** ([ADR 0017](adr/0017-empresa-propria.md)):
- **Conferências:**
  - a NT 2026.004 v1.01 da NF-e torna alfanuméricos o CNPJ do emitente e o do destinatário, em produção desde 01/07/2026;
  - os municípios e as UFs vêm do motor RR (código do IBGE), e as atividades do motor SN.
- **CNPJ:** um padrão só, `^[0-9A-Z]{12}[0-9]{2}$`, e o dígito pelo cálculo do Serpro (o exemplo do manual, 12ABC34501DE35, é teste).
- **Migração 0003:**
  - achado: reconstruir `empresas` com as chaves estrangeiras ligadas apagava itens e notas em cascata;
  - o `migrar` passou a seguir o procedimento da documentação do SQLite.
- **Referências:** `GET /referencias/ufs`, `/municipios?uf=` e `/atividades`.
  - Sobram 01 e 02 (anexo I) e 03 e 04 (anexo II): admissíveis na NF-e, com anexo e sem fator R.
  - O "EX" (exterior) sai da lista.
- **Empresa:**
  - `POST /empresas` (dono), `GET` e `PATCH /empresas/{cnpj}`;
  - as premissas do DAS da própria empresa (P8) e a volta à simulação;
  - na empresa da conta, o aviso de simulação no lugar do de dados fictícios.
- **Catálogo:**
  - `POST /catalogo/itens`, `PATCH /catalogo/{item_id}` e `POST /catalogo/{item_id}/arquivar`;
  - itens com Imposto Seletivo ficam para depois, porque não há fonte oficial consultável para a classificação do IS e os litros.
- **Segurança:**
  - o limite de corpo e o limite por IP passaram a valer para o PATCH;
  - o guarda de SQL pegou uma f-string na linha seguinte ao `execute(`.
- **Saída da C3 no backend:** conferida no modo real com os motores oficiais. A conta nova cadastra a empresa, cria o item, importa as notas e vê o alerta, e a demonstração não muda.

**Para a C3a e a C3b:**
- o cliente da tela mandar o cookie da sessão para `/empresas` e `/referencias/`;
- as notas de exemplo saírem fora da demonstração;
- o formulário converter o CNPJ para maiúsculas.
- cadastrar o par de um item sem par a partir da nota (ficou do 3b), agora que o catálogo é editável.

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
