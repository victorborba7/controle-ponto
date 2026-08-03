"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import type { AdminProfile } from "@/lib/types";

const navegacao = [
  { href: "/pontos", rotulo: "Pontos" },
  { href: "/funcionarios", rotulo: "Funcionários" },
  { href: "/locais", rotulo: "Locais" },
  { href: "/configuracoes", rotulo: "Configurações" },
];

type Sessao = {
  subject_id: string;
  name: string;
  role: AdminProfile["role"];
  tenant_id: string;
};

export function Shell({ children }: { children: React.ReactNode }) {
  const caminho = usePathname();
  const router = useRouter();
  const [sessao, setSessao] = useState<Sessao | null>(null);

  useEffect(() => {
    api
      .get<Sessao>("/auth/me")
      .then(setSessao)
      .catch(() => {
        // Sessao caiu enquanto a aba estava aberta.
        router.push("/login");
      });
  }, [router]);

  async function sair() {
    await fetch("/api/auth/logout", { method: "POST" });
    router.push("/login");
    router.refresh();
  }

  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-b border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-8 gap-y-3 px-6 py-3">
          <Link href="/pontos" className="font-semibold">
            Ponto Facial
          </Link>

          <nav className="flex gap-1">
            {navegacao.map((item) => {
              const ativo = caminho.startsWith(item.href);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`rounded-md px-3 py-1.5 text-sm transition-colors ${
                    ativo
                      ? "bg-zinc-100 font-medium text-zinc-900 dark:bg-zinc-800 dark:text-zinc-100"
                      : "text-zinc-600 hover:bg-zinc-50 dark:text-zinc-400 dark:hover:bg-zinc-800/60"
                  }`}
                >
                  {item.rotulo}
                </Link>
              );
            })}
          </nav>

          <div className="ml-auto flex items-center gap-3 text-sm">
            {sessao && (
              <span className="text-zinc-500 dark:text-zinc-400">{sessao.name}</span>
            )}
            <button
              onClick={sair}
              className="rounded-md px-2 py-1 text-zinc-600 hover:bg-zinc-100 dark:text-zinc-400 dark:hover:bg-zinc-800"
            >
              Sair
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto w-full max-w-7xl flex-1 p-6">{children}</main>
    </div>
  );
}
