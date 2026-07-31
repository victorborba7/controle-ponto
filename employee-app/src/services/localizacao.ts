/**
 * Coleta os sinais de presença: BLE → Wi-Fi → GPS.
 *
 * **O app relata o que observou; quem decide é o servidor.** Isso é
 * deliberado: o app roda no celular do próprio funcionário e não é fonte
 * confiável de veredito. A cascata aqui é só sobre *custo* — a varredura BLE é
 * a mais lenta, então roda primeiro e as demais só entram se ela não achar
 * nada útil, poupando bateria e segundos na fila do relógio de ponto.
 *
 * Cada etapa tem timeout próprio. Sem isso, um Bluetooth travado deixaria o
 * funcionário parado na tela sem entender por quê.
 */

import NetInfo from "@react-native-community/netinfo";
import * as Location from "expo-location";
import { BleManager, State as BleState } from "react-native-ble-plx";

import { consolidar, lerEddystone, type LeituraEddystone } from "./eddystone";
import { consolidarIBeacons, lerIBeacon, type LeituraIBeacon } from "./ibeacon";

/** Tempo de varredura BLE. Curto o bastante para não irritar, longo o bastante
 *  para o anúncio de um beacon (tipicamente a cada 100–1000 ms) aparecer. */
const TIMEOUT_BLE_MS = 4000;
const TIMEOUT_GPS_MS = 8000;

/** Uma leitura de beacon no formato que o backend espera, seja qual for o protocolo. */
export type BeaconRelatado =
  | {
      protocol: "eddystone";
      eddystone_namespace: string;
      eddystone_instance: string;
      rssi: number;
    }
  | {
      protocol: "ibeacon";
      ibeacon_uuid: string;
      ibeacon_major: number;
      ibeacon_minor: number;
      rssi: number;
    };

export type SinaisColetados = {
  beacons: BeaconRelatado[];
  wifi: Array<{ ssid: string; bssid?: string }>;
  gps?: { latitude: number; longitude: number; accuracy_m: number };
  captured_at: string;
};

export type ProgressoColeta = {
  etapa: "bluetooth" | "wifi" | "gps" | "pronto";
  detalhe: string;
};

/** O que a tela mostra ao funcionário sobre o que foi encontrado. */
export type ResumoColeta = {
  sinais: SinaisColetados;
  descricao: string;
  temSinalForte: boolean;
  avisos: string[];
};

let gerenciadorBle: BleManager | null = null;

/** O BleManager é criado sob demanda: instanciá-lo já liga o rádio. */
function obterBle(): BleManager {
  if (!gerenciadorBle) gerenciadorBle = new BleManager();
  return gerenciadorBle;
}

export function encerrarBle() {
  gerenciadorBle?.destroy();
  gerenciadorBle = null;
}

// --------------------------------------------------------------------------
// Bluetooth
// --------------------------------------------------------------------------

type Varredura = {
  eddystone: LeituraEddystone[];
  ibeacon: LeituraIBeacon[];
};

async function coletarBeacons(avisos: string[]): Promise<Varredura> {
  const vazio: Varredura = { eddystone: [], ibeacon: [] };
  const ble = obterBle();

  const estado = await ble.state();
  if (estado !== BleState.PoweredOn) {
    avisos.push("Bluetooth desligado — ligue para detectar os beacons do local.");
    return vazio;
  }

  return new Promise((resolve) => {
    const eddystone: LeituraEddystone[] = [];
    const ibeacon: LeituraIBeacon[] = [];
    let finalizado = false;

    const finalizar = () => {
      if (finalizado) return;
      finalizado = true;
      ble.stopDeviceScan();
      resolve({
        eddystone: consolidar(eddystone),
        ibeacon: consolidarIBeacons(ibeacon),
      });
    };

    const relogio = setTimeout(finalizar, TIMEOUT_BLE_MS);

    ble.startDeviceScan(
      // Sem filtro de serviço: o iBeacon não anuncia service UUID nenhum — ele
      // vive no `manufacturerData`. Filtrar pelo UUID do Eddystone faria os
      // iBeacons jamais aparecerem na varredura.
      null,
      // Sem filtro de duplicatas: o RSSI oscila entre anúncios, e queremos a
      // melhor leitura de cada beacon, não a primeira.
      { allowDuplicates: true },
      (erro, dispositivo) => {
        if (erro) {
          avisos.push("Não foi possível varrer o Bluetooth.");
          clearTimeout(relogio);
          finalizar();
          return;
        }

        const rssi = dispositivo?.rssi ?? null;

        const eddy = lerEddystone(dispositivo?.serviceData, rssi);
        if (eddy) {
          eddystone.push(eddy);
          return;
        }

        const ibec = lerIBeacon(dispositivo?.manufacturerData, rssi);
        if (ibec) ibeacon.push(ibec);
      },
    );
  });
}

