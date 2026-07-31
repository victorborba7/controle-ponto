# Testando com o beacon em mãos

Roteiro para validar o beacon com o app. Escrito a partir do caso concreto de
um **Aruba ARBT0100**, mas os passos valem para qualquer beacon.

> **O app identifica o beacon de três formas:** Eddystone-UID, iBeacon ou o
> endereço MAC. Se o seu beacon transmitir qualquer coisa reconhecível — ou
> simplesmente transmitir —, funciona no Android.

---

## O caso do Aruba ARBT0100 (verificado)

Leitura real de uma unidade, pelo nRF Connect:

```
Beacon Aruba (iBeacon)          7C:EC:79:44:C5:B5      -56 dBm
Company: Apple, Inc. <0x004C>   Type: Beacon <0x02>    Length: 21 bytes
UUID:  4152554e-f99b-4a3b-86d0-947070693a78
Major: 0     Minor: 0
```

Três conclusões:

**1. É um iBeacon padrão.** Company `0x004C`, type `0x02`, 21 bytes — exatamente
o layout que o app lê. Funciona sem reconfigurar nada.

**2. O identificador é de fábrica, e isso é um problema.** Os quatro primeiros
bytes do UUID, `41 52 55 4e`, são ASCII de **"ARUN"** (Aruba Networks) — é o
UUID padrão da linha. Com **Major 0 e Minor 0**, provavelmente **todas as
unidades saem idênticas**.

Isso significa que, por UUID/Major/Minor, você não conseguiria distinguir o
beacon do "Portão A" do que está no "Almoxarifado" — e o cadastro do segundo
seria recusado por duplicidade.

**3. Por isso o MAC é a escolha certa aqui.** `7C:EC:79:44:C5:B5` é único por
aparelho. É a razão de existir o terceiro modo de identificação.

### Duas saídas, e qual escolher

| Caminho | Vantagem | Custo |
|---|---|---|
| **Cadastrar pelo MAC** | Funciona hoje, sem tocar no beacon | **Não funciona no iPhone** — o iOS não expõe MAC de periférico |
| **Configurar Major/Minor distintos** pelo app Aruba Beacons | iBeacon volta a ser único, e o iPhone fica viável depois | Exige conta Meridian |

Se conseguir acesso ao app da Aruba, **prefira configurar Major/Minor** — sai
mais barato que refazer isso quando o iPhone entrar. Se não conseguir, o MAC
resolve o Android agora.

### Antes de comprar o resto dos beacons

Confirme que **o MAC não rotaciona**: leia agora, aguarde 30 minutos e leia de
novo. Alguns beacons giram o endereço por privacidade — se este girar,
identificação por MAC não se sustenta e a configuração via Aruba Beacons passa
a ser obrigatória.

---

## Fase 1 — Descobrir o que o beacon transmite

**Não gere o APK ainda.** Primeiro confirme que o beacon está vivo e anote seu
identificador. Duas opções:

### Opção A — Scanner genérico (mais rápido, 2 min)

Instale **nRF Connect for Mobile** (Nordic Semiconductor, gratuito, Play Store).

1. Ligue o beacon (tire a lingueta da bateria, se houver)
2. Abra o nRF Connect → aba **SCANNER**
3. Encoste o celular no beacon — ele deve aparecer com sinal forte (−40 a −60 dBm)
4. Toque no dispositivo para ver os detalhes do anúncio

O que procurar:

| O que aparece | Significa |
|---|---|
| `Apple` + tipo `iBeacon`, com UUID/Major/Minor | **iBeacon** — anote os três valores |
| Service `0xFEAA` ou `Eddystone` | **Eddystone** — anote namespace e instance |
| Nada reconhecível, ou identificadores repetidos entre beacons | Use o **MAC** (a linha `XX:XX:XX:XX:XX:XX` no topo) |

**Anote o MAC de qualquer forma.** Ele aparece logo abaixo do nome do
dispositivo e é a saída quando o identificador anunciado não distingue uma
unidade da outra.

### Opção B — Tela de diagnóstico do próprio app (mais confiável)

O app tem uma tela **Diagnóstico do local**, acessível **sem login**, na tela de
entrada. Ela usa exatamente o mesmo código de leitura da tela de ponto.

Isso importa: um scanner genérico prova que o beacon transmite, mas não prova
que *este app* consegue lê-lo. Se o identificador aparecer no diagnóstico, ele
aparecerá na batida.

A tela tem duas partes.

**Beacons reconhecidos** — o que o app conseguiu interpretar:

```
IBEACON                                -56 dBm
4152554e-f99b-4a3b-86d0-947070693a78
major 0 · minor 0
Toque para copiar  ·  sugestão de limiar: -61 dBm
```

**Todos os dispositivos vistos** — tudo que o rádio enxergou, com MAC:

```
7C:EC:79:44:C5:B5                      -56 dBm
Beacon Aruba · IBEACON
Toque para copiar o MAC  ·  sugestão de limiar: -61 dBm
```

É esta segunda lista que resolve o caso do Aruba: identifique a unidade pelo
nome ou pelo sinal mais forte (encoste o celular nela) e copie o MAC.

> Esta lista inclui aparelhos de passantes e **fica só no celular** — nada dela
> é enviado ao servidor. Na batida, o app relata apenas os MACs que já estão
> cadastrados, justamente para não coletar identificadores de terceiros.

Requer o APK (Fase 3), então na primeira vez use a Opção A.

---

## Fase 2 — Provar o backend com o identificador real

Com o identificador anotado, dá para validar **toda a cadeia** sem gerar o APK.
Leva 5 minutos.

### 2.1 Suba o ambiente

```bash
docker compose up -d
cd admin-panel && npm run dev
```

