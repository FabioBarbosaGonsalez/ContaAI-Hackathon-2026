# Crítica da C3a (app-screens §2.7)

A primeira vez, o cadastro da empresa e as telas da empresa nova (Painel, Catálogo, Regime e Notas sem itens), julgados pelas capturas em 1440, 768 e 390 px. Dados: modo real, motores RR 1.7.2 e SN 1.0.2, build no `vite preview` com a CSP do cabeçalho (2026-11-27).

- **Inspetor:** `inspect.mjs --app` com 0 FAIL em `/painel`, `/catalogo`, `/notas`, `/regime` e `/privacidade` (0 WARN) e em `/empresa/nova` sem conta (1 WARN, `hero-void`: o aviso curto centrado, o mesmo de `/conta` na C2b). Capturas em `.taste-skill/inspect/c3a-*`.
- **As telas da conta** (a primeira vez, o formulário e a empresa nova): o inspetor abre um Chrome sem cookie e não as vê. Elas foram julgadas pelas capturas do roteiro do DevTools Protocol, nas três larguras, sem rolagem lateral.
- **`lint.mjs --app frontend/src`:** 0 FAIL e os 6 WARN de antes. Os "01" novos dos testes são o código oficial da atividade (`cAtivSN`), marcados com o motivo.

## O que mudou na tela

- **A primeira vez:** no lugar dos dados, um quadro tracejado com o título "Cadastre a empresa para começar", uma frase do que o ContaAI faz e do que ele precisa, o botão preto "Cadastrar a empresa" e "Explorar a demonstração" ao lado.
- **O cadastro:** o formulário na coluna da esquerda (7 de 12) e, à direita, "O que o ContaAI faz com estes dados". Em 390 px, o quadro vai para baixo do botão.
  - O regime e a atividade são opções com a frase de cada uma à vista. A atividade traz o texto oficial do motor, que é longo.
  - A UF e o município são listas do navegador, com a fonte embaixo.
- **A empresa nova:** o Painel responde à pergunta da tela ("Nenhum item no catálogo ainda") na linha inteira. Embaixo ficam a empresa cadastrada e a última nota, lado a lado.

## Perguntas

1. **A pessoa acha o que fazer?** Na primeira vez, o único botão preto é "Cadastrar a empresa". No formulário, o envio vazio põe o foco no CNPJ e diz o que falta em cada campo. O erro some quando o campo é corrigido (antes, ficava vermelho até o próximo envio, visto nas capturas).
2. **O texto é curto?** A primeira vez tem duas frases. O formulário tem uma ajuda por campo. As fontes das listas ("Fonte: Dados abertos do motor RR 1.7.2...") são longas, mas seguem a regra do produto de imprimir a fonte junto do dado (P5).
3. **Cor:** nenhuma cor nova. O erro usa `--negativo`, o mesmo dos formulários da conta.

## O que ainda fica aquém

- **A empresa nova não tem como chegar ao alerta:** os itens e os clientes entram pela C3b. O Painel e o Catálogo dizem que o catálogo está vazio, sem prometer data.
- **Os nomes das UFs vêm em maiúsculas** dos dados abertos do motor ("RIO GRANDE DO SUL"). A tela os mostra como vêm, sem reescrever o dado.
- **A atividade 03 e a 04** (Zona Franca de Manaus) aparecem para qualquer UF, porque o motor as devolve assim. A tela não filtra: quem decide é a lista oficial.
