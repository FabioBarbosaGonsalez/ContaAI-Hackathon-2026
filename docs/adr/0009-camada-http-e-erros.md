# ADR 0009: camada HTTP em routers e erros no formato da RFC 9457

- Status: aceito
- Data: 2026-11-25
- Etapa: refactor entre a E4 e a E5 (B1, B2 e B3 da revisão estrutural da E4)
- Código: `backend/app/main.py` (montagem), `backend/app/api/` (dependências, middlewares, problemas e respostas) e `backend/app/api/rotas/`

## Contexto

A revisão estrutural no fim da E4 apontou três pontos. O usuário aprovou que fossem resolvidos antes da E5, porque o frontend vai consumir a API:

1. **B1.** O `app/main.py` tinha 659 linhas e misturava montagem, middlewares, tratadores de erro, dependências e as 16 rotas.
2. **B2.** As requisições herdavam de `_Operacao`. O sublinhado indica uso privado, mas o tipo era importado em quatro módulos.
3. **B3.** Os erros saíam em três formatos:
   - `{"detail": "..."}` nas rotas;
   - `FalhaMotorResposta` e `RecusaCalculo` nas falhas dos motores e nas recusas de cálculo;
   - a lista de validação do FastAPI, com `detail` como lista.

   O frontend teria de tratar cada um.

## Decisão

### B1: routers

- `app/main.py` só monta a aplicação: o ciclo de vida (migração e sementes), a ordem dos middlewares, os tratadores de erro, os routers e o OpenAPI ajustado.
- `app/api/dependencias.py` reúne a configuração, os clientes dos motores e dos dados abertos (com os caches por processo), o banco, o token da demo, `so_no_modo_real` e `marcar_mock`.
  - O repositório continua sendo criado só no ramo do modo real, para que nenhuma rota do modo mock crie o arquivo do banco.
- `app/api/middlewares.py` tem o tamanho do upload da NF-e, o limite por IP e os cabeçalhos de segurança. Os limitadores ficam neste módulo, e os testes os trocam aqui.
- `app/api/rotas/` tem um router por área:
  - `calculo`: carrinho, preço-alvo, presets e comparação;
  - `notas`: NF-e, alertas, catálogo e painel;
  - `classificacao`: busca de NCM;
  - `explicacao`: explicar e erros;
  - `agente`: chat;
  - `operacao`: saúde, restauração e tipos de problema.
- `app/api/respostas.py` guarda as respostas de erro declaradas no OpenAPI.
- Os caminhos, os parâmetros e os corpos de sucesso não mudaram.

### B2: `Operacao`

- `_Operacao` passou a se chamar `Operacao`. O tipo não aparece no OpenAPI (só as subclasses aparecem), então o contrato exportado não mudou por isso.

### B3: Problem Details (RFC 9457)

Regras conferidas no texto da RFC 9457 (rfc-editor.org/rfc/rfc9457, seções 3, 4 e 5) e seguidas aqui:

- Toda resposta 4xx/5xx sai com `Content-Type: application/problem+json`. Isso inclui:
  - os erros das rotas;
  - a validação de entrada;
  - 404 e 405 do roteador;
  - 411, 413 e 429 dos middlewares;
  - 500 de erro não tratado.
- O corpo tem `type`, `title`, `status` e `detail` (o modelo `Problema` no contrato).
  - `status` é sempre igual ao código HTTP. A RFC exige isso de quem gera a resposta.
  - Sem tipo próprio, vale `type: "about:blank"`, e `title` é a frase do código HTTP (ex.: `Not Found`, `Unauthorized`, `Too Many Requests`), como a RFC recomenda. A frase vem do `http.HTTPStatus` do Python. Por isso o 413 sai como `Request Entity Too Large`, o nome antigo do código.
- Tipos próprios, com caminho completo relativo à API (`/problemas/<nome>`, a forma relativa que a RFC aceita sem ambiguidade):

| Tipo | Status | Extensões |
|---|---|---|
| `entrada-invalida` | 422 | `campos`: origem (body, query, path, header, cookie), JSON Pointer do campo e mensagem |
| `calculo-recusado` | 422 | `erros` do motor (antes `RecusaCalculo`, agora `ProblemaCalculo`) |
| `motor-recusou` | 422 | `motor` e `erros` (antes `FalhaMotorResposta`, agora `ProblemaMotor`) |
| `motor-resposta-invalida` | 502 | `motor` |
| `motor-indisponivel` | 503 | `motor` |
| `nota-invalida` | 422 | |
| `nota-recusada` | 409, 422 | |
| `ia-indisponivel` | 503 | |
| `sementes-indisponiveis` | 503 | |

