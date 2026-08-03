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

const {
  AndroidConfig,
  withAndroidManifest,
  withInfoPlist,
} = require("expo/config-plugins");

const BLUETOOTH_SCAN = "android.permission.BLUETOOTH_SCAN";

/**
 * Modos de segundo plano que este app **não** usa.
 *
 * O `expo-beacon` acrescenta `location` e `bluetooth-central` ao
 * `UIBackgroundModes` de forma incondicional — a opção `backgroundGeolocation`
 * do plugin dele não desliga isso, e não há como optar por fora.
 *
 * Aqui o beacon só é procurado quando o funcionário toca em "Registrar ponto",
 * com o app aberto. Declarar segundo plano que não se usa é motivo conhecido
 * de recusa na revisão da App Store, e pede ao usuário mais acesso do que o
 * app precisa — num produto que já trata biometria, esse é o tipo de excesso
 * que custa caro.
 *
 * Se um dia existir "ponto automático ao entrar no hangar", isto sai daqui de
 * forma deliberada, junto com o código que justifica o modo.
 */
const MODOS_NAO_USADOS = ["location", "bluetooth-central"];

/** Textos que as bibliotecas deixam em inglês e apareceriam no diálogo do iOS. */
const TEXTOS_EM_PORTUGUES = {
  NSMicrophoneUsageDescription:
    "O microfone não é usado para bater ponto; o acesso é pedido pela câmera do sistema.",
  NSFaceIDUsageDescription:
    "O Face ID protege as credenciais de acesso guardadas neste aparelho.",
  NSMotionUsageDescription:
    "Os sensores de movimento não são usados para bater ponto.",
};

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

/** Exportada para teste: opera sobre o Info.plist já lido. */
function ajustarInfoPlist(infoPlist) {
  const modos = Array.isArray(infoPlist.UIBackgroundModes)
    ? infoPlist.UIBackgroundModes.filter((m) => !MODOS_NAO_USADOS.includes(m))
    : [];

  // Chave vazia é pior que chave ausente: o revisor vê a declaração e pergunta
  // por que ela está lá.
  if (modos.length > 0) infoPlist.UIBackgroundModes = modos;
  else delete infoPlist.UIBackgroundModes;

  // Só substitui o que ainda está no texto padrão em inglês — se alguém
  // escrever um texto próprio no app.json, ele vence.
  for (const [chave, texto] of Object.entries(TEXTOS_EM_PORTUGUES)) {
    const atual = infoPlist[chave];
    if (typeof atual === "string" && atual.startsWith("Allow $(PRODUCT_NAME)")) {
      infoPlist[chave] = texto;
    }
  }

  return infoPlist;
}

/**
 * Precisa ser o **primeiro** plugin da lista do `app.json`.
 *
 * Não é engano: **os mods do Expo executam na ordem inversa do registro.**
 * Cada `withInfoPlist` embrulha o anterior, então o último registrado roda
 * primeiro, e o primeiro registrado roda por último. Este plugin desfaz coisas
 * que os outros fizeram — os modos de segundo plano vêm do `expo-beacon`, os
 * textos em inglês vêm do `expo-camera`, do `expo-location` e do
 * `expo-secure-store` — e precisa ser o último a rodar para que os ajustes não
 * sejam sobrescritos.
 *
 * Verificado por medição, não por dedução: com o plugin em último lugar na
 * lista, o `UIBackgroundModes` voltava; em primeiro, some.
 */
const withVarreduraDeBeacon = (config) => {
  config = withAndroidManifest(config, (cfg) => {
    cfg.modResults = removerNeverForLocation(cfg.modResults);
    return cfg;
  });

  return withInfoPlist(config, (cfg) => {
    cfg.modResults = ajustarInfoPlist(cfg.modResults);
    return cfg;
  });
};

module.exports = withVarreduraDeBeacon;
module.exports.removerNeverForLocation = removerNeverForLocation;
module.exports.ajustarInfoPlist = ajustarInfoPlist;
