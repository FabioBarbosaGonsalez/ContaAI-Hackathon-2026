# ADR 0016: telas de entrada, a conta na tela e a demonstração para quem tem conta (C2)

- Status: aceito para a C2a; a C2b (criar conta, entrar e o menu da conta) e a C2c (notas de exemplo e a verificação final) completam este ADR
- Data: 2026-11-26
- Etapa: C2 do [plano v2.1](../plano-v2.1.md), dividida em três PRs pelo usuário
- Código da C2a:
  - `frontend/src/sessao/conta.ts` (`SessaoConta`), `middleware.ts`, `acoes.ts` (`carregarSessao`), `instancias.ts`;
  - `frontend/src/api/rotas.ts` (`ROTAS_DA_CONTA`, `ROTAS_DE_ENTRADA`, `DELETE` no `ChaveRota`);
  - `frontend/src/dados/empresa.ts` (`useOrigemDosDados`, `useGravacao`);
  - `frontend/src/shell/` (`rotas.ts`, `Shell.tsx`, `demonstracao.tsx`, `paginas.tsx`, `StatusSessao.tsx`, `Rodape.tsx`, `navegacao.tsx` com a `Ancora`);
  - `frontend/src/telas/` (`Inicio.tsx`, `Termos.tsx`, `Privacidade.tsx`, `TextoLegal.tsx`, `legal.ts`, `publicas.css`).

## Contexto

A C1 ([ADR 0015](0015-contas.md)) criou as contas no backend: a sessão é um cookie `HttpOnly`, e a API abre o banco da organização quando o pedido traz o cookie e nenhum espaço. A tela ainda não sabia que havia conta. O mapeamento da C2 achou:

1. **Com o cookie e sem espaço, a API abre o banco da organização**, vazio até a C3. A tela pediria o CNPJ fixo da demonstração e receberia 404.
2. **Uma sessão vencida responde 401 em qualquer rota.** O middleware da tela só tratava o 401 de um pedido com o token da demo.
3. **No modo mock, as rotas de conta respondem 501.**
4. **O `ChaveRota` só aceitava GET e POST**, mas sair usa DELETE.
5. **`/` era o Painel.**

Decisões do usuário (plano v2.1, C2): a página inicial em `/` e o Painel em `/painel`; quem tem conta vê a demonstração compartilhada como todo mundo, com os pedidos de dados sem o cookie; quem responde pelos dados é "Equipe ContaAI", sem e-mail; a C2 em três PRs.

## Fontes lidas (2026-11-26)

| Fonte | O que foi usado |
|---|---|
| LGPD (Lei nº 13.709/2018), planalto.gov.br | Art. 5º (dado pessoal, controlador, encarregado, tratamento); art. 7º, V (execução de contrato a pedido do titular), a base citada na privacidade; art. 9º (o que informar, inclusive a identificação e o contato do controlador, incisos III e IV); art. 18 (direitos); art. 41, § 1º (identidade e contato do encarregado divulgados publicamente) |
| ANPD, "Guia orientativo: cookies e proteção de dados pessoais", out/2022 (PDF no gov.br, lido em texto) | p. 10: cookies necessários; p. 20: o consentimento não é a base apropriada para os estritamente necessários; p. 24: o legítimo interesse pode ser; p. 28-29: a política de cookies pode ser uma seção da política de privacidade, com finalidade, retenção e compartilhamento |
| `backend/app/contas/` e `backend/app/api/dependencias.py` | As regras que os termos citam (senha, código, espera, bloqueio, sessão, passe, cadastro pendente) e os nomes dos cookies |

## Decisão

### 1. Rotas públicas e rotas do app

- **Públicas:** `/` (início), `/termos` e `/privacidade`. Têm uma barra própria, com a marca e "Explorar a demonstração" (ou "Minha conta"), sem os destinos do app e sem a faixa. Não pedem dados da empresa.
- **Do app:** `/painel`, `/catalogo`, `/regime`, `/notas` e `/contador`. A barra mostra só estas.
- `/entrar` e `/criar-conta` entram na C2b. Até lá, nenhuma tela leva a uma página que ainda não existe.
- O `ChaveRota` aceita `DELETE`.

### 2. A conta na tela (`SessaoConta`)

- Estados: `desligada` (mock), `carregando`, `anonima`, `conectada` (com `naDemo`), `encerrada` e `erro`.
- **A tela só sabe da conta pelo `GET /conta`**, pedido ao abrir e só no modo real. Nada da conta vai ao armazenamento do navegador nem ao endereço (testado).
- **A conta fica "carregando" desde antes do `/saude`** (`aguardar`), e nenhum dado é pedido até a tela saber se há conta. O teste da tela achou o defeito: no intervalo entre o `/saude` e o `/conta`, o Painel já pedia o catálogo.
- `erro` (rede ou 5xx no `/conta`) segue como quem não tem conta, com "Tentar de novo" na faixa.

