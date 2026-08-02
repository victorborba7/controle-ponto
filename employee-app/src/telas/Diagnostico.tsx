import * as Clipboard from "expo-clipboard";
import { useCallback, useMemo, useRef, useState } from "react";
import { Pressable, ScrollView, Text, TextInput, View } from "react-native";

import {
  coletarSinais,
  type BeaconRelatado,
  type DispositivoVisto,
  type SinaisColetados,
} from "../services/localizacao";
import {
  detectarRotacao,
  varrerComparando,
  varrerCru,
  type ResultadoComparado,
  type ResultadoCru,
} from "../services/varreduraCrua";
import { Aviso, Botao, Cartao, Legenda, Titulo, cores, estilosCampo } from "../ui";

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
  const [vistos, setVistos] = useState<DispositivoVisto[]>([]);
  const [avisos, setAvisos] = useState<string[]>([]);
  const [etapa, setEtapa] = useState<string | null>(null);
  const [copiado, setCopiado] = useState<string | null>(null);
  const [cru, setCru] = useState<ResultadoCru | null>(null);
  const [varrendoCru, setVarrendoCru] = useState(false);
  const [rotacao, setRotacao] = useState<string[]>([]);
  const [filtro, setFiltro] = useState("");
  const [comparado, setComparado] = useState<ResultadoComparado | null>(null);
  const [comparando, setComparando] = useState(false);

  const reconhecidos = cru?.dispositivos.filter((d) => d.reconhecido).length ?? 0;

  /**
   * Filtro por texto livre, sobre tudo que o dispositivo mostra.
   *
   * Numa varredura real aparecem dezenas de aparelhos; procurar um beacon
   * específico rolando a lista é inviável. Busca também nos bytes do anúncio,
   * que é como se acha um beacon cujo MAC mudou.
   */
  const dispositivosFiltrados = useMemo(() => {
    const alvo = filtro.trim().toLowerCase().replace(/[:\s-]/g, "");
    if (!cru) return [];
    if (!alvo) return cru.dispositivos;

    return cru.dispositivos.filter((d) =>
      [d.id, d.nome, d.nomeLocal, d.reconhecido, ...d.payloads, ...d.payloadsServico]
        .filter(Boolean)
        .some((campo) =>
          String(campo).toLowerCase().replace(/[:\s-]/g, "").includes(alvo),
        ),
    );
  }, [cru, filtro]);

  /**
   * Endereços já vistos para cada identidade de beacon, entre varreduras.
   *
   * Fica em `ref` para sobreviver às re-renderizações sem provocá-las: é
   * memória de diagnóstico, não estado de tela.
   */
  const historicoEnderecos = useRef(new Map<string, Set<string>>());

  /**
   * Varredura sem filtro nem interpretação, por mais tempo.
   *
   * Responde "o anúncio chega ao app?", que é pergunta diferente de "o app
   * entende o anúncio?". Quando um beacon some, é o descarte que esconde a
   * causa — aqui nada é descartado.
   */
  const varrerCruamente = useCallback(async () => {
    setVarrendoCru(true);
    setCru(null);
    try {
      const resultado = await varrerCru(12_000);
      setCru(resultado);
      // Comparando com as varreduras anteriores: se a mesma identidade de
      // beacon apareceu sob outro endereço, ele rotaciona — e aí cadastrar
      // por MAC não funciona.
      setRotacao(
        detectarRotacao(historicoEnderecos.current, resultado.dispositivos),
      );
    } finally {
      setVarrendoCru(false);
    }
  }, []);

  /**
   * Duas varreduras variando só o parâmetro `legacy` do rádio.
   *
   * É a única diferença conhecida entre o que este app pede ao Android e o
   * que o nRF Connect pede. Testar isso elimina ou confirma a hipótese sem
   * depender de reinstalar o app com o parâmetro trocado.
   */
  const compararParametros = useCallback(async () => {
    setComparando(true);
    setComparado(null);
    try {
      const resultado = await varrerComparando(8_000);
      setComparado(resultado);
      // A passada abrangente vê tudo que a outra vê, então é a melhor lista
      // para inspecionar depois.
      setCru(resultado.passadas[1]?.resultado ?? null);
    } finally {
      setComparando(false);
    }
  }, []);

  const varrer = useCallback(async () => {
    setSinais(null);
    setVistos([]);
    setCopiado(null);
    setEtapa("Procurando…");
    try {
      const resumo = await coletarSinais((p) => setEtapa(p.detalhe || null));
      setSinais(resumo.sinais);
      setVistos(resumo.vistos);
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

        <Botao
          titulo={cru ? "Varrer de novo (12s, cru)" : "Varredura crua (12s)"}
          variante="secundario"
          onPress={varrerCruamente}
          carregando={varrendoCru}
        />

        <Botao
          titulo="Comparar parâmetros (2 × 8s)"
          variante="secundario"
          onPress={compararParametros}
          carregando={comparando}
        />

        {comparado && (
          <Cartao>
            <Text style={{ color: cores.texto, fontWeight: "700", marginBottom: 8 }}>
              Comparação de parâmetros
            </Text>
            {comparado.conclusoes.map((linha) => (
              <Text
                key={linha}
                style={{
                  color: linha.startsWith("Nenhum") ? cores.aviso : cores.textoFraco,
                  fontSize: 13,
                  lineHeight: 19,
                  marginBottom: 6,
                }}
              >
                {linha}
              </Text>
            ))}
            <Legenda>
              A lista abaixo é a da passada abrangente, que enxerga tudo que a
              outra enxerga.
            </Legenda>
          </Cartao>
        )}

        {cru && (
          <Cartao>
            <Text style={{ color: cores.texto, fontWeight: "700", marginBottom: 8 }}>
              Varredura crua
            </Text>
            <Text style={{ color: cores.textoFraco, fontSize: 13, lineHeight: 19 }}>
              {cru.parametros}
              {"\n"}
              {cru.anunciosRecebidos} anúncio(s) recebido(s) ·{" "}
              {cru.dispositivos.length} dispositivo(s)
            </Text>
            {cru.erro && (
              <Text style={{ color: cores.erro, fontSize: 13, marginTop: 8 }}>
                Erro: {cru.erro}
              </Text>
            )}
            <Text
              style={{
                color: reconhecidos > 0 ? cores.acento : cores.aviso,
                fontSize: 13,
                fontWeight: "600",
                marginTop: 8,
              }}
            >
              {reconhecidos > 0
                ? `${reconhecidos} reconhecido(s) como beacon — aparecem no topo`
                : "Nenhum anúncio de beacon entre eles"}
            </Text>

            <Text style={{ color: cores.textoFraco, fontSize: 12, marginTop: 8 }}>
              Varra duas vezes com alguns minutos de intervalo: se um beacon
              reaparecer sob outro endereço, ele rotaciona o MAC.
            </Text>
          </Cartao>
        )}

        {cru && cru.dispositivos.length > 0 && (
          <TextInput
            style={estilosCampo.entrada}
            value={filtro}
            onChangeText={setFiltro}
            autoCapitalize="none"
            autoCorrect={false}
            placeholder="Filtrar por MAC, nome ou bytes do anúncio"
            placeholderTextColor={cores.textoFraco}
          />
        )}

        {rotacao.map((aviso) => (
          <Aviso key={aviso} tipo="aviso">
            {aviso}
          </Aviso>
        ))}

        {dispositivosFiltrados.map((d) => (
          <Pressable key={d.id} onPress={() => copiar(d.id, `cru-${d.id}`)}>
            <Cartao>
              <View
                style={{
                  flexDirection: "row",
                  justifyContent: "space-between",
                  alignItems: "center",
                }}
              >
                <Text
                  style={{ color: cores.texto, fontFamily: "monospace", fontSize: 14 }}
                  selectable
                >
                  {d.id.toUpperCase()}
                </Text>
                <Text style={{ color: cores.texto, fontWeight: "700" }}>
                  {d.rssi ?? "—"} dBm
                </Text>
              </View>

              {/* Endereço que rotaciona torna o cadastro por MAC inviável —
                  destacado porque é a diferença entre "sumiu" e "mudou". */}
              <Text
                style={{
                  color: d.tipoEndereco.includes("rotaciona")
                    ? cores.aviso
                    : cores.textoFraco,
                  fontSize: 12,
                  marginTop: 2,
                }}
              >
                endereço {d.tipoEndereco}
              </Text>

              {/* O intervalo é a assinatura mais estável do beacon: não muda
                  quando o endereço rotaciona, e é o que permite reconhecê-lo
                  comparando com o que o nRF Connect mostra. */}
              <Text style={{ color: cores.textoFraco, fontSize: 13, marginTop: 4 }}>
                {d.nome ?? d.nomeLocal ?? "(sem nome)"} · {d.anuncios} anúncio(s)
                {d.intervaloMs !== null ? ` · a cada ~${d.intervaloMs} ms` : ""}
              </Text>

              {d.reconhecido ? (
                <Text
                  style={{ color: cores.acento, fontSize: 12, marginTop: 6 }}
                  selectable
                >
                  ✓ {d.reconhecido}
                </Text>
              ) : (
                <Text style={{ color: cores.textoFraco, fontSize: 12, marginTop: 6 }}>
                  não reconhecido como beacon
                </Text>
              )}

              {/* Todos os payloads distintos, não só o último: um beacon que
                  alterna entre quadros esconderia o quadro que interessa. */}
              {d.payloads.map((payload, indice) => (
                <Text
                  key={payload}
                  style={{
                    color: cores.textoFraco,
                    fontFamily: "monospace",
                    fontSize: 11,
                    marginTop: indice === 0 ? 6 : 2,
                  }}
                  selectable
                >
                  mfr: {payload}
                </Text>
              ))}

              {d.payloadsServico.map((payload) => (
                <Text
                  key={payload}
                  style={{
                    color: cores.textoFraco,
                    fontFamily: "monospace",
                    fontSize: 11,
                    marginTop: 2,
                  }}
                  selectable
                >
                  svc: {payload}
                </Text>
              ))}

              {d.payloads.length > 1 && (
                <Text style={{ color: cores.info, fontSize: 11, marginTop: 4 }}>
                  alterna entre {d.payloads.length} quadros diferentes
                </Text>
              )}

              <Text style={{ color: cores.textoFraco, fontSize: 12, marginTop: 6 }}>
                {copiado === `cru-${d.id}` ? "Copiado!" : "Toque para copiar o MAC"}
              </Text>
            </Cartao>
          </Pressable>
        ))}

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
                  const { identificador, paraCopiar } = descreverBeacon(beacon);

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
                              color: corDoProtocolo[beacon.protocol],
                              fontWeight: "700",
                              fontSize: 13,
                            }}
                          >
                            {rotuloDoProtocolo[beacon.protocol]}
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

            <Secao titulo={`Todos os dispositivos vistos (${vistos.length})`}>
              <Legenda>
                Tudo que o rádio enxergou, inclusive aparelhos de passantes.
                Serve para achar um beacon que não anuncia formato conhecido —
                identifique-o pelo nome ou pelo sinal mais forte e cadastre pelo
                MAC. Esta lista fica só no aparelho; nada daqui é enviado.
              </Legenda>

              {vistos.slice(0, 15).map((d) => (
                <Pressable key={d.mac} onPress={() => copiar(d.mac, `mac-${d.mac}`)}>
                  <Cartao>
                    <View
                      style={{
                        flexDirection: "row",
                        justifyContent: "space-between",
                        alignItems: "center",
                      }}
                    >
                      <Text
                        style={{
                          color: cores.texto,
                          fontFamily: "monospace",
                          fontSize: 14,
                        }}
                        selectable
                      >
                        {d.mac.toUpperCase()}
                      </Text>
                      <Text style={{ color: cores.texto, fontWeight: "700" }}>
                        {d.rssi} dBm
                      </Text>
                    </View>

                    <Text style={{ color: cores.textoFraco, fontSize: 13, marginTop: 4 }}>
                      {d.nome ?? "(sem nome)"}
                      {d.reconhecido ? ` · ${d.reconhecido.toUpperCase()}` : ""}
                    </Text>

                    <Text style={{ color: cores.textoFraco, fontSize: 12, marginTop: 6 }}>
                      {copiado === `mac-${d.mac}` ? "MAC copiado!" : "Toque para copiar o MAC"}
                      {"  ·  "}
                      {sugerirLimiar(d.rssi)}
                    </Text>
                  </Cartao>
                </Pressable>
              ))}

              {vistos.length > 15 && (
                <Legenda>…e mais {vistos.length - 15} com sinal mais fraco.</Legenda>
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

const rotuloDoProtocolo = {
  eddystone: "EDDYSTONE-UID",
  ibeacon: "IBEACON",
  mac: "ENDEREÇO MAC",
} as const;

const corDoProtocolo = {
  eddystone: cores.acento,
  ibeacon: cores.info,
  mac: cores.aviso,
} as const;

/**
 * Como exibir e copiar o identificador de cada protocolo.
 *
 * O `switch` exaustivo é de propósito: um protocolo novo passa a dar erro de
 * compilação aqui, em vez de aparecer em branco na tela do técnico.
 */
function descreverBeacon(beacon: BeaconRelatado): {
  identificador: string;
  paraCopiar: string;
} {
  switch (beacon.protocol) {
    case "eddystone":
      return {
        identificador: `${beacon.eddystone_namespace} / ${beacon.eddystone_instance}`,
        paraCopiar: `${beacon.eddystone_namespace}\n${beacon.eddystone_instance}`,
      };
    case "ibeacon":
      return {
        identificador: `${beacon.ibeacon_uuid}\nmajor ${beacon.ibeacon_major} · minor ${beacon.ibeacon_minor}`,
        paraCopiar: `${beacon.ibeacon_uuid}\n${beacon.ibeacon_major}\n${beacon.ibeacon_minor}`,
      };
    case "mac":
      return {
        identificador: beacon.mac_address.toUpperCase(),
        paraCopiar: beacon.mac_address,
      };
  }
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
