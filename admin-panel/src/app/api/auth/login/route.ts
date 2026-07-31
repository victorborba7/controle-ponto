import { NextResponse } from "next/server";

import { backendUrl, saveSession } from "@/lib/session";

/**
 * Login do painel.
 *
 * O navegador nunca recebe os tokens: eles vao direto para cookies httpOnly.
 * A resposta traz apenas quem entrou, para a interface montar o cabecalho.
 */
export async function POST(request: Request) {
  const body = await request.json();

  const resposta = await fetch(backendUrl("/api/v1/auth/admin/login"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  });

  if (!resposta.ok) {
    const erro = await resposta.json().catch(() => ({}));
    return NextResponse.json(
      { detail: erro.detail ?? "Nao foi possivel entrar" },
      { status: resposta.status },
    );
  }

  const dados = await resposta.json();
  await saveSession(dados.tokens);

  return NextResponse.json({ user: dados.user, tenant: dados.tenant });
}
