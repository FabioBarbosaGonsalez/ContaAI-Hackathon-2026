# Backend do ContaAI

FastAPI que orquestra os motores oficiais da Receita. Instruções no README da raiz.

| Pasta | O que tem |
|---|---|
| `app/contrato.py` | Contrato da API (fonte do `docs/contrato/openapi.json`) |
| `app/motores/` | Modelos das respostas, cliente tipado (httpx) e montagem das requisições aos motores |
| `app/precificacao/` | Carrinho real e preço-alvo (ajuste afim + bisseção) |
| `app/cenarios/` | Premissas, aviso de simulação e presets de 2027 com fonte |
| `app/mocks/` | Mocks do modo mock, gerados por `scripts/gerar_mocks.py` a partir dos motores |
| `tests/conftest.py` | Motores falsos para o CI (valores fictícios, só para testar a orquestração) |
