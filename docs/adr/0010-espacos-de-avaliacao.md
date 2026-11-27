# ADR 0010: espaço de avaliação por visitante

- Status: aceito
- Data: 2026-11-25
- Etapa: entre a E4 e a E5 (D2, a "opção 2" da decisão 1 do ADR 0008)
- Código: `backend/app/persistencia/espacos.py`, `backend/app/api/rotas/espacos.py`, `backend/app/api/dependencias.py` (`abrir_estado`) e as rotas de notas, de restauração e do chat

## Contexto

Na E4, o estado da demonstração ficou num SQLite só, global por CNPJ, com o token da demo nas rotas que mudam o estado e a restauração das sementes (ADR 0008). O próprio ADR deixou um ponto aberto: se a URL pública for aberta a qualquer pessoa, vários avaliadores ao mesmo tempo mexem nos mesmos dados.

O usuário lembrou que **a banca precisa conseguir acessar e testar tudo**. Com o estado compartilhado, um avaliador que importa a nota 2 muda o que o outro vê, e quem não tem o token não consegue importar nem aplicar nada.

Decisões do usuário em 2026-11-25 (todas as recomendações aceitas):

1. **Um SQLite por espaço**, escolhido pelo header `X-ContaAI-Espaco`, com validade e teto.
2. **Dentro do próprio espaço, as rotas que mudam o estado dispensam o token da demo.** O espaço é isolado e expira.
3. **O PR vem antes da E5**, porque muda o contrato que o frontend vai consumir.

## Decisão

### Como um espaço nasce

- **`POST /espacos`** (201) devolve `id`, `criadoEm`, `expiraEm` e um aviso.
  - O id é sorteado pelo servidor com `secrets.token_hex(16)` (128 bits) e funciona como a chave do espaço: quem não o tem não chega aos dados.
- **Banco-modelo.** As sementes de `data/demo` são importadas uma vez por processo num `modelo.db`, pelo mesmo código da restauração (com os motores). Cada espaço novo é uma cópia do modelo pela API de backup do SQLite (`Banco.copiar_para`, a mesma da restauração atômica da E4).
  - Criar um espaço **não chama os motores**.
  - Como o modelo é remontado a cada processo, ele sempre segue as migrações e as sementes da versão em execução.
- **Medido com os motores reais em 2026-11-25:**
  - o primeiro espaço do processo levou 0,28 s, porque monta o modelo; os seguintes, 0,04 s;
  - cada espaço ocupa cerca de 120 KB, então o teto padrão dá uns 6 MB;
  - a nota 2 importada num espaço gerou o mesmo alerta da demo (cerveja de 24,12% para 11,19%, sugerido R$ 3,97), sem mudar a demonstração compartilhada.

### Como um espaço é usado

- **O header `X-ContaAI-Espaco`** vale nas rotas de notas (`/nfe/importar`, `/alertas`, `/alertas/{id}/aplicar`, `/catalogo`, `/contador/painel`), em `/demo/restaurar` e no `/chat`, cujas ferramentas leem os alertas do espaço. Sem o header, vale a demonstração compartilhada, como na E4.
- **`abrir_estado`**, em `app/api/dependencias.py`, é o único ponto que decide onde a requisição lê e grava. As rotas chamam esse ponto só no ramo do modo real, para que o modo mock não crie arquivo de banco.
- **Token:**
  - no próprio espaço, importar, aplicar e restaurar não pedem o token;
  - na demonstração compartilhada, nada mudou;
  - **o `/chat` continua exigindo o token mesmo dentro do espaço**, porque esse token protege o crédito do provedor de IA, não o estado.
- **`POST /demo/restaurar` com o header** restaura só aquele espaço, pela cópia do modelo, sem chamar os motores se o modelo já estiver montado.
- **`GET /espacos/atual`** devolve a validade do espaço do header, para a tela mostrar quanto tempo falta.
- **Modo mock:** `POST /espacos` e `GET /espacos/atual` respondem 501, como as outras rotas que mudam o estado.

