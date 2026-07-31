import { NextResponse } from "next/server";

import { backendUrl, clearSession, readSession } from "@/lib/session";

/**
 * Encerra a sessao.
 *
 * Revoga o refresh no backend antes de apagar os cookies: limpar so o
 * navegador deixaria o token valido por mais 30 dias na mao de quem o tivesse
 * interceptado.
 */
export async function POST() {
  const { refreshToken } = await readSession();

  if (refreshToken) {
    await fetch(backendUrl("/api/v1/auth/logout"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
      cache: "no-store",
    }).catch(() => {
      // Backend fora do ar nao pode impedir o usuario de sair daqui.
    });
  }

  await clearSession();
  return NextResponse.json({ ok: true });
}
