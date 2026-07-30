# Ponto Facial

Sistema de controle de ponto por reconhecimento facial com validação de presença
física (beacon BLE → Wi-Fi → GPS).

- **Visão do produto e stack:** [CLAUDE.MD](CLAUDE.MD)
- **Plano de execução por etapas:** [PLANO-DE-ACAO.md](PLANO-DE-ACAO.md)

## Estrutura

```
backend/        FastAPI + reconhecimento facial (Python)
admin-panel/    Next.js — painel do RH
employee-app/   React Native (Expo) — app do funcionário
docs/           documentação de projeto, LGPD e operação
```

## Rodando o ambiente local

Pré-requisitos: **Docker Desktop**. Não é necessário ter Python instalado —
o backend roda inteiro em container (decisão D1 do plano).

```bash
cp .env.example .env          # Windows/PowerShell: Copy-Item .env.example .env
docker compose up -d --build
docker compose exec api alembic upgrade head    # cria o schema
docker compose exec api python -m app.db.seed   # dados de exemplo (opcional)
```

Verificar:

```bash
curl http://localhost:8000/health
# {"status":"ok","database":"ok","environment":"local","version":"0.1.0"}
```

- API: http://localhost:8000
- Documentação interativa (Swagger): http://localhost:8000/docs
- Postgres: `localhost:5432` (usuário/senha/base conforme o `.env`)

O código do backend é montado por bind mount — salvar um arquivo `.py` recarrega
a API automaticamente, sem rebuild.

## Comandos úteis

```bash
docker compose logs -f api         # acompanhar os logs da API
docker compose exec api bash       # shell dentro do container
docker compose exec api pytest     # rodar os testes
docker compose exec api ruff check app/ alembic/   # lint
docker compose down                # parar (mantém os dados)
docker compose down -v             # parar e APAGAR o banco
```

### Migrações

```bash
docker compose exec api alembic upgrade head
docker compose exec api alembic revision --autogenerate -m "descrição"
docker compose exec api alembic check      # o schema bate com os modelos?
docker compose exec api alembic downgrade -1
```

Ao criar um modelo novo, **importe-o em `backend/app/models/__init__.py`** — é o
que faz o Alembic enxergá-lo no autogenerate. Sem isso a migração sai vazia.

### Testes

Rodam contra um Postgres de verdade, num banco separado (`ponto_facial_test`)
que é recriado a cada execução — o schema depende de pgvector e JSONB, então
testar em SQLite testaria outra coisa.

```bash
docker compose exec api pytest          # tudo
docker compose exec api pytest -q tests/test_tenant_isolation.py
```

### Credenciais do seed

Só para desenvolvimento local: admin `rh@empresademo.com.br` e funcionários
`0001` / `0002`, todos com a senha `senha123`.

## Segurança e dados sensíveis

Este sistema trata **dado biométrico**, que é dado pessoal sensível pela LGPD.

- O `.env` nunca vai para o repositório — use o `.env.example` como modelo.
- Imagens de funcionários e embeddings não são versionados (ver `.gitignore`).
- Embeddings nunca são retornados por nenhum endpoint da API.
- Em produção, `JWT_SECRET` precisa ser gerado aleatoriamente e guardado no
  gerenciador de segredos da plataforma, nunca em arquivo.