### 3. O cookie só vai aonde precisa (middleware da sessão)

| Pedido | Na conta | Fora da conta (sem conta, ou com a conta vendo a demonstração) |
|---|---|---|
| Rotas da conta (tag `contas` do contrato) | cookie | cookie |
| Rotas de dados | cookie, sem espaço e sem token | `credentials: 'omit'`, com o espaço e o token como antes |

- Na conta, o id do espaço não vai: para a API, o espaço do header vence o cookie.
- **401 com o cookie, sem token e fora das rotas de entrada** (`POST /contas/ativar`, `/sessoes`, `/sessoes/codigo` e `/conta/excluir`, onde o 401 quer dizer senha ou código errado): a sessão acabou, e a faixa diz "Sua sessão terminou, e você voltou à demonstração".
- As listas `ROTAS_DA_CONTA` e `ROTAS_DE_ENTRADA` são conferidas com o contrato (`rotas.test.ts`).
- **Conferido no Chrome** (build no `vite preview`, API real): o cookie é `__Host-`, `HttpOnly`, `Secure`, `SameSite=Strict` e `Path=/`, e o `document.cookie` não o mostra; a conta sem empresa não pede dados da empresa em 1440, 768 e 390 px; na demonstração, os pedidos de dados saem sem o cookie; o `POST /espacos` sem cookie passa pela conferência de CSRF e cria o espaço; depois de sair em todos os aparelhos, a página volta à demonstração; nenhum erro no console.

### 4. A conta sem empresa

Na conta, as páginas do app dão lugar a um estado vazio com o título da página: "A sua organização ainda não tem empresa cadastrada, e o cadastro da empresa ainda não está disponível", com o botão "Explorar a demonstração". A origem dos dados é `null` na conta: nenhum pedido com o CNPJ da demonstração vai ao banco da organização. A C3 troca este estado pelo cadastro.

### 5. Página inicial

- O que é o ContaAI (as palavras do README), a frase de simulação (P6) e "Explorar a demonstração" como primeiro botão, sem cadastro.
- Ao lado, o que cada tela da demonstração responde (as perguntas do inventário da skill) e como gravar (espaço próprio, ou só leitura no mock).
- Nenhum número da demonstração fica escrito na página.

### 6. Termos de uso e privacidade

- **Rascunho marcado "sem revisão jurídica"** no alto de cada página.
- **Cada regra citada vem do código.** `REGRAS_DA_CONTA` e `COOKIES` (`telas/legal.ts`) são conferidos com o backend por `legal.test.ts`, que lê os arquivos Python. A versão dos termos é o tipo gerado do contrato (o enum de `termosAceitos`) e também é conferida com `termos.py`.
- **Privacidade:** o que fica guardado (das migrações do `contas.db`), a base legal (art. 7º, V), os dois cookies em tabela, com finalidade e duração, e a razão de não pedir consentimento (guia da ANPD), o id do espaço no `localStorage`, os registros técnicos (o IP fica só na memória do limitador e no log do servidor, nunca no banco), o compartilhamento (nenhum), os prazos e os direitos.
- **Quem responde: "Equipe ContaAI"**, sem e-mail e sem nome (decisão 4).
- O índice de cada página sai da mesma lista das seções. As âncoras usam a `Ancora` de `shell/navegacao.tsx`, que só monta `#id` com um id em minúsculas e hífen. A regra do lint (item 2) continua valendo fora desse arquivo.

## Consequências

- **Risco confirmado na leitura da lei:** o art. 9º, III e IV, e o art. 41, § 1º, pedem o contato do controlador e do encarregado. A página mostra só "Equipe ContaAI", por decisão do usuário. Fica registrado no plano para rever antes da E6.
- **A privacidade cita o menu da conta** (ver os dados e excluir a conta), que entra na C2b. A C2a não tem caminho na tela para criar conta, então ninguém chega a uma conta pela tela antes da C2b.
- **Ficam para a E6:**
  - o prazo de guarda do log do servidor;
  - o provedor de hospedagem, que seria um operador (art. 5º, VII) e mudaria a seção de compartilhamento;
  - as cópias de segurança, que mudariam o "apaga na hora" da exclusão.
- **Fica para o 3c:** o chat com um provedor de IA real manda o texto da conversa a terceiros, e a privacidade precisa dizer isso antes.
- **Testes:** 293 na tela (eram 265), com o estado da conta, o cookie por rota, o 401 da sessão, as páginas públicas, o índice e as regras conferidas com o backend. Também foi corrigida uma corrida antiga no teste do tempo limite (`cliente.test.ts`): com a máquina carregada, o sinal já chegava abortado.
- **Portão da skill:** `inspect.mjs --app` com 0 FAIL e 0 WARN no início, nos termos, na privacidade e no Painel com a faixa, em 1440, 768 e 390 px; a crítica está em `.taste-skill/app/critica-c2a.md`.
