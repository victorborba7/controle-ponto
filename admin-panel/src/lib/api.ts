/**
 * Cliente da API, usado pelos componentes do navegador.
 *
 * Aponta para `/api/backend/...` — o proxy do proprio Next —, nunca para o
 * backend direto. E o que permite a sessao viver em cookie httpOnly: o token
 * e anexado no servidor, fora do alcance de qualquer script da pagina.
 */

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }

  /** A sessao caiu e o usuario precisa entrar de novo. */
  get isUnauthorized() {
    return this.status === 401;
  }
}

async function extrairMensagem(resposta: Response): Promise<string> {
  try {
    const corpo = await resposta.json();
    const detalhe = corpo?.detail;

    if (typeof detalhe === "string") return detalhe;

    // Erro de validacao do FastAPI: uma lista de problemas por campo. Sem este
    // tratamento, a tela exibiria "[object Object]".
    if (Array.isArray(detalhe)) {
      return detalhe.map((item) => item?.msg ?? String(item)).join("; ");
    }
    if (detalhe) return JSON.stringify(detalhe);
  } catch {
    // Resposta sem corpo JSON (502 do proxy, por exemplo).
  }
  return `Falha na requisicao (HTTP ${resposta.status})`;
}

async function requisitar<T>(
  caminho: string,
  init: RequestInit = {},
): Promise<T> {
  const resposta = await fetch(`/api/backend${caminho}`, {
    ...init,
    cache: "no-store",
  });

  if (!resposta.ok) {
    throw new ApiError(await extrairMensagem(resposta), resposta.status);
  }

  if (resposta.status === 204) return undefined as T;
  return (await resposta.json()) as T;
}

export const api = {
  get: <T>(caminho: string) => requisitar<T>(caminho),

  post: <T>(caminho: string, corpo?: unknown) =>
    requisitar<T>(caminho, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: corpo === undefined ? undefined : JSON.stringify(corpo),
    }),

  patch: <T>(caminho: string, corpo: unknown) =>
    requisitar<T>(caminho, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(corpo),
    }),

  delete: <T>(caminho: string) => requisitar<T>(caminho, { method: "DELETE" }),

  /**
   * Envio multipart. Sem `Content-Type` explicito de proposito: o navegador
   * precisa gerar o boundary, e defini-lo a mao quebraria o upload.
   */
  upload: <T>(caminho: string, dados: FormData) =>
    requisitar<T>(caminho, { method: "POST", body: dados }),

  /** Baixa um arquivo (CSV, foto) preservando o nome sugerido pelo backend. */
  async download(caminho: string, nomePadrao: string) {
    const resposta = await fetch(`/api/backend${caminho}`, { cache: "no-store" });
    if (!resposta.ok) {
      throw new ApiError(await extrairMensagem(resposta), resposta.status);
    }

    const disposicao = resposta.headers.get("content-disposition") ?? "";
    const nome = /filename="?([^"]+)"?/.exec(disposicao)?.[1] ?? nomePadrao;

    const blob = await resposta.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = nome;
    link.click();
    URL.revokeObjectURL(url);
  },
};

export function paramsDe(filtros: Record<string, string | undefined | null>) {
  const params = new URLSearchParams();
  for (const [chave, valor] of Object.entries(filtros)) {
    if (valor) params.set(chave, valor);
  }
  const texto = params.toString();
  return texto ? `?${texto}` : "";
}
