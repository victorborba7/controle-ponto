/**
 * Idiomas do painel e como um deles é escolhido.
 *
 * Inglês é o padrão porque a operação é nos EUA. O português fica porque o
 * projeto nasceu nele — e porque um catálogo de um idioma só não prova que a
 * estrutura aguenta dois.
 *
 * A escolha viaja em **cookie**, não no caminho da URL. Painel autenticado não
 * tem SEO a defender, e `/{locale}/employees` custaria middleware, um segmento
 * `[locale]` em toda rota e links que precisam lembrar do prefixo — tudo para
 * resolver um problema que este produto não tem.
 */

export const IDIOMAS = ["en", "pt"] as const;
export type Idioma = (typeof IDIOMAS)[number];

export const IDIOMA_PADRAO: Idioma = "en";

/** Nome do cookie. Legível pelo servidor no layout raiz e pelo cliente ao trocar. */
export const COOKIE_IDIOMA = "idioma";

export function ehIdioma(valor: string | undefined | null): valor is Idioma {
  return valor != null && (IDIOMAS as readonly string[]).includes(valor);
}

/**
 * Normaliza o que vier do cookie ou do `Accept-Language`.
 *
 * `pt-BR` e `pt-PT` viram ambos `pt`: enquanto não houver texto que difira
 * entre as variantes, separá-las só criaria catálogo para manter.
 */
export function normalizar(valor: string | undefined | null): Idioma {
  if (!valor) return IDIOMA_PADRAO;
  const base = valor.split("-")[0].toLowerCase();
  return ehIdioma(base) ? base : IDIOMA_PADRAO;
}
