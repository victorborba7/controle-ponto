import { useCallback, useEffect, useState } from "react";
import { FlatList, RefreshControl, Text, View } from "react-native";

import { get } from "../services/api";
import { Aviso, Botao, Cartao, Legenda, Titulo, cores } from "../ui";

type Registro = {
  id: string;
  entry_type: "in" | "out" | "break_start" | "break_end";
  recorded_at: string;
  status: "approved" | "pending_review" | "rejected";
  location_method: "beacon" | "wifi" | "gps" | "none";
  decision_reason: string | null;
};

const rotuloTipo: Record<Registro["entry_type"], string> = {
  in: "Entrada",
  out: "Saída",
  break_start: "Início do intervalo",
  break_end: "Fim do intervalo",
};

const rotuloStatus: Record<Registro["status"], string> = {
  approved: "Aprovado",
  pending_review: "Em conferência",
  rejected: "Rejeitado",
};

const corStatus: Record<Registro["status"], string> = {
  approved: cores.acento,
  pending_review: cores.aviso,
  rejected: cores.erro,
};

const rotuloMetodo: Record<Registro["location_method"], string> = {
  beacon: "Beacon do local",
  wifi: "Wi-Fi do local",
  gps: "GPS",
  none: "Sem sinal de local",
};

function formatar(iso: string) {
  const d = new Date(iso);
  return d.toLocaleString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function Historico({ aoVoltar }: { aoVoltar: () => void }) {
  const [registros, setRegistros] = useState<Registro[]>([]);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState<string | null>(null);

  const carregar = useCallback(async () => {
    setErro(null);
    try {
      const resposta = await get<{ items: Registro[] }>("/time-entries/me?limit=100");
      setRegistros(resposta.items);
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao carregar");
    } finally {
      setCarregando(false);
    }
  }, []);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  return (
    <View style={{ flex: 1, backgroundColor: cores.fundo }}>
      <View style={{ padding: 16, paddingTop: 24 }}>
        <Titulo>Meus registros</Titulo>
      </View>

      {erro && (
        <View style={{ paddingHorizontal: 16, paddingBottom: 12 }}>
          <Aviso tipo="erro">{erro}</Aviso>
        </View>
      )}

      <FlatList
        data={registros}
        keyExtractor={(item) => item.id}
        contentContainerStyle={{ padding: 16, paddingTop: 0, gap: 12 }}
        refreshControl={
          <RefreshControl
            refreshing={carregando}
            onRefresh={carregar}
            tintColor={cores.textoFraco}
          />
        }
        ListEmptyComponent={
          carregando ? null : (
            <Legenda>Nenhum registro ainda.</Legenda>
          )
        }
        renderItem={({ item }) => (
          <Cartao>
            <View
              style={{
                flexDirection: "row",
                justifyContent: "space-between",
                alignItems: "center",
              }}
            >
              <Text style={{ color: cores.texto, fontSize: 16, fontWeight: "600" }}>
                {rotuloTipo[item.entry_type]}
              </Text>
              <Text style={{ color: corStatus[item.status], fontSize: 13, fontWeight: "600" }}>
                {rotuloStatus[item.status]}
              </Text>
            </View>

            <Text style={{ color: cores.texto, fontSize: 15, marginTop: 4 }}>
              {formatar(item.recorded_at)}
            </Text>

            <Text style={{ color: cores.textoFraco, fontSize: 13, marginTop: 2 }}>
              {rotuloMetodo[item.location_method]}
            </Text>

            {/* O motivo aparece só quando não foi aprovado direto: é a resposta
                para "por que meu ponto está em conferência?". */}
            {item.status !== "approved" && item.decision_reason && (
              <Text style={{ color: cores.textoFraco, fontSize: 13, marginTop: 8 }}>
                {item.decision_reason}
              </Text>
            )}
          </Cartao>
        )}
      />

      <View style={{ padding: 16 }}>
        <Botao titulo="Voltar" variante="secundario" onPress={aoVoltar} />
      </View>
    </View>
  );
}
