# Mapeamento dos beacons no hangar

Guia para a instalação física e o cadastro dos beacons BLE. Preencha a tabela
no fim conforme os beacons forem instalados — ela é a referência de campo
quando alguém não conseguir bater ponto em alguma área.

> **Status:** aguardando compra do hardware e visita ao local.

---

## O que comprar

**Beacons Eddystone** (decisão D8 do [plano](../PLANO-DE-ACAO.md)).

Ao cotar, exija:

| Requisito | Por quê |
|---|---|
| Suporte a **Eddystone-UID** | É o formato que o app lê igual em Android e iOS. Eddystone-URL e Eddystone-EID não servem aqui. |
| Namespace e instance **configuráveis** | Beacons com identificador fixo de fábrica impedem reorganizar as áreas depois. |
| Potência de transmissão ajustável | É como se calibra o alcance por área (veja "Calibração" abaixo). |
| Bateria trocável, autonomia de 1+ ano | Bateria selada vira lixo eletrônico e uma nova compra a cada troca. |
| Classificação IP mínima IP54 | Hangar tem poeira e variação de temperatura. |

**Se o modelo transmitir Eddystone e iBeacon ao mesmo tempo pelo mesmo preço,
prefira esse.** Não é necessário hoje, mas é a única saída caso um dia seja
preciso detecção em segundo plano no iOS — e sai de graça agora.

Fabricantes comuns: Kontakt.io, Estimote, MinewTech, e genéricos com chip
Nordic nRF52.

---

## Onde instalar

**Regra geral:** um beacon por ponto de passagem obrigatória, não um por metro
quadrado. O objetivo não é rastrear a pessoa dentro do hangar — é confirmar
que ela está lá. Cobertura excessiva aumenta custo, manutenção e a superfície
de dados de localização coletados (que é dado pessoal protegido).

Priorize:

1. **Entradas e portões** — onde a batida de entrada e saída acontece
2. **Área de vestiário / relógio de ponto atual** — onde as pessoas já se
   habituaram a registrar
3. **Áreas grandes de trabalho** — se houver expectativa de bater ponto lá

**Altura:** 2,5 a 3 m do chão, fora do alcance de esbarrão e de material sendo
movimentado.

**Evite:**

- Encostado em superfície metálica — estrutura de hangar é metálica e reflete
  e absorve 2,4 GHz, distorcendo a leitura de forma imprevisível
- Dentro de armário, caixa de passagem ou atrás de painel
- Perto de motores, solda ou forno industrial (ruído eletromagnético)
- Ao lado de roteador Wi-Fi — 2,4 GHz disputado degrada a detecção dos dois

---

## Calibração do RSSI

O campo `min_rssi` é o que impede alguém confirmar presença do estacionamento.
Ele é o limiar: uma leitura mais fraca que isso não conta.

Referência prática (varia com o ambiente, sempre meça no local):

| RSSI | Distância aproximada |
|---|---|
| −50 dBm | encostado, ~1 m |
| −65 dBm | mesma área, ~5 m |
| −75 dBm | ~10 m, ainda dentro |
| −85 dBm | outro canto do galpão |
| −95 dBm | provavelmente fora do prédio |

**Como calibrar cada beacon:**

1. Instale o beacon na posição definitiva.
2. Com um app de varredura BLE (nRF Connect, BLE Scanner), fique no ponto mais
   distante que ainda deve contar como "presente" e anote o RSSI.
3. Cadastre `min_rssi` com **5 dBm de folga** abaixo do valor medido — a
   leitura oscila naturalmente, e um limiar justo demais gera falha
   intermitente, que é o pior tipo de falha para diagnosticar.
4. Confirme fora da área: o RSSI deve ficar claramente abaixo do limiar.

Repita depois de qualquer mudança no leiaute do hangar. Estrutura metálica
nova ou uma estante grande mudam a propagação.

---

## Cadastro no sistema

Depois de instalar, cadastre pelo painel ou pela API:

```bash
POST /api/v1/sites/{site_id}/beacons
{
  "label": "Hangar - Portão A",
  "protocol": "eddystone",
  "eddystone_namespace": "edd1ebeac04e5defa017",
  "eddystone_instance": "000000000001",
  "min_rssi": -75
}
```

O `label` é o que o RH vê ao investigar um registro — use a linguagem de quem
trabalha no hangar ("Portão A", "Almoxarifado"), não código interno.

**Sobre a grafia dos identificadores:** o sistema normaliza tudo para
minúsculas sem separadores, então pode digitar como estiver na etiqueta
(`ED-D1-EB-...` ou `EDD1EBEA...`) que o resultado é o mesmo. Isso existe porque
um identificador gravado com grafia diferente da que o aparelho reporta nunca
casaria — e a falha seria silenciosa: nada dá erro, o beacon só nunca é
reconhecido.

---

## Manutenção

- **Bateria:** anote a data de instalação. Um beacon com bateria fraca reduz o
  alcance antes de morrer, então a falha aparece como "às vezes não pega" e não
  como "parou".
- **Beacon substituído:** cadastre o novo e **desative o antigo** — não edite o
  identificador do existente. Os pontos já registrados apontam para o beacon
  antigo e precisam continuar explicáveis na auditoria.
- **Verificação periódica:** rode uma varredura no hangar a cada trimestre e
  confira se todos os beacons cadastrados aparecem com RSSI acima do limiar.

---

## Planta e inventário

> Anexe aqui a planta do hangar com a posição de cada beacon marcada.

| # | Rótulo (label) | Área | Namespace | Instance | RSSI medido | `min_rssi` cadastrado | Instalado em | Bateria trocada em |
|---|---|---|---|---|---|---|---|---|
| 1 | | | | | | | | |
| 2 | | | | | | | | |
| 3 | | | | | | | | |
| 4 | | | | | | | | |

---

## Redes Wi-Fi (segundo elo da cadeia)

Cadastre também os pontos de acesso da empresa, com **BSSID**:

```bash
POST /api/v1/sites/{site_id}/wifi-networks
{
  "ssid": "EmpresaDemo-Corp",
  "bssid": "a4:2b:8c:00:11:22",
  "label": "AP do hangar"
}
```

O BSSID é o endereço MAC do ponto de acesso físico e é o que realmente
identifica a rede. O SSID é só o nome, e qualquer um cria um hotspot com o
mesmo nome — por isso a Etapa 6 dá menos confiança a um match que veio só por
SSID.

Um AP com múltiplas bandas (2,4 GHz e 5 GHz) costuma ter **um BSSID por
banda**. Cadastre os dois, senão o funcionário conectado na banda não
cadastrada não será reconhecido.

| # | SSID | BSSID | Banda | Local do AP |
|---|---|---|---|---|
| 1 | | | | |
| 2 | | | | |
