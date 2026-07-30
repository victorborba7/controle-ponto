# Sistema de Ponto com Reconhecimento Facial

## Contexto

MVP para controle de ponto via reconhecimento facial, a ser implantado inicialmente em uma empresa cliente (baixa escala). A arquitetura deve ser pensada desde já para, numa segunda fase, virar um produto SaaS vendido para múltiplas empresas.

**Fases:**
1. **MVP** (este documento): 1 empresa, poucos funcionários, validar o fluxo ponta a ponta.
2. **Produto**: multi-tenant, self-service, escala para vários clientes.
3. **Edge**: reconhecimento rodando no próprio dispositivo (offline), hoje roda no servidor.

O código já deve nascer multi-tenant e com o modelo de reconhecimento desacoplado, mesmo que o MVP sirva só uma empresa — evita retrabalho caro depois.

---

## Stack Tecnológica

### Reconhecimento Facial
- Modelo: **InsightFace / ArcFace** (open source), rodando no backend.
- Liveness/anti-spoofing: **MediaPipe** (detecção de piscar/profundidade), para evitar burlar com foto/vídeo.
- Formato de export pensando na fase edge: **ONNX** ou **TensorFlow Lite**, para rodar futuramente no dispositivo sem trocar de modelo.

### Backend
- **Python + FastAPI** (mesma linguagem das libs de reconhecimento facial, evita fragmentar stack).
- Autenticação: **JWT**, já com escopo de `tenant_id` no token.
- Fila (opcional no MVP, mas deixar preparado): RabbitMQ ou similar, se o processamento de imagem começar a travar a API.

### Banco de Dados
- **PostgreSQL**.
- Toda tabela relevante já com coluna `tenant_id` (empresa), mesmo com 1 empresa só no MVP.
- Se o volume de embeddings crescer: considerar **pgvector** para busca por similaridade facial.

### Frontend
- **App do funcionário**: **React Native**, desde o MVP (não PWA).
  - Motivo da mudança: BLE é requisito de dia 1 (beacons no hangar), e **Web Bluetooth não funciona no Safari/iOS** — só em Chrome/Android. Um PWA deixaria qualquer funcionário com iPhone sem conseguir usar o beacon. React Native fala com BLE nativamente nos dois sistemas via `react-native-ble-plx`.
  - Câmera (reconhecimento facial), Wi-Fi e GPS também funcionam bem em React Native, sem perda em nenhuma frente.
- **Painel administrativo** (gestão de funcionários e relatórios de ponto): **Next.js**.

### Distribuição do app (MVP interno, sem lojas públicas)
- **Android**: instalação direta via APK (sideload) ou faixa de teste interno / Internal App Sharing do Google Play — sem custo extra, sem revisão.
- **iOS**: precisa de conta paga de desenvolvedor Apple ($99/ano). Caminho recomendado: **TestFlight** (até 10.000 testadores, builds precisam ser reenviados periodicamente). Alternativa mais manual: Ad Hoc (limitado a 100 aparelhos, exige registrar UDID de cada iPhone).
  - O Apple Developer Enterprise Program (distribuição interna "de verdade", sem TestFlight) exige a organização ter 100+ funcionários — não se aplica ainda no MVP.
- **Fase 2 (produto/SaaS)**: publicar de verdade na App Store e Play Store, com acesso controlado por login/código da empresa dentro do app (padrão usado por apps B2B como Slack, Deel etc.) — evita gerenciar TestFlight/Enterprise por cliente conforme a base cresce.

### Localização (validação de que o funcionário está no local)
Cadeia de fallback, do mais preciso ao mais genérico:
1. **Beacons BLE** espalhados pelo hangar — o app detecta o beacon mais próximo via Bluetooth, confirma presença física com boa precisão (inclusive indoor, onde GPS costuma falhar).
2. **Wi-Fi** — se não detectar nenhum beacon, o app verifica se está conectado à rede Wi-Fi da empresa (SSID/BSSID conhecido) como segundo sinal de presença.
3. **Geolocalização (GPS)** — se nenhum dos dois anteriores estiver disponível, cai para GPS do celular + geofencing (raio aceitável em torno do endereço cadastrado).

