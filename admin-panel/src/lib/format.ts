/**
 * Formatacao para leitura humana, em portugues do Brasil.
 *
 * Centralizado porque os mesmos valores aparecem em varias telas: o RH nao
 * pode ver "pending_review" numa e "Em revisao" noutra.
 */

import type {
  EmployeeStatus,
  EntryType,
  LocationMethod,
  TimeEntryStatus,
} from "./types";

const dataHora = new Intl.DateTimeFormat("pt-BR", {
  dateStyle: "short",
  timeStyle: "short",
});

const somenteData = new Intl.DateTimeFormat("pt-BR", { dateStyle: "short" });

export function formatarDataHora(iso: string | null | undefined) {
  if (!iso) return "—";
  return dataHora.format(new Date(iso));
}

export function formatarData(iso: string | null | undefined) {
  if (!iso) return "—";
  return somenteData.format(new Date(iso));
}

/** Converte um ISO em UTC para o valor que um `<input type="datetime-local">` espera. */
export function paraInputDataHora(iso: string) {
  const d = new Date(iso);
  const local = new Date(d.getTime() - d.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 16);
}

export function formatarPercentual(valor: number | null | undefined) {
  if (valor === null || valor === undefined) return "—";
  return `${Math.round(valor * 100)}%`;
}

export function formatarMetros(valor: number | null | undefined) {
  if (valor === null || valor === undefined) return "—";
  return `${Math.round(valor)} m`;
}

export const rotuloTipo: Record<EntryType, string> = {
  in: "Entrada",
  out: "Saída",
  break_start: "Início do intervalo",
  break_end: "Fim do intervalo",
};

export const rotuloStatus: Record<TimeEntryStatus, string> = {
  approved: "Aprovado",
  pending_review: "Em revisão",
  rejected: "Rejeitado",
};

export const rotuloMetodo: Record<LocationMethod, string> = {
  beacon: "Beacon",
  wifi: "Wi-Fi",
  gps: "GPS",
  none: "Nenhum",
};

export const rotuloStatusFuncionario: Record<EmployeeStatus, string> = {
  active: "Ativo",
  inactive: "Inativo",
  suspended: "Suspenso",
};

/**
 * Cor do metodo de localizacao, do mais forte ao mais fraco.
 *
 * A escala e a mesma da confianca definida na cadeia de validacao: o RH bate o
 * olho na coluna e sabe quanto aquele registro prova, sem precisar ler o
 * numero.
 */
export const corMetodo: Record<LocationMethod, string> = {
  beacon: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300",
  wifi: "bg-sky-100 text-sky-800 dark:bg-sky-950 dark:text-sky-300",
  gps: "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300",
  none: "bg-zinc-200 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300",
};

export const corStatus: Record<TimeEntryStatus, string> = {
  approved: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300",
  pending_review: "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300",
  rejected: "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300",
};
