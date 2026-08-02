/**
 * Varredura crua, para diagnóstico.
 *
 * Reporta **tudo** que o rádio entrega, sem filtro, sem interpretação e sem
 * descartar nada — inclusive dispositivos sem RSSI ou sem nome. É a ferramenta
 * para responder a pergunta "o anúncio deste beacon chega ao app?", que é
 * diferente de "o app entende este beacon".
 *
 * Existe separada da coleta normal de propósito: a coleta descarta o que não
 * interessa, e é justamente o descarte que esconde a causa quando algo some.
 */

import { BleManager, ScanMode, State as BleState } from "react-native-ble-plx";

import { lerEddystone } from "./eddystone";
import { lerIBeacon } from "./ibeacon";
import { garantirPermissoesBluetooth } from "./permissoes";

export type DispositivoCru = {
  id: string;
  nome: string | null;
  nomeLocal: string | null;
  rssi: number | null;
  /** Quantas vezes este dispositivo apareceu durante a varredura. */
  anuncios: number;
  /** manufacturerData inteiro em hex — permite decodificar o anúncio à mão. */
  manufacturerHex: string | null;
  serviceUUIDs: string[];
  serviceDataHex: string | null;
  /** Se os parsers do app reconhecem este anúncio, e como. */
  reconhecido: string | null;
  /** Se o endereço rotaciona por privacidade (ver `tipoDeEndereco`). */
  tipoEndereco: string;
};

/**
 * Palpite sobre o tipo do endereço BLE, pelos dois bits mais altos.
 *
 * **É palpite mesmo, e o texto diz isso.** Os bits só têm significado se o
 * endereço for aleatório; um endereço público é atribuído pelo IEEE e pode
 * ter qualquer valor. Como o `ble-plx` não expõe a flag de tipo do endereço,
 * não há como distinguir os dois casos a partir do MAC.
 *
 *     11 → aleatório estático, ou público
 *     01 → privado resolvível (rotaciona), ou público
 *     00 → privado não resolvível (rotaciona), ou público
 *     10 → só pode ser público — não é subtipo aleatório válido
 *
 * Por isso a resposta confiável sobre rotação não vem daqui: vem de observar
 * o mesmo beacon aparecer sob endereços diferentes entre duas varreduras
 * (ver `detectarRotacao`). Medir é melhor que deduzir.
 */
export function tipoDeEndereco(mac: string): string {
  const primeiro = parseInt(mac.slice(0, 2), 16);
  if (Number.isNaN(primeiro)) return "desconhecido";

  switch (primeiro >> 6) {
    case 0b10:
      return "público (fixo)";
    case 0b11:
      return "fixo, ou público";
    default:
      // 01 e 00 são os padrões de endereço privado, que rotaciona.
      return "possivelmente rotativo";
  }
}

/**
 * Detecta rotação de endereço por observação, não por dedução.
 *
 * Se o mesmo beacon — mesma identidade de anúncio — aparece sob endereços
 * diferentes entre varreduras, ele rotaciona. Isso é prova, ao contrário do
 * palpite pelos bits.
 *
 * Importa porque muda a decisão de cadastro: com endereço rotativo,
 * identificar por MAC não funciona, e é preciso usar iBeacon ou Eddystone.
 */
export function detectarRotacao(
  historico: Map<string, Set<string>>,
  dispositivos: DispositivoCru[],
): string[] {
  const avisos: string[] = [];

  for (const dispositivo of dispositivos) {
    if (!dispositivo.reconhecido) continue;

    const enderecos = historico.get(dispositivo.reconhecido) ?? new Set<string>();
    enderecos.add(dispositivo.id);
    historico.set(dispositivo.reconhecido, enderecos);

    if (enderecos.size > 1) {
      avisos.push(
        `${dispositivo.reconhecido} já apareceu sob ${enderecos.size} endereços ` +
          `diferentes — ele ROTACIONA o MAC. Cadastre por iBeacon/Eddystone, ` +
          `não por endereço.`,
      );
    }
  }

  return avisos;
}

export type ResultadoCru = {
  dispositivos: DispositivoCru[];
  /** Total de callbacks recebidos, antes de agrupar por dispositivo. */
  anunciosRecebidos: number;
  duracaoMs: number;
  erro: string | null;
  parametros: string;
};

