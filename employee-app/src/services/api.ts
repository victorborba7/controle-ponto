/**
 * Cliente da API e sessão do funcionário.
 *
 * Os tokens ficam em `expo-secure-store` (Keychain no iOS, EncryptedSharedPreferences
 * no Android), e não em AsyncStorage: num aparelho com root ou num backup
 * desprotegido, AsyncStorage é um arquivo de texto legível.
 */

import * as SecureStore from "expo-secure-store";

import { t } from "../i18n";

const CHAVE_ACCESS = "ponto_access";
const CHAVE_REFRESH = "ponto_refresh";
const CHAVE_PERFIL = "ponto_perfil";
const CHAVE_DISPOSITIVO = "ponto_device_fingerprint";

export type Perfil = {
  employeeId: string;
  nome: string;
  matricula: string;
  cargo: string | null;
  precisaTrocarSenha: boolean;
  empresa: string;
  tenantSlug: string;
  /** Falso enquanto o funcionário não tiver cadastrado o próprio rosto. */
  rostoCadastrado: boolean;
};

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

/** Endereço do backend, definido no build (`EXPO_PUBLIC_API_URL`). */
export function baseUrl(): string {
  const url = process.env.EXPO_PUBLIC_API_URL;
  if (!url) {
    throw new Error(
      "EXPO_PUBLIC_API_URL não definido. Configure em .env antes de compilar.",
    );
  }
  return `${url.replace(/\/$/, "")}/api/v1`;
}

// --------------------------------------------------------------------------
// Sessão
// --------------------------------------------------------------------------

export async function salvarSessao(
  tokens: { access_token: string; refresh_token: string },
  perfil: Perfil,
) {
  await SecureStore.setItemAsync(CHAVE_ACCESS, tokens.access_token);
  await SecureStore.setItemAsync(CHAVE_REFRESH, tokens.refresh_token);
  await SecureStore.setItemAsync(CHAVE_PERFIL, JSON.stringify(perfil));
}

/**
 * Regrava só o perfil, mantendo os tokens.
 *
 * Usado quando algo do perfil muda sem novo login — hoje, o rosto passando a
 * estar cadastrado. Sem isto, fechar e reabrir o app devolveria o funcionário
 * à tela de cadastro que ele acabou de concluir.
 */
export async function salvarPerfil(perfil: Perfil) {
  await SecureStore.setItemAsync(CHAVE_PERFIL, JSON.stringify(perfil));
}

export async function lerPerfil(): Promise<Perfil | null> {
  const bruto = await SecureStore.getItemAsync(CHAVE_PERFIL);
  return bruto ? (JSON.parse(bruto) as Perfil) : null;
}

export async function temSessao(): Promise<boolean> {
  return (await SecureStore.getItemAsync(CHAVE_REFRESH)) !== null;
}

export async function encerrarSessao() {
  const refresh = await SecureStore.getItemAsync(CHAVE_REFRESH);

  if (refresh) {
    // Revoga no servidor antes de apagar daqui: limpar só o aparelho deixaria
    // o token valido por mais 30 dias.
    await fetch(`${baseUrl()}/auth/logout`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refresh }),
    }).catch(() => undefined);
  }

  await SecureStore.deleteItemAsync(CHAVE_ACCESS);
  await SecureStore.deleteItemAsync(CHAVE_REFRESH);
  await SecureStore.deleteItemAsync(CHAVE_PERFIL);
  // A identificação do aparelho NÃO é apagada: ela é do aparelho, não da
  // sessão. Reaproveitá-la mantém o pareamento no próximo login.
}

/**
 * Identificação estável deste aparelho.
 *
 * Gerada na primeira execução e guardada com a sessão. É o que amarra o ponto
 * a um celular conhecido — sem isso, uma credencial vazada bateria ponto de
 * qualquer lugar.
 */
export async function identificacaoDoAparelho(): Promise<string> {
  const existente = await SecureStore.getItemAsync(CHAVE_DISPOSITIVO);
  if (existente) return existente;

  const nova = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
  await SecureStore.setItemAsync(CHAVE_DISPOSITIVO, nova);
  return nova;
}

