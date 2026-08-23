/**
 * Idioma do app, decidido pelo aparelho.
 *
 * Inglês é o padrão porque a operação é nos EUA — mesma razão do painel. O
 * português fica porque o projeto nasceu nele, e porque um catálogo de um
 * idioma só não prova que a estrutura aguenta dois.
 *
 * ## Por que não há seletor de idioma
 *
 * O painel tem um, e faz sentido lá: o RH escolhe. Aqui não. O funcionário
 * abre o app para bater ponto em dez segundos, e o aparelho dele já sabe em
 * que idioma ele lê — perguntar seria acrescentar uma tela de configuração
 * para responder algo que o sistema operacional já respondeu.
 *
 * Se um dia houver alguém cujo celular está num idioma e a pessoa prefere
 * outro, aí o seletor se justifica. Antes disso, não.
 */

import { getLocales } from "expo-localization";

export const IDIOMAS = ["en", "pt"] as const;
export type Idioma = (typeof IDIOMAS)[number];

export const IDIOMA_PADRAO: Idioma = "en";

export function ehIdioma(valor: string | undefined | null): valor is Idioma {
  return valor != null && (IDIOMAS as readonly string[]).includes(valor);
}

/**
 * Normaliza o que vier do sistema.
 *
 * `pt-BR` e `pt-PT` viram ambos `pt`: enquanto não houver texto que difira
 * entre as variantes, separá-las só criaria catálogo para manter.
 */
export function normalizar(valor: string | undefined | null): Idioma {
  if (!valor) return IDIOMA_PADRAO;
  const base = valor.split("-")[0].toLowerCase();
  return ehIdioma(base) ? base : IDIOMA_PADRAO;
}

/**
 * Percorre as preferências do aparelho na ordem em que a pessoa as definiu.
 *
 * Um celular configurado como espanhol > português > inglês deve cair em
 * português, não em inglês: parar na primeira que o app conhece respeita a
 * ordem de preferência, enquanto olhar só a primeira da lista descartaria a
 * segunda escolha de quem tem mais de um idioma.
 */
export function idiomaDoAparelho(): Idioma {
  try {
    for (const local of getLocales()) {
      const candidato = local.languageCode ?? local.languageTag;
      const base = candidato?.split("-")[0].toLowerCase();
      if (ehIdioma(base)) return base;
    }
  } catch {
    // getLocales() falhar não pode impedir o app de abrir.
  }
  return IDIOMA_PADRAO;
}
