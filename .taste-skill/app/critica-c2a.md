# Crítica da C2a (app-screens §2.7)

Página inicial, termos de uso, privacidade, a faixa da demonstração no Painel e a conta sem empresa, julgados pelas capturas em 1440, 768 e 390 px. Dados: modo real, motores RR 1.7.2 e SN 1.0.2, build no `vite preview`.

- **Inspetor:** `inspect.mjs --app` com 0 FAIL e 0 WARN em `/`, `/termos`, `/privacidade` e `/painel` (com a faixa), nas três larguras.
- **Conta sem empresa:** o inspetor abre um Chrome sem cookie, então ela foi vista pelas capturas do roteiro do DevTools Protocol (conta fictícia criada pela página, nas três larguras).
- **`lint.mjs --app frontend/src`:** 0 FAIL e os mesmos 5 WARN do 3a e do 3b (`mono` 4, a cara escolhida no inventário §3, e o "01" de um teste).
- **Leitura da página inicial:** é a porta de um app, e não um site de marketing. Segue as regras de telas de app (título até 32 px, cromo sem cor, um botão principal), no estilo já sorteado (achromatic-ledger).

## Rodada 1: o que estava errado

1. **O rodapé ficava no meio da janela** em páginas curtas, com uma faixa vazia embaixo (início e conta sem empresa em 1440 × 900). Agora a página ocupa a janela, e o rodapé fica no pé.
2. **O botão do estado vazio estava ilegível:** texto em tinta sobre o preto, porque a regra `.vazio a` vencia a cor do `.botao-principal`.
3. **O estado vazio parava em 720 px**, com o resto da linha vazio. Agora o quadro ocupa a coluna inteira, como os blocos das outras telas, e só o texto fica com a medida de leitura.

## As perguntas do §2.7, na última rodada

1. **A pergunta é respondida pelo maior bloco, lido primeiro?** Sim.
   - Início: o título (30 px) diz o que é. O primeiro botão é "Explorar a demonstração". Ao lado, o que cada tela responde.
   - Termos e privacidade: o título, a versão e o aviso de rascunho vêm antes do texto.
   - Conta sem empresa: o título da página e uma frase com o próximo passo, no lugar dos dados.
2. **Os blocos dividem as bordas?** Sim.
   - Início: 667 + 12 + 473 = 1152.
   - Termos e privacidade: 279 + 12 + 861 = 1152, e o texto fica em 720 px para a leitura.
   - Conta sem empresa: o quadro ocupa os 1152 px.
3. **A cor só no dado?** Sim. As páginas novas não têm dado com cor.
   - O único matiz é o âmbar do aviso de rascunho: a nota de "dado que não vale como final" (§11), uma vez por página.
   - A faixa da demonstração é um passo de tom (`#e5e5e5`), sem cor.
4. **Os números fecham?** As páginas novas não mostram valor calculado.
   - Os números dos termos (8 caracteres, 6 dígitos, 10 códigos, 5 e 100 tentativas, 30 s a 1 h, 30 min, 8 h, 5 min) vêm de `REGRAS_DA_CONTA`, conferida com o backend por teste.
5. **Zero é zero e ausente é traço?** Não se aplica.
6. **Legendas?** Não se aplica. A tabela dos cookies tem cabeçalho em 12 px cinza, sem faixa.
7. **No celular?**
   - A barra pública cabe em 390 px (marca e um link).
   - No app, o nome da organização vai para a folha do menu.
   - Os botões principais ocupam a largura, com 44 px.
   - O índice dos termos vai para cima do texto.

## O que ainda fica aquém

- **A página inicial não mostra nada que só o ContaAI tem.** Um recorte vivo da demonstração (o alerta da nota 2, vindo da API) daria essa cara. Fica para depois, porque pediria dados na página pública.
- **Entrar e Criar conta faltam na página inicial** até a C2b.
- **Os termos e a privacidade são texto corrido longo** (1,9 e 2,3 telas em 1440 px). O índice ajuda, mas não há resumo no topo.
