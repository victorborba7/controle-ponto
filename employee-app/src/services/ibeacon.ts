/**
 * Leitura de iBeacon a partir de um anúncio BLE.
 *
 * O iBeacon não usa `serviceData` como o Eddystone: ele vai no
 * `manufacturerData`, sob o código de fabricante da Apple (0x004C), com este
 * layout:
 *
 *     bytes 0–1    company ID = 0x4C 0x00 (little endian)
 *     byte  2      subtipo = 0x02 (iBeacon)
 *     byte  3      comprimento = 0x15 (21)
 *     bytes 4–19   UUID (16 bytes)
 *     bytes 20–21  major (big endian)
 *     bytes 22–23  minor (big endian)
 *     byte  24     potência calibrada
 *
 * **Isto funciona no Android, não no iOS** — e a distinção é a mesma que
 * motivou a decisão D8 do plano. O iOS filtra anúncios de iBeacon do
 * CoreBluetooth e só os entrega via CoreLocation, com o UUID conhecido de
 * antemão. Como o MVP valida no Android primeiro (D9), ler iBeacon aqui
 * resolve hoje; o iPhone (Etapa 9b) exigirá CoreLocation ou um beacon que
 * também transmita Eddystone.
 */

const COMPANY_ID_APPLE = 0x004c;
const SUBTIPO_IBEACON = 0x02;
const COMPRIMENTO_IBEACON = 0x15;
const TAMANHO_MINIMO = 25;

export type LeituraIBeacon = {
  uuid: string;
  major: number;
  minor: number;
  rssi: number;
};

function base64ParaBytes(base64: string): Uint8Array {
  const alfabeto =
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

  const limpo = base64.replace(/[^A-Za-z0-9+/]/g, "");
  const bytes: number[] = [];

  for (let i = 0; i < limpo.length; i += 4) {
    const n =
      (alfabeto.indexOf(limpo[i]) << 18) |
      (alfabeto.indexOf(limpo[i + 1]) << 12) |
      ((limpo[i + 2] ? alfabeto.indexOf(limpo[i + 2]) : 0) << 6) |
      (limpo[i + 3] ? alfabeto.indexOf(limpo[i + 3]) : 0);

    bytes.push((n >> 16) & 0xff);
    if (limpo[i + 2]) bytes.push((n >> 8) & 0xff);
    if (limpo[i + 3]) bytes.push(n & 0xff);
  }

  return Uint8Array.from(bytes);
}

/** UUID na forma canônica minúscula, igual à que o backend normaliza. */
function formatarUuid(bytes: Uint8Array): string {
  const hex = Array.from(bytes)
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");

  return [
    hex.slice(0, 8),
    hex.slice(8, 12),
    hex.slice(12, 16),
    hex.slice(16, 20),
    hex.slice(20, 32),
  ].join("-");
}

/**
 * Extrai o identificador iBeacon de um anúncio, se houver.
 *
 * Devolve `null` para qualquer outro dispositivo — uma varredura encontra
 * fones, relógios e TVs, e todos passam por aqui.
 */
export function lerIBeacon(
  manufacturerData: string | null | undefined,
  rssi: number | null,
): LeituraIBeacon | null {
  if (!manufacturerData || rssi === null) return null;

  const bytes = base64ParaBytes(manufacturerData);
  const inicio = acharInicioDoPayload(bytes);
  if (inicio === null) return null;

  return {
    uuid: formatarUuid(bytes.slice(inicio + 2, inicio + 18)),
    // Major e minor em big endian, ao contrário do company ID.
    major: (bytes[inicio + 18] << 8) | bytes[inicio + 19],
    minor: (bytes[inicio + 20] << 8) | bytes[inicio + 21],
    rssi,
  };
}

/**
 * Onde começa o payload do iBeacon (o byte `0x02` de subtipo).
 *
 * Duas formas convivem no mundo real, e a diferença decide se o beacon é
 * reconhecido ou some sem erro nenhum:
 *
 * - **Com o company ID** — `4C 00 02 15 <uuid> <major> <minor> <power>`. É o
 *   que sai quando a biblioteca entrega a estrutura de anúncio crua.
 * - **Sem o company ID** — `02 15 <uuid> ...`. É o que sai quando o Android
 *   já separou os dados por fabricante (`getManufacturerSpecificData` devolve
 *   um mapa indexado pelo company ID, com o valor já sem ele).
 *
 * Aceitar as duas custa cinco linhas e evita um modo de falha silencioso, em
 * que o beacon nunca aparece e nada indica o porquê.
 */
function acharInicioDoPayload(bytes: Uint8Array): number | null {
  // Forma com company ID: 4C 00 02 15
  if (
    bytes.length >= TAMANHO_MINIMO &&
    (bytes[0] | (bytes[1] << 8)) === COMPANY_ID_APPLE &&
    bytes[2] === SUBTIPO_IBEACON &&
    bytes[3] === COMPRIMENTO_IBEACON
  ) {
    return 2;
  }

  // Forma sem company ID: 02 15
  if (
    bytes.length >= TAMANHO_MINIMO - 2 &&
    bytes[0] === SUBTIPO_IBEACON &&
    bytes[1] === COMPRIMENTO_IBEACON
  ) {
    return 0;
  }

  return null;
}

/** Consolida leituras repetidas do mesmo beacon, ficando com o sinal mais forte. */
export function consolidarIBeacons(leituras: LeituraIBeacon[]): LeituraIBeacon[] {
  const porIdentificador = new Map<string, LeituraIBeacon>();

  for (const leitura of leituras) {
    const chave = `${leitura.uuid}:${leitura.major}:${leitura.minor}`;
    const atual = porIdentificador.get(chave);
    if (!atual || leitura.rssi > atual.rssi) {
      porIdentificador.set(chave, leitura);
    }
  }

  return Array.from(porIdentificador.values()).sort((a, b) => b.rssi - a.rssi);
}
