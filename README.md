# Waypoint

Sistema de controle de ponto por reconhecimento facial com validação de presença
física (beacon BLE → Wi-Fi → GPS).

- **Visão do produto e stack:** [CLAUDE.MD](CLAUDE.MD)
- **Plano de execução por etapas:** [PLANO-DE-ACAO.md](PLANO-DE-ACAO.md)
- **Instalação e cadastro dos beacons:** [docs/mapeamento-beacons.md](docs/mapeamento-beacons.md)
- **Build e teste do app:** [docs/app-do-funcionario.md](docs/app-do-funcionario.md)
- **Implantar, conferir e reverter:** [docs/runbook.md](docs/runbook.md)

**Estado atual:** backend, painel do RH e app do funcionário implementados. O
app aguarda validação num Android físico com beacons de verdade — é o único
critério de pronto que depende de hardware ainda não adquirido.

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

### Reconhecimento facial

Duas implementações atrás da mesma interface (`app/facial/base.py`). Nada fora
de [backend/app/facial/](backend/app/facial/) importa `insightface` — é o que
permitirá, na fase edge, mover a inferência para o aparelho sem reescrever o
backend.

| Engine | Quando usar | Custo |
|---|---|---|
| `stub` (padrão) | Desenvolvimento e testes | Nenhum |
| `insightface` | **Qualquer coisa com rosto de verdade** | ~1 GB de libs + ~300 MB de modelo |

> ⚠️ **A engine stub não funciona com foto real, e falha de um jeito enganoso.**
> Ela trata a *cor dominante* da imagem como identidade — cores próximas são a
> mesma pessoa, distantes são pessoas diferentes. Uma selfie tem fundo, cabelo,
> rosto e roupa em cores diferentes, então ela responde **"Mais de um rosto na
> foto"** mesmo com a pessoa sozinha.
>
> Ela existe para exercitar a canalização (limiares, escolha de template, fila,
> erros) sem baixar 1,3 GB. **Para cadastrar rosto pela webcam ou pelo app, suba
> a variante facial.**

Para rodar com o modelo real:

```bash
docker compose -f docker-compose.yml -f docker-compose.facial.yml up -d --build api
docker compose -f docker-compose.yml -f docker-compose.facial.yml \
    exec api pytest tests/test_facial_real_model.py -v
```

Para voltar à variante leve:

```bash
docker compose up -d --build api
```

Confira qual está no ar — as duas escutam na mesma porta:

```bash
docker compose exec api python -c "from app.core.config import settings; print(settings.face_engine)"
```

O modelo é baixado no primeiro uso para o volume `facemodels`, não empacotado
na imagem — senão cada deploy transferiria 1,3 GB. As duas variantes têm nomes
de imagem distintos (`controle-ponto_api` e `controle-ponto_api_facial`), para
um `up -d` sem `--build` não reaproveitar a errada.

A suíte de testes usa a engine stub **sempre**, independentemente da variante no
ar: ela monta cenários com imagens sintéticas, que o ArcFace corretamente não
reconhece como rosto. O modelo real é verificado em `test_facial_real_model.py`.

### Credenciais do seed

Só para desenvolvimento local: admin `rh@empresademo.com.br` e funcionários
`0001` / `0002`, todos com a senha `senha123`.

## Segurança e dados sensíveis

Este sistema trata **dado biométrico**, que é dado pessoal sensível pela LGPD.

- O `.env` nunca vai para o repositório — use o `.env.example` como modelo.
- Imagens de funcionários e embeddings não são versionados (ver `.gitignore`).
- **Embeddings nunca são retornados por nenhum endpoint** — há teste garantindo.
- **Imagens de rosto são gravadas cifradas** (AES-GCM), inclusive em disco local
  de desenvolvimento.
- Cadastro biométrico exige consentimento explícito, com a versão do termo
  aceito registrada.

Em produção, gere segredos novos e guarde-os no gerenciador da plataforma —
nunca em arquivo:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"          # JWT_SECRET
python -c "import base64,os; print(base64.b64encode(os.urandom(32)).decode())"  # STORAGE_ENCRYPTION_KEY
```

> Perder a `STORAGE_ENCRYPTION_KEY` torna as imagens já gravadas
> irrecuperáveis. Ela não rotaciona sozinha.
