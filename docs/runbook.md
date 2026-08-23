# Runbook — implantar, conferir e reverter

Quatro peças, quatro donos diferentes. Este documento existe para o dia em que
algo cair e a pessoa de plantão não for quem construiu.

| Peça | Onde roda | Comando de implantação |
|---|---|---|
| API | Fly.io, região `iad` | `cd backend && fly deploy --remote-only` |
| Banco | Neon, AWS `us-east-1` | migrações sobem junto com a API |
| Painel do RH | Vercel | `vercel --prod` a partir da **raiz** |
| App do funcionário | TestFlight (iOS) / APK (Android) | `eas build` |

**Endereços de produção**

```
API      https://waypoint-api.fly.dev
Painel   https://waypoint-victor-borbas-projects.vercel.app
```

---

## 1. Backend (Fly.io)

```bash
cd backend
fly deploy --remote-only
```

`--remote-only` compila no builder do Fly; não é preciso Docker na máquina.

### O que acontece, em ordem

1. Build da imagem (`Dockerfile.prod`). O primeiro build de cada máquina leva
   ~10 min porque compila o `insightface` e embute o modelo `buffalo_l`; os
   seguintes reaproveitam camadas.
2. **`alembic upgrade head` numa máquina temporária.** Se a migração falhar, o
   deploy aborta e a versão antiga continua servindo — nenhum tráfego chega à
   versão nova.
3. A máquina nova sobe, carrega o modelo (~25 s) e só então passa no
   healthcheck.

### Conferir

```bash
curl https://waypoint-api.fly.dev/health
# {"status":"ok","database":"ok","environment":"production","version":"0.1.0"}

fly logs --app waypoint-api --no-tail | grep -i agendador
# ... Agendador de lembretes ligado (a cada 5 min).
```

O segundo comando não é opcional: **um agendador parado é indistinguível de um
agendador rodando** se ninguém olhar o log.

### Reverter

```bash
fly releases --app waypoint-api          # lista as versões
fly deploy --image <imagem-da-versao-anterior> --app waypoint-api
```

⚠️ **Reverter código não reverte migração.** Se a versão nova aplicou uma
migração destrutiva, voltar o código deixa o banco à frente dele. As migrações
deste projeto são aditivas até aqui; se um dia houver uma que apague coluna,
o `downgrade` correspondente tem de rodar **antes** do rollback.

### Segredos

```bash
fly secrets list --app waypoint-api      # nomes e digests, nunca os valores
fly secrets set CHAVE="valor" --app waypoint-api
```

Trocar um segredo reinicia a máquina. Os quatro que existem:

| Segredo | Perder significa |
|---|---|
| `DATABASE_URL` | Trocar no Neon e atualizar aqui |
| `JWT_SECRET` | Inconveniente: todos tomam 401 e renovam sozinhos pelo refresh |
| `STORAGE_ENCRYPTION_KEY` | **Irreversível.** Toda foto de rosto vira lixo cifrado |
| `CORS_ORIGINS` | Painel para de conversar com a API |

---

## 2. Banco (Neon)

As migrações sobem com a API — não há passo separado.

### Criar o primeiro tenant de um ambiente

```bash
fly ssh console --app waypoint-api
# dentro da sessão:
export SEED_TENANT_NAME="Nome da Empresa"
export SEED_TENANT_SLUG="slug-da-empresa"
export SEED_ADMIN_EMAIL="rh@empresa.com"
export SEED_SITE_LAT="00.000000"
export SEED_SITE_LNG="-00.000000"
export SEED_SITE_RADIUS_M="100"
export SEED_TIMEZONE="America/New_York"
python -m app.db.seed_producao
```

**A senha do admin é impressa uma única vez.** O banco guarda só o hash Argon2.

### Trocar a senha de um admin

```bash
fly ssh console --app waypoint-api
ADMIN_TENANT_SLUG=slug ADMIN_EMAIL=rh@empresa.com python -m app.db.trocar_senha_admin
```

Pede a senha sem exibir, e **revoga as sessões ativas** do usuário. Precisa ser
a sessão interativa: `fly ssh console -C` não tem terminal e o `getpass` falha.

