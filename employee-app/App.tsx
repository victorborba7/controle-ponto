import AsyncStorage from "@react-native-async-storage/async-storage";
import { StatusBar } from "expo-status-bar";
import { useCallback, useEffect, useState } from "react";
import { SafeAreaView, View } from "react-native";

import {
  encerrarSessao,
  lerPerfil,
  salvarPerfil,
  sincronizarPerfil,
  type Perfil,
} from "./src/services/api";
import { registrarParaLembretes } from "./src/services/lembretes";
import { encerrarBle } from "./src/services/localizacao";
import { BaterPonto } from "./src/telas/BaterPonto";
import { CadastroDoRosto } from "./src/telas/CadastroDoRosto";
import { Consentimento, VERSAO_DO_TERMO } from "./src/telas/Consentimento";
import { Diagnostico } from "./src/telas/Diagnostico";
import { Historico } from "./src/telas/Historico";
import { Login } from "./src/telas/Login";
import { Legenda, cores } from "./src/ui";

const CHAVE_CONSENTIMENTO = "ponto_consentimento_versao";
const CHAVE_INSTALACAO = "ponto_instalacao";

/**
 * Derruba a sessão que não foi aberta nesta instalação.
 *
 * No iOS a sessão fica no Keychain, que **não** é apagado quando o app é
 * desinstalado; no Android o armazenamento seguro vai embora junto. Sem isto,
 * um iPhone que já rodou o Waypoint abre direto na batida de ponto, com o
 * perfil de quem entrou antes e sem passar pelo login: o ponto sai no nome
 * errado, e foi assim que o problema apareceu.
 *
 * O marcador vive no AsyncStorage justamente porque ele **é** apagado na
 * remoção do app. Sem marcador, a sessão guardada não tem procedência: ou é
 * instalação nova sobre um Keychain velho, ou é a primeira abertura desta
 * versão, que é onde estão as sessões que ninguém sabe de quem são. Nos dois
 * casos o certo é pedir login.
 *
 * O preço é uma entrada a mais para quem já usava o app, uma única vez. É
 * menos que deixar um aparelho batendo ponto no nome de outra pessoa.
 */
async function descartarSessaoSemProcedencia() {
  if (await AsyncStorage.getItem(CHAVE_INSTALACAO)) return;

  await encerrarSessao();
  await AsyncStorage.setItem(CHAVE_INSTALACAO, "1");
}

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

  /**
   * Retoma a sessão guardada, conferindo antes com o servidor.
   *
   * O perfil salvo envelhece: o rosto pode ter sido cadastrado pelo painel
   * depois do último login, ou desativado. Decidir a tela só pelo cache foi o
   * que mandou um funcionário sem rosto direto para a batida de ponto.
   */
  const retomarSessao = useCallback(async () => {
    const salvo = await lerPerfil();
    if (!salvo) {
      setPerfil(null);
      setTela("login");
      return;
    }

    const conferido = await sincronizarPerfil(salvo);
    if (conferido.situacao === "invalida") {
      setPerfil(null);
      setTela("login");
      return;
    }

    setPerfil(conferido.perfil);
    setTela(telaDeQuemEntrou(conferido.perfil));
  }, []);

  const decidirTelaInicial = useCallback(async () => {
    await descartarSessaoSemProcedencia();

    const consentido = await AsyncStorage.getItem(CHAVE_CONSENTIMENTO);

    // Termo novo exige aceite novo: sem isso não daria para provar *o que* a
    // pessoa concordou.
    if (consentido !== VERSAO_DO_TERMO) {
      setTela("consentimento");
      return;
    }

    await retomarSessao();
  }, [retomarSessao]);

  useEffect(() => {
    void decidirTelaInicial();
  }, [decidirTelaInicial]);

  // O rádio BLE não pode ficar ligado depois que o app fecha.
  useEffect(() => encerrarBle, []);

  async function aceitarTermo() {
    await AsyncStorage.setItem(CHAVE_CONSENTIMENTO, VERSAO_DO_TERMO);
    await retomarSessao();
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
            // Sem await: o lembrete é conveniência, e esperar pela permissão
            // de notificação atrasaria a tela de quem só quer bater o ponto.
            void registrarParaLembretes();
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
