/**
 * Tradução do app.
 *
 * ## Por que `t()` é função de módulo, e não um hook
 *
 * O painel usa contexto React porque o idioma vem de um cookie e pode mudar
 * sem recarregar. Aqui ele vem do aparelho e é fixo enquanto o app está
 * aberto — um contexto só acrescentaria árvore para propagar algo constante.
 *
 * O que decide, porém, é outra coisa: **metade dos textos nasce fora de
 * componente**. `permissoes.ts`, `localizacao.ts` e `ponto.ts` produzem
 * mensagens que a tela apenas exibe, e um hook não é chamável de lá. Ou os
 * serviços devolveriam chaves para a tela traduzir — espalhando a
 * responsabilidade — ou a tradução fica acessível de qualquer lugar. É esta.
 */

import { dicionario, type Chave } from "./dicionario";
import { IDIOMA_PADRAO, idiomaDoAparelho, type Idioma } from "./idioma";

export type { Chave, Idioma };

//: Resolvido uma vez, na carga do módulo. O idioma do aparelho não muda
//: enquanto o app está aberto; se mudar, o sistema reinicia o app de qualquer
//: forma.
let idiomaAtual: Idioma = idiomaDoAparelho();

export function idioma(): Idioma {
  return idiomaAtual;
}

/** Só para teste: fixa o idioma sem depender do aparelho. */
export function definirIdioma(novo: Idioma): void {
  idiomaAtual = novo;
}

export function t(
  chave: Chave,
  parametros?: Record<string, string | number>,
): string {
  const catalogo = dicionario[idiomaAtual] ?? dicionario[IDIOMA_PADRAO];
  const texto = catalogo[chave];
  if (!parametros) return texto;
  return texto.replace(/\{(\w+)\}/g, (inteiro, nome: string) =>
    nome in parametros ? String(parametros[nome]) : inteiro,
  );
}

/**
 * Traduz um código que veio do backend, caindo no próprio código se não houver
 * tradução.
 *
 * Backend novo com valor que este app ainda não conhece é cenário real: o
 * servidor atualiza sozinho e os aparelhos atualizam quando cada pessoa
 * atualiza. Exibir `break_start` é feio; exibir vazio esconde a informação.
 */
export function tCodigo(prefixo: string, codigo: string | null | undefined): string {
  if (!codigo) return t(`${prefixo}.none` as Chave) ?? "";
  const chave = `${prefixo}.${codigo}` as Chave;
  return dicionario[idiomaAtual][chave] ?? codigo;
}
