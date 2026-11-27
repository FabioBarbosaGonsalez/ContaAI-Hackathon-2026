# Crítica da C2b (app-screens §2.7)

Criar conta (3 passos), Entrar, o menu da conta e a página Sua conta, julgados pelas capturas em 1440 (ou 1280), 768 e 390 px. Dados: modo real, motores RR 1.7.2 e SN 1.0.2, build no `vite preview` com a CSP do cabeçalho (verificação final da C2b, 2026-11-27).

- **Inspetor:** `inspect.mjs --app` com 0 FAIL e 0 WARN em `/`, `/painel`, `/catalogo`, `/regime`, `/notas`, `/entrar`, `/criar-conta`, `/termos` e `/privacidade`, nas três larguras. Em `/conta`, 0 FAIL e 1 WARN (`hero-void`): o inspetor não leva cookie e mede o aviso curto de quem não entrou, centrado na altura, como o Entrar. O vazio simétrico é o descanso da tela.
- **A visão de quem entrou** (passos 2 e 3, o código novo, o menu, a folha do celular e Sua conta) foi vista pelas capturas dos roteiros do DevTools Protocol, nas mesmas larguras.
- **`lint.mjs --app frontend/src`:** 0 FAIL e 6 WARN: os 5 de antes (`mono` 4, o "01" de um teste) e o `padStart` dos segundos da contagem ("4 min 05 s"), que é um relógio.

## Rodada final: o que estava errado

1. **A barra pública rolava de lado em 390 px com um e-mail longo** (achado na verificação final): o botão do menu da conta não encolhia, e "Ir ao Painel" quebrava em duas linhas. Agora a barra encolhe, os links não quebram e o e-mail é cortado com reticências. A etapa 9 tinha conferido as larguras no app e com um e-mail curto; a barra pública só mostra o menu depois de entrar, no passo "Guarde o código novo".
2. **Medir as telas de dados com os motores fora do ar** dá FAIL de `blank-gap`: o esqueleto de carregamento conta como vazio. Com os motores de pé e as sementes restauradas, as quatro telas dão 0 e 0. Não é defeito da tela, mas o portão só vale com os dados no lugar.

## As perguntas do §2.7

1. **A pergunta é respondida pelo maior bloco, lido primeiro?** Sim. Em cada passo, o título do passo recebe o foco, e o bloco da esquerda é a tarefa (formulário, QR, códigos). O quadro da direita é só apoio ("Como a conta é protegida", "Sem acesso?", "Sessão").
2. **Os blocos dividem as bordas?** Sim. A tarefa e o quadro lateral dividem a coluna de 1152 px, e no celular o quadro vai para baixo da tarefa (em Sua conta, a exclusão fica por último também no celular).
3. **A cor só no dado?** Sim. O medidor de força usa vermelho, amarelo e verde com a palavra ao lado (a cor não é o único sinal), e o único botão vermelho é o de excluir a conta, depois da senha e da caixa de confirmação.
4. **Os números fecham?** As regras escritas na tela (8 caracteres, 6 dígitos, 10 códigos, 5 e 100 tentativas, 30 min, 8 h, 5 min) vêm de `REGRAS_DA_CONTA`, conferida com o backend por teste. A contagem do passe parte da chegada da resposta, com os 5 min do backend.
