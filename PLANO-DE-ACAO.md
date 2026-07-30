# Plano de Ação — Sistema de Ponto com Reconhecimento Facial

> Documento de execução. O "o quê" e o "porquê" estão em [CLAUDE.MD](CLAUDE.MD).
> Aqui está o **como** e em **que ordem**.

**Status geral:** `Etapa 0 concluída — Etapa 1 a seguir`
**Última atualização:** 2026-07-30

---

## Princípios que guiam todas as etapas

1. **Multi-tenant desde a primeira linha.** Toda tabela de negócio tem `tenant_id`. Todo
   acesso a dados passa por um filtro de tenant vindo do JWT — nunca por parâmetro de query.
2. **Reconhecimento facial atrás de uma interface.** O resto do sistema nunca importa
   `insightface` diretamente. Trocar de modelo (ou empurrar para o device na fase edge)
   deve ser trocar uma implementação, não reescrever o backend.
3. **Cada etapa termina rodando.** Nada de "faço o painel e testo no fim". Cada etapa tem
   um critério de pronto verificável.
4. **Backend ponta a ponta antes de qualquer tela.** Etapas 1–7 fecham o fluxo completo
   testável por HTTP. Só depois vêm painel (8) e app (9).
5. **Dado biométrico é dado sensível.** Imagem e embedding nunca em log, nunca em resposta
   de API, sempre criptografados em repouso.

---

## Decisões técnicas tomadas (e por quê)

| # | Decisão | Motivo |
|---|---|---|
| D1 | **Backend roda em Docker**, não em Python local | `insightface` exige compilação C/Cython no Windows e a máquina só tem Python 3.13 (fora do PATH), versão em que várias wheels ainda não existem. Docker elimina isso e já é o formato do deploy. |
| D2 | **pgvector desde o dia 1** (imagem `pgvector/pgvector:pg16`) | Custo zero agora (só troca a imagem do Postgres) e evita migração de coluna quando a base de embeddings crescer. |
| D3 | **Match facial 1:1 como padrão**, engine preparada para 1:N | O funcionário já está logado no app, então sabemos quem ele diz ser. Comparar contra o embedding dele é mais preciso e mais seguro que varrer a base. A API da engine expõe `verify()` e `identify()` — o modo quiosque (tablet na portaria) da fase 2 usa o 1:N sem reescrita. |
| D4 | **Múltiplos embeddings por funcionário** (3–5 fotos no cadastro) | Um único embedding erra muito com mudança de luz, óculos, barba. Score final = melhor match entre os templates ativos. |
| D5 | **Ponto duvidoso vira `pending_review`, não erro** | Se o rosto bate com score no limiar ou nenhum sinal de localização apareceu, registra mesmo assim e sinaliza para o RH decidir. Bloquear o funcionário de bater ponto é pior que um registro para revisar. |
| D6 | **Expo + EAS Build** no app React Native | A máquina de desenvolvimento é Windows: **não é possível compilar iOS localmente sem um Mac**. O EAS Build compila na nuvem e envia para o TestFlight. BLE, câmera e GPS funcionam via config plugins + dev client. |
| D7 | **SQLAlchemy 2.0 async + Alembic + asyncpg** | Padrão atual do ecossistema FastAPI, migrações versionadas desde o começo. |

---

## Riscos mapeados (tratar antes da etapa indicada)

| # | Risco | Impacto | Quando tratar |
|---|---|---|---|
| R1 | **iOS não entrega advertisement de iBeacon via CoreBluetooth.** O `react-native-ble-plx` citado no documento enxerga iBeacons no Android, mas o iOS filtra esses pacotes e só os expõe via CoreLocation (region monitoring, UUID precisa ser conhecido antecipadamente). | Sem tratar, o beacon simplesmente não funciona em iPhone — exatamente o problema que motivou largar o PWA. | **Antes de comprar o hardware.** Duas saídas: (a) beacons Eddystone / advertisement BLE genérico, que o `ble-plx` lê nos dois sistemas; (b) manter iBeacon e somar uma lib CoreLocation no iOS. O modelo de dados da Etapa 5 já guarda os dois formatos, então isso não trava o backend. |
| R2 | **Ler SSID/BSSID exige permissão de localização** (Android 10+) e a entitlement *Access WiFi Information* (iOS), que só vem com a conta paga Apple. | Fallback Wi-Fi silenciosamente vazio. | Etapa 9, ao configurar as permissões do app. |
| R3 | **Liveness client-side é burlável** se o servidor confiar num booleano do app. | Foto do funcionário no celular de outro bate ponto. | Etapa 10 — o servidor precisa validar o desafio, não aceitar o veredito do cliente. |
| R4 | **Conta Apple Developer ($99/ano) é pré-requisito de prazo**, aprovação não é instantânea. | Trava a distribuição iOS no fim do projeto. | Comprar já, em paralelo à Etapa 1. |
| R5 | Imagem do backend com InsightFace passa de 1 GB (onnxruntime + modelos). | Build lento, deploy caro em plano free. | Etapa 3 — multi-stage build e baixar o modelo em volume, não na imagem. |