### Backup e restauração

O Neon mantém histórico de restauração no próprio console. **Restaurar nunca
foi testado neste projeto** — é o item que falta para a Etapa 12 fechar, e um
backup não testado é uma suposição, não um backup.

---

## 3. Painel do RH (Vercel)

```bash
# da RAIZ do repositório, não de admin-panel/
vercel --prod
```

Da raiz porque o projeto tem **Root Directory = `admin-panel`**: a Vercel
recebe o monorepo e desce até lá. Enviar de dentro da pasta falha com
*"Root Directory does not exist"*.

O [`.vercelignore`](../.vercelignore) recorta o resto do monorepo. Os padrões
de diretório têm barra inicial (`/backend`) de propósito — sem ela, a sintaxe
gitignore casa o nome em qualquer nível e `backend` também excluiria
`admin-panel/src/app/api/backend/`, que é o proxy do painel. Já aconteceu: o
login funcionava e todo o resto dava 404.

### Variáveis

`BACKEND_URL` = `https://waypoint-api.fly.dev`, nos três ambientes.

**Não marque como "Sensitive" o que não é segredo.** Uma URL pública mascarada
esconde justamente o erro de digitação — já custou uma sessão de depuração, com
uma senha de Wi-Fi colada no lugar da URL.

### Conferir

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://waypoint-victor-borbas-projects.vercel.app/login
# 200 — se vier 307/302 para vercel.com/sso-api, a Deployment Protection está
# ligada e o cliente não consegue entrar
```

### Reverter

Painel da Vercel → Deployments → a versão anterior → **Promote to Production**.
Instantâneo, sem rebuild.

---

## 4. App do funcionário

### iOS — TestFlight

```bash
cd employee-app
npx eas-cli build --platform ios --profile production
npx eas-cli submit --platform ios --latest
```

Depois, no App Store Connect: **TestFlight → grupo externo → adicionar o
build**. A primeira submissão de cada versão passa por Beta App Review
(normalmente algumas horas).

O acesso de demonstração para o revisor está em
[`docs/app-do-funcionario.md`](app-do-funcionario.md) — sem ele a revisão
reprova, porque o app recusa qualquer rosto não cadastrado.

⚠️ **O build expira 90 dias após o upload.** Quando expira, o app para de
abrir — funcionário parado na porta do hangar, em data previsível. Marque
lembrete no **dia 60**.

### Android — APK direto

```bash
cd employee-app
npx eas-cli build --platform android --profile preview
```

Tem de ser o perfil `preview`: ele gera `.apk`. O `production` gera `.aab`, que
**só serve para a Play Store** e não instala em aparelho nenhum.

O EAS devolve um link. O funcionário abre no celular e instala, autorizando
"instalar apps de fontes desconhecidas". Não há atualização automática: cada
versão é um link novo.

### Credenciais que não podem ser perdidas

```bash
npx eas-cli credentials --platform android   # baixe e guarde o keystore
```

Perder o keystore Android significa **nunca mais poder atualizar o app**
publicado. No iOS o certificado se revoga e reemite; aqui não há caminho de
volta.

---

## Quando algo cai

| Sintoma | Primeiro lugar para olhar |
|---|---|
| Ninguém bate ponto, painel também fora | `curl .../health` — API ou banco |
| Painel abre, API responde, batida falha | `fly logs` — provavelmente a engine facial |
| Painel dá 404 em tudo, menos login | `.vercelignore` comeu `api/backend/` |
| Lembretes pararam | `fly logs \| grep -i lembrete` — agendador morreu no restart |
| iPhone não acha beacon | Cache de config (12 h) ou beacon é iBeacon não cadastrado |
| App não abre no iPhone | Build do TestFlight expirou (90 dias) |

### Ordem de diagnóstico

Sempre de baixo para cima: **banco → API → painel/app**. O contrário faz
perder tempo investigando sintoma quando a causa está duas camadas abaixo.

```bash
curl https://waypoint-api.fly.dev/health   # banco e API de uma vez
fly status --app waypoint-api              # a máquina está de pé?
fly logs --app waypoint-api --no-tail      # o que ela disse antes de cair
```
