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
  /**
   * **Todos** os payloads de fabricante distintos vistos, em hex.
   *
   * Plural de propósito. Um mesmo aparelho pode alternar entre quadros
   * diferentes — um beacon que transmite iBeacon e um quadro de telemetria,
   * por exemplo. Guardar só o último faz o quadro que interessa desaparecer
   * sem deixar rastro, que é exatamente o descarte silencioso que esta tela
   * existe para evitar.
   */
  payloads: string[];
  serviceUUIDs: string[];
  /** Idem, para os payloads de serviço (é onde o Eddystone viaja). */
  payloadsServico: string[];
  /** Se os parsers do app reconhecem este anúncio, e como. */
  reconhecido: string | null;
  /** Se o endereço rotaciona por privacidade (ver `tipoDeEndereco`). */
  tipoEndereco: string;
  /**
   * Intervalo médio entre anúncios, em ms.
   *
   * É uma assinatura útil: o intervalo de transmissão de um beacon é fixo e
   * conhecido (o Aruba ARBT0100 sai de fábrica em ~505 ms), então bate com o
   * que o nRF Connect mostra mesmo quando o endereço mudou.
   */
  intervaloMs: number | null;
};

/**
 * Quantos payloads distintos guardar por aparelho.
 *
 * Aparelhos da rede Find My trocam o payload a cada anúncio; sem limite, uma
 * varredura de 12 s acumularia centenas de linhas inúteis por aparelho.
 */
const MAXIMO_PAYLOADS = 6;

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

/**
 * Parâmetros da varredura, para poder variar **um de cada vez**.
 *
 * Quando um app enxerga um beacon e o outro não, a diferença está em algum
 * parâmetro de varredura. Chutar qual é custa uma reinstalação por tentativa;
 * variar de forma controlada responde numa passada só.
 */
export type ParametrosVarredura = {
  /**
   * `true` (padrão do Android) reporta **só** anúncios legados; `false`
   * reporta legados **e** estendidos (BLE 5).
   *
   * O nome engana: `false` é o mais abrangente, e é o que o nRF Connect usa.
   * Um beacon que anuncie de forma estendida some por completo com `true`.
   */
  legacy: boolean;
  scanMode: number;
  rotulo: string;
};

export const PARAMETROS_PADRAO: ParametrosVarredura = {
  legacy: true,
  scanMode: ScanMode.LowLatency,
  rotulo: "legado apenas",
};

export const PARAMETROS_ABRANGENTES: ParametrosVarredura = {
  legacy: false,
  scanMode: ScanMode.LowLatency,
  rotulo: "legado + estendido",
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

export async function varrerCru(
  duracaoMs = 12_000,
  opcoes: ParametrosVarredura = PARAMETROS_PADRAO,
): Promise<ResultadoCru> {
  const parametros = `LowLatency · ${opcoes.rotulo} · sem filtro · ${duracaoMs / 1000}s`;

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
    /** Acumulador interno: o que só serve para calcular fica fora do tipo público. */
    type Acumulado = Omit<DispositivoCru, "payloads" | "payloadsServico" | "intervaloMs"> & {
      payloads: Set<string>;
      payloadsServico: Set<string>;
      primeiroEm: number;
      ultimoEm: number;
    };

    const encontrados = new Map<string, Acumulado>();
    let anunciosRecebidos = 0;
    let erro: string | null = null;
    let finalizado = false;

    /** Média entre anúncios; precisa de ao menos dois para existir. */
    const intervalo = (d: Acumulado): number | null =>
      d.anuncios >= 2 && d.ultimoEm > d.primeiroEm
        ? Math.round((d.ultimoEm - d.primeiroEm) / (d.anuncios - 1))
        : null;

    const finalizar = () => {
      if (finalizado) return;
      finalizado = true;
      ble.stopDeviceScan();
      ble.destroy();
      resolve({
        // Beacons reconhecidos primeiro, e só depois por sinal. Numa varredura
        // de hangar aparecem dezenas de aparelhos, e ordenar só por RSSI
        // enterra o beacon procurado no meio de fones e televisores.
        dispositivos: Array.from(encontrados.values())
          .map((d) => ({
            ...d,
            payloads: Array.from(d.payloads),
            payloadsServico: Array.from(d.payloadsServico),
            intervaloMs: intervalo(d),
          }))
          .sort((a, b) => {
            const pesoA = a.reconhecido ? 1 : 0;
            const pesoB = b.reconhecido ? 1 : 0;
            if (pesoA !== pesoB) return pesoB - pesoA;
            return (b.rssi ?? -999) - (a.rssi ?? -999);
          }),
        anunciosRecebidos,
        duracaoMs,
        erro,
        parametros,
      });
    };

    const relogio = setTimeout(finalizar, duracaoMs);

    ble.startDeviceScan(
      null,
      {
        allowDuplicates: true,
        scanMode: opcoes.scanMode,
        legacyScan: opcoes.legacy,
      },
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
        const agora = Date.now();

        // Acumula os payloads em vez de sobrescrever. Um aparelho que alterna
        // entre quadros mostraria só o último, e o quadro de beacon sumiria.
        const payloads = anterior?.payloads ?? new Set<string>();
        const hexFabricante = paraHex(dispositivo.manufacturerData);
        if (hexFabricante && payloads.size < MAXIMO_PAYLOADS) payloads.add(hexFabricante);

        const payloadsServico = anterior?.payloadsServico ?? new Set<string>();
        for (const bruto of Object.values(dispositivo.serviceData ?? {})) {
          const hex = paraHex(bruto);
          if (hex && payloadsServico.size < MAXIMO_PAYLOADS) payloadsServico.add(hex);
        }

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
          payloads,
          serviceUUIDs: dispositivo.serviceUUIDs ?? anterior?.serviceUUIDs ?? [],
          payloadsServico,
          reconhecido:
            reconhecer(dispositivo.serviceData, dispositivo.manufacturerData) ??
            anterior?.reconhecido ??
            null,
          tipoEndereco: tipoDeEndereco(dispositivo.id),
          primeiroEm: anterior?.primeiroEm ?? agora,
          ultimoEm: agora,
        });
      },
    );
  });
}

