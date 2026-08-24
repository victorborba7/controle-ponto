import type { Metadata } from "next";
import { Geist } from "next/font/google";
import { cookies, headers } from "next/headers";

import { ProvedorDeIdioma } from "@/i18n/contexto";
import { dicionario } from "@/i18n/dicionario";
import { COOKIE_IDIOMA, deAccept, normalizar } from "@/i18n/idioma";

import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

/**
 * O título da aba fica em inglês fixo, e não no idioma da sessão.
 *
 * `generateMetadata` conseguiria lê-lo do cookie — mas o título é a única
 * string que existe antes de qualquer sessão, e amarrá-lo ao cookie tornaria
 * a rota dinâmica só por causa disso. Não compensa.
 */
export const metadata: Metadata = {
  title: `${dicionario.en["app.nome"]}: ${dicionario.en["app.painel"]}`,
  description: dicionario.en["app.descricao"],
};

export default async function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  // O cookie ganha do navegador: quem usou o seletor fez uma escolha explícita,
  // e o cabeçalho do navegador é só um palpite sobre a mesma pergunta.
  const escolhido = (await cookies()).get(COOKIE_IDIOMA)?.value;
  const idioma = escolhido
    ? normalizar(escolhido)
    : (deAccept((await headers()).get("accept-language")) ?? normalizar(null));

  return (
    <html lang={idioma} className={`${geistSans.variable} h-full antialiased`}>
      <body className="flex min-h-full flex-col bg-zinc-50 text-zinc-900 dark:bg-zinc-950 dark:text-zinc-100">
        <ProvedorDeIdioma idioma={idioma}>{children}</ProvedorDeIdioma>
      </body>
    </html>
  );
}
