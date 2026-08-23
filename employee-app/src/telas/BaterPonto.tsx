import { CameraView, useCameraPermissions } from "expo-camera";
import * as Location from "expo-location";
import { useCallback, useEffect, useRef, useState } from "react";
import { Pressable, ScrollView, Text, TextInput, View } from "react-native";

import type { Perfil } from "../services/api";
import {
  CONFIG_PADRAO,
  faltaPreencher,
  lerCache as lerConfigBatida,
  pedeAlgo,
  sincronizarConfig,
  type ConfigBatida,
} from "../services/configBatida";
import { lerFila } from "../services/fila";
import {
  coletarSinais,
  encerrarBle,
  type ProgressoColeta,
  type ResumoColeta,
} from "../services/localizacao";
import { t } from "../i18n";
import { baterPonto, sincronizar } from "../services/ponto";
import { Aviso, Botao, Cartao, Legenda, Titulo, cores, estilosCampo } from "../ui";

type Etapa =
  | { nome: "ocioso" }
  | { nome: "coletando"; detalhe: string }
  | { nome: "capturando" }
  | { nome: "enviando" }
  | { nome: "concluido"; titulo: string; mensagem: string; tipo: "sucesso" | "aviso" }
  | { nome: "erro"; mensagem: string };

export function BaterPonto({
  perfil,
  aoAbrirHistorico,
  aoAbrirDiagnostico,
  aoSair,
}: {
  perfil: Perfil;
  aoAbrirHistorico: () => void;
  aoAbrirDiagnostico: () => void;
  aoSair: () => void;
}) {
  const cameraRef = useRef<CameraView>(null);
  const [permissaoCamera, pedirPermissaoCamera] = useCameraPermissions();
  const [permissaoLocalizacao, setPermissaoLocalizacao] = useState<boolean | null>(null);
  const [etapa, setEtapa] = useState<Etapa>({ nome: "ocioso" });
  const [pendentes, setPendentes] = useState(0);
  /**
   * Batidas que saíram da fila sem virar registro.
   *
   * Acontece quando o servidor recusa em definitivo — inclusive quando a foto
   * já não está no cache do aparelho. Sumir em silêncio é inaceitável num
   * sistema de ponto: é um dia de trabalho que ninguém vai reclamar porque
   * ninguém ficou sabendo.
   */
  const [descartadas, setDescartadas] = useState(0);

  /**
   * O que esta empresa pede na batida.
   *
   * Começa no padrão (nada) e é substituído pelo cache, e só então pelo
   * servidor. A ordem importa: a tela precisa estar utilizável no primeiro
   * quadro, mesmo sem sinal.
   */
  const [config, setConfig] = useState<ConfigBatida>(CONFIG_PADRAO);
  const [rotulo, setRotulo] = useState<string | null>(null);
  const [observacao, setObservacao] = useState("");

  // O BleManager mantém o rádio ligado enquanto existe; encerrar ao sair da
  // tela evita consumo de bateria com o app aberto e parado.
  useEffect(() => encerrarBle, []);

  useEffect(() => {
    Location.getForegroundPermissionsAsync().then((r) =>
      setPermissaoLocalizacao(r.granted),
    );
  }, []);

  // Cache primeiro, servidor depois: a tela fica utilizável mesmo sem sinal, e
  // se atualiza quando houver.
  useEffect(() => {
    lerConfigBatida()
      .then(setConfig)
      .then(() => sincronizarConfig().then(setConfig))
      .catch(() => undefined);
  }, []);

  const atualizarPendentes = useCallback(async () => {
    setPendentes((await lerFila()).length);
  }, []);

  // Ao abrir o app, tenta subir o que ficou represado no ponto cego de sinal.
  useEffect(() => {
    sincronizar()
      .then(async (resultado) => {
        if (resultado.descartadas > 0) setDescartadas(resultado.descartadas);
        await atualizarPendentes();
      })
      .catch(() => undefined);
  }, [atualizarPendentes]);

  async function pedirLocalizacao() {
    const resultado = await Location.requestForegroundPermissionsAsync();
    setPermissaoLocalizacao(resultado.granted);
  }

  async function registrar(encerraODia = false) {
    // Antes de acionar a câmera: numa área sem sinal a batida iria para a fila
    // e a recusa por campo faltando só apareceria horas depois, na
    // sincronização — quando já não dá para corrigir o que se ia escrever.
    const pendencia = faltaPreencher(config, { label: rotulo, note: observacao });
    if (pendencia) {
      setEtapa({ nome: "erro", mensagem: pendencia });
      return;
    }

    setEtapa({ nome: "coletando", detalhe: t("ponto.procurandoBeacons") });

    let resumo: ResumoColeta;
    try {
      resumo = await coletarSinais((p: ProgressoColeta) =>
        setEtapa({ nome: "coletando", detalhe: p.detalhe }),
      );
    } catch {
      setEtapa({ nome: "erro", mensagem: t("ponto.falhaSinais") });
      return;
    }

    setEtapa({ nome: "capturando" });

    let fotoUri: string;
    try {
      const foto = await cameraRef.current?.takePictureAsync({
        quality: 0.85,
        skipProcessing: false,
      });
      if (!foto?.uri) throw new Error("sem foto");
      fotoUri = foto.uri;
    } catch {
      setEtapa({ nome: "erro", mensagem: t("ponto.falhaFoto") });
      return;
    }

    setEtapa({ nome: "enviando" });

    const resultado = await baterPonto(fotoUri, resumo.sinais, {
      rotulo: rotulo ?? undefined,
      observacao,
      encerraODia,
    });
    await atualizarPendentes();

    if (resultado.situacao === "enviado") {
      const entry = resultado.resposta.entry;
      // Os campos só se limpam quando a batida foi de fato aceita: se ela ficou
      // na fila, o que a pessoa escreveu segue junto e continua visível.
      setRotulo(null);
      setObservacao("");
      setEtapa({
        nome: "concluido",
        // O rótulo que a pessoa escolheu diz mais que "Entrada"/"Saída": foi o
        // que ela leu na tela, e é como ela vai conferir se bateu o certo.
        titulo:
          entry.label ??
          (entry.entry_type === "in"
            ? t("ponto.entradaRegistrada")
            : entry.entry_type === "out"
              ? t("ponto.saidaRegistrada")
              : t("ponto.registroRegistrado")),
        mensagem: resultado.resposta.message,
        tipo: entry.status === "approved" ? "sucesso" : "aviso",
      });
      return;
    }

    if (resultado.situacao === "enfileirado") {
      // Falha de rede não é erro para quem bateu o ponto: o registro está
      // guardado e sobe sozinho. Dizer "falhou" faria a pessoa bater de novo.
      //
      // Mas dizer "sem conexão" para toda falha é pior: manda a pessoa esperar
      // por um sinal que já está lá, e esconde de quem instala o sistema a
      // única pista do que quebrou. O registro está guardado nos dois casos —
      // muda o que se deve fazer a respeito.
      setEtapa({
        nome: "concluido",
        titulo: t("ponto.guardado"),
        mensagem: resultado.ehFalhaDeRede
          ? t("ponto.semConexao")
          : `O registro foi salvo com o horário de agora e será reenviado, mas o servidor não aceitou o envio: ${resultado.motivo}`,
        tipo: "aviso",
      });
      return;
    }

    setEtapa({ nome: "erro", mensagem: resultado.motivo });
  }

  // ---- Permissões ----

  if (!permissaoCamera) {
    return <Centralizado><Legenda>{t("ponto.verificandoPermissoes")}</Legenda></Centralizado>;
  }

  if (!permissaoCamera.granted) {
    return (
      <Centralizado>
        <Titulo>{t("permissao.camera.titulo")}</Titulo>
        <View style={{ marginVertical: 16 }}>
          <Legenda>{t("permissao.camera.explicacao")}</Legenda>
        </View>
        <Botao titulo={t("permissao.camera.permitir")} onPress={pedirPermissaoCamera} />
      </Centralizado>
    );
  }

  if (permissaoLocalizacao === false) {
    return (
      <Centralizado>
        <Titulo>{t("permissao.local.titulo")}</Titulo>
        <View style={{ marginVertical: 16, gap: 12 }}>
          <Legenda>{t("permissao.local.explicacao")}</Legenda>
          <Legenda>{t("permissao.local.android")}</Legenda>
        </View>
        <Botao titulo={t("permissao.local.permitir")} onPress={pedirLocalizacao} />
      </Centralizado>
    );
  }

  // ---- Resultado ----

  if (etapa.nome === "concluido" || etapa.nome === "erro") {
    const sucesso = etapa.nome === "concluido";
    return (
      <Centralizado>
        <Titulo>{sucesso ? etapa.titulo : t("ponto.naoRegistrado")}</Titulo>
        <View style={{ marginVertical: 20, width: "100%" }}>
          <Aviso tipo={sucesso ? etapa.tipo : "erro"}>
            {sucesso ? etapa.mensagem : etapa.mensagem}
          </Aviso>
        </View>
        <View style={{ width: "100%", gap: 12 }}>
          <Botao titulo={t("ponto.voltar")} onPress={() => setEtapa({ nome: "ocioso" })} />
          <Botao
            titulo="Ver meus registros"
            variante="secundario"
            onPress={aoAbrirHistorico}
          />
        </View>
      </Centralizado>
    );
  }

  // ---- Câmera ----

  const ocupado = etapa.nome !== "ocioso";
  const mensagemDeEtapa =
    etapa.nome === "coletando"
      ? etapa.detalhe
      : etapa.nome === "capturando"
        ? "Capturando…"
        : etapa.nome === "enviando"
          ? "Enviando…"
          : "";

  return (
    <View style={{ flex: 1, backgroundColor: cores.fundo }}>
      <View style={{ padding: 16, paddingTop: 24 }}>
        <Text style={{ color: cores.texto, fontSize: 18, fontWeight: "600" }}>
          {perfil.nome}
        </Text>
        <Legenda>
          {perfil.matricula}
          {perfil.cargo ? ` · ${perfil.cargo}` : ""} · {perfil.empresa}
        </Legenda>
      </View>

      <View style={{ flex: 1, marginHorizontal: 16, borderRadius: 16, overflow: "hidden" }}>
        <CameraView
          ref={cameraRef}
          style={{ flex: 1 }}
          facing="front"
          // Espelhado só na exibição: enquadrar-se numa imagem não espelhada é
          // confuso, mas o arquivo precisa sair na orientação real.
          mirror
        />

        {/* Guia de enquadramento */}
        <View
          pointerEvents="none"
          style={{
            position: "absolute",
            top: "12%",
            left: "12%",
            right: "12%",
            bottom: "20%",
            borderWidth: 3,
            borderColor: ocupado ? cores.acento : "rgba(250,250,250,0.6)",
            borderRadius: 999,
          }}
        />
      </View>

      <View style={{ padding: 16, gap: 12 }}>
        {pendentes > 0 && (
          <Aviso tipo="aviso">
            {pendentes === 1
              ? t("ponto.fila.aguardando_um")
              : t("ponto.fila.aguardando_varios", { n: pendentes })}
          </Aviso>
        )}

        {descartadas > 0 && (
          <Aviso tipo="erro">
            {descartadas === 1
              ? t("ponto.fila.descartado_um")
              : t("ponto.fila.descartado_varios", { n: descartadas })}
          </Aviso>
        )}

        {!ocupado && pedeAlgo(config) && (
          <CamposDaBatida
            config={config}
            rotulo={rotulo}
            observacao={observacao}
            aoEscolherRotulo={setRotulo}
            aoEscreverObservacao={setObservacao}
          />
        )}

        {ocupado ? (
          <Cartao>
            <Text style={{ color: cores.texto, fontSize: 16, textAlign: "center" }}>
              {mensagemDeEtapa}
            </Text>
          </Cartao>
        ) : (
          <Legenda>{t("ponto.enquadre")}</Legenda>
        )}

        <Botao
          titulo={t("ponto.registrar")}
          onPress={() => registrar(false)}
          carregando={ocupado}
          desabilitado={ocupado}
        />

        {/* Botão próprio, e não um interruptor acima do de registrar.
            Encerrar a jornada é irreversível dentro do dia — quem esquecer de
            marcar volta amanhã com o dia aberto —, e um interruptor que se
            esquece ligado provocaria justamente o engano que ele deveria
            evitar. Dois botões tornam a escolha um ato, não um estado. */}
        <Botao
          titulo={t("ponto.baterSaida")}
          variante="secundario"
          onPress={() => registrar(true)}
          carregando={ocupado}
          desabilitado={ocupado}
        />

        <View style={{ flexDirection: "row", gap: 12 }}>
          <View style={{ flex: 1 }}>
            <Botao
              titulo={t("ponto.meusRegistros")}
              variante="secundario"
              onPress={aoAbrirHistorico}
            />
          </View>
          <View style={{ flex: 1 }}>
            <Botao
              titulo={t("ponto.diagnostico")}
              variante="secundario"
              onPress={aoAbrirDiagnostico}
            />
          </View>
        </View>

        <Botao titulo={t("ponto.sair")} variante="texto" onPress={aoSair} />
      </View>
    </View>
  );
}

