import { CameraView, useCameraPermissions } from "expo-camera";
import * as Location from "expo-location";
import { useCallback, useEffect, useRef, useState } from "react";
import { ScrollView, Text, View } from "react-native";

import type { Perfil } from "../services/api";
import { lerFila } from "../services/fila";
import {
  coletarSinais,
  encerrarBle,
  type ProgressoColeta,
  type ResumoColeta,
} from "../services/localizacao";
import { baterPonto, sincronizar } from "../services/ponto";
import { Aviso, Botao, Cartao, Legenda, Titulo, cores } from "../ui";

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

  // O BleManager mantém o rádio ligado enquanto existe; encerrar ao sair da
  // tela evita consumo de bateria com o app aberto e parado.
  useEffect(() => encerrarBle, []);

  useEffect(() => {
    Location.getForegroundPermissionsAsync().then((r) =>
      setPermissaoLocalizacao(r.granted),
    );
  }, []);

  const atualizarPendentes = useCallback(async () => {
    setPendentes((await lerFila()).length);
  }, []);

  // Ao abrir o app, tenta subir o que ficou represado no ponto cego de sinal.
  useEffect(() => {
    sincronizar()
      .then(atualizarPendentes)
      .catch(() => undefined);
  }, [atualizarPendentes]);

  async function pedirLocalizacao() {
    const resultado = await Location.requestForegroundPermissionsAsync();
    setPermissaoLocalizacao(resultado.granted);
  }

  async function registrar() {
    setEtapa({ nome: "coletando", detalhe: "Procurando beacons do local…" });

    let resumo: ResumoColeta;
    try {
      resumo = await coletarSinais((p: ProgressoColeta) =>
        setEtapa({ nome: "coletando", detalhe: p.detalhe }),
      );
    } catch {
      setEtapa({ nome: "erro", mensagem: "Falha ao ler os sinais do local." });
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
      setEtapa({ nome: "erro", mensagem: "Não foi possível capturar a foto." });
      return;
    }

    setEtapa({ nome: "enviando" });

    const resultado = await baterPonto(fotoUri, resumo.sinais);
    await atualizarPendentes();

    if (resultado.situacao === "enviado") {
      const entry = resultado.resposta.entry;
      setEtapa({
        nome: "concluido",
        titulo: entry.entry_type === "in" ? "Entrada registrada" : "Saída registrada",
        mensagem: resultado.resposta.message,
        tipo: entry.status === "approved" ? "sucesso" : "aviso",
      });
      return;
    }

    if (resultado.situacao === "enfileirado") {
      // Falha de rede não é erro para quem bateu o ponto: o registro está
      // guardado e sobe sozinho. Dizer "falhou" faria a pessoa bater de novo.
      setEtapa({
        nome: "concluido",
        titulo: "Ponto guardado",
        mensagem:
          "Sem conexão agora. O registro foi salvo com o horário de agora e será enviado assim que houver sinal.",
        tipo: "aviso",
      });
      return;
    }

    setEtapa({ nome: "erro", mensagem: resultado.motivo });
  }

  // ---- Permissões ----

  if (!permissaoCamera) {
    return <Centralizado><Legenda>Verificando permissões…</Legenda></Centralizado>;
  }

  if (!permissaoCamera.granted) {
    return (
      <Centralizado>
        <Titulo>Permissão da câmera</Titulo>
        <View style={{ marginVertical: 16 }}>
          <Legenda>
            O reconhecimento facial é o que comprova que foi você quem bateu o
            ponto. Sem acesso à câmera, o registro não pode ser feito.
          </Legenda>
        </View>
        <Botao titulo="Permitir câmera" onPress={pedirPermissaoCamera} />
      </Centralizado>
    );
  }

  if (permissaoLocalizacao === false) {
    return (
      <Centralizado>
        <Titulo>Permissão de localização</Titulo>
        <View style={{ marginVertical: 16, gap: 12 }}>
          <Legenda>
            A localização confirma que você está no local de trabalho. Ela é
            usada apenas no momento da batida — o app não acompanha seus
            deslocamentos.
          </Legenda>
          <Legenda>
            No Android, esta permissão também é o que libera a leitura dos
            beacons e da rede Wi-Fi do local.
          </Legenda>
        </View>
        <Botao titulo="Permitir localização" onPress={pedirLocalizacao} />
      </Centralizado>
    );
  }

  // ---- Resultado ----

  if (etapa.nome === "concluido" || etapa.nome === "erro") {
    const sucesso = etapa.nome === "concluido";
    return (
      <Centralizado>
        <Titulo>{sucesso ? etapa.titulo : "Não foi possível registrar"}</Titulo>
        <View style={{ marginVertical: 20, width: "100%" }}>
          <Aviso tipo={sucesso ? etapa.tipo : "erro"}>
            {sucesso ? etapa.mensagem : etapa.mensagem}
          </Aviso>
        </View>
        <View style={{ width: "100%", gap: 12 }}>
          <Botao titulo="Voltar" onPress={() => setEtapa({ nome: "ocioso" })} />
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
            {pendentes} {pendentes === 1 ? "registro aguardando" : "registros aguardando"}{" "}
            envio. Serão enviados assim que houver sinal.
          </Aviso>
        )}

        {ocupado ? (
          <Cartao>
            <Text style={{ color: cores.texto, fontSize: 16, textAlign: "center" }}>
              {mensagemDeEtapa}
            </Text>
          </Cartao>
        ) : (
          <Legenda>Centralize o rosto na moldura e toque em registrar.</Legenda>
        )}

        <Botao
          titulo="Registrar ponto"
          onPress={registrar}
          carregando={ocupado}
          desabilitado={ocupado}
        />

        <View style={{ flexDirection: "row", gap: 12 }}>
          <View style={{ flex: 1 }}>
            <Botao
              titulo="Meus registros"
              variante="secundario"
              onPress={aoAbrirHistorico}
            />
          </View>
          <View style={{ flex: 1 }}>
            <Botao
              titulo="Diagnóstico"
              variante="secundario"
              onPress={aoAbrirDiagnostico}
            />
          </View>
        </View>

        <Botao titulo="Sair" variante="texto" onPress={aoSair} />
      </View>
    </View>
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
