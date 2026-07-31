import * as Clipboard from "expo-clipboard";
import { useCallback, useState } from "react";
import { Pressable, ScrollView, Text, View } from "react-native";

import { coletarSinais, type SinaisColetados } from "../services/localizacao";
import { Aviso, Botao, Cartao, Legenda, Titulo, cores } from "../ui";

/**
 * Diagnóstico dos sinais do local.
 *
 * Existe para a instalação, não para o uso diário: ao montar os beacons no
 * hangar, alguém precisa descobrir **o que cada um transmite** e **com que
 * força**, para cadastrar no painel e calibrar o limiar de RSSI.
 *
 * Usa exatamente o mesmo código de leitura da tela de ponto. Isso é o ponto
 * principal: um scanner BLE genérico diria que o beacon está transmitindo,
 * mas não provaria que *este app* consegue lê-lo. Se o identificador aparecer
 * aqui, aparecerá na batida.
 */
export function Diagnostico({ aoVoltar }: { aoVoltar: () => void }) {
  const [sinais, setSinais] = useState<SinaisColetados | null>(null);
  const [avisos, setAvisos] = useState<string[]>([]);
  const [etapa, setEtapa] = useState<string | null>(null);
  const [copiado, setCopiado] = useState<string | null>(null);

  const varrer = useCallback(async () => {
    setSinais(null);
    setCopiado(null);
    setEtapa("Procurando…");
    try {
      const resumo = await coletarSinais((p) => setEtapa(p.detalhe || null));
      setSinais(resumo.sinais);
      setAvisos(resumo.avisos);
    } catch {
      setAvisos(["Falha ao varrer os sinais."]);
    } finally {
      setEtapa(null);
    }
  }, []);

  async function copiar(texto: string, rotulo: string) {
    await Clipboard.setStringAsync(texto);
    setCopiado(rotulo);
  }

  return (
    <View style={{ flex: 1, backgroundColor: cores.fundo }}>
      <ScrollView contentContainerStyle={{ padding: 16, gap: 16 }}>
        <View>
          <Titulo>Diagnóstico do local</Titulo>
          <Legenda>
            Aproxime o celular do beacon e toque em varrer. Os identificadores
            que aparecerem são os que devem ser cadastrados no painel.
          </Legenda>
        </View>

        <Botao
          titulo={etapa ?? "Varrer sinais"}
          onPress={varrer}
          carregando={etapa !== null}
        />

        {avisos.map((aviso) => (
          <Aviso key={aviso} tipo="aviso">
            {aviso}
          </Aviso>
        ))}

        {sinais && (
          <>
            <Secao titulo={`Beacons (${sinais.beacons.length})`}>
              {sinais.beacons.length === 0 ? (
                <Aviso tipo="erro">
                  Nenhum beacon reconhecido. Verifique se ele está ligado, se
                  transmite Eddystone-UID ou iBeacon, e se o Bluetooth e a
                  permissão de localização estão liberados.
                </Aviso>
              ) : (
                sinais.beacons.map((beacon, indice) => {
                  const identificador =
                    beacon.protocol === "eddystone"
                      ? `${beacon.eddystone_namespace} / ${beacon.eddystone_instance}`
                      : `${beacon.ibeacon_uuid}\nmajor ${beacon.ibeacon_major} · minor ${beacon.ibeacon_minor}`;

                  const paraCopiar =
                    beacon.protocol === "eddystone"
                      ? `${beacon.eddystone_namespace}\n${beacon.eddystone_instance}`
                      : `${beacon.ibeacon_uuid}\n${beacon.ibeacon_major}\n${beacon.ibeacon_minor}`;

                  return (
                    <Pressable
                      key={indice}
                      onPress={() => copiar(paraCopiar, `beacon-${indice}`)}
                    >
                      <Cartao>
                        <View
                          style={{
                            flexDirection: "row",
                            justifyContent: "space-between",
                            marginBottom: 8,
                          }}
                        >
                          <Text
                            style={{
                              color:
                                beacon.protocol === "eddystone"
                                  ? cores.acento
                                  : cores.info,
                              fontWeight: "700",
                              fontSize: 13,
                            }}
                          >
                            {beacon.protocol === "eddystone"
                              ? "EDDYSTONE-UID"
                              : "IBEACON"}
                          </Text>
                          <Text style={{ color: cores.texto, fontWeight: "700" }}>
                            {beacon.rssi} dBm
                          </Text>
                        </View>

                        <Text
                          style={{
                            color: cores.texto,
                            fontFamily: "monospace",
                            fontSize: 13,
                            lineHeight: 19,
                          }}
                          selectable
                        >
                          {identificador}
                        </Text>

                        <Text style={{ color: cores.textoFraco, fontSize: 12, marginTop: 8 }}>
                          {copiado === `beacon-${indice}`
                            ? "Copiado!"
                            : "Toque para copiar"}
                          {"  ·  "}
                          {sugerirLimiar(beacon.rssi)}
                        </Text>
                      </Cartao>
                    </Pressable>
                  );
                })
              )}
            </Secao>

            <Secao titulo={`Wi-Fi (${sinais.wifi.length})`}>
              {sinais.wifi.length === 0 ? (
                <Legenda>
                  Nenhuma rede identificada. No Android, a leitura do SSID exige
                  a permissão de localização.
                </Legenda>
              ) : (
                sinais.wifi.map((rede) => (
                  <Pressable
                    key={rede.ssid}
                    onPress={() => copiar(rede.bssid ?? rede.ssid, "wifi")}
                  >
                    <Cartao>
                      <Text style={{ color: cores.texto, fontWeight: "600" }}>
                        {rede.ssid}
                      </Text>
                      <Text
                        style={{
                          color: cores.textoFraco,
                          fontFamily: "monospace",
                          fontSize: 13,
                          marginTop: 4,
                        }}
                        selectable
                      >
                        {rede.bssid ?? "BSSID não disponível"}
                      </Text>
                      <Text style={{ color: cores.textoFraco, fontSize: 12, marginTop: 8 }}>
                        {copiado === "wifi" ? "Copiado!" : "Toque para copiar"}
                      </Text>
                    </Cartao>
                  </Pressable>
                ))
              )}
            </Secao>

            <Secao titulo="GPS">
              {sinais.gps ? (
                <Pressable
                  onPress={() =>
                    copiar(`${sinais.gps!.latitude}\n${sinais.gps!.longitude}`, "gps")
                  }
                >
                  <Cartao>
                    <Text
                      style={{
                        color: cores.texto,
                        fontFamily: "monospace",
                        fontSize: 13,
                      }}
                      selectable
                    >
                      {sinais.gps.latitude.toFixed(6)}, {sinais.gps.longitude.toFixed(6)}
                    </Text>
                    <Text style={{ color: cores.textoFraco, fontSize: 13, marginTop: 4 }}>
                      precisão ±{Math.round(sinais.gps.accuracy_m)} m
                    </Text>
                    <Text style={{ color: cores.textoFraco, fontSize: 12, marginTop: 8 }}>
                      {copiado === "gps" ? "Copiado!" : "Toque para copiar"}
                    </Text>
                  </Cartao>
                </Pressable>
              ) : (
                <Legenda>Localização indisponível.</Legenda>
              )}
            </Secao>
          </>
        )}
      </ScrollView>

      <View style={{ padding: 16 }}>
        <Botao titulo="Voltar" variante="secundario" onPress={aoVoltar} />
      </View>
    </View>
  );
}

/**
 * Limiar sugerido a partir da leitura atual.
 *
 * 5 dBm de folga abaixo do medido, como recomenda o guia de instalação: o RSSI
 * oscila naturalmente, e um limiar justo demais gera falha intermitente — o
 * pior tipo de falha para diagnosticar em campo.
 */
function sugerirLimiar(rssi: number): string {
  return `sugestão de limiar: ${rssi - 5} dBm`;
}

function Secao({ titulo, children }: { titulo: string; children: React.ReactNode }) {
  return (
    <View style={{ gap: 8 }}>
      <Text style={{ color: cores.textoFraco, fontSize: 13, fontWeight: "600" }}>
        {titulo.toUpperCase()}
      </Text>
      {children}
    </View>
  );
}