Cada ponto registrado deve salvar **qual método de localização validou a presença** (beacon/wifi/gps), para auditoria e para dar mais ou menos confiança ao registro depois.

### Infraestrutura
- MVP: **Railway, Render ou Fly.io** — deploy simples e barato para validar rápido.
- Fase 2 (escala): migrar para **AWS/GCP** com containers (ECS ou Kubernetes).
- Armazenamento de imagens/embeddings: **S3** (ou equivalente), com criptografia em repouso e política de retenção definida.
- HTTPS obrigatório em todas as comunicações (dado biométrico trafegando).
- **Hardware físico necessário**: beacons BLE (ex: Estimote, Kontakt.io ou genéricos iBeacon/Eddystone) instalados no hangar. Precisa mapear IDs dos beacons por área/local no cadastro do backend.

---

## Escopo do MVP

**Dentro do MVP:**
- Cadastro de funcionários (foto de referência para gerar o embedding facial).
- App React Native no celular do funcionário, capturando a foto e enviando para o backend.
- Detecção de localização com a cadeia de fallback (beacon BLE → Wi-Fi → GPS).
- Backend validando o rosto contra os embeddings cadastrados + validando a localização, e registrando o ponto (entrada/saída) com o método de localização usado.
- Painel simples para o RH visualizar os registros de ponto.
- Estrutura de dados já multi-tenant (`tenant_id`), mesmo servindo só uma empresa.
- Instalação e mapeamento dos beacons BLE no hangar.

**Fora do MVP (fica para a fase produto/edge):**
- Onboarding self-service de novas empresas.
- Reconhecimento rodando localmente no dispositivo (offline).
- Cobrança/billing.
- Publicação nas lojas (App Store/Play Store) — MVP usa distribuição interna (TestFlight/APK direto).

---

## Conformidade (LGPD)

Dado biométrico é dado sensível, e dado de localização também é dado pessoal protegido. Antes de escalar para outros clientes:
- Termo de consentimento explícito do funcionário para uso da imagem/biometria e da localização.
- Política de retenção clara (por quanto tempo guarda a imagem/embedding e o histórico de localização).
- Preparar um DPA (contrato de tratamento de dados) para usar com futuros clientes.
- No MVP, já vale documentar como os dados são tratados, mesmo informalmente — facilita formalizar depois.

---

## Estrutura sugerida do repositório

```
ponto-facial/
├── backend/          # FastAPI + reconhecimento facial
│   ├── app/
│   │   ├── api/
│   │   ├── models/         # com tenant_id em todas as entidades
│   │   ├── facial/         # lógica de embedding/comparação (desacoplada)
│   │   └── core/
│   └── requirements.txt
├── employee-app/      # React Native, app do funcionário (câmera + BLE/Wi-Fi/GPS)
├── admin-panel/       # Next.js, painel do RH
└── docs/
    └── projeto-ponto-facial.md   # este documento
```

---

## Próximos passos com Claude Code

1. Inicializar o backend (FastAPI) com o modelo de dados multi-tenant.
2. Integrar o InsightFace para gerar e comparar embeddings.
3. Modelar o cadastro de beacons BLE (ID, local/área no hangar) e de redes Wi-Fi válidas.
4. Criar endpoint de cadastro de funcionário (foto de referência).
5. Criar endpoint de bater ponto (recebe foto + dado de localização — beacon/wifi/gps —, valida ambos, registra).
6. Subir o app React Native do funcionário: captura de foto + leitura de beacons BLE (`react-native-ble-plx`) com fallback Wi-Fi → GPS.
7. Painel admin básico para listar registros de ponto (incluindo o método de localização usado em cada um).
8. Configurar distribuição interna: TestFlight (iOS) + APK/faixa interna (Android).