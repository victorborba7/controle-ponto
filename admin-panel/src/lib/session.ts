/**
 * Sessao do painel, guardada em cookies httpOnly.
 *
 * Os tokens NAO ficam em localStorage, que e o padrao mais comum em SPA. O
 * motivo e concreto: o refresh token vale 30 dias e da acesso a dados
 * biometricos de todos os funcionarios da empresa. Em localStorage, qualquer
 * XSS — inclusive vindo de uma dependencia comprometida — o entrega inteiro.
 * Um cookie httpOnly nao e legivel por JavaScript.
 *
 * O custo e um proxy no proprio Next (`/api/backend/...`) que anexa o token
 * no servidor. Em troca, o navegador nunca ve credencial nenhuma.
 */

import { cookies } from "next/headers";

const ACCESS_COOKIE = "ponto_access";
const REFRESH_COOKIE = "ponto_refresh";

/** Duracao do refresh no backend (REFRESH_TOKEN_TTL_DAYS). */
const REFRESH_MAX_AGE = 30 * 24 * 60 * 60;

const baseCookie = {
  httpOnly: true,
  sameSite: "lax" as const,
  // Em producao o painel roda em HTTPS; em desenvolvimento, http://localhost
  // nao aceitaria um cookie marcado como secure.
  secure: process.env.NODE_ENV === "production",
  path: "/",
};

export type SessionTokens = {
  access_token: string;
  refresh_token: string;
  expires_in: number;
};

export async function saveSession(tokens: SessionTokens) {
  const jar = await cookies();

  jar.set(ACCESS_COOKIE, tokens.access_token, {
    ...baseCookie,
    maxAge: tokens.expires_in,
  });
  jar.set(REFRESH_COOKIE, tokens.refresh_token, {
    ...baseCookie,
    maxAge: REFRESH_MAX_AGE,
  });
}

export async function readSession() {
  const jar = await cookies();
  return {
    accessToken: jar.get(ACCESS_COOKIE)?.value ?? null,
    refreshToken: jar.get(REFRESH_COOKIE)?.value ?? null,
  };
}

export async function clearSession() {
  const jar = await cookies();
  jar.delete(ACCESS_COOKIE);
  jar.delete(REFRESH_COOKIE);
}

export function backendUrl(path: string) {
  const base = process.env.BACKEND_URL ?? "http://localhost:8000";
  return `${base.replace(/\/$/, "")}${path}`;
}
