/**
 * Peças de interface e a paleta do app.
 *
 * Alvo de uso: funcionário de hangar, muitas vezes de luva, sob luz forte ou
 * escuridão. Daí os botões grandes, o contraste alto e o tema escuro fixo —
 * um app que muda de aparência conforme o sistema confunde quem o usa duas
 * vezes por dia sempre do mesmo jeito.
 */

import { ActivityIndicator, Pressable, StyleSheet, Text, View } from "react-native";
import type { ReactNode } from "react";

export const cores = {
  fundo: "#09090b",
  superficie: "#18181b",
  borda: "#27272a",
  texto: "#fafafa",
  textoFraco: "#a1a1aa",
  acento: "#22c55e",
  aviso: "#f59e0b",
  erro: "#ef4444",
  info: "#38bdf8",
};

export function Botao({
  titulo,
  onPress,
  variante = "primario",
  carregando,
  desabilitado,
}: {
  titulo: string;
  onPress: () => void;
  variante?: "primario" | "secundario" | "texto";
  carregando?: boolean;
  desabilitado?: boolean;
}) {
  const inativo = desabilitado || carregando;

  const fundo =
    variante === "primario"
      ? cores.acento
      : variante === "secundario"
        ? cores.superficie
        : "transparent";

  return (
    <Pressable
      onPress={onPress}
      disabled={inativo}
      style={({ pressed }) => [
        estilos.botao,
        { backgroundColor: fundo, opacity: inativo ? 0.5 : pressed ? 0.85 : 1 },
        variante === "secundario" && { borderWidth: 1, borderColor: cores.borda },
      ]}
    >
      {carregando ? (
        <ActivityIndicator color={variante === "primario" ? "#052e16" : cores.texto} />
      ) : (
        <Text
          style={[
            estilos.botaoTexto,
            { color: variante === "primario" ? "#052e16" : cores.texto },
          ]}
        >
          {titulo}
        </Text>
      )}
    </Pressable>
  );
}

export function Cartao({ children }: { children: ReactNode }) {
  return <View style={estilos.cartao}>{children}</View>;
}

export function Aviso({
  tipo = "info",
  children,
}: {
  tipo?: "info" | "aviso" | "erro" | "sucesso";
  children: ReactNode;
}) {
  const cor = {
    info: cores.info,
    aviso: cores.aviso,
    erro: cores.erro,
    sucesso: cores.acento,
  }[tipo];

  return (
    <View style={[estilos.aviso, { borderLeftColor: cor }]}>
      <Text style={{ color: cores.texto, fontSize: 14, lineHeight: 20 }}>{children}</Text>
    </View>
  );
}

export function Titulo({ children }: { children: ReactNode }) {
  return <Text style={estilos.titulo}>{children}</Text>;
}

export function Legenda({ children }: { children: ReactNode }) {
  return <Text style={estilos.legenda}>{children}</Text>;
}

const estilos = StyleSheet.create({
  botao: {
    minHeight: 56,
    borderRadius: 12,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: 24,
  },
  botaoTexto: {
    fontSize: 17,
    fontWeight: "600",
  },
  cartao: {
    backgroundColor: cores.superficie,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: cores.borda,
    padding: 16,
  },
  aviso: {
    backgroundColor: cores.superficie,
    borderLeftWidth: 4,
    borderRadius: 8,
    padding: 14,
  },
  titulo: {
    color: cores.texto,
    fontSize: 22,
    fontWeight: "700",
  },
  legenda: {
    color: cores.textoFraco,
    fontSize: 14,
    lineHeight: 20,
  },
});

export const estilosCampo = StyleSheet.create({
  entrada: {
    backgroundColor: cores.superficie,
    borderWidth: 1,
    borderColor: cores.borda,
    borderRadius: 10,
    color: cores.texto,
    fontSize: 16,
    minHeight: 52,
    paddingHorizontal: 14,
  },
  rotulo: {
    color: cores.textoFraco,
    fontSize: 14,
    marginBottom: 6,
  },
});
