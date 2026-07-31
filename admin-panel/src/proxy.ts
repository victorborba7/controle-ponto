import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

/**
 * Barra o acesso ao painel sem sessao.
 *
 * Checa apenas a presenca do cookie de refresh, e nao a validade do token:
 * validar aqui exigiria uma chamada ao backend em toda navegacao. A validacao
 * de verdade acontece no backend, a cada requisicao — isto so evita a tela
 * piscar para quem nunca entrou.
 *
 * O cookie de acesso nao serve para isto: ele expira em 30 minutos e o proxy
 * de API o renova sozinho, entao sua ausencia nao significa sessao encerrada.
 *
 * Arquivo `proxy.ts` e nao `middleware.ts`: e a convencao do Next 16, que
 * deprecou a anterior.
 */
export function proxy(request: NextRequest) {
  const temSessao = Boolean(request.cookies.get("ponto_refresh")?.value);
  const url = request.nextUrl.clone();
  const noLogin = url.pathname === "/login";

  if (!temSessao && !noLogin) {
    url.pathname = "/login";
    return NextResponse.redirect(url);
  }

  if (temSessao && noLogin) {
    url.pathname = "/pontos";
    return NextResponse.redirect(url);
  }

  return NextResponse.next();
}

export const config = {
  // Fora do matcher: rotas de API (o proxy de backend trata a sessao por conta
  // propria), arquivos estaticos e o favicon.
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico).*)"],
};
