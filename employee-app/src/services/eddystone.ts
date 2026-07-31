/**
 * Leitura de beacons Eddystone-UID a partir de um anúncio BLE.
 *
 * O `react-native-ble-plx` entrega `serviceData` como um mapa de UUID para
 * base64. Um quadro Eddystone-UID vem sob o service UUID `0xFEAA` com este
 * layout:
 *
 *     byte  0      tipo do quadro (0x00 = UID)
 *     byte  1      potência de transmissão calibrada
 *     bytes 2–11   namespace  (10 bytes)
 *     bytes 12–17  instance   (6 bytes)
 *     bytes 18–19  reservado
 *
 * **Os identificadores saem em hexadecimal minúsculo, sem separadores.** Não é
 * cosmético: o backend normaliza para essa mesma forma, e uma diferença de
 * grafia faria o beacon nunca casar — sem erro nenhum, ele simplesmente jamais
 * seria reconhecido.
 */

/** Service UUID do Eddystone, na forma completa que o BLE reporta. */
export const EDDYSTONE_SERVICE_UUID = "0000feaa-0000-1000-8000-00805f9b34fb";

/** Forma curta, aceita por alguns aparelhos Android. */
export const EDDYSTONE_SERVICE_UUID_CURTO = "feaa";

const FRAME_TYPE_UID = 0x00;
const TAMANHO_MINIMO_UID = 18;

export type LeituraEddystone = {
  namespace: string;
  instance: string;
  rssi: number;
};

/** Decodifica base64 em bytes, sem depender de `Buffer` (ausente no RN). */
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

function paraHex(bytes: Uint8Array): string {
  return Array.from(bytes)
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

/**
 * Extrai o identificador Eddystone de um anúncio, se houver.
 *
 * Devolve `null` para qualquer dispositivo que não seja um Eddystone-UID —
 * uma varredura num hangar encontra fones, relógios e o carro do vizinho, e
 * todos passam por aqui.
 */
export function lerEddystone(
  serviceData: Record<string, string> | null | undefined,
  rssi: number | null,
): LeituraEddystone | null {
  if (!serviceData || rssi === null) return null;

  // Fabricantes de aparelho divergem na forma do UUID reportado; aceitar as
  // duas evita perder beacon em modelos específicos de Android.
  const base64 =
    serviceData[EDDYSTONE_SERVICE_UUID] ??
    serviceData[EDDYSTONE_SERVICE_UUID.toUpperCase()] ??
    serviceData[EDDYSTONE_SERVICE_UUID_CURTO] ??
    serviceData[EDDYSTONE_SERVICE_UUID_CURTO.toUpperCase()];

  if (!base64) return null;

  const bytes = base64ParaBytes(base64);

  // Eddystone define também os quadros URL, TLM e EID. Só o UID carrega
  // identificador de local; os outros são descartados aqui.
  if (bytes.length < TAMANHO_MINIMO_UID || bytes[0] !== FRAME_TYPE_UID) {
    return null;
  }

  return {
    namespace: paraHex(bytes.slice(2, 12)),
    instance: paraHex(bytes.slice(12, 18)),
    rssi,
  };
}

/**
 * Consolida várias leituras do mesmo beacon, ficando com o sinal mais forte.
 *
 * Uma varredura de poucos segundos vê o mesmo beacon várias vezes, e o RSSI
 * oscila bastante entre anúncios. Enviar todas as leituras faria o backend
 * decidir com uma amostra ruim escolhida ao acaso.
 */
export function consolidar(leituras: LeituraEddystone[]): LeituraEddystone[] {
  const porIdentificador = new Map<string, LeituraEddystone>();

  for (const leitura of leituras) {
    const chave = `${leitura.namespace}:${leitura.instance}`;
    const atual = porIdentificador.get(chave);
    if (!atual || leitura.rssi > atual.rssi) {
      porIdentificador.set(chave, leitura);
    }
  }

  return Array.from(porIdentificador.values()).sort((a, b) => b.rssi - a.rssi);
}