---

## Etapa 0 — Fundação do repositório e ambiente local

**Objetivo:** ter o esqueleto do monorepo versionado e um `docker compose up` que sobe
Postgres + API respondendo.

**Entregáveis**
- `git init` + `.gitignore` (Python, Node, `.env`, modelos `.onnx`, uploads)
- Estrutura `backend/`, `admin-panel/`, `employee-app/`, `docs/`
- `docker-compose.yml`: `db` (pgvector/pgvector:pg16) + `api` (FastAPI com hot reload)
- `backend/Dockerfile` (dev), `backend/pyproject.toml`, `backend/.env.example`
- `GET /health` retornando status da API e conectividade com o banco
- `README.md` com como subir o ambiente

**Critério de pronto:** `docker compose up` e `curl localhost:8000/health` → `{"status":"ok","database":"ok"}`

---

## Etapa 1 — Modelo de dados multi-tenant

**Objetivo:** todo o schema do MVP modelado, migrado e com dados de exemplo.

**Entregáveis**
- Base declarativa com mixins: `TenantMixin` (`tenant_id`), `TimestampMixin`, `UUIDPrimaryKey`
- Tabelas:
  - `tenants` — empresa
  - `users` — acesso ao painel (RH/admin)
  - `employees` — funcionários
  - `devices` — aparelhos pareados por funcionário
  - `face_templates` — embeddings (`vector(512)`, versão do modelo, ativo/inativo)
  - `sites` — unidades/locais, com lat/lng e raio de geofence
  - `beacons` — iBeacon (uuid/major/minor) **e** Eddystone (namespace/instance), RSSI mínimo
  - `wifi_networks` — SSID/BSSID válidos por site
  - `time_entries` — o ponto, com `location_method`, scores e `status`
  - `consents` — LGPD (biometria e localização, versionado)
  - `audit_logs` — trilha de auditoria
- Alembic configurado + migração inicial
- Índices compostos começando por `tenant_id`
- Seed: 1 tenant, 1 admin, 1 site, 2 funcionários

**Critério de pronto:** `alembic upgrade head` cria tudo do zero; seed roda; `\dt` mostra as tabelas.

---

## Etapa 2 — Autenticação e isolamento por tenant

**Objetivo:** ninguém enxerga dado de outra empresa, nem por acidente.

**Entregáveis**
- Hash de senha (Argon2), emissão/validação de JWT com `tenant_id`, `sub` e `scope`
- Dois públicos: `POST /auth/admin/login` (painel) e `POST /auth/employee/login` (app)
- Dependência `CurrentTenant` — repositórios recebem o tenant, não confiam no request
- Refresh token e revogação
- Pareamento de dispositivo: primeiro login registra o `device`, logins seguintes validam
- **Teste automatizado que prova o isolamento**: token do tenant A não lê dado do tenant B

**Critério de pronto:** suíte de testes de tenancy passando (verde = isolamento provado).

---

## Etapa 3 — Módulo facial desacoplado

**Objetivo:** o coração do reconhecimento, isolado do resto e testável sem GPU.

**Entregáveis**
- `backend/app/facial/base.py` — protocolo `FaceEngine`:
  `detect()`, `extract_embedding()`, `verify(embedding, template) -> score`, `identify(embedding, candidates)`
- `InsightFaceEngine` — ArcFace via `onnxruntime`, modelo `buffalo_l` em volume (não na imagem)
- `StubFaceEngine` — determinística, para testes e CI sem baixar 300 MB
- Seleção da engine por variável de ambiente
- Serviço de storage abstrato (`LocalStorage` no MVP → `S3Storage` na fase 2), com chaves opacas
- Validação de qualidade da foto: um rosto só, tamanho mínimo, nitidez, frontalidade

**Critério de pronto:** teste que gera embedding de duas fotos da mesma pessoa e de pessoas diferentes, confirmando que o limiar separa os casos.

