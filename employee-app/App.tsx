import AsyncStorage from "@react-native-async-storage/async-storage";
import { StatusBar } from "expo-status-bar";
import { useCallback, useEffect, useState } from "react";
import { SafeAreaView, View } from "react-native";

import { encerrarSessao, lerPerfil, salvarPerfil, type Perfil } from "./src/services/api";
import { encerrarBle } from "./src/services/localizacao";
import { BaterPonto } from "./src/telas/BaterPonto";
import { CadastroDoRosto } from "./src/telas/CadastroDoRosto";
import { Consentimento, VERSAO_DO_TERMO } from "./src/telas/Consentimento";
import { Diagnostico } from "./src/telas/Diagnostico";
import { Historico } from "./src/telas/Historico";
import { Login } from "./src/telas/Login";
import { Legenda, cores } from "./src/ui";

const CHAVE_CONSENTIMENTO = "ponto_consentimento_versao";

/**
 * Para onde vai quem acabou de entrar.
 *
 * Sem rosto cadastrado não existe ponto possível — o backend recusaria a
 * batida com "rosto não cadastrado". Mandar direto para o cadastro transforma
 * um erro sem saída num passo com instrução.
 */
function telaDeQuemEntrou(perfil: Perfil): Tela {
  return perfil.rostoCadastrado ? "ponto" : "cadastro-do-rosto";
}

type Tela =
  | "carregando"
  | "consentimento"
  | "login"
  | "cadastro-do-rosto"
  | "ponto"
  | "historico"
  | "diagnostico";

/**
 * Navegação por estado, sem biblioteca de rotas.
 *
 * São quatro telas com transições lineares; um roteador aqui traria
 * configuração e peso sem resolver problema nenhum. Se o app crescer para abas
 * ou histórico de navegação, aí vale a troca.
 */
export default function App() {
  const [tela, setTela] = useState<Tela>("carregando");
  const [perfil, setPerfil] = useState<Perfil | null>(null);

  const decidirTelaInicial = useCallback(async () => {
    const consentido = await AsyncStorage.getItem(CHAVE_CONSENTIMENTO);

    // Termo novo exige aceite novo: sem isso não daria para provar *o que* a
    // pessoa concordou.
    if (consentido !== VERSAO_DO_TERMO) {
      setTela("consentimento");
      return;
    }

    const salvo = await lerPerfil();
    if (salvo) {
      setPerfil(salvo);
      setTela(telaDeQuemEntrou(salvo));
    } else {
      setTela("login");
    }
  }, []);

  useEffect(() => {
    void decidirTelaInicial();
  }, [decidirTelaInicial]);

  // O rádio BLE não pode ficar ligado depois que o app fecha.
  useEffect(() => encerrarBle, []);

  async function aceitarTermo() {
    await AsyncStorage.setItem(CHAVE_CONSENTIMENTO, VERSAO_DO_TERMO);
    const salvo = await lerPerfil();
    setPerfil(salvo);
    setTela(salvo ? telaDeQuemEntrou(salvo) : "login");
  }

  async function sair() {
    await encerrarSessao();
    setPerfil(null);
    setTela("login");
  }

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: cores.fundo }}>
      <StatusBar style="light" />

      {tela === "carregando" && (
        <View style={{ flex: 1, alignItems: "center", justifyContent: "center" }}>
          <Legenda>Carregando…</Legenda>
        </View>
      )}

      {tela === "consentimento" && <Consentimento aoAceitar={aceitarTermo} />}

      {tela === "login" && (
        <Login
          aoEntrar={(novo) => {
            setPerfil(novo);
            setTela(telaDeQuemEntrou(novo));
          }}
          // Acessível sem login de propósito: na instalação, os beacons são
          // mapeados antes de existir funcionário cadastrado — e quem faz esse
          // trabalho é o técnico, não alguém com credencial de ponto.
          aoAbrirDiagnostico={() => setTela("diagnostico")}
        />
      )}

      {tela === "diagnostico" && (
        <Diagnostico aoVoltar={() => setTela(perfil ? "ponto" : "login")} />
      )}

      {tela === "cadastro-do-rosto" && perfil && (
        <CadastroDoRosto
          perfil={perfil}
          aoConcluir={() => {
            const atualizado = { ...perfil, rostoCadastrado: true };
            setPerfil(atualizado);
            void salvarPerfil(atualizado);
            setTela("ponto");
          }}
          aoSair={sair}
        />
      )}

      {tela === "ponto" && perfil && (
        <BaterPonto
          perfil={perfil}
          aoAbrirHistorico={() => setTela("historico")}
          aoAbrirDiagnostico={() => setTela("diagnostico")}
          aoSair={sair}
        />
      )}

      {tela === "historico" && <Historico aoVoltar={() => setTela("ponto")} />}
    </SafeAreaView>
  );
}
