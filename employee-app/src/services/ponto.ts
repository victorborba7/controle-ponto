/**
 * Envio da batida ao servidor, com fila e reenvio.
 */

import { File } from "expo-file-system";

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
    /** O que o funcionário declarou, quando a empresa pede. */
    label: string | null;
    note: string | null;
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

/**
 * Monta o multipart da batida.
 *
 * A selfie vai como `File` do `expo-file-system`, e **não** como o objeto
 * `{ uri, name, type }` que o React Native aceita. A partir do SDK 54 o Expo
 * substitui o `fetch` global pela implementação dele, que não entende esse
 * formato — ela aceita texto, `Blob`, ou objeto com `bytes()`, e recusa o
 * resto com "Unsupported FormDataPart implementation".
 *
 * O `File` serve porque implementa `Blob`: expõe `bytes()`, e também `name` e
 * `type`, que viram o `filename` e o content-type da parte. O `filename` não é
 * detalhe — é ele que faz o FastAPI tratar a parte como arquivo em vez de
 * campo de texto.
 */
async function montarFormulario(batida: BatidaPendente): Promise<FormData> {
  const dados = new FormData();

  const arquivo = new File(batida.fotoUri);
  if (!arquivo.exists) {
    // Acontece com batida represada: a foto fica no cache, e o Android pode
    // limpá-lo. Falhar aqui com o motivo certo evita reenviar para sempre uma
    // batida que nunca vai completar.
    throw new ApiError("A foto desta batida não está mais no aparelho.", 422);
  }
  dados.append("selfie", arquivo as unknown as Blob);

  dados.append("evidence", JSON.stringify(batida.sinais));
  dados.append("idempotency_key", batida.idempotencyKey);
  dados.append("client_recorded_at", batida.capturadaEm);

  // Só vão se a empresa os pedir. Mandar campo vazio quando a configuração é
  // "oculto" faria o servidor recusar a batida.
  if (batida.rotulo) dados.append("label", batida.rotulo);
  if (batida.observacao) dados.append("note", batida.observacao);

  // `entry_type` fica de fora de propósito: o servidor deduz entrada ou saída
  // pela última batida, o que tira do funcionário uma escolha que ele pode
  // errar — e um erro aí vira hora extra fantasma ou falta indevida. A exceção
  // é o rótulo escolhido de uma lista do RH, e mesmo aí quem traduz rótulo em
  // tipo é o servidor, não o app.
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
  declarado: { rotulo?: string; observacao?: string } = {},
): Promise<ResultadoEnvio> {
  const batida: BatidaPendente = {
    idempotencyKey: novaChave(),
    fotoUri,
    sinais,
    capturadaEm: new Date().toISOString(),
    tentativas: 0,
    rotulo: declarado.rotulo?.trim() || undefined,
    observacao: declarado.observacao?.trim() || undefined,
  };

  try {
    const resposta = await enviarMultipart<RespostaPonto>(
      "/time-entries",
      await montarFormulario(batida),
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
      await enviarMultipart<RespostaPonto>(
        "/time-entries",
        await montarFormulario(batida),
      );
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
