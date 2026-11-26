# ADR 0013: telas do Painel e do Catálogo (PR 3a)

- Status: aceito
- Data: 2026-11-26
- Etapa: E5 (PR 3a dos três em que o usuário dividiu as telas: 3a Painel, Catálogo e explicação lateral; 3b Regime e Notas; 3c Contador, chat e crítica final)
- Código: `frontend/src/dados/`, `frontend/src/telas/`, `frontend/src/shell/BarreiraDeErro.tsx`, `frontend/src/teste/fixtures/`, `.taste-skill/app/critica-3a.md`

## Contexto

A fundação (ADR 0012) deixou as páginas vazias. O 3a entrega as duas telas de uso mais frequente (inventário §2):
- o **Painel**, que responde "qual item está perdendo margem e o que eu faço?";
- o **Catálogo**, que responde "quanto de CBS/IBS cada item carrega e quanto sobra?";
- a **explicação lateral**, que responde "por que este item paga isso?".

Também estão aqui as duas gravações da tela que o ADR 0011 preparou: o preço e a classificação.

## Decisão

- **A tela só monta pedidos com o que a API devolveu.**
  - O carrinho de cada tela é o catálogo inteiro, um lote de `loteReferencia` por item, com a operação de `cenario.operacao`. Nenhuma alíquota, data ou premissa fica escrita na tela (P6).
  - A conta é a mesma do teste do backend `test_tela.py::entrada` (`frontend/src/dados/pedidos.ts`).
- **Um fato, uma variável.** A margem da cerveja na lista do Painel e a do alerta vêm do mesmo cálculo do backend e são iguais (11,19%). O achado do Catálogo soma os dois valores exibidos (R$ 32,40 + R$ 0,36 = R$ 32,76), nunca um valor sem arredondamento.
- **Estados em palavras do ofício.** REG-011 (motor RR) e VSN-047 (motor SN) viram "NCM não combina com a classificação". Os outros estados ganham frases curtas, e o código do motor fica ao lado.
- **Corrigir a classificação.**
  - As candidatas vêm de `GET /busca/ncm` para a NCM do item, na data do cenário. Para a carne: 200003 (Anexo I, 100%) e 000001.
  - A escolhida vai para `POST /catalogo/{id}/classificacao`. O backend aceita só uma candidata válida e tira o CST da fundamentação oficial (ADR 0011).
- **Quando a tela grava.**
  - Grava só no modo real, no espaço próprio ou com o token.
  - Fora disso, o botão fica desligado, legível (5,6:1), e diz por quê: "Para gravar, crie seu espaço no alto da tela"; no modo mock, "só leitura".
- **Empresa da tela.** Toda tela abre a Distribuidora Serra Azul ME (CNPJ fictício de `data/demo`). O seletor de empresa entra com o painel do contador, no 3c.
- **Barreira de erro por página.** Uma resposta num formato que a tela não espera quebra só a página: a barra, o menu e o rodapé continuam. O texto do erro não é mostrado.
  - **Achado:** sem a barreira, a tela inteira sumia. Os testes antigos do shell mostraram isso, porque respondem a toda rota com o JSON da saúde.
- **Dados que mudam com a origem.** A chave de todo dado leva o espaço (ou a demonstração compartilhada). Trocar de espaço cancela o pedido antigo e descarta a resposta dele, e uma recarga mantém os valores na tela até os novos chegarem (app-screens §11).
- **A explicação mostra só o que a API manda.**
  - **Achado:** a primeira versão anexava "da LC 214/2025" ao texto curto da fundamentação, que já traz a referência ("Art. 125" ou "LC 214/2025"), e na cerveja saía "LC 214/2025 da LC 214/2025". A tela não acrescenta nada ao texto da lei.
- **Barra preta com o texto em branco e o símbolo na marca (pedido do usuário, 2026-11-26).**
  - O usuário quer a tela alternando preto e branco: a barra do topo fica em `#000`, com os destinos em `#b4b4b4` (10,6:1), o atual em branco com um traço embaixo, e o foco do teclado em branco.
  - A marca ganha o símbolo do favicon (quadrado preto com o "C" branco) à esquerda do nome. Na barra, o quadrado leva um contorno branco fino para não sumir no preto.
  - É uma troca consciente da folha do estilo, que põe a barra no fundo da página, e do capítulo de telas da skill, que desaconselha "quadrado preto com uma letra" como marca. Vale a preferência do usuário pela identidade do produto. O inspetor segue em 0 FAIL e 0 WARN.
- **Testes com respostas reais.** `src/teste/fixtures/` guarda respostas da API no modo real (motores RR 1.7.2 e SN 1.0.2, com a nota 2 da demonstração importada). São só dados fictícios.

## Verificação

- **Portão da skill:** `inspect.mjs --app` com 0 FAIL e 0 WARN no Painel e no Catálogo, em 1440, 768 e 390 px, depois de 3 e 2 rodadas. A crítica está em `.taste-skill/app/critica-3a.md`.
- **Lint da skill:** 0 FAIL e 6 WARN (`mono` do estilo, a sombra do diálogo e um "01" de teste).
- **Frontend:** 214 testes (eram 191), tsc, ESLint, build e `npm run seguranca`.
- **Chrome com o build publicado (CSP com Trusted Types):** 0 violações no carregamento, na explicação, na troca de regime e nas chamadas à API.
- **Ao vivo no modo real, num espaço próprio:** a carne corrigida para 200003 volta a calcular (margem de 21,13% no tradicional), e o Painel deixa de mostrar a pendência.
- **Achado do ambiente:** no Git Bash desta máquina, o Vitest falha antes de rodar qualquer teste ("Cannot read properties of undefined (reading 'config')"), até nos testes antigos. No PowerShell e no CI, roda normalmente. Não é do projeto.

## Consequências

- Painel e Catálogo funcionam nos modos mock e real. Regime e Notas seguem como páginas provisórias até o 3b, e Contador até o 3c.
- O contrato do backend não mudou.

### Em aberto

- Na demonstração compartilhada sem token, "Aplicar" fica desligado de propósito (ADR 0010). Para a demo ao vivo, vale criar o espaço antes.
