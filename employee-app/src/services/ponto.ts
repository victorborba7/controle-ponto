/**
 * Envio da batida ao servidor, com fila e reenvio.
 */

import { ApiError, enviarMultipart } from "./api";
import {
  type BatidaPendente,
  enfileirar,
  lerFila,
  novaChave,
  registrarFalha,
  remover,
} from "./fila";
import type { SinaisColetados } from "./localizacao";

export type RespostaPonto = {
  entry: {
    id: string;
    entry_type: "in" | "out" | "break_start" | "break_end";
    recorded_at: string;
    status: "approved" | "pending_review" | "rejected";
    location_method: "beacon" | "wifi" | "gps" | "none";
  };
  message: string;
  duplicate: boolean;
};

export type ResultadoEnvio =
  | { situacao: "enviado"; resposta: RespostaPonto }
  | {
      situacao: "enfileirado";
      motivo: string;
      /**
       * Se a batida ficou na fila por falta de rede mesmo.
       *
       * Separa dois casos que a fila trata igual mas que a pessoa precisa
       * distinguir: sem sinal se resolve sozinho quando o sinal voltar;
       * qualquer outra falha não se resolve nunca, e chamá-la de "sem conexão"
       * manda alguém esperar por um sinal que já está lá.
       */
      ehFalhaDeRede: boolean;
    }
  | { situacao: "recusado"; motivo: string };

/**
 * O servidor está inalcançável, ou algo mais deu errado?
 *
 * Só falha no nível do `fetch` conta como falta de rede: o React Native lança
 * `TypeError` quando não consegue abrir a conexão. Um 5xx, ao contrário, prova
 * que o servidor foi alcançado — e um erro de configuração (URL da API
 * ausente no build, por exemplo) nem chega a tentar.
 */
export function ehFalhaDeRede(erro: unknown): boolean {
  if (erro instanceof ApiError) return false;

  const mensagem = erro instanceof Error ? erro.message : String(erro);
  return (
    erro instanceof TypeError ||
    /network request failed|failed to fetch|timeout|timed out/i.test(mensagem)
  );
}

function montarFormulario(batida: BatidaPendente): FormData {
  const dados = new FormData();

  // O React Native aceita este formato de arquivo em FormData; o TypeScript do
  // DOM não o conhece, daí o cast.
  dados.append("selfie", {
    uri: batida.fotoUri,
    name: "selfie.jpg",
    type: "image/jpeg",
  } as unknown as Blob);

  dados.append("evidence", JSON.stringify(batida.sinais));
  dados.append("idempotency_key", batida.idempotencyKey);
  dados.append("client_recorded_at", batida.capturadaEm);

  // `entry_type` fica de fora de propósito: o servidor deduz entrada ou saída
  // pela última batida, o que tira do funcionário uma escolha que ele pode
  // errar — e um erro aí vira hora extra fantasma ou falta indevida.
  return dados;
}

/**
 * Bate o ponto.
 *
 * Falha de rede não é erro para o usuário: a batida entra na fila e sobe
 * depois. Já uma recusa do servidor (rosto diferente, aparelho revogado) é
 * definitiva e não deve ser reenviada — insistir só repetiria a recusa.
 */
export async function baterPonto(
  fotoUri: string,
  sinais: SinaisColetados,
): Promise<ResultadoEnvio> {
  const batida: BatidaPendente = {
    idempotencyKey: novaChave(),
    fotoUri,
    sinais,
    capturadaEm: new Date().toISOString(),
    tentativas: 0,
  };

  try {
    const resposta = await enviarMultipart<RespostaPonto>(
      "/time-entries",
      montarFormulario(batida),
    );
    return { situacao: "enviado", resposta };
  } catch (erro) {
    if (erro instanceof ApiError && ehDefinitivo(erro.status)) {
      return { situacao: "recusado", motivo: erro.message };
    }

    await enfileirar(batida);
    return {
      situacao: "enfileirado",
      motivo:
        erro instanceof Error ? erro.message : "Sem conexão com o servidor",
      ehFalhaDeRede: ehFalhaDeRede(erro),
    };
  }
}

/**
 * O servidor decidiu, e a decisão não muda com um reenvio.
 *
 * 409 (batida repetida) e 412 (sem cadastro biométrico) entram aqui: reenviar
 * daria o mesmo resultado e só encheria a fila.
 */
function ehDefinitivo(status: number): boolean {
  return [400, 403, 409, 412, 413, 422].includes(status);
}

export type ResultadoSincronizacao = {
  enviadas: number;
  descartadas: number;
  pendentes: number;
};

/**
 * Tenta subir as batidas represadas.
 *
 * Chamada ao abrir o app e depois de cada batida nova. Como cada uma carrega
 * a chave de idempotência original, uma que já tenha chegado ao servidor
 * volta marcada como duplicata e sai da fila sem virar registro novo.
 */
export async function sincronizar(): Promise<ResultadoSincronizacao> {
  const fila = await lerFila();
  let enviadas = 0;
  let descartadas = 0;

  for (const batida of fila) {
    try {
      await enviarMultipart<RespostaPonto>("/time-entries", montarFormulario(batida));
      await remover(batida.idempotencyKey);
      enviadas += 1;
    } catch (erro) {
      if (erro instanceof ApiError && ehDefinitivo(erro.status)) {
        await remover(batida.idempotencyKey);
        descartadas += 1;
        continue;
      }
      await registrarFalha(
        batida.idempotencyKey,
        erro instanceof Error ? erro.message : "Falha no envio",
      );
      // Sem conexão agora significa sem conexão para as próximas; insistir na
      // fila inteira só gastaria bateria.
      break;
    }
  }

  return { enviadas, descartadas, pendentes: (await lerFila()).length };
}
