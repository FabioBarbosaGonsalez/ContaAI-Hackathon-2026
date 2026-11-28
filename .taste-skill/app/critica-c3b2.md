# Crítica da C3b, etapas 6 a 9 (app-screens §2.7)

Cadastrar, alterar e arquivar o item no Catálogo, "Cadastrar este item" e "Ver o recibo" em Notas e a página nova `/clientes`, julgados pelas capturas em 1440, 768 e 390 px. Dados: modo real, motores RR 1.7.2 e SN 1.0.2, build no `vite preview` com a CSP, conta e empresa fictícias criadas pela própria página (2026-11-28).

- **Inspetor:** `inspect.mjs --app` com 0 FAIL e 0 WARN em `/catalogo`, `/notas` e `/regime` (na demonstração). Em `/clientes`, 1 WARN (`hero-void`): a demonstração tem um cliente, e a tabela termina cedo. A tela fica do tamanho dos dados que a conta tem (app-screens §10), como os avisos iguais das telas curtas da C3b1.
- **As telas da conta e os diálogos:** o inspetor abre um Chrome sem cookie. Eles foram julgados pelas capturas do roteiro do DevTools Protocol, nas três larguras. O roteiro faz o caminho de saída da C3: a conta cadastra a empresa e os itens (um pelo Catálogo, outro a partir da nota 1001), importa a nota 1002 do mesmo fornecedor e vê o alerta. Também cadastra o cliente, recebe o 409 do item em uso e abre o recibo pela lista. Sem violação da CSP, sem exceção, sem rolagem lateral, nada no armazenamento do navegador, e a demonstração sem mudança.
- **`lint.mjs --app frontend/src`:** 0 FAIL e os 6 WARN de antes.

## O que mudou na tela

- **Catálogo:** "Cadastrar item" ao lado do seletor de regime; no catálogo vazio, "Cadastrar o primeiro item" dentro da caixa vazia, onde os itens vão aparecer (§11, primeira vez). Em cada linha, "Alterar" ao lado de "Explicar" e "Preço".
- **O diálogo do item:** os campos um abaixo do outro, com o rótulo em cima (§8.1). A NCM vem da busca nos dados abertos, pelo código ou pelo nome; a classificação é escolhida entre as válidas, com a redução e a fonte à vista. A NCM com Imposto Seletivo aparece fora da escolha, no selo de atenção, com o motivo.
- **Alterar e arquivar:** um "Salvar" no pé do formulário (§8.2, um modelo de gravação). Arquivar fica por último, numa seção própria, com a consequência em palavras, o aviso de que não tem volta e a confirmação que nomeia o item (§8.2). O 409 diz de quais clientes e leva à página deles.
- **Notas:** cada linha sem par com a ação à direita: "Cadastrar este item", o motivo de não poder, ou "Cadastrado no catálogo". A lista das notas ganhou "Ver o recibo", e a nota aberta diz "Recibo aberto".
- **Clientes empresa:** uma tabela (cliente, local, itens por mês, a compra em palavras) e os diálogos de cadastrar, alterar e excluir. Fora da barra, com o caminho pelo Regime e pelo 409.

## Perguntas

1. **A pessoa acha o que fazer?** O catálogo vazio, o Painel da empresa sem itens e o Regime sem clientes levam ao cadastro. Um único botão filled por tela.
2. **Os números conferem?** O custo da linha sem par sai como a API manda (até 4 casas, sem arredondar). O achado do recibo lido depois do cadastro diz que um item nasceu com o custo daquela nota.
3. **Cor:** nenhuma cor nova. Gravação no selo positivo, o Imposto Seletivo e o "não tem volta" no selo de atenção, arquivar e excluir no `--negativo` da exclusão da conta.
4. **Celular:** os diálogos ocupam a largura com 16 px de margem e rolam por dentro; a tabela dos clientes vira linhas de rótulo e valor, como as outras.

## Corrigido nas rodadas

- Os botões "Cadastrar este item" esticavam até 280 px e eram a coisa mais pesada do recibo. Agora têm a largura do texto.
- Depois do cadastro a partir da nota, o achado do recibo dizia só "nenhum custo mudou". Agora diz também que um item foi cadastrado com o custo da nota.
- O catálogo vazio tinha o botão sozinho numa linha, longe da caixa vazia.
- No diálogo a partir da nota, a NCM aparecia duas vezes.
- No celular, "R$" e o valor do custo quebravam em linhas diferentes.
- O link "Ir aos clientes empresa" do 409 saía no azul do navegador (o mesmo achado da C3b1).
- O CNPJ do cliente saía alinhado à direita, embaixo do nome.
- Com só NCMs de Imposto Seletivo na busca, o erro do envio não aparecia em lugar nenhum (achado pelo teste).

## O que ainda fica aquém

- **`/clientes` com um cliente** deixa a parte de baixo da tela vazia em 1440 px (o WARN acima).
- **O diálogo do item é longo** quando a NCM tem várias classificações. Ele rola por dentro, com o botão no pé.
- **Os botões "Cadastrar este item"** são cinza (secundários). Numa nota com muitos itens sem par, a lista fica com muitos botões; uma ação em lote fica para depois.
