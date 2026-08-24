/**
 * Idiomas do painel e como um deles é escolhido.
 *
 * Três fontes, em ordem de precedência:
 *
 * 1. **O cookie**, quando a pessoa usou o seletor. Escolha explícita ganha de
 *    qualquer palpite.
 * 2. **O `Accept-Language` do navegador**, na primeira visita. Mesmo critério
 *    que o app do funcionário aplica sobre os idiomas do aparelho.
 * 3. **Inglês**, quando o navegador não pede nenhum idioma que o painel fale.
 *
 * Inglês como último recurso, e não como padrão fixo, foi correção: antes o
 * painel abria em inglês para todo mundo, e um usuário brasileiro tinha de
 * trocar no seletor a cada primeira visita de cada navegador.
 *
 * O português fica porque o projeto nasceu nele, e porque um catálogo de um
 * idioma só não prova que a estrutura aguenta dois.
 *
 * A escolha viaja em **cookie**, não no caminho da URL. Painel autenticado não
 * tem SEO a defender, e `/{locale}/employees` custaria middleware, um segmento
 * `[locale]` em toda rota e links que precisam lembrar do prefixo: tudo para
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
/**
 * Escolhe o idioma a partir do cabeçalho `Accept-Language` do navegador.
 *
 * Percorre as preferências na ordem em que a pessoa as definiu, respeitando o
 * peso `q`. Um navegador configurado como espanhol > português > inglês cai em
 * português, e não em inglês: parar na primeira que o painel conhece é o que
 * honra a segunda escolha de quem tem mais de um idioma.
 *
 * Mesma lógica que o app do funcionário aplica sobre os idiomas do aparelho, e
 * que o backend já aplica para traduzir as mensagens de erro.
 */
export function deAccept(cabecalho: string | undefined | null): Idioma | null {
  if (!cabecalho) return null;

  const preferencias = cabecalho
    .split(",")
    .map((parte) => {
      const [tag, ...parametros] = parte.trim().split(";");
      const q = parametros
        .map((p) => p.trim())
        .find((p) => p.startsWith("q="));
      return { tag: tag.trim(), q: q ? Number(q.slice(2)) : 1 };
    })
    .filter((p) => p.tag && Number.isFinite(p.q) && p.q > 0)
    // `sort` é estável, então empate em `q` preserva a ordem do cabeçalho.
    .sort((a, b) => b.q - a.q);

  for (const { tag } of preferencias) {
    const base = tag.split("-")[0].toLowerCase();
    if (ehIdioma(base)) return base;
  }
  return null;
}

export function normalizar(valor: string | undefined | null): Idioma {
  if (!valor) return IDIOMA_PADRAO;
  const base = valor.split("-")[0].toLowerCase();
  return ehIdioma(base) ? base : IDIOMA_PADRAO;
}
