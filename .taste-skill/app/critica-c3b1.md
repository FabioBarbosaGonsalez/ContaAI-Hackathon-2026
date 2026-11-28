# Crítica da C3b, etapas 3 a 5 (app-screens §2.7)

As configurações da empresa (`/empresa`), a exclusão da empresa, "Baixar os seus dados" em Sua conta e o caminho às configurações (o menu da conta e o Painel), julgados pelas capturas em 1440, 768 e 390 px. Dados: modo real, motores RR 1.7.2 e SN 1.0.2, build no `vite preview` com a CSP, conta e empresa fictícias (2026-11-28).

- **Inspetor:** `inspect.mjs --app` com 0 FAIL e 0 WARN em `/painel` e `/privacidade`. Em `/empresa` e `/conta` sem conta, 1 WARN cada (`hero-void`): o aviso curto centrado ("Entre para..."), o mesmo de `/empresa/nova` na C3a e de `/conta` na C2b.
- **As telas da conta:** o inspetor abre um Chrome sem cookie e não as vê. Elas foram julgadas pelas capturas do roteiro do DevTools Protocol, nas três larguras, com a conta e a empresa criadas pela própria página. O roteiro também conferiu que não há violação da CSP, nem rolagem lateral, nem nada no armazenamento do navegador, e que o arquivo baixado tem o nome e o conteúdo da API.
- **`lint.mjs --app frontend/src`:** 0 FAIL e os 6 WARN de antes. Os "01" e "03" novos dos testes são o código oficial da atividade (`cAtivSN`), marcados com o motivo.

## O que mudou na tela

- **Configurações da empresa:** os formulários na coluna da esquerda, como no cadastro: os dados da empresa (com um botão "Salvar os dados"), as alíquotas do DAS (com "Salvar as alíquotas") e, por último, a exclusão. À direita fica "O que muda nos cálculos". Um "Salvar" por bloco, no pé dele (§8.2, um modelo de gravação por tela).
- **A gravação:** "Configurações salvas." no selo positivo, no alto, e os campos passam a mostrar a resposta da API.
- **A exclusão:** a última seção, com a consequência em palavras e o aviso de guardar as notas. A confirmação pede o CNPJ da empresa e a senha (§8.2: a confirmação nomeia o objeto). O botão vermelho só aparece com o formulário aberto.
- **Sua conta:** "Baixar os seus dados" entre os avisos e a exclusão da conta, com o mesmo desenho de botão que abre um formulário curto.
- **O caminho:** "Configurações da empresa" no menu da conta (só com empresa) e abaixo do título do Painel (só na empresa da conta).

## Perguntas

1. **A pessoa acha o que fazer?** Os campos já vêm com os valores gravados. Salvar sem mudar nada diz "Nada mudou" e não chama a API. O erro de um campo some quando ele é corrigido.
2. **Os números conferem?** Na primeira rodada, a alíquota aparecia duas vezes com precisões diferentes ("1,1612" no campo e "Hoje: 1,16%" embaixo). Agora ela aparece uma vez, no campo, e a visão do membro mostra o valor sem arredondar ("1,1612%").
3. **Cor:** nenhuma cor nova. Gravação no selo positivo, a simulação e o aviso das notas no selo de atenção, a exclusão no `--negativo` da exclusão da conta.

## Corrigido nas rodadas

- O link "Configurações da empresa" do Painel saía no azul do navegador. Agora usa o link dos cabeçalhos dos blocos.
- "Ir ao Painel" no pé das configurações repetia a barra e saía no azul do navegador. Foi tirado.
- A alíquota repetida e arredondada (acima).
- A fonte das alíquotas terminava em ".." quando o texto da API já tinha ponto (achado pelo teste).

## O que ainda fica aquém

- **O quadro da direita fica curto** perto dos formulários longos em 1440 px, como no cadastro da C3a. A atividade traz o texto oficial do motor, que é longo.
- **A carga atual** (`cargaAtualPct`) não tem campo: nenhuma tela a mostra, e um campo sem efeito confundiria.
