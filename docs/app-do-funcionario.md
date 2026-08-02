# App do funcionário — build e teste

Como gerar o APK e validar o fluxo num Android físico. É o critério de pronto
da Etapa 9 do [plano](../PLANO-DE-ACAO.md).

> **Este app não roda no Expo Go.** Ele usa BLE (`react-native-ble-plx`), que é
> código nativo. É preciso gerar um build próprio — o `development build` abaixo.

---

## Antes de começar

| Item | Situação |
|---|---|
| Node 18+ e npm | ✅ já instalado |
| Conta Expo (gratuita) | necessária para o EAS Build |
| Android físico | necessário — emulador não tem rádio Bluetooth |
| Beacons Eddystone | necessários para validar o elo mais forte da cadeia |
| Mac ou conta Apple | **não** é necessário nesta etapa (só na 9b) |

Sem os beacons ainda, dá para validar os elos de Wi-Fi e GPS — o fluxo completo
funciona, apenas com confiança menor.

---

## 1. Apontar o app para o backend

```bash
cd employee-app
cp .env.example .env
```

Edite o `.env` com o **IP da sua máquina na rede local**, não `localhost` — do
ponto de vista do celular, `localhost` é o próprio celular:

```bash
ipconfig            # procure o IPv4 do adaptador Wi-Fi
```

```
EXPO_PUBLIC_API_URL=http://192.168.3.27:8000
```

> ### O `.env` sozinho não chega ao APK
>
> `.env` está no `.gitignore`, e o EAS envia o projeto **pelo git** — então a
> variável não entra no build. O mesmo valor precisa estar em `eas.json`, no
> perfil usado:
>
> ```json
> "development": {
>   "env": { "EXPO_PUBLIC_API_URL": "http://192.168.3.27:8000" }
> }
> ```
>
> **Ao trocar de rede ou de máquina, os dois precisam mudar.**
>
> O sintoma de esquecer o `eas.json` é enganoso: rodando com
> `npx expo start --dev-client`, o JS vem do Metro e carrega o `.env` **desta
> máquina**, então tudo funciona. Abrindo o app sozinho, ele usa o bundle
> embutido, sem a variável — e as batidas caem na fila local sem nunca subir.

O backend precisa aceitar conexões de fora do container:

```bash
docker compose up -d      # já publica em 0.0.0.0:8000
```

Confirme do próprio celular, pelo navegador: `http://SEU_IP:8000/health`.

---

## 2. Gerar o APK

```bash
npm install -g eas-cli
eas login
eas build:configure          # cria o projeto no EAS e preenche o projectId
eas build --profile development --platform android
```

O build roda na nuvem (~10–15 min) e devolve um link. Baixe o APK pelo próprio
celular e instale — o Android vai pedir para autorizar "instalação de fontes
desconhecidas".

Depois, para o ciclo de desenvolvimento, o JavaScript recarrega sem novo build:

```bash
npx expo start --dev-client
```

**Só é preciso gerar um APK novo quando mudar código nativo** — dependência
nova, permissão nova ou alteração no `app.json`.

### Alternativa sem EAS

Se preferir compilar localmente, é possível — mas exige Android Studio, JDK 17
e ~10 GB de SDK:

```bash
npx expo prebuild --platform android
cd android && ./gradlew assembleRelease
```

O EAS evita tudo isso e é gratuito para volumes baixos.

---

## 3. Cadastrar o funcionário antes de testar

O app não faz cadastro — quem cadastra é o RH. Pelo painel
(`http://localhost:3000`):

1. **Locais** → cadastre o local, com coordenadas e raio
2. **Locais → beacons** → cadastre cada beacon (namespace + instance + RSSI)
3. **Funcionários** → cadastre a pessoa **com senha inicial**
4. Abra a ficha → **Cadastrar rosto** → 3 a 5 fotos pela webcam

Sem o rosto cadastrado o app recusa a batida com "Seu rosto ainda não foi
cadastrado".

---

## 4. Roteiro de teste no aparelho

| # | Passo | Resultado esperado |
|---|---|---|
| 1 | Abrir o app pela primeira vez | Tela de consentimento LGPD |
| 2 | Aceitar e entrar (empresa + matrícula + senha) | Vai para a tela de ponto |
| 3 | Conceder câmera e localização | Câmera frontal com a moldura |
| 4 | **Perto do beacon**, registrar | "Ponto registrado" · painel mostra método **Beacon** |
| 5 | **Longe do beacon, no Wi-Fi da empresa** | Método **Wi-Fi** |
| 6 | Desligar Bluetooth e Wi-Fi, ficar no raio | Método **GPS** |
| 7 | Fora do local, sem sinal nenhum | "Enviado para conferência" · método **Nenhum** |
| 8 | **Ativar modo avião** e registrar | "Ponto guardado" · aviso de pendente |
| 9 | Reativar a rede e reabrir o app | Pendência some, registro aparece no painel |
| 10 | Registrar duas vezes seguidas | Segunda recusada: "Você acabou de bater o ponto" |
| 11 | Outra pessoa tentar no seu login | "Não reconhecemos seu rosto" — sem registro |

O passo 9 é o que valida a fila offline, que existe por causa do ponto cego de
sinal do hangar.

---

## 5. Calibrar o RSSI dos beacons

Com o app instalado, aproveite para calibrar — o procedimento está em
[mapeamento-beacons.md](mapeamento-beacons.md). Resumindo: fique no ponto mais
distante que ainda deve contar como "presente", anote o RSSI que um app de
varredura mostra, e cadastre o limiar com **5 dBm de folga**.

Um limiar justo demais gera falha intermitente, que é o pior tipo de falha para
diagnosticar em campo.

---

## Distribuição para a equipe (Android)

Enquanto o MVP roda numa empresa só, o mais simples é **distribuir o APK
direto** — link interno, e-mail ou pendrive. Não há custo nem revisão.

Quando incomodar instalar na mão, o próximo passo é o **Internal App Sharing**
do Google Play: também gratuito, sem revisão, e o funcionário instala por um
link do Play Store.

---

## iOS (Etapa 9b)

O mesmo código roda no iPhone, mas depende de:

1. Conta Apple Developer paga (US$ 99/ano) — **compre só depois de validar o
   Android**, e comece o cadastro no mesmo dia, porque a aprovação leva dias
2. `eas build --profile preview --platform ios` (compila na nuvem, sem Mac)
3. `eas submit --platform ios` para o TestFlight
4. Validar a varredura Eddystone em iPhone físico — é o ponto que motivou a
   escolha do formato, e o único que não dá para verificar antes

A entitlement de leitura de Wi-Fi já está declarada no `app.json`, mas só passa
a valer com a conta paga.

---

## Problemas comuns

**"EXPO_PUBLIC_API_URL não definido"** — falta o `.env`, ou o APK foi gerado
antes de criá-lo. A variável é embutida no build; mudou o valor, gere de novo.

**Nenhum beacon é encontrado** — confira, nesta ordem: Bluetooth ligado;
permissão de localização concedida (no Android ela é o que libera o BLE); o
beacon está transmitindo **Eddystone-UID**, não iBeacon nem Eddystone-URL; e o
namespace cadastrado no painel é o mesmo que o beacon transmite.

**Wi-Fi não é identificado** — no Android 10+ a leitura do SSID exige permissão
de localização. Se ela foi negada, o elo do meio da cadeia fica vazio em
silêncio; o app avisa quando isso acontece.

**O ponto sempre cai em "conferência"** — normal se nenhum sinal foi
reconhecido. Abra o registro no painel: o motivo da pendência aparece por
extenso.
