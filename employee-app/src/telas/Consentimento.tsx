import { useState } from "react";
import { Pressable, ScrollView, Text, View } from "react-native";

import { Botao, Cartao, Titulo, cores } from "../ui";

/**
 * Termo de uso de biometria e localização, aceito no primeiro acesso.
 *
 * Exibido no app, e não só assinado em papel no RH: a LGPD exige que o titular
 * seja informado de forma clara sobre a finalidade, e o consentimento precisa
 * ser específico. Um formulário assinado no meio da papelada de admissão não
 * cumpre bem esse papel.
 *
 * A versão aqui precisa acompanhar a que o RH registrou no cadastro
 * biométrico — mudou o texto, sobe a versão nos dois lugares.
 */
export const VERSAO_DO_TERMO = "2026.1";

export function Consentimento({ aoAceitar }: { aoAceitar: () => void }) {
  const [aceito, setAceito] = useState(false);

  return (
    <View style={{ flex: 1, backgroundColor: cores.fundo }}>
      <ScrollView contentContainerStyle={{ padding: 24, gap: 16 }}>
        <Titulo>Como seus dados são usados</Titulo>

        <Cartao>
          <Secao titulo="Sua imagem">
            No momento de bater o ponto, o aplicativo tira uma foto do seu rosto
            e a compara com as fotos que você cadastrou com o RH. A comparação
            acontece no servidor da empresa e serve apenas para confirmar que foi
            você quem registrou o ponto.
          </Secao>
        </Cartao>

        <Cartao>
          <Secao titulo="Sua localização">
            No mesmo momento, o aplicativo verifica se você está no local de
            trabalho — pelos beacons instalados, pela rede Wi-Fi da empresa ou
            pelo GPS.
            {"\n\n"}
            Isso acontece <Text style={{ fontWeight: "700" }}>apenas quando você
            bate o ponto</Text>. O aplicativo não acompanha seus deslocamentos e
            não coleta nada em segundo plano.
          </Secao>
        </Cartao>

        <Cartao>
          <Secao titulo="Seus direitos">
            Você pode pedir ao RH, a qualquer momento, para ver os dados que a
            empresa tem sobre você, corrigi-los ou revogar este consentimento.
            {"\n\n"}
            Revogar impede o uso do ponto por reconhecimento facial — nesse
            caso, combine com o RH outra forma de registrar sua jornada.
          </Secao>
        </Cartao>

        <Pressable
          onPress={() => setAceito((v) => !v)}
          style={{
            flexDirection: "row",
            gap: 12,
            padding: 16,
            backgroundColor: cores.superficie,
            borderRadius: 12,
            borderWidth: 1,
            borderColor: aceito ? cores.acento : cores.borda,
          }}
        >
          <View
            style={{
              width: 24,
              height: 24,
              borderRadius: 6,
              borderWidth: 2,
              borderColor: aceito ? cores.acento : cores.textoFraco,
              backgroundColor: aceito ? cores.acento : "transparent",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            {aceito && <Text style={{ color: "#052e16", fontWeight: "700" }}>✓</Text>}
          </View>
          <Text style={{ color: cores.texto, flex: 1, fontSize: 15, lineHeight: 21 }}>
            Li e concordo com o uso da minha imagem e da minha localização para
            registro de ponto.
          </Text>
        </Pressable>

        <Text style={{ color: cores.textoFraco, fontSize: 12 }}>
          Termo versão {VERSAO_DO_TERMO}
        </Text>
      </ScrollView>

      <View style={{ padding: 24, paddingTop: 0 }}>
        <Botao titulo="Continuar" onPress={aoAceitar} desabilitado={!aceito} />
      </View>
    </View>
  );
}

function Secao({ titulo, children }: { titulo: string; children: React.ReactNode }) {
  return (
    <>
      <Text
        style={{ color: cores.texto, fontSize: 16, fontWeight: "600", marginBottom: 8 }}
      >
        {titulo}
      </Text>
      <Text style={{ color: cores.textoFraco, fontSize: 15, lineHeight: 22 }}>
        {children}
      </Text>
    </>
  );
}
