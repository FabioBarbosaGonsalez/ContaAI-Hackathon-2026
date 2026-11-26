# Atalhos do ContaAI. No Windows sem make, rode os comandos da direita direto no terminal.

.PHONY: motores parar api real sementes golden llm gravar-golden notas mocks indice openapi test lint tipos cobertura auditoria tela tela-instalar tela-checar tela-contrato

motores:        ## sobe os dois motores oficiais (primeira vez demora: Maven + banco)
	docker compose up -d --build motor-rr motor-sn

parar:          ## derruba os containers
	docker compose down

api:            ## API em modo mock (Etapa 0), documentação em http://127.0.0.1:8000/docs
	cd backend && uv run uvicorn app.main:app --reload

real:           ## API no modo real (motores de pé); banco vazio recebe as sementes na subida
	cd backend && CONTAAI_MODO=real uv run uvicorn app.main:app --reload

sementes:       ## restaura o estado do modo real às sementes de data/demo (motores de pé)
	cd backend && uv run python -m app.persistencia.sementes

golden:         ## testes de referência contra os motores em execução
	cd backend && uv run pytest -m golden

llm:            ## as 20 perguntas com o provedor de IA do backend/.env (GASTA crédito do provedor)
	cd backend && uv run pytest -m llm

gravar-golden:  ## regrava as respostas de referência (só ao trocar a versão fixada de um motor)
	cd backend && uv run python scripts/gravar_golden.py

notas:          ## regera as NF-e fictícias de data/demo (motor RR de pé)
	cd backend && uv run python scripts/gerar_notas_demo.py

mocks:          ## regera os mocks da API a partir dos motores (motores de pé)
	cd backend && uv run python scripts/gerar_mocks.py

indice:         ## regera o índice de busca de NCM a partir dos dados abertos (motor RR de pé, ~2 min)
	cd backend && uv run python scripts/gerar_indice_ncm.py

openapi:        ## reexporta o contrato para docs/contrato/openapi.json
	cd backend && uv run python scripts/exportar_openapi.py

test:           ## testes do backend que não precisam dos motores (os mesmos do CI)
	cd backend && uv run pytest

lint:           ## lint e formatação do Python (o ruff travado no backend/uv.lock)
	uv run --project backend ruff check . && uv run --project backend ruff format --check .

tipos:          ## checagem de tipos do app (mypy com o plugin do Pydantic)
	cd backend && uv run mypy

cobertura:      ## testes do CI com cobertura; falha abaixo de 90% no app/
	cd backend && uv run coverage run -m pytest && uv run coverage report

auditoria:      ## vulnerabilidades conhecidas nas dependências travadas (pip-audit, banco do PyPI)
	cd backend && uv export --locked --all-extras --no-emit-project --format requirements-txt -o .req-auditoria.txt 		&& uvx pip-audit==2.10.1 -r .req-auditoria.txt --require-hashes --disable-pip --strict; 		status=$$?; rm -f .req-auditoria.txt; exit $$status

tela-instalar:  ## instala as dependências travadas do frontend (npm ci, sem scripts de instalação)
	cd frontend && npm ci

tela:           ## tela em desenvolvimento em http://127.0.0.1:3000 (a origem liberada no CORS)
	cd frontend && npm run dev

tela-checar:    ## o mesmo que o job de frontend do CI: auditoria, lint, tipos, testes, build e segurança
	cd frontend && npm audit --audit-level=low && npm audit signatures && npm run contrato:checar && npm run lint && npm run typecheck && npm test && npx vite build && npm run seguranca

tela-contrato:  ## regera os tipos da tela a partir de docs/contrato/openapi.json (depois do make openapi)
	cd frontend && npm run contrato
