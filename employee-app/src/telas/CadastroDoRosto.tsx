import { CameraView, useCameraPermissions } from "expo-camera";
import { useRef, useState } from "react";
import { Image, ScrollView, Text, View } from "react-native";

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

const PASSOS = [
  {
    titulo: "Olhando para a câmera",
    instrucao: "Rosto centralizado, luz no rosto e sem boné ou óculos escuros.",
  },
  {
    titulo: "Um pouco mais perto",
    instrucao: "Aproxime o celular até o rosto ocupar quase todo o círculo.",
  },
  {
    titulo: "Expressão natural",
    instrucao: "Afaste de novo e relaxe o rosto, como você estaria no dia a dia.",
  },
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
      setEstado({ nome: "erro", mensagem: "Não foi possível capturar a foto." });
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
        mensagem: erro instanceof Error ? erro.message : "Não foi possível cadastrar.",
      });
    }
  }

  if (!permissao) {
    return (
      <View style={{ flex: 1, alignItems: "center", justifyContent: "center" }}>
        <Legenda>Verificando a câmera…</Legenda>
      </View>
    );
  }

  if (!permissao.granted) {
    return (
      <ScrollView contentContainerStyle={{ padding: 24, gap: 16 }}>
        <Titulo>Cadastro do seu rosto</Titulo>
        <Cartao>
          <Text style={{ color: cores.textoFraco, lineHeight: 21 }}>
            Para cadastrar seu rosto, o aplicativo precisa da câmera. Ela é usada
            só neste cadastro e no momento de bater o ponto.
          </Text>
        </Cartao>
        <Botao titulo="Permitir câmera" onPress={pedirPermissao} />
        <Botao titulo="Sair" variante="secundario" onPress={aoSair} />
      </ScrollView>
    );
  }

  const completo = fotos.length >= MINIMO_DE_FOTOS;

  return (
    <View style={{ flex: 1 }}>
      <View style={{ paddingHorizontal: 24, paddingTop: 16, paddingBottom: 8 }}>
        <Titulo>Cadastre seu rosto</Titulo>
        <Legenda>
          {perfil.nome} · {perfil.empresa}
        </Legenda>
      </View>

      {!completo && (
        <View style={{ paddingHorizontal: 24, paddingBottom: 8 }}>
          <Text style={{ color: cores.texto, fontWeight: "700" }}>
            Foto {fotos.length + 1} de {MINIMO_DE_FOTOS} — {passo.titulo}
          </Text>
          <Legenda>{passo.instrucao}</Legenda>
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
          <Botao titulo="Tirar foto" onPress={capturar} />
        ) : (
          <Botao
            titulo={ocupado ? "Enviando…" : "Concluir cadastro"}
            onPress={enviar}
            carregando={ocupado}
          />
        )}

        {fotos.length > 0 && !ocupado && (
          <Botao titulo="Recomeçar" variante="secundario" onPress={() => setFotos([])} />
        )}

        {!ocupado && <Botao titulo="Sair" variante="secundario" onPress={aoSair} />}
      </View>
    </View>
  );
}
