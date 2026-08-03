/**
 * Configuração dos locais, baixada e cacheada do servidor.
 *
 * Serve a dois propósitos:
 *
 * 1. **Privacidade.** Para reconhecer um beacon pelo MAC, a varredura precisa
 *    ser aberta — e aberta ela enxerga dezenas de aparelhos alheios: celulares,
 *    fones, relógios de quem passa. Relatar todos os MACs ao servidor seria
 *    coletar identificadores de terceiros que nunca consentiram. Com a lista
 *    de MACs cadastrados em mãos, o app relata **apenas os que interessam**.
 *
 * 2. **Área sem sinal.** O cache permite reconhecer o local mesmo quando a
 *    batida vai para a fila offline.
 *
 * O `config_version` do servidor evita rebaixar a configuração inteira só para
 * descobrir que nada mudou — importa num hangar com conexão ruim.
 */

import AsyncStorage from "@react-native-async-storage/async-storage";

import { get } from "./api";

const CHAVE_CACHE = "ponto_config_locais";

/** Passado disso, vale reconsultar mesmo que a versão não tenha mudado. */
const VALIDADE_HORAS = 12;

export type BeaconConfigurado = {
  id: string;
  protocol: "eddystone" | "ibeacon" | "mac";
  eddystone_namespace: string | null;
  eddystone_instance: string | null;
  ibeacon_uuid: string | null;
  ibeacon_major: number | null;
  ibeacon_minor: number | null;
  mac_address: string | null;
  min_rssi: number;
};

export type ConfigLocal = {
  site_id: string;
  site_name: string;
  beacons: BeaconConfigurado[];
  wifi_networks: Array<{ id: string; ssid: string; bssid: string | null }>;
  config_version: string;
};

type Cache = {
  atualizadoEm: string;
  locais: ConfigLocal[];
};

export async function lerCache(): Promise<ConfigLocal[]> {
  const bruto = await AsyncStorage.getItem(CHAVE_CACHE);
  if (!bruto) return [];

  try {
    return (JSON.parse(bruto) as Cache).locais;
  } catch {
    await AsyncStorage.removeItem(CHAVE_CACHE);
    return [];
  }
}

async function cacheEstaVelho(): Promise<boolean> {
  const bruto = await AsyncStorage.getItem(CHAVE_CACHE);
  if (!bruto) return true;

  try {
    const cache = JSON.parse(bruto) as Cache;
    const idade = Date.now() - new Date(cache.atualizadoEm).getTime();
    return idade > VALIDADE_HORAS * 60 * 60 * 1000;
  } catch {
    return true;
  }
}

/**
 * Atualiza o cache a partir do servidor.
 *
 * Falha em silêncio de propósito: sem rede, o app segue com a configuração que
 * já tem — e é justamente aí que o cache serve para alguma coisa.
 */
export async function sincronizarConfig(forcar = false): Promise<ConfigLocal[]> {
  if (!forcar && !(await cacheEstaVelho())) {
    return lerCache();
  }

  try {
    const sites = await get<{ items: Array<{ id: string }> }>(
      "/sites?only_active=true",
    );

    const locais = await Promise.all(
      sites.items.map((site) =>
        get<ConfigLocal>(`/sites/${site.id}/location-config`),
      ),
    );

    await AsyncStorage.setItem(
      CHAVE_CACHE,
      JSON.stringify({ atualizadoEm: new Date().toISOString(), locais } satisfies Cache),
    );
    return locais;
  } catch {
    return lerCache();
  }
}

/**
 * MACs cadastrados, em minúsculas, para filtrar a varredura.
 *
 * Inclui o MAC de beacons de qualquer protocolo — um beacon cadastrado como
 * iBeacon pode ter o MAC preenchido no inventário, e reconhecê-lo por ele é
 * um sinal a mais, não um a menos.
 */
export function macsConhecidos(locais: ConfigLocal[]): Set<string> {
  const macs = new Set<string>();
  for (const local of locais) {
    for (const beacon of local.beacons) {
      if (beacon.mac_address) macs.add(beacon.mac_address.toLowerCase());
    }
  }
  return macs;
}

/**
 * UUIDs de iBeacon cadastrados, em maiúsculas.
 *
 * Existe por causa do iOS. Lá o iBeacon não chega pelo CoreBluetooth — só pelo
 * CoreLocation, que **exige saber o UUID de antemão**: não há varredura
 * genérica de iBeacon no iPhone. Sem esta lista, o app iOS não teria o que
 * procurar.
 *
 * O CoreLocation compara UUID sem diferenciar caixa, mas a API nativa espera a
 * forma canônica em maiúsculas — normalizar aqui evita depender disso.
 */
export function uuidsIBeaconConhecidos(locais: ConfigLocal[]): string[] {
  const uuids = new Set<string>();
  for (const local of locais) {
    for (const beacon of local.beacons) {
      if (beacon.ibeacon_uuid) uuids.add(beacon.ibeacon_uuid.toUpperCase());
    }
  }
  return Array.from(uuids);
}