// --------------------------------------------------------------------------
// Wi-Fi
// --------------------------------------------------------------------------

async function coletarWifi(avisos: string[]) {
  try {
    const estado = await NetInfo.fetch("wifi");
    if (estado.type !== "wifi" || !estado.details) return [];

    const detalhes = estado.details as { ssid?: string | null; bssid?: string | null };
    if (!detalhes.ssid) {
      // Acontece quando falta permissão de localização (Android 10+) ou a
      // entitlement de Wi-Fi (iOS). Vale avisar: sem isso o elo do meio da
      // cadeia fica silenciosamente vazio.
      avisos.push("Rede Wi-Fi não identificada — verifique a permissão de localização.");
      return [];
    }

    return [
      {
        ssid: detalhes.ssid,
        ...(detalhes.bssid ? { bssid: detalhes.bssid } : {}),
      },
    ];
  } catch {
    return [];
  }
}

// --------------------------------------------------------------------------
// GPS
// --------------------------------------------------------------------------

async function coletarGps(avisos: string[]) {
  try {
    const { status } = await Location.getForegroundPermissionsAsync();
    if (status !== "granted") return undefined;

    const posicao = await Promise.race([
      Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.High }),
      new Promise<null>((resolve) => setTimeout(() => resolve(null), TIMEOUT_GPS_MS)),
    ]);

    if (!posicao) {
      avisos.push("Não foi possível obter a localização a tempo.");
      return undefined;
    }

    return {
      latitude: posicao.coords.latitude,
      longitude: posicao.coords.longitude,
      // O Android nem sempre reporta accuracy; 100 m é um valor conservador
      // que leva o backend a tratar a leitura como fraca, e não como precisa.
      accuracy_m: posicao.coords.accuracy ?? 100,
    };
  } catch {
    return undefined;
  }
}

// --------------------------------------------------------------------------
// Cascata
// --------------------------------------------------------------------------

export async function coletarSinais(
  aoProgredir?: (progresso: ProgressoColeta) => void,
): Promise<ResumoColeta> {
  const avisos: string[] = [];

  aoProgredir?.({ etapa: "bluetooth", detalhe: "Procurando beacons do local…" });
  const beacons = await coletarBeacons(avisos);

  aoProgredir?.({ etapa: "wifi", detalhe: "Verificando a rede Wi-Fi…" });
  const wifi = await coletarWifi(avisos);

  // O GPS roda mesmo com beacon encontrado, e de propósito: o backend cruza os
  // dois para detectar incoerência — um beacon do hangar "visto" de outra
  // cidade denuncia um anúncio falsificado.
  aoProgredir?.({ etapa: "gps", detalhe: "Obtendo a localização…" });
  const gps = await coletarGps(avisos);

  const relatados: BeaconRelatado[] = [
    ...beacons.eddystone.map((b) => ({
      protocol: "eddystone" as const,
      eddystone_namespace: b.namespace,
      eddystone_instance: b.instance,
      rssi: b.rssi,
    })),
    ...beacons.ibeacon.map((b) => ({
      protocol: "ibeacon" as const,
      ibeacon_uuid: b.uuid,
      ibeacon_major: b.major,
      ibeacon_minor: b.minor,
      rssi: b.rssi,
    })),
  ].sort((a, b) => b.rssi - a.rssi);

  const sinais: SinaisColetados = {
    beacons: relatados,
    wifi,
    ...(gps ? { gps } : {}),
    captured_at: new Date().toISOString(),
  };

  aoProgredir?.({ etapa: "pronto", detalhe: "" });

  return {
    sinais,
    descricao: descrever(sinais),
    temSinalForte: relatados.length > 0 || wifi.length > 0,
    avisos,
  };
}

function descrever(sinais: SinaisColetados): string {
  if (sinais.beacons.length > 0) {
    const melhor = sinais.beacons[0];
    return `Beacon do local detectado (${melhor.rssi} dBm)`;
  }
  if (sinais.wifi.length > 0) {
    return `Conectado à rede ${sinais.wifi[0].ssid}`;
  }
  if (sinais.gps) {
    return `Localização por GPS (±${Math.round(sinais.gps.accuracy_m)} m)`;
  }
  return "Nenhum sinal de localização detectado";
}
