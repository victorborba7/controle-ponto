import { useState } from "react";
import { Pressable, ScrollView, Text, View } from "react-native";

import { t } from "../i18n";
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
        <Titulo>{t("termo.titulo")}</Titulo>

        <Cartao>
          <Secao titulo={t("termo.imagem.titulo")}>{t("termo.imagem.corpo")}</Secao>
        </Cartao>

        <Cartao>
          <Secao titulo={t("termo.local.titulo")}>
            {t("termo.local.corpo1")}
            {"\n\n"}
            {/* O destaque volta como <Text> negrito: interpolar HTML no
                catálogo obrigaria cada idioma a acertar marcação, e uma tag
                mal fechada numa tradução quebraria a tela inteira. */}
            {partirNoDestaque(t("termo.local.corpo2"), t("termo.local.destaque"))}
          </Secao>
        </Cartao>

        <Cartao>
          <Secao titulo={t("termo.direitos.titulo")}>
            {t("termo.direitos.corpo1")}
            {"\n\n"}
            {t("termo.direitos.corpo2")}
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
            {t("termo.aceite")}
          </Text>
        </Pressable>

        <Text style={{ color: cores.textoFraco, fontSize: 12 }}>
          {t("termo.versao", { versao: VERSAO_DO_TERMO })}
        </Text>
      </ScrollView>

      <View style={{ padding: 24, paddingTop: 0 }}>
        <Botao titulo={t("termo.continuar")} onPress={aoAceitar} desabilitado={!aceito} />
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


/**
 * Devolve o texto com o trecho destacado em negrito.
 *
 * O destaque viaja como chave separada, e não como marcação dentro da frase:
 * interpolar HTML no catálogo obrigaria cada idioma a acertar a marcação, e
 * uma tag mal fechada numa tradução quebraria a tela toda. Aqui o pior caso é
 * o texto sair sem negrito.
 */
function partirNoDestaque(texto: string, destaque: string) {
  const partes = texto.split("{destaque}");
  if (partes.length !== 2) return texto;
  return (
    <>
      {partes[0]}
      <Text style={{ fontWeight: "700" }}>{destaque}</Text>
      {partes[1]}
    </>
  );
}
