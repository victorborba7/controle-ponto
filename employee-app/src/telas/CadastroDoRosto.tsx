import { CameraView, useCameraPermissions } from "expo-camera";
import { useRef, useState } from "react";
import { Image, ScrollView, Text, View } from "react-native";

import { t } from "../i18n";
import type { Perfil } from "../services/api";
import {
  MINIMO_DE_FOTOS,
  cadastrarRosto,
  type FotoRecusada,
} from "../services/cadastroFacial";
import { Aviso, Botao, Cartao, Legenda, Titulo, cores } from "../ui";
import { VERSAO_DO_TERMO } from "./Consentimento";

/**
 * Cadastro do próprio rosto, no primeiro acesso.
 *
 * Substitui a ida ao RH. O servidor aceita **uma vez só**: depois de existir
 * rosto ativo, refazer volta a ser tarefa do RH.
 *
 * ## Por que três fotos, e com instruções diferentes
 *
 * Um único embedding erra muito com mudança de luz, óculos ou barba (decisão
 * D4). O que o modelo precisa não são três cliques iguais, e sim três
 * *condições* diferentes — por isso cada passo pede uma pose distinta em vez de
 * repetir "tire uma foto".
 */

// As chaves, e não os textos: `PASSOS` é constante de módulo e seria montada
// antes de qualquer render, congelando o idioma de forma correta mas frágil —
// traduzir na hora de exibir deixa isso óbvio para quem mexer depois.
const PASSOS = [
  { titulo: "cadastro.passo1.titulo", instrucao: "cadastro.passo1.instrucao" },
  { titulo: "cadastro.passo2.titulo", instrucao: "cadastro.passo2.instrucao" },
  { titulo: "cadastro.passo3.titulo", instrucao: "cadastro.passo3.instrucao" },
] as const;

type Estado =
  | { nome: "capturando" }
  | { nome: "enviando" }
  | { nome: "erro"; mensagem: string; recusadas?: FotoRecusada[] };

export function CadastroDoRosto({
  perfil,
  aoConcluir,
  aoSair,
}: {
  perfil: Perfil;
  aoConcluir: () => void;
  aoSair: () => void;
}) {
  const cameraRef = useRef<CameraView>(null);
  const [permissao, pedirPermissao] = useCameraPermissions();
  const [fotos, setFotos] = useState<string[]>([]);
  const [estado, setEstado] = useState<Estado>({ nome: "capturando" });

  const passo = PASSOS[Math.min(fotos.length, PASSOS.length - 1)];
  const ocupado = estado.nome === "enviando";

  async function capturar() {
    try {
      const foto = await cameraRef.current?.takePictureAsync({
        quality: 0.85,
        skipProcessing: false,
      });
      if (!foto?.uri) throw new Error("sem foto");
      setFotos((atuais) => [...atuais, foto.uri]);
      setEstado({ nome: "capturando" });
    } catch {
      setEstado({ nome: "erro", mensagem: t("ponto.falhaFoto") });
    }
  }

  async function enviar() {
    setEstado({ nome: "enviando" });
    try {
      await cadastrarRosto(fotos, VERSAO_DO_TERMO);
      aoConcluir();
    } catch (erro) {
      // Recomeça do zero em vez de deixar completar o que falta: quando o
      // servidor recusa fotos por qualidade, quase sempre a causa é o ambiente
      // (contraluz, câmera suja) e vale para todas — aproveitar as que
      // passaram só adiaria o mesmo problema para a hora de bater ponto.
      setFotos([]);
      setEstado({
        nome: "erro",
        mensagem: erro instanceof Error ? erro.message : t("cadastro.falhou"),
      });
    }
  }

  if (!permissao) {
    return (
      <View style={{ flex: 1, alignItems: "center", justifyContent: "center" }}>
        <Legenda>{t("cadastro.verificandoCamera")}</Legenda>
      </View>
    );
  }

  if (!permissao.granted) {
    return (
      <ScrollView contentContainerStyle={{ padding: 24, gap: 16 }}>
        <Titulo>{t("cadastro.tituloPermissao")}</Titulo>
        <Cartao>
          <Text style={{ color: cores.textoFraco, lineHeight: 21 }}>
            {t("cadastro.explicacaoCamera")}
          </Text>
        </Cartao>
        <Botao titulo={t("permissao.camera.permitir")} onPress={pedirPermissao} />
        <Botao titulo={t("ponto.sair")} variante="secundario" onPress={aoSair} />
      </ScrollView>
    );
  }

  const completo = fotos.length >= MINIMO_DE_FOTOS;

  return (
    <View style={{ flex: 1 }}>
      <View style={{ paddingHorizontal: 24, paddingTop: 16, paddingBottom: 8 }}>
        <Titulo>{t("cadastro.titulo")}</Titulo>
        <Legenda>
          {perfil.nome} · {perfil.empresa}
        </Legenda>
      </View>

      {!completo && (
        <View style={{ paddingHorizontal: 24, paddingBottom: 8 }}>
          <Text style={{ color: cores.texto, fontWeight: "700" }}>
            {t("cadastro.contador", {
              atual: fotos.length + 1,
              total: MINIMO_DE_FOTOS,
              passo: t(passo.titulo),
            })}
          </Text>
          <Legenda>{t(passo.instrucao)}</Legenda>
        </View>
      )}

      <View style={{ flex: 1, marginHorizontal: 16, borderRadius: 16, overflow: "hidden" }}>
        <CameraView ref={cameraRef} style={{ flex: 1 }} facing="front" mirror />

        <View
          pointerEvents="none"
          style={{
            position: "absolute",
            top: "12%",
            left: "12%",
            right: "12%",
            bottom: "20%",
            borderWidth: 3,
            borderColor: completo ? cores.acento : "rgba(250,250,250,0.6)",
            borderRadius: 999,
          }}
        />
      </View>

      <View style={{ flexDirection: "row", gap: 8, padding: 16, justifyContent: "center" }}>
        {Array.from({ length: MINIMO_DE_FOTOS }).map((_, indice) => {
          const uri = fotos[indice];
          return (
            <View
              key={indice}
              style={{
                width: 56,
                height: 56,
                borderRadius: 12,
                overflow: "hidden",
                borderWidth: 2,
                borderColor: uri ? cores.acento : cores.borda,
                backgroundColor: cores.superficie,
              }}
            >
              {uri && <Image source={{ uri }} style={{ width: "100%", height: "100%" }} />}
            </View>
          );
        })}
      </View>

      <View style={{ paddingHorizontal: 24, paddingBottom: 24, gap: 12 }}>
        {estado.nome === "erro" && <Aviso tipo="erro">{estado.mensagem}</Aviso>}

        {!completo ? (
          <Botao titulo={t("cadastro.tirarFoto")} onPress={capturar} />
        ) : (
          <Botao
            titulo={ocupado ? t("cadastro.enviando") : t("cadastro.concluir")}
            onPress={enviar}
            carregando={ocupado}
          />
        )}

        {fotos.length > 0 && !ocupado && (
          <Botao titulo={t("cadastro.recomecar")} variante="secundario" onPress={() => setFotos([])} />
        )}

        {!ocupado && <Botao titulo={t("ponto.sair")} variante="secundario" onPress={aoSair} />}
      </View>
    </View>
  );
}
