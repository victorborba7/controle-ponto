/**
 * Fila de batidas pendentes de envio.
 *
 * O hangar tem ponto cego de sinal. Sem fila, o funcionário bateria o ponto,
 * veria um erro de rede e ficaria sem saber se o registro valeu — e o
 * comportamento natural seria bater de novo, gerando duplicata.
 *
 * Cada batida carrega uma **chave de idempotência** gerada no momento da
 * captura e preservada em todas as tentativas. É ela que garante que dez
 * reenvios da mesma batida virem um registro só, e não dez.
 *
 * As fotos ficam no sistema de arquivos do app (a câmera já as grava lá) e a
 * fila guarda só o caminho: um base64 de selfie em AsyncStorage estouraria o
 * limite de tamanho com poucas batidas represadas.
 */

import AsyncStorage from "@react-native-async-storage/async-storage";

import type { SinaisColetados } from "./localizacao";

const CHAVE_FILA = "ponto_fila";

/** Depois disso, um registro represado não é mais confiável nem útil. */
const VALIDADE_HORAS = 48;

export type BatidaPendente = {
  idempotencyKey: string;
  fotoUri: string;
  sinais: SinaisColetados;
  capturadaEm: string;
  tentativas: number;
  ultimoErro?: string;
  /**
   * O que o funcionário declarou, quando a empresa pede (ver `configBatida`).
   *
   * Vai na fila junto com a batida: uma batida represada por falta de sinal
   * precisa subir com o que a pessoa escreveu na hora, não com o que ela
   * escreveria horas depois.
   */
  rotulo?: string;
  /**
   * Declaração de que esta é a última batida do dia.
   *
   * Vai na fila pelo mesmo motivo dos outros dois: uma saída represada por
   * falta de sinal no hangar precisa chegar ao servidor **como saída**. Perder
   * este campo no caminho transformaria o fim da jornada numa batida comum, e
   * o dia ficaria aberto para sempre — inclusive para as notificações.
   */
  encerraODia?: boolean;
  observacao?: string;
};

export async function lerFila(): Promise<BatidaPendente[]> {
  const bruto = await AsyncStorage.getItem(CHAVE_FILA);
  if (!bruto) return [];

  try {
    const fila = JSON.parse(bruto) as BatidaPendente[];
    return descartarExpiradas(fila);
  } catch {
    // Fila corrompida não pode travar o app: melhor perder o histórico local
    // de envio do que impedir novas batidas.
    await AsyncStorage.removeItem(CHAVE_FILA);
    return [];
  }
}

async function gravar(fila: BatidaPendente[]) {
  await AsyncStorage.setItem(CHAVE_FILA, JSON.stringify(fila));
}

function descartarExpiradas(fila: BatidaPendente[]): BatidaPendente[] {
  const limite = Date.now() - VALIDADE_HORAS * 60 * 60 * 1000;
  return fila.filter((b) => new Date(b.capturadaEm).getTime() > limite);
}

export async function enfileirar(batida: BatidaPendente) {
  const fila = await lerFila();
  fila.push(batida);
  await gravar(fila);
}

export async function remover(idempotencyKey: string) {
  const fila = await lerFila();
  await gravar(fila.filter((b) => b.idempotencyKey !== idempotencyKey));
}

export async function registrarFalha(idempotencyKey: string, erro: string) {
  const fila = await lerFila();
  const alvo = fila.find((b) => b.idempotencyKey === idempotencyKey);
  if (alvo) {
    alvo.tentativas += 1;
    alvo.ultimoErro = erro;
    await gravar(fila);
  }
}

export function novaChave(): string {
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
}