// --------------------------------------------------------------------------
// Requisições
// --------------------------------------------------------------------------

async function mensagemDoErro(resposta: Response): Promise<string> {
  try {
    const corpo = await resposta.json();
    const detalhe = corpo?.detail;
    if (typeof detalhe === "string") return detalhe;
    if (Array.isArray(detalhe)) {
      return detalhe.map((i) => i?.msg ?? String(i)).join("; ");
    }
  } catch {
    // Resposta sem corpo JSON.
  }
  return t("erro.httpGenerico", { status: resposta.status });
}

async function renovar(): Promise<string | null> {
  const refresh = await SecureStore.getItemAsync(CHAVE_REFRESH);
  if (!refresh) return null;

  const resposta = await fetch(`${baseUrl()}/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refresh }),
  });

  if (!resposta.ok) return null;

  const tokens = await resposta.json();
  await SecureStore.setItemAsync(CHAVE_ACCESS, tokens.access_token);
  await SecureStore.setItemAsync(CHAVE_REFRESH, tokens.refresh_token);
  return tokens.access_token as string;
}

export async function autenticado(caminho: string, init: RequestInit): Promise<Response> {
  const token = await SecureStore.getItemAsync(CHAVE_ACCESS);

  const chamar = (bearer: string | null) =>
    fetch(`${baseUrl()}${caminho}`, {
      ...init,
      headers: {
        ...(init.headers ?? {}),
        ...(bearer ? { Authorization: `Bearer ${bearer}` } : {}),
      },
    });

  let resposta = await chamar(token);

  if (resposta.status === 401) {
    const novo = await renovar();
    if (!novo) throw new ApiError(t("erro.sessaoExpirada"), 401);
    resposta = await chamar(novo);
  }

  return resposta;
}

export async function get<T>(caminho: string): Promise<T> {
  const resposta = await autenticado(caminho, { method: "GET" });
  if (!resposta.ok) throw new ApiError(await mensagemDoErro(resposta), resposta.status);
  return (await resposta.json()) as T;
}

export async function enviarMultipart<T>(
  caminho: string,
  dados: FormData,
): Promise<T> {
  // Sem `Content-Type` explícito: o runtime precisa gerar o boundary, e
  // defini-lo à mão quebra o upload.
  const resposta = await autenticado(caminho, { method: "POST", body: dados });
  if (!resposta.ok) throw new ApiError(await mensagemDoErro(resposta), resposta.status);
  return (await resposta.json()) as T;
}

// --------------------------------------------------------------------------
// Login
// --------------------------------------------------------------------------

export async function entrar(params: {
  tenantSlug: string;
  matricula: string;
  senha: string;
  plataforma: "android" | "ios";
  modelo?: string;
  versaoOs?: string;
  versaoApp: string;
}): Promise<Perfil> {
  const resposta = await fetch(`${baseUrl()}/auth/employee/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      tenant_slug: params.tenantSlug,
      external_code: params.matricula,
      password: params.senha,
      device: {
        fingerprint: await identificacaoDoAparelho(),
        platform: params.plataforma,
        model: params.modelo,
        os_version: params.versaoOs,
        app_version: params.versaoApp,
      },
    }),
  });

  if (!resposta.ok) {
    throw new ApiError(await mensagemDoErro(resposta), resposta.status);
  }

  const corpo = await resposta.json();
  const perfil: Perfil = {
    employeeId: corpo.employee.id,
    nome: corpo.employee.name,
    matricula: corpo.employee.external_code,
    cargo: corpo.employee.job_title ?? null,
    precisaTrocarSenha: corpo.employee.must_change_password,
    empresa: corpo.tenant.name,
    tenantSlug: corpo.tenant.slug,
    // Ausente num backend antigo: assumir "cadastrado" mantém o comportamento
    // anterior em vez de mandar quem já tem rosto refazer o cadastro.
    rostoCadastrado: corpo.employee.face_enrolled ?? true,
  };

  await salvarSessao(corpo.tokens, perfil);
  return perfil;
}
