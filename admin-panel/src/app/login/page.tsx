"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Alerta, Button, Field, Input } from "@/components/ui";

export default function LoginPage() {
  const router = useRouter();
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  async function entrar(evento: React.FormEvent<HTMLFormElement>) {
    evento.preventDefault();
    setErro(null);
    setEnviando(true);

    const dados = new FormData(evento.currentTarget);

    try {
      const resposta = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          tenant_slug: String(dados.get("tenant_slug")).trim(),
          email: String(dados.get("email")).trim().toLowerCase(),
          password: String(dados.get("password")),
        }),
      });

      if (!resposta.ok) {
        const corpo = await resposta.json().catch(() => ({}));
        setErro(corpo.detail ?? "Não foi possível entrar");
        return;
      }

      router.push("/pontos");
      router.refresh();
    } catch {
      setErro("Não foi possível falar com o servidor");
    } finally {
      setEnviando(false);
    }
  }

  return (
    <main className="flex flex-1 items-center justify-center p-6">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <h1 className="text-2xl font-semibold">Ponto Facial</h1>
          <p className="mt-1 text-sm text-zinc-500">Painel administrativo</p>
        </div>

        <form
          onSubmit={entrar}
          className="space-y-4 rounded-lg border border-zinc-200 bg-white p-6 shadow-sm dark:border-zinc-800 dark:bg-zinc-900"
        >
          {erro && <Alerta>{erro}</Alerta>}

          <Field
            label="Empresa"
            hint="Código da empresa, informado na implantação"
          >
            <Input
              name="tenant_slug"
              required
              autoFocus
              autoComplete="organization"
              placeholder="empresa-demo"
            />
          </Field>

          <Field label="E-mail">
            <Input name="email" type="email" required autoComplete="username" />
          </Field>

          <Field label="Senha">
            <Input
              name="password"
              type="password"
              required
              autoComplete="current-password"
            />
          </Field>

          <Button type="submit" className="w-full" disabled={enviando}>
            {enviando ? "Entrando…" : "Entrar"}
          </Button>
        </form>
      </div>
    </main>
  );
}
