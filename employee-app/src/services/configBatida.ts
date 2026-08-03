/**
 * O que a empresa pede na batida, baixado do servidor e cacheado.
 *
 * Cacheia pelo mesmo motivo da configuração dos locais: o hangar tem área sem
 * sinal, e a tela de bater ponto precisa saber o que desenhar mesmo quando a
 * batida vai para a fila offline. Sem cache, quem entrasse sem sinal veria a
 * tela simples e bateria um ponto sem o rótulo que a empresa exige — e a
 * recusa só apareceria na sincronização, horas depois.
 */

import AsyncStorage from "@react-native-async-storage/async-storage";

import { get } from "./api";

const CHAVE_CACHE = "ponto_config_batida";

export type NoteMode = "hidden" | "optional" | "required";
export type LabelMode = "hidden" | "free" | "list";

export type ConfigBatida = {
  note_mode: NoteMode;
  note_prompt: string | null;
  label_mode: LabelMode;
  label_required: boolean;
  labels: { name: string }[];
};

/** Batida simples, sem campo nenhum. É o que vale enquanto nada foi baixado. */
export const CONFIG_PADRAO: ConfigBatida = {
  note_mode: "hidden",
  note_prompt: null,
  label_mode: "hidden",
  label_required: false,
  labels: [],
};

export async function lerCache(): Promise<ConfigBatida> {
  const bruto = await AsyncStorage.getItem(CHAVE_CACHE);
  if (!bruto) return CONFIG_PADRAO;

  try {
    return JSON.parse(bruto) as ConfigBatida;
  } catch {
    // Cache corrompido não pode impedir de bater ponto: descarta e segue no
    // padrão, que é sempre uma configuração válida.
    await AsyncStorage.removeItem(CHAVE_CACHE);
    return CONFIG_PADRAO;
  }
}

/**
 * Busca do servidor e atualiza o cache; devolve o cache se a rede falhar.
 *
 * Nunca lança. Uma configuração indisponível não pode barrar a batida — o
 * servidor valida de novo no recebimento, e é lá que a recusa tem de acontecer.
 */
export async function sincronizarConfig(): Promise<ConfigBatida> {
  try {
    const config = await get<ConfigBatida>("/punch-config/form");
    await AsyncStorage.setItem(CHAVE_CACHE, JSON.stringify(config));
    return config;
  } catch {
    return lerCache();
  }
}

/** Se a tela precisa mostrar algum campo além da câmera. */
export function pedeAlgo(config: ConfigBatida): boolean {
  return config.note_mode !== "hidden" || config.label_mode !== "hidden";
}

/**
 * O que impede de bater, conferido antes de acionar a câmera.
 *
 * Duplica a regra do servidor de propósito: descobrir que faltava um campo
 * depois de tirar a foto e enviar é pior aqui do que em qualquer outra tela —
 * numa área sem sinal a recusa chegaria só na sincronização.
 */
export function faltaPreencher(
  config: ConfigBatida,
  { label, note }: { label: string | null; note: string },
): string | null {
  if (config.note_mode === "required" && !note.trim()) {
    return config.note_prompt || "Escreva uma observação para continuar.";
  }
  if (config.label_required && config.label_mode !== "hidden" && !label?.trim()) {
    return "Escolha o tipo da batida para continuar.";
  }
  return null;
}
