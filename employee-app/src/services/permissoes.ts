/**
 * Permissões de tempo de execução para a varredura BLE.
 *
 * Declarar no `app.json` **não basta**. No Android 12 (API 31) o Bluetooth
 * deixou de depender de localização e ganhou permissões próprias —
 * `BLUETOOTH_SCAN` e `BLUETOOTH_CONNECT` —, que são *dangerous permissions* e
 * precisam ser pedidas explicitamente ao usuário.
 *
 * O sintoma de esquecer isso é enganoso: `startDeviceScan` falha de imediato e
 * a varredura devolve **zero dispositivos** — nem o beacon, nem o relógio do
 * vizinho. Parece defeito de hardware ou de formato do anúncio, e não é.
 *
 * Nas versões anteriores ao Android 12, quem libera a varredura é
 * `ACCESS_FINE_LOCATION`.
 *
 * No Android 12 e acima, `ACCESS_FINE_LOCATION` **continua necessária aqui**,
 * mesmo com `BLUETOOTH_SCAN` concedida. A dispensa só valeria para um app que
 * declarasse `neverForLocation` — e o preço dessa dispensa é o sistema apagar
 * os anúncios de beacon dos resultados, que é justamente o que este app
 * precisa ler. Ver `plugins/withVarreduraDeBeacon.js`.
 *
 * Ou seja: as duas permissões, em toda versão. A diferença por versão é só
 * quais existem para pedir.
 */

import { PermissionsAndroid, Platform } from "react-native";

export type ResultadoPermissao = {
  concedida: boolean;
  /** Mensagem para a tela quando faltar algo. */
  motivo?: string;
};

const ANDROID_12 = 31;

export async function garantirPermissoesBluetooth(): Promise<ResultadoPermissao> {
  // No iOS o pedido é feito pelo próprio sistema na primeira varredura, a
  // partir da descrição declarada no Info.plist.
  if (Platform.OS !== "android") return { concedida: true };

  const versao = Number(Platform.Version);

  if (versao >= ANDROID_12) {
    const resposta = await PermissionsAndroid.requestMultiple([
      PermissionsAndroid.PERMISSIONS.BLUETOOTH_SCAN,
      PermissionsAndroid.PERMISSIONS.BLUETOOTH_CONNECT,
      // Sem esta, o sistema entrega a varredura mas filtra dela os anúncios
      // de beacon — e o sintoma é ver dezenas de aparelhos e nenhum beacon.
      PermissionsAndroid.PERMISSIONS.ACCESS_FINE_LOCATION,
    ]);

    const negadas = Object.entries(resposta)
      .filter(([, estado]) => estado !== PermissionsAndroid.RESULTS.GRANTED)
      .map(([permissao]) => permissao);

    if (negadas.length) {
      const permanente = Object.values(resposta).some(
        (estado) => estado === PermissionsAndroid.RESULTS.NEVER_ASK_AGAIN,
      );
      // Distingue as duas por serem telas diferentes nos Ajustes, e por a de
      // localização ser a que o usuário não espera um app de ponto pedir.
      const soLocalizacao = negadas.every((p) => p.includes("ACCESS_"));

      return {
        concedida: false,
        motivo: soLocalizacao
          ? "Falta a permissão de localização. O Android a exige para entregar " +
            "os anúncios dos beacons — sem ela a varredura acha celulares e " +
            "fones, mas nenhum beacon." +
            (permanente
              ? " Libere em Ajustes → Aplicativos → Waypoint → Permissões → Localização."
              : "")
          : permanente
            ? "Permissão de Bluetooth negada. Libere em Ajustes → Aplicativos → Waypoint → Permissões."
            : "Sem permissão de Bluetooth não é possível detectar os beacons do local.",
      };
    }
    return { concedida: true };
  }

  // Android 11 e anteriores: a varredura BLE é tratada como coleta de
  // localização, então é ACCESS_FINE_LOCATION que a libera.
  const resposta = await PermissionsAndroid.request(
    PermissionsAndroid.PERMISSIONS.ACCESS_FINE_LOCATION,
  );

  if (resposta !== PermissionsAndroid.RESULTS.GRANTED) {
    return {
      concedida: false,
      motivo:
        "Nesta versão do Android, a permissão de localização é o que libera a leitura dos beacons.",
    };
  }
  return { concedida: true };
}
