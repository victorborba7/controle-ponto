/**
 * Formatação para leitura humana, dependente do idioma.
 *
 * Antes isto era `lib/format.ts` com `pt-BR` fixo em três lugares. O detalhe
 * que torna isso perigoso nos EUA: `03/04` é 3 de abril no Brasil e 4 de março
 * lá. Numa tela de ponto, essa ambiguidade não é cosmética — é a data de uma
 * jornada de trabalho.
 *
 * Por isso o formatador é criado a partir do idioma, e não importado pronto.
 */

import type {
  EmployeeStatus,
  EntryType,
  LocationMethod,
  TimeEntryStatus,
} from "@/lib/types";

import { type Chave, dicionario } from "./dicionario";
import type { Idioma } from "./idioma";

/** Sem valor não se inventa zero: traço deixa claro que o dado não existe. */
const AUSENTE = "—";

const LOCALE_INTL: Record<Idioma, string> = {
  en: "en-US",
  pt: "pt-BR",
};

/** Unidade de distância exibida, e o fator a partir do metro (a do banco). */
const UNIDADE: Record<Idioma, string> = { en: "ft", pt: "m" };
const FATOR: Record<Idioma, number> = { en: 3.28084, pt: 1 };

const CHAVE_TIPO: Record<EntryType, Chave> = {
  in: "tipo.in",
  out: "tipo.out",
  break_start: "tipo.break_start",
  break_end: "tipo.break_end",
};

const CHAVE_STATUS: Record<TimeEntryStatus, Chave> = {
  approved: "status.approved",
  pending_review: "status.pending_review",
  rejected: "status.rejected",
};

const CHAVE_METODO: Record<LocationMethod, Chave> = {
  beacon: "metodo.beacon",
  wifi: "metodo.wifi",
  gps: "metodo.gps",
  none: "metodo.none",
};

const CHAVE_STATUS_FUNCIONARIO: Record<EmployeeStatus, Chave> = {
  active: "situacao.active",
  inactive: "situacao.inactive",
  suspended: "situacao.suspended",
};

/**
 * Código de problema de qualidade -> chave da orientação.
 *
 * O backend devolve código (`blurry`, `face_too_small`) justamente para o
 * painel dizer o que FAZER. "Qualidade insuficiente" não informa a ninguém se
 * deve chegar mais perto, acender a luz ou firmar a mão.
 */
const CHAVE_QUALIDADE: Record<string, Chave> = {
  blurry: "qualidade.blurry",
  face_too_small: "qualidade.face_too_small",
  face_too_far: "qualidade.face_too_far",
  face_cropped: "qualidade.face_cropped",
  low_detection_confidence: "qualidade.low_detection_confidence",
};

export type Formatador = ReturnType<typeof criarFormatador>;

export function criarFormatador(idioma: Idioma) {
  const locale = LOCALE_INTL[idioma];
  const t = (chave: Chave) => dicionario[idioma][chave];

  const dataHora = new Intl.DateTimeFormat(locale, {
    dateStyle: "short",
    timeStyle: "short",
  });
  const somenteData = new Intl.DateTimeFormat(locale, { dateStyle: "short" });
  const numero = new Intl.NumberFormat(locale);

  return {
    dataHora(iso: string | null | undefined) {
      return iso ? dataHora.format(new Date(iso)) : AUSENTE;
    },

    data(iso: string | null | undefined) {
      return iso ? somenteData.format(new Date(iso)) : AUSENTE;
    },

    percentual(valor: number | null | undefined) {
      if (valor === null || valor === undefined) return AUSENTE;
      return `${Math.round(valor * 100)}%`;
    },

    /**
     * Distância na unidade que o leitor espera.
     *
     * Metro para quem lê em português, pé para quem lê em inglês americano:
     * um RH em Ohio não tem intuição de quanto são 40 m de raio, e essa
     * intuição é justamente o que a tela precisa dar.
     *
     * **O banco continua em metros, sempre.** A conversão vive só aqui, na
     * borda de exibição — unidade de armazenamento que muda com o idioma de
     * quem está olhando seria um defeito esperando acontecer.
     */
    distancia(metros: number | null | undefined) {
      if (metros === null || metros === undefined) return AUSENTE;
      return `${numero.format(Math.round(metros * FATOR[idioma]))} ${UNIDADE[idioma]}`;
    },

    /** Símbolo da unidade, para rotular um campo de entrada. */
    unidadeDistancia: UNIDADE[idioma],

    /** Metros -> o número que o campo de entrada mostra. */
    distanciaParaCampo(metros: number) {
      return Math.round(metros * FATOR[idioma]);
    },

    /** O que foi digitado no campo -> metros, para gravar. */
    distanciaEmMetros(valor: number) {
      return Math.round(valor / FATOR[idioma]);
    },

    tipo(valor: EntryType) {
      return t(CHAVE_TIPO[valor]);
    },

    status(valor: TimeEntryStatus) {
      return t(CHAVE_STATUS[valor]);
    },

    metodo(valor: LocationMethod) {
      return t(CHAVE_METODO[valor]);
    },

    situacao(valor: EmployeeStatus) {
      return t(CHAVE_STATUS_FUNCIONARIO[valor]);
    },

    /**
     * Por que uma foto foi recusada, em orientação acionável.
     *
     * `reason` chega como código do catálogo do backend; `issues` são os
     * problemas de qualidade. Código desconhecido é exibido cru de propósito:
     * some da tela é pior do que aparecer feio, porque quem está cadastrando
     * fica sem saber o que corrigir.
     */
    recusa(reason: string, issues: string[]): string {
      if (issues.length) {
        return issues.map((i) => (CHAVE_QUALIDADE[i] ? t(CHAVE_QUALIDADE[i]) : i)).join("; ");
      }
      const chave = `recusa.${reason}` as Chave;
      return chave in dicionario[idioma] ? t(chave) : reason;
    },
  };
}

/** Converte um ISO em UTC para o valor que um `<input type="datetime-local">` espera. */
export function paraInputDataHora(iso: string) {
  const d = new Date(iso);
  const local = new Date(d.getTime() - d.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 16);
}