---

## Etapa 4 — Cadastro de funcionários e enrollment facial

**Objetivo:** o RH consegue cadastrar alguém e registrar o rosto dele.

**Entregáveis**
- CRUD de funcionários (escopo de tenant)
- `POST /employees/{id}/face-templates` — recebe de 3 a 5 fotos, valida qualidade,
  gera embeddings, rejeita se as fotos forem de pessoas diferentes entre si
- Listar / desativar / substituir templates (nunca deletar em hard delete — auditoria)
- Registro de consentimento LGPD no ato do enrollment
- Imagem original salva criptografada; **embedding nunca sai pela API**

**Critério de pronto:** cadastrar funcionário + 3 fotos por HTTP e ver os templates persistidos com score de qualidade.

---

## Etapa 5 — Locais, beacons e redes Wi-Fi

**Objetivo:** o backend sabe o que conta como "estar no hangar".

**Entregáveis**
- CRUD de `sites` (endereço, coordenadas, raio de geofence, fuso)
- CRUD de `beacons` — aceita iBeacon e Eddystone, vinculado a site e área, com RSSI mínimo
- CRUD de `wifi_networks` — SSID + BSSID por site
- `GET /sites/{id}/location-config` — o app baixa e cacheia os identificadores válidos
- Documento `docs/mapeamento-beacons.md` — planta de onde cada beacon fica no hangar

**Critério de pronto:** um site com 2 beacons e 1 rede Wi-Fi cadastrados e retornados pelo endpoint de config.

---

## Etapa 6 — Cadeia de validação de localização

**Objetivo:** decidir se o funcionário está no local, e registrar **como** foi decidido.

**Entregáveis**
- `LocationValidator` com a cadeia beacon → Wi-Fi → GPS
  - **Beacon**: identificador cadastrado no site + RSSI acima do limiar → confiança alta
  - **Wi-Fi**: BSSID conhecido → confiança média (SSID sozinho é falsificável, pesa menos)
  - **GPS**: distância pelo cálculo de haversine dentro do raio, considerando a precisão
    reportada → confiança baixa
  - Nenhum sinal → `method=none`, ponto vai para revisão (D5)
- Resultado tipado: método, confiança, site, identificador que casou, motivo
- Payload cru guardado em `jsonb` para auditoria
- Testes de mesa cobrindo cada ramo e as fronteiras (RSSI fraco, GPS impreciso, spoof)

**Critério de pronto:** testes unitários cobrindo os quatro desfechos da cadeia.

---

## Etapa 7 — Bater ponto (fecha o backend ponta a ponta)

**Objetivo:** o endpoint que é o produto.

**Entregáveis**
- `POST /time-entries` — multipart: selfie + payload de localização + tipo (entrada/saída)
- Orquestração: valida device → valida qualidade da foto → embedding → `verify` 1:1 contra
  os templates ativos → cadeia de localização → decide `approved` / `pending_review`
- Regras de negócio: intervalo mínimo entre batidas, dedução automática de entrada/saída
  pelo último registro, proteção contra reenvio duplicado (chave de idempotência)
- `GET /time-entries` com filtros (funcionário, período, método, status) e paginação
- `PATCH /time-entries/{id}/review` — RH aprova ou rejeita pendências
- Trilha de auditoria em toda decisão

**Critério de pronto:** roteiro completo via HTTP — cadastra funcionário, enrola rosto, bate ponto com beacon, com Wi-Fi, com GPS e sem sinal nenhum; os quatro registros aparecem com o método correto.

> **Marco: backend do MVP funcional.** Daqui em diante são as interfaces.

---

## Etapa 8 — Painel administrativo (Next.js)

**Objetivo:** o RH opera o sistema sem curl.

**Entregáveis**
- Next.js (App Router) + TypeScript + Tailwind, cliente de API tipado
- Login e sessão com refresh
- Funcionários: listar, cadastrar, enrollment facial pela webcam, desativar
- Locais: sites, beacons e redes Wi-Fi
- Pontos: tabela com filtros, **coluna do método de localização** e do score, foto do registro
- Fila de revisão das pendências
- Exportar CSV do período

**Critério de pronto:** operar o ciclo inteiro pelo navegador, sem tocar na API na mão.

---

## Etapa 9 — App do funcionário (React Native / Expo)

**Objetivo:** bater ponto pelo celular, com a cadeia de localização real.

