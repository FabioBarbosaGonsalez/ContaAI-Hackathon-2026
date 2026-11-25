# Backend do ContaAI

FastAPI que orquestra os motores oficiais da Receita. Instruções no README da raiz.

| Pasta | O que tem |
|---|---|
| `app/contrato.py` | Contrato da API (fonte do `docs/contrato/openapi.json`) |
| `app/motores/` | Modelos das respostas, cliente tipado (httpx) e montagem das requisições aos motores |
| `app/precificacao/` | Carrinho real e preço-alvo (ajuste afim + bisseção) |
| `app/regime/` | Comparação Simples tradicional × híbrido (E3) |
| `app/nfe/` | Leitor seguro da NF-e, importação (casamento, crédito, histórico e alertas) e consultas do estado (E4) |
| `app/persistencia/` | SQLite: migrações versionadas (`migracoes/`), repositório e sementes de `data/demo` (E4, ADR 0008) |
| `app/empresa.py` | Operação de cálculo de uma empresa cadastrada (data, local e premissas do cenário dela) |
| `app/cenarios/` | Premissas, aviso de simulação e presets de 2027 com fonte |
| `app/agente/` | Agente: formato interno, tomada do provedor de IA, provedor `roteiro`, ferramentas, loop e verificador |
| `app/classificacao/` | Índice de NCM (gerado por `scripts/gerar_indice_ncm.py`) e candidatos de classificação |
| `app/motores/dados_abertos.py` | Consultas GET aos dados abertos e ao catálogo de erros dos motores |
| `app/explicacao.py` | Memória de cálculo, fundamentação e premissas de um item |
| `app/seguranca.py` | Limite de requisições por IP e token da demo |
| `app/mocks/` | Mocks do modo mock, gerados por `scripts/gerar_mocks.py` a partir dos motores |
| `tests/conftest.py` | Motores e dados abertos falsos para o CI (valores fictícios, só para testar a orquestração) |
