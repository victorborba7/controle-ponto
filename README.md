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
docker compose logs -f api      # acompanhar os logs da API
docker compose exec api bash    # shell dentro do container
docker compose exec api pytest  # rodar os testes
docker compose down             # parar (mantém os dados)
docker compose down -v          # parar e APAGAR o banco
```

## Segurança e dados sensíveis

Este sistema trata **dado biométrico**, que é dado pessoal sensível pela LGPD.

- O `.env` nunca vai para o repositório — use o `.env.example` como modelo.
- Imagens de funcionários e embeddings não são versionados (ver `.gitignore`).
- Embeddings nunca são retornados por nenhum endpoint da API.
- Em produção, `JWT_SECRET` precisa ser gerado aleatoriamente e guardado no
  gerenciador de segredos da plataforma, nunca em arquivo.
