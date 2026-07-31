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

import { garantirPermissoesBluetooth } from "./permissoes";

export type DispositivoCru = {
  id: string;
  nome: string | null;
  nomeLocal: string | null;
  rssi: number | null;
  /** Quantas vezes este dispositivo apareceu durante a varredura. */
  anuncios: number;
  temManufacturerData: boolean;
  temServiceData: boolean;
  serviceUUIDs: string[];
  /** Primeiros bytes do manufacturerData, em hex — identifica o fabricante. */
  fabricante: string | null;
};

export type ResultadoCru = {
  dispositivos: DispositivoCru[];
  /** Total de callbacks recebidos, antes de agrupar por dispositivo. */
  anunciosRecebidos: number;
  duracaoMs: number;
  erro: string | null;
  parametros: string;
};

function primeirosBytes(base64: string | null | undefined, quantos = 4): string | null {
  if (!base64) return null;

  const alfabeto =
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
  const limpo = base64.replace(/[^A-Za-z0-9+/]/g, "");
  const bytes: number[] = [];

  for (let i = 0; i < limpo.length && bytes.length < quantos; i += 4) {
    const n =
      (alfabeto.indexOf(limpo[i]) << 18) |
      (alfabeto.indexOf(limpo[i + 1]) << 12) |
      ((limpo[i + 2] ? alfabeto.indexOf(limpo[i + 2]) : 0) << 6) |
      (limpo[i + 3] ? alfabeto.indexOf(limpo[i + 3]) : 0);
    bytes.push((n >> 16) & 0xff, (n >> 8) & 0xff, n & 0xff);
  }

  return bytes
    .slice(0, quantos)
    .map((b) => b.toString(16).padStart(2, "0"))
    .join(" ");
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
        encontrados.set(dispositivo.id, {
          id: dispositivo.id,
          nome: dispositivo.name ?? anterior?.nome ?? null,
          nomeLocal: dispositivo.localName ?? anterior?.nomeLocal ?? null,
          rssi:
            dispositivo.rssi !== null &&
            (anterior?.rssi === null ||
              anterior === undefined ||
              dispositivo.rssi > (anterior.rssi ?? -999))
              ? dispositivo.rssi
              : (anterior?.rssi ?? null),
          anuncios: (anterior?.anuncios ?? 0) + 1,
          temManufacturerData:
            Boolean(dispositivo.manufacturerData) || Boolean(anterior?.temManufacturerData),
          temServiceData:
            Boolean(dispositivo.serviceData) || Boolean(anterior?.temServiceData),
          serviceUUIDs: dispositivo.serviceUUIDs ?? anterior?.serviceUUIDs ?? [],
          fabricante:
            primeirosBytes(dispositivo.manufacturerData) ?? anterior?.fabricante ?? null,
        });
      },
    );
  });
}
