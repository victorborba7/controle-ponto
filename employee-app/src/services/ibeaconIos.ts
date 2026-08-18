/**
 * Leitura de iBeacon no iOS, via CoreLocation.
 *
 * ## Por que existe um caminho separado
 *
 * No Android, iBeacon é um anúncio BLE como outro qualquer: o
 * `react-native-ble-plx` entrega o `manufacturerData` e `ibeacon.ts` o
 * decodifica. **No iOS isso não acontece.** O CoreBluetooth filtra
 * deliberadamente os anúncios de iBeacon e não os entrega a app nenhum — a
 * Apple os reservou ao CoreLocation, que é uma API de localização, com
 * permissão de localização e um modelo próprio.
 *
 * A consequência prática, e é ela que molda este arquivo: **o CoreLocation não
 * faz varredura genérica**. Ele não responde "que iBeacons existem por perto?";
 * responde apenas "o beacon de UUID X está perto?". O UUID precisa ser
 * conhecido antes de procurar — daí `uuidsIBeaconConhecidos` em `configLocal`.
 *
 * ## Sobre a dependência
 *
 * `expo-beacon` é um pacote novo e de pouca adoção. Está atrás desta interface
 * de propósito: se ele for abandonado ou quebrar, o que muda é este arquivo, e
 * `localizacao.ts` não fica sabendo. A forma devolvida é a mesma
 * `LeituraIBeacon` que o caminho Android produz.
 */

import { Platform } from "react-native";

import { consolidarIBeacons, type LeituraIBeacon } from "./ibeacon";

export type ResultadoIBeaconIos = {
  leituras: LeituraIBeacon[];
  /** Motivo de não ter lido nada, para a tela de diagnóstico. */
  aviso: string | null;
};

const VAZIO: ResultadoIBeaconIos = { leituras: [], aviso: null };

/**
 * Procura os iBeacons cadastrados.
 *
 * Nunca lança: falha de beacon não pode impedir a batida, que ainda tem Wi-Fi e
 * GPS na cadeia de fallback. O motivo volta em `aviso`, para o diagnóstico.
 */
export async function varrerIBeaconsIos(
  uuids: string[],
  duracaoMs: number,
): Promise<ResultadoIBeaconIos> {
  if (Platform.OS !== "ios") return VAZIO;

  if (uuids.length === 0) {
    // Não é erro do aparelho: é local sem iBeacon cadastrado. Dizer isso evita
    // uma caça a defeito onde não há defeito.
    return {
      leituras: [],
      aviso:
        "Nenhum iBeacon cadastrado neste local. No iPhone é preciso conhecer o " +
        "UUID de antemão — o iOS não varre iBeacon genericamente.",
    };
  }

  let modulo: typeof import("expo-beacon");
  try {
    modulo = await import("expo-beacon");
  } catch {
    // Acontece num build sem o módulo nativo (Expo Go, por exemplo). O app
    // segue funcionando pelos outros elos da cadeia.
    return {
      leituras: [],
      aviso: "Leitura de iBeacon indisponível nesta versão do app.",
    };
  }

  try {
    const permissao = await modulo.default.requestPermissionsAsync();
    if (!concedida(permissao)) {
      return {
        leituras: [],
        aviso:
          "Sem permissão de localização, o iPhone não entrega os beacons. " +
          "Libere em Ajustes → Waypoint → Localização.",
      };
    }

    const encontrados = await modulo.scanForBeacons({ uuids, durationMs: duracaoMs });

    return {
      leituras: consolidarIBeacons(
        encontrados
          // RSSI 0 é o que o CoreLocation devolve quando não conseguiu medir;
          // tratá-lo como sinal forte colocaria um beacon inalcançável no topo.
          .filter((b) => typeof b.rssi === "number" && b.rssi < 0)
          .map((b) => ({
            uuid: b.uuid.toLowerCase(),
            major: b.major,
            minor: b.minor,
            rssi: b.rssi,
          })),
      ),
      aviso: null,
    };
  } catch (erro) {
    return {
      leituras: [],
      aviso: `Falha ao procurar iBeacons: ${
        erro instanceof Error ? erro.message : String(erro)
      }`,
    };
  }
}

/**
 * O pacote não tipa o retorno de permissão de forma estável entre versões,
 * então a checagem aceita as duas formas usuais do Expo.
 */
function concedida(resposta: unknown): boolean {
  if (typeof resposta === "boolean") return resposta;
  if (resposta && typeof resposta === "object") {
    const r = resposta as { granted?: boolean; status?: string };
    if (typeof r.granted === "boolean") return r.granted;
    if (typeof r.status === "string") return r.status === "granted";
  }
  // Sem resposta reconhecível, tenta varrer assim mesmo: o pior caso é uma
  // varredura vazia, e barrar aqui esconderia um beacon que funcionaria.
  return true;
}