/** Converte base64 em hexadecimal legível, para decodificar o anúncio à mão. */
export function paraHex(base64: string | null | undefined, maximo = 32): string | null {
  if (!base64) return null;

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

  const hex = bytes
    .slice(0, maximo)
    .map((b) => b.toString(16).padStart(2, "0"))
    .join(" ");

  return bytes.length > maximo ? `${hex} … (+${bytes.length - maximo})` : hex;
}

/**
 * O que os parsers do app enxergam neste anúncio.
 *
 * É o que separa "o anúncio não chega" de "o anúncio chega mas não é
 * entendido" — dois problemas com o mesmo sintoma e correções opostas.
 */
export function reconhecer(
  serviceData: Record<string, string> | null | undefined,
  manufacturerData: string | null | undefined,
): string | null {
  const eddy = lerEddystone(serviceData, -50);
  if (eddy) return `Eddystone ${eddy.namespace} / ${eddy.instance}`;

  const ibec = lerIBeacon(manufacturerData, -50);
  if (ibec) return `iBeacon ${ibec.uuid} · ${ibec.major}/${ibec.minor}`;

  return null;
}

export async function varrerCru(duracaoMs = 12_000): Promise<ResultadoCru> {
  const parametros = `LowLatency · legacy · sem filtro · ${duracaoMs / 1000}s`;

  const permissao = await garantirPermissoesBluetooth();
  if (!permissao.concedida) {
    return {
      dispositivos: [],
      anunciosRecebidos: 0,
      duracaoMs,
      erro: permissao.motivo ?? "Sem permissão de Bluetooth",
      parametros,
    };
  }

  const ble = new BleManager();
  const estado = await ble.state();

  if (estado !== BleState.PoweredOn) {
    ble.destroy();
    return {
      dispositivos: [],
      anunciosRecebidos: 0,
      duracaoMs,
      erro: `Bluetooth não está ligado (estado: ${estado})`,
      parametros,
    };
  }

  return new Promise((resolve) => {
    const encontrados = new Map<string, DispositivoCru>();
    let anunciosRecebidos = 0;
    let erro: string | null = null;
    let finalizado = false;

    const finalizar = () => {
      if (finalizado) return;
      finalizado = true;
      ble.stopDeviceScan();
      ble.destroy();
      resolve({
        dispositivos: Array.from(encontrados.values()).sort(
          (a, b) => (b.rssi ?? -999) - (a.rssi ?? -999),
        ),
        anunciosRecebidos,
        duracaoMs,
        erro,
        parametros,
      });
    };

    const relogio = setTimeout(finalizar, duracaoMs);

    ble.startDeviceScan(
      null,
      { allowDuplicates: true, scanMode: ScanMode.LowLatency, legacyScan: true },
      (falha, dispositivo) => {
        if (falha) {
          erro = falha.reason ?? falha.message ?? String(falha);
          clearTimeout(relogio);
          finalizar();
          return;
        }
        if (!dispositivo) return;

        anunciosRecebidos += 1;

        // Sem descartar por RSSI ausente: o objetivo aqui é ver TUDO.
        const anterior = encontrados.get(dispositivo.id);
        const rssiAtual = dispositivo.rssi;

        encontrados.set(dispositivo.id, {
          id: dispositivo.id,
          nome: dispositivo.name ?? anterior?.nome ?? null,
          nomeLocal: dispositivo.localName ?? anterior?.nomeLocal ?? null,
          // Fica com o sinal mais forte visto: o RSSI oscila muito entre
          // anúncios, e o pico é o que melhor indica a proximidade real.
          rssi:
            rssiAtual !== null && rssiAtual > (anterior?.rssi ?? -999)
              ? rssiAtual
              : (anterior?.rssi ?? null),
          anuncios: (anterior?.anuncios ?? 0) + 1,
          manufacturerHex:
            paraHex(dispositivo.manufacturerData) ?? anterior?.manufacturerHex ?? null,
          serviceUUIDs: dispositivo.serviceUUIDs ?? anterior?.serviceUUIDs ?? [],
          serviceDataHex:
            paraHex(Object.values(dispositivo.serviceData ?? {})[0]) ??
            anterior?.serviceDataHex ??
            null,
          reconhecido:
            reconhecer(dispositivo.serviceData, dispositivo.manufacturerData) ??
            anterior?.reconhecido ??
            null,
          tipoEndereco: tipoDeEndereco(dispositivo.id),
        });
      },
    );
  });
}
