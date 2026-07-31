# Testando com o beacon em mãos

Roteiro para validar o beacon com o app. Escrito a partir do caso concreto de
um **Aruba ARBT0100**, mas os passos valem para qualquer beacon.

> **O app lê os dois formatos.** Eddystone-UID e iBeacon. Se o seu beacon
> transmitir qualquer um dos dois, funciona — não é preciso reconfigurá-lo para
> um formato específico.

---

## Sobre o Aruba ARBT0100 especificamente

Duas coisas a saber antes de começar:

**1. Beacons Aruba nascem no ecossistema Meridian.** São configurados pelo app
"Aruba Beacons", que normalmente pede login em uma conta Meridian (a plataforma
de localização da HPE). Se você não tem essa conta, pode não conseguir *alterar*
a configuração de fábrica — mas isso não impede o teste, porque o beacon já vem
transmitindo alguma coisa.

**2. Não sei de cor o que este modelo transmite de fábrica.** Beacons Aruba
costumam sair em iBeacon, e alguns firmwares fazem Eddystone em paralelo. Em vez
de adivinhar, a Fase 1 abaixo descobre em 2 minutos — e o app lê os dois casos.

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
| Só `Aruba` ou dados brutos, sem nenhum dos dois | Precisa configurar pelo app da Aruba |

### Opção B — Tela de diagnóstico do próprio app (mais confiável)

O app tem uma tela **Diagnóstico do local**, acessível **sem login**, na tela de
entrada. Ela usa exatamente o mesmo código de leitura da tela de ponto.

Isso importa: um scanner genérico prova que o beacon transmite, mas não prova
que *este app* consegue lê-lo. Se o identificador aparecer no diagnóstico, ele
aparecerá na batida.

A tela mostra:

```
EDDYSTONE-UID                          -58 dBm
edd1ebeac04e5defa017 / 000000000001
Toque para copiar  ·  sugestão de limiar: -63 dBm
```

ou

```
IBEACON                                -58 dBm
f7826da6-4fa2-4e98-8024-bc5b71e0893e
major 1 · minor 42
Toque para copiar  ·  sugestão de limiar: -63 dBm
```

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

| Se for Eddystone | Se for iBeacon |
|---|---|
| Namespace (20 dígitos hex) | UUID |
| Instance (12 dígitos hex) | Major e Minor |
| RSSI mínimo: o medido **−5 dBm** | idem |

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

## Nota sobre iBeacon e o iPhone

O app lê iBeacon **no Android**. No iOS, não: o sistema filtra esses anúncios do
CoreBluetooth e só os entrega via CoreLocation, com o UUID conhecido de antemão
— foi exatamente esse limite que motivou a decisão D8 do plano, de preferir
Eddystone.

Consequência prática: **se o Aruba só fizer iBeacon, ele funciona no Android
hoje, mas a Etapa 9b (iPhone) exigirá** uma destas saídas:

- configurar o beacon para transmitir Eddystone também (muitos fazem os dois em
  paralelo), ou
- somar uma biblioteca CoreLocation ao app para o caminho iOS

Nada disso bloqueia a validação agora. Só vale saber antes de comprar o resto
dos beacons para o hangar.