### Validade, teto e limpeza

- **Validade fixa de 120 minutos desde a criação** (`CONTAAI_ESPACO_VALIDADE_MIN`). Não se renova com o uso, para que o disco tenha limite certo.
- **Teto de 50 espaços válidos ao mesmo tempo** (`CONTAAI_ESPACOS_MAX`). Acima disso, a resposta é 503 `/problemas/espacos-esgotados`, com `Retry-After` igual aos segundos até o mais antigo vencer.
- **Limpeza sem processo em segundo plano:**
  - ao criar um espaço, os vencidos saem do registro e seus arquivos são apagados;
  - ao abrir um espaço vencido, ele é apagado e a resposta é 404 `/problemas/espaco-inexistente`.

  Um id desconhecido e um vencido dão a mesma resposta.
- **Registro:** um SQLite próprio (`registro.db`), com id, criação e validade, e a contagem e a criação numa transação `BEGIN IMMEDIATE`. Fica na pasta `espacos/`, ao lado do banco principal (`CONTAAI_BANCO_CAMINHO`).

### Segurança

- **O id vai num header, não na URL.** O log de acesso padrão do uvicorn registra a linha da requisição (método e caminho), não os headers. Desde a etapa 7 da C3-B, o log de acesso é o nosso, com a rota-modelo e sem o IP, e também não lê headers ([ADR 0017](0017-empresa-propria.md)).
- **O id só vira nome de arquivo depois de conferido pelo padrão `^[0-9a-f]{32}$`.** Fora do padrão, o header dá 422 (validação do contrato), e o gerenciador recusa de novo antes de montar qualquer caminho. Testado com `../`, maiúsculas, tamanho errado e quebra de linha.
- **Abuso:**
  - `POST /espacos` tem limite próprio por IP (`CONTAAI_LIMITE_ESPACOS_POR_MINUTO`, 5) além do limite geral;
  - o teto limita o disco, e a validade limita o tempo de ocupação.
- **CORS:** passa a liberar o header `X-ContaAI-Espaco`.

## Consequências

- **Contrato, só com acréscimos:**
  - modelo `EspacoResposta`;
  - rotas `POST /espacos` e `GET /espacos/atual`;
  - header opcional `X-ContaAI-Espaco` nas rotas de estado e no chat;
  - tipos de problema `espaco-inexistente` (404) e `espacos-esgotados` (503).

  `docs/contrato/openapi.json` foi reexportado.
- **`RestaurarResposta.notasImportadas`** passou a ser lida do banco restaurado (`Sessao.numeros_das_notas`), igual nos dois caminhos. Logo depois da restauração, são as mesmas notas iniciais.
- **Testes:** `tests/test_espacos.py` (21 testes) cobre isolamento, token, modelo montado uma vez, restauração sem motor, validade, teto, limpeza, padrão do id, limite por IP, modo mock e CORS. São 317 testes no CI, 50 golden e cobertura de 96% no `app/`.

### Em aberto

- **Esgotar os espaços.** Criar não pede token, para a banca testar sem combinar nada. Quem fizer muitos pedidos de IPs diferentes ocupa o teto até os espaços vencerem; a demonstração compartilhada segue funcionando. Se isso acontecer na demo pública, as saídas são subir o teto, exigir o token também para criar, ou limitar por IP com o IP real do proxy (E6).
- **Atrás de proxy** (E6), o limite por IP vira global até o backend ler `X-Forwarded-For` só de um proxy nosso (pendência do ADR 0006).
- **Vários processos** (mais de um worker do uvicorn): cada um monta o próprio modelo. A cópia é atômica e o registro é transacional, então eles não se atrapalham. A conta de 0,28 s acontece uma vez por processo.
- **Sementes alteradas com o processo no ar** só entram no modelo na próxima subida.
- **O `criadoEm` dos alertas** de um espaço é a hora em que o modelo foi montado, não a hora da criação do espaço. É a hora real da importação das notas iniciais, como no ADR 0008.
