"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Alerta, Button, Field, Input } from "@/components/ui";
import { useIdioma } from "@/i18n/contexto";
import { rotas } from "@/rotas";

export default function LoginPage() {
  const router = useRouter();
  const { t } = useIdioma();
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
        setErro(corpo.detail ?? t("login.falhou"));
        return;
      }

      router.push(rotas.pontos);
      router.refresh();
    } catch {
      setErro(t("login.semServidor"));
    } finally {
      setEnviando(false);
    }
  }

  return (
    <main className="flex flex-1 items-center justify-center p-6">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <h1 className="text-2xl font-semibold">{t("app.nome")}</h1>
          <p className="mt-1 text-sm text-zinc-500">{t("app.painel")}</p>
        </div>

        <form
          onSubmit={entrar}
          className="space-y-4 rounded-lg border border-zinc-200 bg-white p-6 shadow-sm dark:border-zinc-800 dark:bg-zinc-900"
        >
          {erro && <Alerta>{erro}</Alerta>}

          <Field label={t("login.empresa")} hint={t("login.empresaAjuda")}>
            <Input
              name="tenant_slug"
              required
              autoFocus
              autoComplete="organization"
              placeholder="empresa-demo"
            />
          </Field>

          <Field label={t("login.email")}>
            <Input name="email" type="email" required autoComplete="username" />
          </Field>

          <Field label={t("login.senha")}>
            <Input
              name="password"
              type="password"
              required
              autoComplete="current-password"
            />
          </Field>

          <Button type="submit" className="w-full" disabled={enviando}>
            {enviando ? t("login.entrando") : t("login.entrar")}
          </Button>
        </form>
      </div>
    </main>
  );
}
