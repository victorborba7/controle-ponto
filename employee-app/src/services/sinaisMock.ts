/**
 * Sinais falsos para rodar no simulador, onde não há rádio BLE, Wi-Fi de
 * verdade nem GPS confiável.
 *
 * **Só entra em jogo em build de desenvolvimento** (ver `mockAtivo`): mesmo que
 * a variável de ambiente vaze para um build de produção, o `__DEV__` a ignora.
 *
 * A intercepção acontece lá em cima, em `coletarSinais` — não aqui embaixo, no
 * `react-native-ble-plx` ou no CoreBluetooth. Fingir o rádio não faz sentido no
 * simulador: o objetivo é exercitar o fluxo do app (progresso, batida, fila),
 * e para isso basta devolver o que uma varredura devolveria.
 *
 * Sempre que possível o mock ecoa um beacon/Wi-Fi **de fato cadastrado** (lido
 * do cache de configuração), para que a batida simulada seja validada de ponta
 * a ponta pelo servidor, e não só na tela.
 */

import { lerCache, type BeaconConfigurado } from "./configLocal";
import type {
  BeaconRelatado,
  ProgressoColeta,
  ResumoColeta,
  SinaisColetados,
} from "./localizacao";

/** Cenário a simular. Vazio/ausente = usa os sinais reais. */
export type CenarioMock = "beacon" | "wifi" | "gps" | "nada";

const CENARIOS: readonly CenarioMock[] = ["beacon", "wifi", "gps", "nada"];

/**
 * Cenário pedido pelo ambiente, ou `null` para seguir com os sinais reais.
 *
 * Fora de `__DEV__` sempre devolve `null`: o mock não existe em produção.
 */
export function mockAtivo(): CenarioMock | null {
  if (!__DEV__) return null;
  const bruto = process.env.EXPO_PUBLIC_MOCK_SINAIS;
  return CENARIOS.includes(bruto as CenarioMock) ? (bruto as CenarioMock) : null;
}

/** RSSI plausível de um beacon a poucos metros — forte o bastante para passar. */
const RSSI_SIMULADO = -55;

/** Coordenada de exemplo (usada só no cenário `gps`). */
const GPS_SIMULADO = { latitude: -23.5505, longitude: -46.6333, accuracy_m: 12 };

/** Espera curta para imitar a duração de cada etapa da coleta real. */
function pausa(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/** Converte um beacon cadastrado no formato que o servidor espera receber. */
function relatarDeConfig(b: BeaconConfigurado): BeaconRelatado | null {
  if (b.protocol === "eddystone" && b.eddystone_namespace && b.eddystone_instance) {
    return {
      protocol: "eddystone",
      eddystone_namespace: b.eddystone_namespace,
      eddystone_instance: b.eddystone_instance,
      rssi: RSSI_SIMULADO,
    };
  }
  if (b.protocol === "ibeacon" && b.ibeacon_uuid) {
    return {
      protocol: "ibeacon",
      ibeacon_uuid: b.ibeacon_uuid,
      ibeacon_major: b.ibeacon_major ?? 0,
      ibeacon_minor: b.ibeacon_minor ?? 0,
      rssi: RSSI_SIMULADO,
    };
  }
  if (b.protocol === "mac" && b.mac_address) {
    return {
      protocol: "mac",
      mac_address: b.mac_address.toLowerCase(),
      rssi: RSSI_SIMULADO,
    };
  }
  return null;
}

/** Primeiro beacon cadastrado que dá para relatar, varrendo todos os locais. */
async function beaconCadastrado(): Promise<BeaconRelatado | null> {
  const locais = await lerCache();
  for (const local of locais) {
    for (const beacon of local.beacons) {
      const relatado = relatarDeConfig(beacon);
      if (relatado) return relatado;
    }
  }
  return null;
}

/** Primeira rede Wi-Fi cadastrada, para o cenário `wifi`. */
async function wifiCadastrado(): Promise<{ ssid: string; bssid?: string } | null> {
  const locais = await lerCache();
  for (const local of locais) {
    const rede = local.wifi_networks[0];
    if (rede) return { ssid: rede.ssid, ...(rede.bssid ? { bssid: rede.bssid } : {}) };
  }
  return null;
}

/**
 * Monta o `ResumoColeta` do cenário pedido, percorrendo as mesmas etapas de
 * progresso da coleta real para que a tela se comporte igual.
 */
export async function coletarSinaisMock(
  cenario: CenarioMock,
  aoProgredir?: (progresso: ProgressoColeta) => void,
): Promise<ResumoColeta> {
  const avisos: string[] = [`Sinais simulados (cenário “${cenario}”) — build de desenvolvimento.`];

  aoProgredir?.({ etapa: "bluetooth", detalhe: "Procurando beacons do local…" });
  await pausa(600);

  const beacons: BeaconRelatado[] = [];
  if (cenario === "beacon") {
    const relatado = await beaconCadastrado();
    if (relatado) beacons.push(relatado);
    else
      avisos.push(
        "Nenhum beacon no cache de configuração — sincronize o app conectado ao backend primeiro.",
      );
  }

  aoProgredir?.({ etapa: "wifi", detalhe: "Verificando a rede Wi-Fi…" });
  await pausa(300);

  let wifi: Array<{ ssid: string; bssid?: string }> = [];
  if (cenario === "wifi") {
    const rede = await wifiCadastrado();
    if (rede) wifi = [rede];
    else avisos.push("Nenhuma rede Wi-Fi no cache de configuração.");
  }

  aoProgredir?.({ etapa: "gps", detalhe: "Obtendo a localização…" });
  await pausa(300);

  const gps = cenario === "gps" ? GPS_SIMULADO : undefined;

  const sinais: SinaisColetados = {
    beacons,
    wifi,
    ...(gps ? { gps } : {}),
    captured_at: new Date().toISOString(),
  };

  aoProgredir?.({ etapa: "pronto", detalhe: "" });

  return {
    sinais,
    descricao: descrever(sinais, cenario),
    temSinalForte: beacons.length > 0 || wifi.length > 0,
    avisos,
    // A tela de diagnóstico lista o que o rádio "viu"; no mock não há rádio.
    vistos: [],
  };
}

function descrever(sinais: SinaisColetados, cenario: CenarioMock): string {
  if (sinais.beacons.length > 0) return `Beacon simulado (${sinais.beacons[0].rssi} dBm)`;
  if (sinais.wifi.length > 0) return `Wi-Fi simulado (${sinais.wifi[0].ssid})`;
  if (sinais.gps) return `GPS simulado (±${Math.round(sinais.gps.accuracy_m)} m)`;
  return cenario === "nada"
    ? "Nenhum sinal (cenário simulado)"
    : "Nenhum sinal de localização detectado";
}