/**
 * Os campos que a empresa configurou, acima do botão de registrar.
 *
 * Fica na mesma tela em vez de virar um passo antes: bater ponto é gesto de
 * segundos na porta do hangar, e uma tela a mais no caminho é a diferença
 * entre bater e deixar para depois.
 */
function CamposDaBatida({
  config,
  rotulo,
  observacao,
  aoEscolherRotulo,
  aoEscreverObservacao,
}: {
  config: ConfigBatida;
  rotulo: string | null;
  observacao: string;
  aoEscolherRotulo: (valor: string | null) => void;
  aoEscreverObservacao: (valor: string) => void;
}) {
  return (
    <Cartao>
      {config.label_mode === "list" && (
        <View style={{ gap: 8 }}>
          <Legenda>
            Tipo da batida{config.label_required ? "" : " (opcional)"}
          </Legenda>
          <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
            {config.labels.map((opcao) => {
              const escolhido = rotulo === opcao.name;
              return (
                <Pressable
                  key={opcao.name}
                  // Tocar de novo desmarca — sem isso, quem escolhe errado num
                  // campo opcional não tem como voltar a não escolher.
                  onPress={() => aoEscolherRotulo(escolhido ? null : opcao.name)}
                  style={{
                    paddingVertical: 10,
                    paddingHorizontal: 14,
                    borderRadius: 999,
                    borderWidth: 1,
                    borderColor: escolhido ? cores.acento : cores.borda,
                    backgroundColor: escolhido ? cores.acento : "transparent",
                  }}
                >
                  <Text
                    style={{
                      color: escolhido ? cores.fundo : cores.texto,
                      fontWeight: escolhido ? "700" : "500",
                    }}
                  >
                    {opcao.name}
                  </Text>
                </Pressable>
              );
            })}
          </View>
        </View>
      )}

      {config.label_mode === "free" && (
        <View style={{ gap: 8 }}>
          <Legenda>
            Tipo da batida{config.label_required ? "" : " (opcional)"}
          </Legenda>
          <TextInput
            style={estilosCampo.entrada}
            value={rotulo ?? ""}
            onChangeText={(texto) => aoEscolherRotulo(texto || null)}
            maxLength={60}
            placeholder={t("ponto.exemploRotulo")}
            placeholderTextColor={cores.textoFraco}
          />
        </View>
      )}

      {config.note_mode !== "hidden" && (
        <View style={{ gap: 8, marginTop: config.label_mode === "hidden" ? 0 : 16 }}>
          <Legenda>
            {config.note_prompt ??
              (config.note_mode === "required"
              ? t("ponto.observacao")
              : t("ponto.observacaoOpcional"))}
          </Legenda>
          <TextInput
            style={[estilosCampo.entrada, { minHeight: 72, textAlignVertical: "top" }]}
            value={observacao}
            onChangeText={aoEscreverObservacao}
            maxLength={500}
            multiline
            placeholder={
              config.note_mode === "required" ? t("ponto.obrigatorio") : t("ponto.opcional")
            }
            placeholderTextColor={cores.textoFraco}
          />
        </View>
      )}
    </Cartao>
  );
}

function Centralizado({ children }: { children: React.ReactNode }) {
  return (
    <ScrollView
      style={{ backgroundColor: cores.fundo }}
      contentContainerStyle={{
        flexGrow: 1,
        alignItems: "center",
        justifyContent: "center",
        padding: 24,
      }}
    >
      {children}
    </ScrollView>
  );
}
