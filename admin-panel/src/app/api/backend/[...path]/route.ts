import { NextResponse } from "next/server";

import { backendUrl, clearSession, readSession, saveSession } from "@/lib/session";

/**
 * Encaminha as chamadas do painel ao backend, anexando o token no servidor.
 *
 * E a contrapartida de guardar a sessao em cookie httpOnly: como o navegador
 * nao le o token, quem o anexa e este proxy. Ele tambem renova a sessao
 * sozinho — o access token dura 30 minutos, e sem isso o RH seria deslogado no
 * meio de um cadastro.
 *
 * Repassa o corpo como stream e devolve a resposta como blob, para funcionar
 * igual com JSON, multipart (fotos do enrollment), imagem e CSV.
 */

const METODOS_COM_CORPO = new Set(["POST", "PUT", "PATCH"]);

async function encaminhar(request: Request, caminho: string[]) {
  const url = new URL(request.url);
  const destino = backendUrl(`/api/v1/${caminho.join("/")}${url.search}`);

  const corpo = METODOS_COM_CORPO.has(request.method)
    ? await request.arrayBuffer()
    : undefined;

  const { accessToken } = await readSession();
  let resposta = await chamar(destino, request, accessToken, corpo);

  // 401 aqui significa access token expirado — o refresh vale 30 dias.
  if (resposta.status === 401) {
    const novoToken = await renovar();
    if (novoToken) {
      resposta = await chamar(destino, request, novoToken, corpo);
    } else {
      await clearSession();
      return NextResponse.json({ detail: "Sessao expirada" }, { status: 401 });
    }
  }

  const conteudo = await resposta.arrayBuffer();
  const cabecalhos = new Headers();

  for (const nome of ["content-type", "content-disposition", "cache-control"]) {
    const valor = resposta.headers.get(nome);
    if (valor) cabecalhos.set(nome, valor);
  }

  return new NextResponse(conteudo, {
    status: resposta.status,
    headers: cabecalhos,
  });
}

function chamar(
  destino: string,
  request: Request,
  token: string | null,
  corpo: ArrayBuffer | undefined,
) {
  const cabecalhos = new Headers();

  // Repassa o content-type original: e o que preserva o boundary do multipart
  // quando o painel envia as fotos do cadastro biometrico.
  const tipo = request.headers.get("content-type");
  if (tipo) cabecalhos.set("content-type", tipo);
  if (token) cabecalhos.set("authorization", `Bearer ${token}`);

  return fetch(destino, {
    method: request.method,
    headers: cabecalhos,
    body: corpo,
    cache: "no-store",
  });
}

async function renovar(): Promise<string | null> {
  const { refreshToken } = await readSession();
  if (!refreshToken) return null;

  const resposta = await fetch(backendUrl("/api/v1/auth/refresh"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refreshToken }),
    cache: "no-store",
  });

  if (!resposta.ok) return null;

  const tokens = await resposta.json();
  await saveSession(tokens);
  return tokens.access_token as string;
}

type Contexto = { params: Promise<{ path: string[] }> };

export async function GET(request: Request, { params }: Contexto) {
  return encaminhar(request, (await params).path);
}

export async function POST(request: Request, { params }: Contexto) {
  return encaminhar(request, (await params).path);
}

export async function PATCH(request: Request, { params }: Contexto) {
  return encaminhar(request, (await params).path);
}

export async function DELETE(request: Request, { params }: Contexto) {
  return encaminhar(request, (await params).path);
}