**Entregáveis**
- Expo + dev client + TypeScript; config plugins de BLE, câmera e localização
- Login, pareamento do device, sessão persistida em secure storage
- Tela de ponto: câmera frontal com guia de enquadramento
- Coleta de localização em cascata: varredura BLE (`react-native-ble-plx`) → Wi-Fi → GPS,
  com timeout por etapa e feedback do que foi detectado
- Envio com fila offline e retry (hangar tem ponto cego de sinal)
- Histórico dos próprios registros
- Textos de consentimento LGPD e telas de permissão

**Critério de pronto:** APK instalado num Android físico batendo ponto contra o backend, detectando beacon de verdade.

---

## Etapa 10 — Liveness e anti-spoofing

**Objetivo:** foto na tela de outro celular não passa.

**Entregáveis**
- Desafio ativo: servidor sorteia a ação (piscar / virar o rosto), app captura a sequência
- MediaPipe validando a sequência **no backend** — o veredito é do servidor (R3)
- Desafio com expiração curta e uso único, amarrado ao `time_entry`
- Score de liveness gravado no registro; reprovação → `pending_review`
- Limiares configuráveis por tenant

**Critério de pronto:** teste de mesa — tentar bater ponto com foto impressa e com vídeo em tela, ambos reprovados.

---

## Etapa 11 — LGPD e retenção

**Objetivo:** estar defensável antes de vender para o segundo cliente.

**Entregáveis**
- Consentimento versionado, com registro de aceite e possibilidade de revogação
- Política de retenção aplicada por rotina: selfies de ponto expiram em N dias,
  embeddings vivem enquanto o vínculo existir
- Exportação e exclusão de dados do titular (portabilidade e direito ao esquecimento)
- Criptografia em repouso das imagens; segredos fora do repositório
- `docs/tratamento-de-dados.md` — inventário de dados pessoais, base legal, retenção
- Minuta de DPA em `docs/dpa-modelo.md`

**Critério de pronto:** rotina de expurgo rodando e documentação de tratamento escrita.

---

## Etapa 12 — Deploy e distribuição

**Objetivo:** rodando na nuvem, na mão dos funcionários.

**Entregáveis**
- Backend em Railway/Fly.io: Dockerfile de produção, Postgres gerenciado com pgvector,
  migrações no deploy, segredos no gerenciador da plataforma, HTTPS obrigatório
- Painel na Vercel
- App: EAS Build → APK/faixa interna no Android, TestFlight no iOS (D6)
- Logs estruturados, tratamento de erro e healthcheck monitorado
- Backup do banco configurado e **restauração testada**
- `docs/runbook.md` — como implantar, como reverter, o que fazer quando cair

**Critério de pronto:** funcionário instala pelo TestFlight/APK e bate ponto em produção.

---

## Sequência de trabalho

```
0 ──> 1 ──> 2 ──> 3 ──> 4 ──┐
                  └──> 5 ──> 6 ──> 7 ──> 8 ──> 9 ──> 10 ──> 11 ──> 12
```

- 4 e 5/6 são independentes entre si e podem ser feitas em qualquer ordem depois da 3.
- 8 (painel) e 9 (app) só dependem da 7 estar fechada.
- 10 depende da 9 (o desafio precisa do app para ser capturado).
- 11 e 12 podem começar em paralelo assim que a 9 estiver de pé.

**Em paralelo, fora do código (não deixar para o fim):**
- Comprar a conta Apple Developer — R4
- Escolher e comprar os beacons, resolvendo o R1 antes da compra
- Mapear fisicamente o hangar para posicionar os beacons

---

## Registro de progresso

| Etapa | Status | Concluída em |
|---|---|---|
| 0 — Fundação | 🟢 concluída | 2026-07-30 |
| 1 — Modelo de dados | ⚪ não iniciada | |
| 2 — Auth e tenancy | ⚪ não iniciada | |
| 3 — Módulo facial | ⚪ não iniciada | |
| 4 — Cadastro e enrollment | ⚪ não iniciada | |
| 5 — Locais e beacons | ⚪ não iniciada | |
| 6 — Validação de localização | ⚪ não iniciada | |
| 7 — Bater ponto | ⚪ não iniciada | |
| 8 — Painel admin | ⚪ não iniciada | |
| 9 — App do funcionário | ⚪ não iniciada | |
| 10 — Liveness | ⚪ não iniciada | |
| 11 — LGPD | ⚪ não iniciada | |
| 12 — Deploy | ⚪ não iniciada | |
