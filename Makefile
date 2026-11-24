# Atalhos do ContaAI. No Windows sem make, rode os comandos da direita direto no terminal.

.PHONY: motores parar golden gravar-golden test lint

motores:        ## sobe os dois motores oficiais (primeira vez demora: Maven + banco)
	docker compose up -d --build motor-rr motor-sn

parar:          ## derruba os containers
	docker compose down

golden:         ## testes de referência contra os motores em execução
	cd backend && uv run pytest -m golden

gravar-golden:  ## regrava as respostas de referência (só ao trocar a versão fixada de um motor)
	cd backend && uv run python scripts/gravar_golden.py

test:           ## testes do backend que não precisam dos motores (os mesmos do CI)
	cd backend && uv run pytest

lint:           ## lint e formatação do Python
	ruff check . && ruff format --check .