### 2.2 Cadastre pelo painel (`http://localhost:3000`)

Entre com `empresa-demo` / `rh@empresademo.com.br` / `senha123`.

1. **Locais** → *Cadastrar local* → nome, coordenadas do hangar, raio 200 m
2. Abra o local → **Beacons** → escolha o protocolo no seletor e preencha:

| Eddystone | iBeacon | MAC |
|---|---|---|
| Namespace (20 hex) | UUID | Endereço MAC |
| Instance (12 hex) | Major e Minor | — |

Em todos: **RSSI mínimo = o medido − 5 dBm**.

Para o Aruba do exemplo, seria: protocolo **Endereço MAC**,
`7C:EC:79:44:C5:B5`, RSSI mínimo `-61` (medido −56, menos a folga).

Pode colar exatamente como o scanner mostrou — com hífens, maiúsculas, dois
pontos. O sistema normaliza; foi feito justamente para isso.

3. **Funcionários** → cadastre você mesmo, **com senha inicial**
4. Abra a ficha → **Cadastrar rosto** → aceite o termo → 3 a 5 fotos pela webcam

### 2.3 Confirme que o ambiente aceita o beacon

Nesse ponto, o backend já reconhece o identificador do seu beacon. A Fase 3
fecha o circuito com o rádio de verdade.

---

## Fase 3 — Gerar o APK e testar em campo

```bash
cd employee-app
cp .env.example .env
```

Coloque no `.env` o **IP da sua máquina na rede local** (não `localhost` — do
ponto de vista do celular, `localhost` é o próprio celular):

```bash
ipconfig      # procure o IPv4 do adaptador Wi-Fi
```

```
EXPO_PUBLIC_API_URL=http://192.168.3.27:8000
```

Confirme do celular, pelo navegador: `http://SEU_IP:8000/health`.

Depois:

```bash
npm install -g eas-cli
eas login                    # conta Expo gratuita
eas build:configure
eas build --profile development --platform android
```

O build roda na nuvem (~10–15 min). Baixe o APK pelo celular e instale
(o Android vai pedir para autorizar fontes desconhecidas).

### Roteiro no aparelho

| # | Passo | Esperado |
|---|---|---|
| 1 | Abrir → **Diagnóstico do local** (sem login) | O beacon aparece com identificador e RSSI |
| 2 | Afastar-se e varrer de novo | RSSI cai — é assim que se calibra o limiar |
| 3 | Aceitar o termo e entrar | Tela de ponto com a câmera |
| 4 | Perto do beacon, **Registrar ponto** | "Ponto registrado" · painel mostra **Beacon** |
| 5 | Longe do beacon, no Wi-Fi da empresa | Método **Wi-Fi** |
| 6 | Bluetooth e Wi-Fi desligados, dentro do raio | Método **GPS** |
| 7 | Fora do local, sem nada | "Enviado para conferência" · método **Nenhum** |
| 8 | Modo avião → registrar | "Ponto guardado" |
| 9 | Reativar rede → reabrir o app | Pendência some, registro aparece no painel |

O passo 1 é o decisivo: **se o beacon aparecer no diagnóstico, o resto é
consequência.**

---

## Calibrando o limiar de RSSI

O `min_rssi` é o que impede confirmar presença do estacionamento.

1. Vá ao ponto **mais distante que ainda deve contar** como "no local"
2. Abra o diagnóstico e varra — anote o RSSI
3. Cadastre o limiar com **5 dBm de folga** (o diagnóstico já sugere o valor)
4. Confirme fora da área: o RSSI deve ficar claramente abaixo

A folga não é preciosismo: o RSSI oscila naturalmente entre anúncios, e um
limiar justo demais gera falha intermitente — o pior tipo de falha para
diagnosticar em campo.

---

## Se o beacon não aparecer

Verifique nesta ordem:

1. **Bluetooth ligado** no celular
2. **Permissão de localização concedida** — no Android, é ela que libera o BLE.
   Sem ela a varredura retorna vazia sem dar erro
3. **O beacon está transmitindo** — confirme no nRF Connect. Bateria nova? A
   lingueta plástica foi removida?
4. **O formato é UID ou iBeacon** — Eddystone-**URL** e Eddystone-**TLM** são
   descartados de propósito: não carregam identificador de local
5. **O identificador cadastrado é o mesmo** que o beacon transmite

Para o Aruba, se ele não transmitir nada reconhecível, será preciso configurá-lo
pelo app **Aruba Beacons** — e aí a conta Meridian entra na conta.

---

## O que cada modo custa no iPhone (Etapa 9b)

| Modo | Android | iPhone |
|---|---|---|
| **Eddystone-UID** | ✅ | ✅ |
| **iBeacon** | ✅ | ⚠️ só via CoreLocation, com UUID fixo no app |
| **MAC** | ✅ | ❌ **impossível** — o iOS não expõe MAC de periférico |

Foi exatamente esse quadro que motivou a decisão D8 do plano, de preferir
Eddystone.

Consequência para o Aruba: ele funciona no Android hoje pelo MAC, mas a Etapa 9b
exigirá uma destas saídas:

1. **Configurar Major/Minor distintos** pelo app Aruba Beacons e cadastrar por
   iBeacon, somando uma biblioteca CoreLocation ao app iOS — funciona, mas o
   UUID precisa ser fixo e conhecido em tempo de build
2. **Configurar o beacon para Eddystone**, se o firmware permitir — a saída mais
   limpa
3. **Trocar por beacons que transmitam Eddystone** no hangar definitivo

Nada disso bloqueia a validação agora. Mas vale resolver **antes de comprar o
resto dos beacons**, porque a escolha do hardware é o que fica difícil de
desfazer.