- A RFC pede que um tipo novo documente a URI, o título e o código HTTP. A RFC diz que uma URI `http(s)` dereferenciada deveria trazer documentação; por isso `GET /problemas/{nome}` devolve esses dados e o significado (`TipoProblema`). Um teste confere que todo tipo do catálogo tem essa descrição.
- Nomes das extensões: `campos`, `erros` e `motor` seguem a recomendação da RFC (letra inicial, só letras, dígitos e `_`, 3 ou mais caracteres). Quem consome deve ignorar extensão desconhecida.
- **Segurança** (RFC 9457, seção 5, sobre não expor detalhes de implementação):
  - O erro não tratado vai para o log do servidor. O cliente recebe só "Erro interno", sem pilha nem mensagem da exceção.
  - A validação devolve o local e a mensagem de cada campo, mas não o valor enviado (`input`) nem o contexto interno (`ctx`) do Pydantic.
  - As falhas dos motores e do provedor continuam sem URL, host ou corpo de terceiros.
- **OpenAPI:**
  - O `app.openapi` passa por `ajustar_openapi`. Toda resposta 4xx/5xx é documentada em `application/problem+json`, e todo 422 aceita `ProblemaValidacao` além do modelo da rota.
  - O `HTTPValidationError` do FastAPI sai do contrato.
  - O ajuste é idempotente, e um teste confere isso.

### Achado corrigido junto: CORS por dentro dos limites

O `CORSMiddleware` era o primeiro a ser adicionado e por isso ficava por dentro dos outros middlewares. As recusas dos middlewares (411, 413 e 429) saíam sem `Access-Control-Allow-Origin`. O frontend da E5, em outra origem, receberia um erro de rede em vez de "muitas requisições". A ordem agora é, de fora para dentro:

1. cabeçalhos de segurança;
2. CORS;
3. limite por IP;
4. tamanho da NF-e.

Um teste confere que o 429 sai com o cabeçalho CORS.

## Consequências

- **Mudança de contrato, feita antes de existir consumidor.** O frontend é a E5, e o agente usa as funções internas, não o HTTP.
  - `FalhaMotorResposta` virou `ProblemaMotor` e `RecusaCalculo` virou `ProblemaCalculo`, ambos com `type`, `title` e `status` a mais.
  - O erro de validação trocou a lista em `detail` por um texto em `detail` mais a lista `campos`.
  - `detail` continua sendo um texto em todos os erros, então quem já lia `detail` segue lendo.
- **O 500 continua sem os cabeçalhos de segurança e de CORS.** Ele é montado pelo `ServerErrorMiddleware` do Starlette, que fica por fora de todos. O corpo não traz nada interno, e o caso só acontece em erro não previsto.
- Os testes do CI passaram de 265 para 287 (`tests/test_problemas.py` e asserções de tipo nos testes de recusa). Os 50 golden passam contra os motores reais.

## Revisão na E5: mensagens de validação em português

**Contexto.** O `detail` do 422 e o `detalhe` de cada campo saíam com a mensagem do Pydantic, em inglês ("String should have at least 2 characters", "String should match pattern '^\d{8}$'"). A tela mostra os dois como texto (ADR 0012), e a pessoa que preenche não deveria ver nem inglês nem expressão regular.

**Decisão.**

- A frase nasce em `app/api/mensagens.py`, pelo `type` do erro e pelo `ctx` dele, nunca pelo texto em inglês. O `type` é a parte estável do erro do Pydantic (lista oficial em docs.pydantic.dev, "Validation Errors"); o texto muda entre versões.
- **A tabela cobre só os 30 tipos que as rotas geram.** O levantamento foi feito com uma sonda que manda entradas inválidas, geradas do próprio OpenAPI, a todas as rotas, nos modos mock e real (os dois deram os mesmos 30 tipos). A sonda virou teste (`tests/test_mensagens.py`).
  - A tabela é igual ao conjunto que a sonda vê, mais os casos gerados direto com o Pydantic. Tipo sem caso reprova o teste, e tipo que a sonda vê sem tradução também.
  - Tipo fora da tabela vira "Valor inválido." e fica no log (só o tipo, sem o valor enviado).
- **Cada padrão do contrato tem a sua frase** ("Use exatamente 8 dígitos, sem pontos nem traços."). Padrão novo sem frase reprova `test_todo_padrao_do_contrato_tem_frase`.
- **Regras do contrato** (`model_validator`) já falam português: sai só o texto da regra, sem o prefixo "Value error,". A única `value_error` que não nasce no ContaAI é a do FastAPI para um arquivo enviado como texto, que vira "Envie um arquivo.".
- **Números dos limites no jeito brasileiro:** "menor ou igual a 1.000.000.000".
- **O `detail`** diz o campo e a origem em português: "itens/0/ncm (corpo): Use exatamente 8 dígitos…", com "E mais N problema(s)." quando há outros. Em `campos`, a origem segue com o nome do contrato (`body`, `query`, `path`, `header`).
- **Achado corrigido junto:** no JSON quebrado, o FastAPI põe a posição do caractere no local do erro, e o ponteiro saía como `#/1`, como se fosse um campo. Agora é `#`.

**Consequências.**

- Nenhuma mudança de forma no contrato: `detail` e `detalhe` continuam texto, e o `openapi.json` não mudou. Muda só o idioma do texto.
- Nada do que a pessoa enviou volta na mensagem; a sonda confere isso em todas as respostas.
- Testes do CI: de 391 para 431. A sonda roda em cerca de 10 s, porque cada esquema de campo é sondado uma vez, mesmo quando aparece em várias rotas.
