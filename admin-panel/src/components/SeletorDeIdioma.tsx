"use client";

import { useRouter } from "next/navigation";

import { useIdioma } from "@/i18n/contexto";
import { COOKIE_IDIOMA, IDIOMAS, type Idioma } from "@/i18n/idioma";

/**
 * Troca o idioma da sessão.
 *
 * Grava o cookie e chama `router.refresh()`: o idioma é lido no layout raiz,
 * que roda no servidor, então recarregar a árvore é o que faz o `<html lang>`
 * e o provider acompanharem. Sem o refresh, só o que já estava montado mudaria.
 *
 * Um ano de validade porque a escolha é do aparelho, não da sessão — quem
 * troca para português não quer refazer isso a cada login.
 */
const NOMES: Record<Idioma, string> = {
  en: "English",
  pt: "Português",
};

export function SeletorDeIdioma() {
  const router = useRouter();
  const { idioma } = useIdioma();

  function trocar(novo: string) {
    document.cookie = `${COOKIE_IDIOMA}=${novo}; path=/; max-age=${60 * 60 * 24 * 365}; samesite=lax`;
    router.refresh();
  }

  return (
    <select
      value={idioma}
      onChange={(e) => trocar(e.target.value)}
      aria-label={NOMES[idioma]}
      className="rounded-md border border-zinc-300 bg-white px-2 py-1 text-xs text-zinc-600 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-400"
    >
      {IDIOMAS.map((valor) => (
        <option key={valor} value={valor}>
          {NOMES[valor]}
        </option>
      ))}
    </select>
  );
}
