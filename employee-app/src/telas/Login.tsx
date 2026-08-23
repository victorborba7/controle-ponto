import { useState } from "react";
import {
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  Text,
  TextInput,
  View,
} from "react-native";
import * as Application from "expo-application";

import { t } from "../i18n";
import { entrar, type Perfil } from "../services/api";
import { Aviso, Botao, Legenda, Titulo, cores, estilosCampo } from "../ui";

export function Login({
  aoEntrar,
  aoAbrirDiagnostico,
}: {
  aoEntrar: (perfil: Perfil) => void;
  aoAbrirDiagnostico: () => void;
}) {
  const [empresa, setEmpresa] = useState("");
  const [matricula, setMatricula] = useState("");
  const [senha, setSenha] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  async function autenticar() {
    setEnviando(true);
    setErro(null);
    try {
      const perfil = await entrar({
        tenantSlug: empresa.trim().toLowerCase(),
        matricula: matricula.trim(),
        senha,
        plataforma: Platform.OS === "ios" ? "ios" : "android",
        modelo: Platform.OS === "android" ? "Android" : "iPhone",
        versaoOs: String(Platform.Version),
        versaoApp: Application.nativeApplicationVersion ?? "0.1.0",
      });
      aoEntrar(perfil);
    } catch (e) {
      setErro(e instanceof Error ? e.message : t("login.falhou"));
    } finally {
      setEnviando(false);
    }
  }

  const podeEnviar = empresa.trim() && matricula.trim() && senha.length > 0;

  return (
    <KeyboardAvoidingView
      style={{ flex: 1, backgroundColor: cores.fundo }}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <ScrollView
        contentContainerStyle={{ flexGrow: 1, justifyContent: "center", padding: 24 }}
        keyboardShouldPersistTaps="handled"
      >
        <View style={{ marginBottom: 32, alignItems: "center" }}>
          <Titulo>Waypoint</Titulo>
          <Legenda>{t("login.subtitulo")}</Legenda>
        </View>

        {erro && (
          <View style={{ marginBottom: 16 }}>
            <Aviso tipo="erro">{erro}</Aviso>
          </View>
        )}

        <View style={{ gap: 16 }}>
          <View>
            <Text style={estilosCampo.rotulo}>{t("login.empresa")}</Text>
            <TextInput
              style={estilosCampo.entrada}
              value={empresa}
              onChangeText={setEmpresa}
              autoCapitalize="none"
              autoCorrect={false}
              placeholder="empresa-demo"
              placeholderTextColor={cores.textoFraco}
            />
          </View>

          <View>
            <Text style={estilosCampo.rotulo}>{t("login.matricula")}</Text>
            <TextInput
              style={estilosCampo.entrada}
              value={matricula}
              onChangeText={setMatricula}
              autoCapitalize="none"
              autoCorrect={false}
              placeholder="0001"
              placeholderTextColor={cores.textoFraco}
            />
          </View>

          <View>
            <Text style={estilosCampo.rotulo}>{t("login.senha")}</Text>
            <TextInput
              style={estilosCampo.entrada}
              value={senha}
              onChangeText={setSenha}
              secureTextEntry
              onSubmitEditing={() => podeEnviar && autenticar()}
            />
          </View>

          <Botao
            titulo={t("login.entrar")}
            onPress={autenticar}
            carregando={enviando}
            desabilitado={!podeEnviar}
          />
        </View>

        <View style={{ marginTop: 32, gap: 16 }}>
          <Legenda>{t("login.ajuda")}</Legenda>

          <Botao
            titulo={t("login.diagnostico")}
            variante="texto"
            onPress={aoAbrirDiagnostico}
          />
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}
