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
import { Platform } from "react-native";

import { t } from "../i18n";
import { BleManager, State as BleState, ScanMode } from "react-native-ble-plx";

import {
  macsConhecidos,
  sincronizarConfig,
  uuidsIBeaconConhecidos,
} from "./configLocal";
import { consolidar, lerEddystone, type LeituraEddystone } from "./eddystone";
import { consolidarIBeacons, lerIBeacon, type LeituraIBeacon } from "./ibeacon";
import { varrerIBeaconsIos } from "./ibeaconIos";
import { garantirPermissoesBluetooth } from "./permissoes";
import { coletarSinaisMock, mockAtivo } from "./sinaisMock";

/** Tempo de varredura BLE. Curto o bastante para não irritar, longo o bastante
 *  para o anúncio de um beacon (tipicamente a cada 100–1000 ms) aparecer. */
const TIMEOUT_BLE_MS = 4000;
const TIMEOUT_GPS_MS = 8000;

/**
 * Faixa de RSSI que o servidor aceita como leitura, e por que ela é filtrada
 * aqui e não lá.
 *
 * O RSSI viaja num byte com sinal, então −127 é o piso físico. Fora disso o que
 * existe são **sentinelas de "não medido"**, e cada plataforma usa o seu: o
 * Android devolve 127 e o CoreLocation devolve 0. Nenhum dos dois é um sinal
 * fortíssimo — são a ausência de medição, e tratá-los como leitura colocaria um
 * beacon inalcançável no topo da lista.
 *
 * Descartar aqui, e não deixar o servidor recusar, é deliberado: a validação
 * dele é do payload inteiro. Uma única leitura fora da faixa derrubaria a
 * batida toda — inclusive o beacon certo que veio junto — e o app trata a
 * recusa como definitiva, ou seja, a batida nem iria para a fila.
 */
const RSSI_MINIMO = -127;
const RSSI_MAXIMO = -1;

/** Teto de leituras por batida, espelhando `MAX_BEACON_READINGS` no servidor. */
const MAXIMO_BEACONS_RELATADOS = 30;

function rssiMedido(rssi: number): boolean {
  return Number.isInteger(rssi) && rssi >= RSSI_MINIMO && rssi <= RSSI_MAXIMO;
}

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
    }
  | {
      protocol: "mac";
      mac_address: string;
      rssi: number;
    };

/** Dispositivo BLE cru, como a tela de diagnóstico o exibe. */
export type DispositivoVisto = {
  mac: string;
  nome: string | null;
  rssi: number;
  reconhecido: "eddystone" | "ibeacon" | null;
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
  /** Tudo que o rádio enxergou. Só a tela de diagnóstico usa — nunca é enviado. */
  vistos: DispositivoVisto[];
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
  /** MACs relatáveis: só os que estão cadastrados (ver `macsPermitidos`). */
  macs: Array<{ mac: string; rssi: number }>;
  /** Tudo que apareceu, para a tela de diagnóstico. **Nunca é enviado.** */
  vistos: DispositivoVisto[];
};

/**
 * Varre o Bluetooth.
 *
 * `macsPermitidos` é o filtro de privacidade: a varredura precisa ser aberta
 * para enxergar iBeacons e MACs, e aberta ela vê celulares e relógios de quem
 * passa. Só os MACs cadastrados entram no que será relatado ao servidor.
 */
