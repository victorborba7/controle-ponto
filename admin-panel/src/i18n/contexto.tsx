"use client";

import { createContext, useContext, useMemo } from "react";

import { criarFormatador, type Formatador } from "./formato";
import { type Chave, dicionario } from "./dicionario";
import { IDIOMA_PADRAO, type Idioma } from "./idioma";

const Contexto = createContext<Idioma>(IDIOMA_PADRAO);

export function ProvedorDeIdioma({
  idioma,
  children,
}: {
  idioma: Idioma;
  children: React.ReactNode;
}) {
  return <Contexto.Provider value={idioma}>{children}</Contexto.Provider>;
}

export type Traduz = (chave: Chave, parametros?: Record<string, string | number>) => string;

/**
 * Resolve uma chave no idioma dado.
 *
 * Fora do componente para o teste conseguir chamar sem montar árvore React, e
 * para o `criarT` abaixo poder memorizar.
 */
export function traduzir(
  idioma: Idioma,
  chave: Chave,
  parametros?: Record<string, string | number>,
): string {
  const texto = dicionario[idioma][chave];
  if (!parametros) return texto;
  return texto.replace(/\{(\w+)\}/g, (inteiro, nome: string) =>
    nome in parametros ? String(parametros[nome]) : inteiro,
  );
}

/**
 * Texto e formatação no idioma da sessão.
 *
 * Os dois vêm juntos de propósito: data, percentual e rótulo de enum mudam
 * com o idioma tanto quanto uma frase, e separá-los em dois hooks convidaria
 * a traduzir o texto e esquecer a data — que é o defeito mais comum em
 * tradução parcial, e o mais difícil de notar revisando código.
 */
export function useIdioma(): { idioma: Idioma; t: Traduz; fmt: Formatador } {
  const idioma = useContext(Contexto);

  return useMemo(
    () => ({
      idioma,
      t: (chave, parametros) => traduzir(idioma, chave, parametros),
      fmt: criarFormatador(idioma),
    }),
    [idioma],
  );
}
