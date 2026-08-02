/**
 * Tira `neverForLocation` da permissão BLUETOOTH_SCAN no manifesto final.
 *
 * ## Por que isto existe
 *
 * A partir do Android 12, quem declara
 *
 *     <uses-permission android:name="android.permission.BLUETOOTH_SCAN"
 *                      android:usesPermissionFlags="neverForLocation" />
 *
 * está prometendo ao sistema que não usa Bluetooth para inferir localização.
 * Em troca, o app fica dispensado de pedir permissão de localização — e o
 * sistema **remove dos resultados de varredura todo anúncio que permitiria
 * inferir posição**. Isso é exatamente a definição de um beacon: iBeacon e
 * Eddystone somem dos resultados.
 *
 * Aqui a promessa seria falsa. O app usa beacon precisamente para saber onde o
 * funcionário está, que é o caso de uso que a flag existe para excluir.
 *
 * ## Por que não basta configurar o plugin do ble-plx
 *
 * O `react-native-ble-plx` aceita `neverForLocation` (padrão `false`), mas essa
 * opção só decide se o plugin **acrescenta** a flag. O manifesto da própria
 * biblioteca, em `android/src/main/AndroidManifest.xml`, já a declara — e o
 * merge de manifestos do Gradle junta os manifestos das bibliotecas ao do app.
 * A flag entra pela porta dos fundos, sem aparecer em lugar nenhum do
 * `app.json`.
 *
 * O sintoma é cruel de diagnosticar: a varredura funciona, aparecem dezenas de
 * celulares, fones e televisores — e só o beacon nunca aparece. Parece defeito
 * do beacon ou do parser.
 *
 * `tools:remove` instrui o merge a apagar o atributo do resultado final,
 * inclusive o que vier das bibliotecas.
 *
 * ## Contrapartida
 *
 * Sem a flag, o Android 12+ passa a exigir `ACCESS_FINE_LOCATION` concedida em
 * tempo de execução **e** o serviço de localização ligado para entregar
 * resultados de varredura. Ver `src/services/permissoes.ts`.
 */

const { AndroidConfig, withAndroidManifest } = require("expo/config-plugins");

const BLUETOOTH_SCAN = "android.permission.BLUETOOTH_SCAN";

/** Exportada para teste: opera sobre o manifesto já lido. */
function removerNeverForLocation(androidManifest) {
  AndroidConfig.Manifest.ensureToolsAvailable(androidManifest);

  const permissoes = androidManifest.manifest["uses-permission"] ?? [];
  androidManifest.manifest["uses-permission"] = permissoes;

  let scan = permissoes.find((p) => p.$?.["android:name"] === BLUETOOTH_SCAN);

  if (!scan) {
    // Precisa existir no manifesto do app: `tools:remove` só age sobre um
    // elemento declarado aqui, não sobre o da biblioteca isoladamente.
    scan = { $: { "android:name": BLUETOOTH_SCAN, "tools:targetApi": "31" } };
    permissoes.push(scan);
  }

  delete scan.$["android:usesPermissionFlags"];
  scan.$["tools:remove"] = "android:usesPermissionFlags";

  return androidManifest;
}

const withVarreduraDeBeacon = (config) =>
  withAndroidManifest(config, (config) => {
    config.modResults = removerNeverForLocation(config.modResults);
    return config;
  });

module.exports = withVarreduraDeBeacon;
module.exports.removerNeverForLocation = removerNeverForLocation;