async function coletarBeacons(
  avisos: string[],
  macsPermitidos: Set<string>,
): Promise<Varredura> {
  const vazio: Varredura = { eddystone: [], ibeacon: [], macs: [], vistos: [] };

  // Antes de tocar no radio: sem BLUETOOTH_SCAN concedido em tempo de execucao,
  // a varredura falha de imediato e devolve zero dispositivos — sintoma que
  // parece defeito de hardware e nao e.
  const permissao = await garantirPermissoesBluetooth();
  if (!permissao.concedida) {
    avisos.push(permissao.motivo ?? t("sinal.semPermissaoBluetooth"));
    return vazio;
  }

  const ble = obterBle();

  const estado = await ble.state();
  if (estado !== BleState.PoweredOn) {
    avisos.push(t("sinal.bluetoothDesligado"));
    return vazio;
  }

  return new Promise((resolve) => {
    const eddystone: LeituraEddystone[] = [];
    const ibeacon: LeituraIBeacon[] = [];
    const porMac = new Map<string, { mac: string; rssi: number }>();
    const vistos = new Map<string, DispositivoVisto>();
    let finalizado = false;

    const finalizar = () => {
      if (finalizado) return;
      finalizado = true;
      ble.stopDeviceScan();
      resolve({
        eddystone: consolidar(eddystone),
        ibeacon: consolidarIBeacons(ibeacon),
        macs: Array.from(porMac.values()).sort((a, b) => b.rssi - a.rssi),
        vistos: Array.from(vistos.values()).sort((a, b) => b.rssi - a.rssi),
      });
    };

    const relogio = setTimeout(finalizar, TIMEOUT_BLE_MS);

    ble.startDeviceScan(
      // Sem filtro de serviço: o iBeacon não anuncia service UUID nenhum — ele
      // vive no `manufacturerData`. Filtrar pelo UUID do Eddystone faria os
      // iBeacons jamais aparecerem na varredura.
      null,
      {
        // Sem filtro de duplicatas: o RSSI oscila entre anúncios, e queremos a
        // melhor leitura de cada beacon, não a primeira.
        allowDuplicates: true,

        // **Varredura contínua, e isto não é otimização — é o que faz o beacon
        // aparecer.** O padrão do Android é `LowPower`: liga o rádio 500 ms a
        // cada 5 s, ou seja, 10% do tempo. Numa varredura de 4 s isso dá uma
        // única janela, e um beacon que anuncia a cada ~500 ms passa batido
        // com facilidade — enquanto aparelhos que anunciam muito rápido são
        // pegos assim mesmo. O sintoma é cruel: a lista enche de dispositivos
        // e justamente o beacon procurado falta.
        //
        // O custo de bateria é irrelevante aqui: são 4 segundos, disparados
        // por um toque do funcionário, não uma varredura de fundo.
        scanMode: ScanMode.LowLatency,

        // O Aruba (e a maioria dos beacons) usa advertising legado, não
        // estendido. Explícito para não depender do padrão da biblioteca.
        legacyScan: true,
      },
      (erro, dispositivo) => {
        if (erro) {
          // A mensagem do ble-plx e o que distingue "permissao negada" de
          // "adaptador desligado" de "hardware nao suporta". Sem ela, a tela
          // dizia so "não foi possível varrer", que nao ajuda ninguem.
          const detalhe = erro.reason ?? erro.message ?? "";
          avisos.push(
            detalhe
              ? `Falha na varredura Bluetooth: ${detalhe}`
              : t("sinal.falhaVarredura"),
          );
          clearTimeout(relogio);
          finalizar();
          return;
        }

        const rssi = dispositivo?.rssi ?? null;
        if (rssi === null) return;

        // No Android, `device.id` é o MAC. No iOS é um UUID por app — por isso
        // identificação por MAC não funciona lá.
        const mac = (dispositivo?.id ?? "").toLowerCase();

        const eddy = lerEddystone(dispositivo?.serviceData, rssi);
        const ibec = eddy ? null : lerIBeacon(dispositivo?.manufacturerData, rssi);

        if (eddy) eddystone.push(eddy);
        if (ibec) ibeacon.push(ibec);

        if (mac) {
          if (macsPermitidos.has(mac)) {
            const atual = porMac.get(mac);
            if (!atual || rssi > atual.rssi) porMac.set(mac, { mac, rssi });
          }

          const antes = vistos.get(mac);
          if (!antes || rssi > antes.rssi) {
            vistos.set(mac, {
              mac,
              nome: dispositivo?.localName ?? dispositivo?.name ?? null,
              rssi,
              reconhecido: eddy ? "eddystone" : ibec ? "ibeacon" : null,
            });
          }
        }
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
      avisos.push(t("sinal.wifiNaoIdentificado"));
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
      avisos.push(t("sinal.gpsDemorou"));
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
  // No simulador não há rádio BLE, Wi-Fi nem GPS de verdade. Em build de
  // desenvolvimento, `EXPO_PUBLIC_MOCK_SINAIS` substitui toda a coleta por
  // sinais falsos (ver `sinaisMock`). Em produção `mockAtivo()` é sempre null.
  const cenario = mockAtivo();
  if (cenario) return coletarSinaisMock(cenario, aoProgredir);

  const avisos: string[] = [];

  // A configuração vem do cache quando não há rede — que é exatamente o caso
  // em que ela mais importa.
  const locais = await sincronizarConfig();

  aoProgredir?.({ etapa: "bluetooth", detalhe: t("ponto.procurandoBeacons") });

  // No iPhone o `device.id` do BLE é um identificador rotativo por app, não o
  // endereço do rádio. Passar a lista de MACs conhecidos ali não filtraria
  // nada — só criaria a chance de um identificador alheio coincidir. Por isso
  // o conjunto vai vazio, e o bloco abaixo nunca relata MAC no iOS.
  const beacons = await coletarBeacons(
    avisos,
    Platform.OS === "ios" ? new Set<string>() : macsConhecidos(locais),
  );

  // O iOS não entrega iBeacon pelo CoreBluetooth; a varredura acima traz
  // Eddystone, e os iBeacons vêm do CoreLocation, procurados por UUID.
  let uuidsProcurados = uuidsIBeaconConhecidos(locais);
  let iosIBeacons = await varrerIBeaconsIos(uuidsProcurados, TIMEOUT_BLE_MS);

  // **Cache velho é cego no iPhone, e só no iPhone.** No Android o app relata
  // tudo que viu e quem compara com o cadastro é o servidor, sempre atualizado.
  // No iOS o CoreLocation exige a lista de UUIDs *antes* de procurar: um beacon
  // cadastrado depois da última sincronização não é "não encontrado", é
  // "nunca procurado" — e o cache dura 12 horas.
  //
  // Isso aparece no dia da instalação: o RH cadastra o beacon, o funcionário
  // aponta o celular para ele, e nada acontece sem explicação nenhuma.
  //
  // Só a configuração é rebaixada de imediato (chamada curta); a varredura só
  // se repete quando surgiu UUID que não existia — do contrário todo
  // funcionário longe do hangar pagaria 4 s a mais para reconfirmar o óbvio.
  if (Platform.OS === "ios" && iosIBeacons.leituras.length === 0) {
    const atualizados = uuidsIBeaconConhecidos(await sincronizarConfig(true));
    const conhecidos = new Set(uuidsProcurados);
    if (atualizados.some((uuid) => !conhecidos.has(uuid))) {
      uuidsProcurados = atualizados;
      iosIBeacons = await varrerIBeaconsIos(uuidsProcurados, TIMEOUT_BLE_MS);
    }
  }

  if (iosIBeacons.aviso) avisos.push(iosIBeacons.aviso);

  aoProgredir?.({ etapa: "wifi", detalhe: t("sinal.verificandoWifi") });
  const wifi = await coletarWifi(avisos);

  // O GPS roda mesmo com beacon encontrado, e de propósito: o backend cruza os
  // dois para detectar incoerência — um beacon do hangar "visto" de outra
  // cidade denuncia um anúncio falsificado.
  aoProgredir?.({ etapa: "gps", detalhe: t("sinal.obtendoLocalizacao") });
  const gps = await coletarGps(avisos);

  const relatados: BeaconRelatado[] = [
    ...beacons.eddystone.map((b) => ({
      protocol: "eddystone" as const,
      eddystone_namespace: b.namespace,
      eddystone_instance: b.instance,
      rssi: b.rssi,
    })),
    // Android e iOS chegam aqui pela mesma forma, por caminhos diferentes:
    // `beacons.ibeacon` vem do BLE cru (Android) e `iosIBeacons` do
    // CoreLocation. Um dos dois está sempre vazio.
    ...[...beacons.ibeacon, ...iosIBeacons.leituras].map((b) => ({
      protocol: "ibeacon" as const,
      ibeacon_uuid: b.uuid,
      ibeacon_major: b.major,
      ibeacon_minor: b.minor,
      rssi: b.rssi,
    })),
    ...beacons.macs.map((b) => ({
      protocol: "mac" as const,
      mac_address: b.mac,
      rssi: b.rssi,
    })),
  ]
    .filter((b) => rssiMedido(b.rssi))
    // Ordenado antes de cortar: se houver mais beacons do que o servidor
    // aceita, os que ficam de fora precisam ser os mais fracos.
    .sort((a, b) => b.rssi - a.rssi)
    .slice(0, MAXIMO_BEACONS_RELATADOS);

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
    vistos: beacons.vistos,
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
  return t("sinal.nenhum");
}
