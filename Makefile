# Atalhos do ContaAI. No Windows sem make, rode os comandos da direita direto no terminal.

.PHONY: motores parar api golden gravar-golden notas mocks openapi test lint

motores:        ## sobe os dois motores oficiais (primeira vez demora: Maven + banco)
	docker compose up -d --build motor-rr motor-sn

parar:          ## derruba os containers
	docker compose down

api:            ## API em modo mock (Etapa 0), documentação em http://127.0.0.1:8000/docs
	cd backend && uv run uvicorn app.main:app --reload

golden:         ## testes de referência contra os motores em execução
	cd backend && uv run pytest -m golden

gravar-golden:  ## regrava as respostas de referência (só ao trocar a versão fixada de um motor)
	cd backend && uv run python scripts/gravar_golden.py

notas:          ## regera as NF-e fictícias de data/demo/notas (motor RR de pé)
	cd backend && uv run python scripts/gerar_notas_demo.py

mocks:          ## regera os mocks da API a partir dos motores (motores de pé)
	cd backend && uv run python scripts/gerar_mocks.py

openapi:        ## reexporta o contrato para docs/contrato/openapi.json
	cd backend && uv run python scripts/exportar_openapi.py

test:           ## testes do backend que não precisam dos motores (os mesmos do CI)
	cd backend && uv run pytest

lint:           ## lint e formatação do Python
	ruff check . && ruff format --check .