export type ResultadoComparado = {
  passadas: { rotulo: string; resultado: ResultadoCru }[];
  /** Conclusões prontas, para não exigir comparar duas listas na mão. */
  conclusoes: string[];
};

/**
 * Varre duas vezes, variando só o parâmetro `legacy`.
 *
 * É a diferença conhecida entre o que este app pede ao rádio e o que o nRF
 * Connect pede. Se um aparelho aparece só na passada abrangente, ele anuncia
 * de forma estendida, e a correção é trocar o parâmetro — não o parser. Se
 * aparece nas duas, ou em nenhuma, o problema está em outro lugar, e ter
 * eliminado esta hipótese já vale a varredura.
 */
export async function varrerComparando(duracaoMs = 8_000): Promise<ResultadoComparado> {
  const passadas: { rotulo: string; resultado: ResultadoCru }[] = [];

  for (const parametros of [PARAMETROS_PADRAO, PARAMETROS_ABRANGENTES]) {
    passadas.push({
      rotulo: parametros.rotulo,
      resultado: await varrerCru(duracaoMs, parametros),
    });
  }

  return { passadas, conclusoes: compararPassadas(passadas) };
}

/** Traduz as duas listas em frases sobre o que fazer. Exportada para teste. */
export function compararPassadas(
  passadas: { rotulo: string; resultado: ResultadoCru }[],
): string[] {
  const [padrao, abrangente] = passadas;
  if (!padrao || !abrangente) return [];

  const erro = padrao.resultado.erro ?? abrangente.resultado.erro;
  if (erro) return [`Varredura falhou: ${erro}`];

  const conclusoes: string[] = [];
  const idsPadrao = new Set(padrao.resultado.dispositivos.map((d) => d.id));

  // Endereço rotativo faria qualquer aparelho parecer "só na 2ª passada" por
  // acaso, então só conta o que o rádio classificaria de forma diferente.
  const soNoAbrangente = abrangente.resultado.dispositivos.filter(
    (d) => !idsPadrao.has(d.id),
  );
  const beaconsSoNoAbrangente = soNoAbrangente.filter((d) => d.reconhecido);

  if (beaconsSoNoAbrangente.length > 0) {
    conclusoes.push(
      `${beaconsSoNoAbrangente.length} beacon(s) aparecem SÓ com anúncio ` +
        `estendido. É a causa: o app precisa varrer com legacy=false.`,
    );
  }

  const reconhecidos =
    padrao.resultado.dispositivos.filter((d) => d.reconhecido).length +
    beaconsSoNoAbrangente.length;

  if (reconhecidos === 0) {
    conclusoes.push(
      "Nenhum beacon reconhecido em nenhuma das duas passadas — o parâmetro " +
        "legacy não é a causa. O anúncio não está chegando ao app.",
    );
  }

  conclusoes.push(
    `${padrao.resultado.dispositivos.length} aparelho(s) só com legado, ` +
      `${abrangente.resultado.dispositivos.length} com legado + estendido ` +
      `(${soNoAbrangente.length} exclusivo(s) da 2ª passada).`,
  );

  return conclusoes;
}
