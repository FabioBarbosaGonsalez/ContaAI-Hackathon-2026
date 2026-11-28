# Backend do ContaAI

FastAPI que orquestra os motores oficiais da Receita. Instruções no README da raiz.

| Pasta | O que tem |
|---|---|
| `app/main.py` | Montagem da API: ciclo de vida, ordem dos middlewares, tratadores de erro e routers (ADR 0009) |
| `app/api/` | Camada HTTP: dependências, middlewares, erros RFC 9457 (`problemas.py`) e as rotas por área (`rotas/`) |
| `app/contrato.py` | Contrato da API (fonte do `docs/contrato/openapi.json`) |
| `app/motores/` | Modelos das respostas, cliente tipado (httpx) e montagem das requisições aos motores |
| `app/precificacao/` | Carrinho real, preço-alvo (ajuste afim + bisseção) e o lote de referência (`lote.py`, ADR 0011) |
| `app/regime/` | Comparação Simples tradicional × híbrido (E3) |
| `app/nfe/` | Leitor seguro da NF-e, importação (casamento, crédito, histórico e alertas) e consultas do estado (E4), com o preço e a classificação gravados pela tela (ADR 0011) |
| `app/persistencia/` | SQLite: migrações versionadas (`migracoes/`), repositório, sementes de `data/demo` (E4, ADR 0008) e espaços de avaliação (`espacos.py`, ADR 0010) |
| `app/api/registro.py` | Log de acesso sem dado pessoal (rota-modelo, sem o IP) e o erro não tratado sem a mensagem (ADR 0017, etapa 7) |
| `app/contas/` | Contas (C1, ADR 0015): senha, segundo fator (TOTP), sessão e organização, num banco próprio (`contas.db`), e o comando de desbloqueio |
| `app/cnpj.py` | CNPJ numérico e alfanumérico: formato e dígitos verificadores pelo cálculo do Serpro (ADR 0017) |
| `app/cadastro.py` | Empresa própria (ADR 0017): referências dos motores, cadastro, configurações, catálogo e clientes B2B editáveis, e o item a partir de uma linha sem par da nota (revisão da C3b) |
| `app/dados_da_conta.py` | O arquivo JSON dos dados da conta e das empresas, sem senha, segredo nem hash (LGPD, arts. 18 e 19; ADR 0017, etapa 7) |
| `app/empresa.py` | Operação de cálculo de uma empresa cadastrada (data, local e premissas do cenário dela) |
| `app/cenarios/` | Premissas, aviso de simulação e presets de 2027 com fonte |
| `app/agente/` | Agente: formato interno, tomada do provedor de IA, provedor `roteiro`, ferramentas, loop e verificador |
| `app/classificacao/` | Índice de NCM (gerado por `scripts/gerar_indice_ncm.py`) e candidatos de classificação |
| `app/motores/dados_abertos.py` | Consultas GET aos dados abertos e ao catálogo de erros dos motores |
| `app/explicacao.py` | Memória de cálculo, fundamentação e premissas de um item |
| `app/seguranca.py` | Limite de requisições por IP, token da demo e os métodos que mudam o estado (Host, Origin, tamanho do corpo e o erro 500 ficam em `app/api/middlewares.py`, ADR 0011 e ADR 0017) |
| `app/mocks/` | Mocks do modo mock, gerados por `scripts/gerar_mocks.py` a partir dos motores (o que cada rota faz no mock: `tests/test_modo_mock.py`) |
| `tests/conftest.py` | Motores e dados abertos falsos para o CI (valores fictícios, só para testar a orquestração) |
