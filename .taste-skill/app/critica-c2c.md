# Crítica da C2c (app-screens §2.7)

As notas de exemplo na tela de Notas, julgadas pelas capturas em 1440, 768 e 390 px. Dados: modo real, motores RR 1.7.2 e SN 1.0.2, build no `vite preview` com a CSP do cabeçalho (2026-11-27).

- **Inspetor:** `inspect.mjs --app` em `/notas` com 0 FAIL e 0 WARN nas três larguras (capturas em `.taste-skill/inspect/c2c-notas`).
- **`lint.mjs --app frontend/src`:** 0 FAIL e os 6 WARN de antes (`mono` 4, o "01" de um teste e o `padStart` da contagem).

## O que mudou na tela

- No bloco "Importar nota de compra", abaixo do campo, a seção "Notas de exemplo para baixar (fictícias)" com os três arquivos. Cada linha tem o nome do arquivo (o link) e o que a nota mostra, numa frase. Em 390 px, a frase fica embaixo do nome.
- A ordem é a de interesse: a nota que gera o alerta, a dos itens sem par e a que já está na demonstração.
- O link tem 24 px de alvo (WCAG 2.2, 2.5.8), sem depender da exceção de espaçamento.

## Perguntas

1. **A pessoa acha o que fazer?** Na demonstração compartilhada, o botão "Importar nota" fica desligado e diz "Para gravar, crie seu espaço no alto da tela". Os links logo abaixo continuam ativos: dá para baixar antes de criar o espaço.
2. **O texto é curto?** Três frases de uma linha em 1440 px. O inspetor conta 197 palavras na página inteira, com a barra, o rodapé e a tabela das notas importadas. Não dá para comparar com as 82 da C2b, que contaram só o conteúdo, por outro método.
3. **Cor:** nenhuma cor nova. O link usa a cor do texto, e a frase usa `--texto-suave`, que já tem contraste conferido.

## O que ainda fica aquém

- **As notas de exemplo são da Serra Azul.** Na empresa própria (C3), a API recusa a nota de outro destinatário (422). Na C3, falta decidir se a seção some fora da demonstração e do espaço.
