/**
 * Cadastro do próprio rosto, feito pelo funcionário.
 *
 * O RH continua podendo cadastrar pelo painel; esta rota existe para o
 * recém-contratado não precisar se deslocar. O servidor só aceita **uma vez**:
 * havendo rosto ativo, o caminho volta a ser o RH.
 */

import { File } from "expo-file-system";

import { t } from "../i18n";

import { ApiError, enviarMultipart } from "./api";

/** Mínimo e máximo aceitos pelo servidor (`FACE_MIN/MAX_ENROLLMENT_IMAGES`). */
export const MINIMO_DE_FOTOS = 3;
export const MAXIMO_DE_FOTOS = 5;

export type FotoRecusada = {
  index: number;
  reason: string;
};

export type ResultadoCadastro = {
  criadas: number;
  recusadas: FotoRecusada[];
};

/**
 * Envia as fotos e o aceite do termo.
 *
 * O `File` do `expo-file-system` é usado em vez de `{ uri, name, type }`: o
 * Expo SDK 54 substituiu o `fetch` global, e a forma antiga passou a falhar com
 * "Unsupported FormDataPart implementation". Mesma razão documentada em
 * `ponto.ts` — a diferença aqui é que são várias partes com o mesmo nome, que
 * é como o FastAPI recebe `list[UploadFile]`.
 */
export async function cadastrarRosto(
  urisDasFotos: string[],
  versaoDoTermo: string,
): Promise<ResultadoCadastro> {
  if (urisDasFotos.length < MINIMO_DE_FOTOS) {
    throw new ApiError(t("cadastro.poucasFotos", { minimo: MINIMO_DE_FOTOS }), 422);
  }

  const dados = new FormData();

  urisDasFotos.slice(0, MAXIMO_DE_FOTOS).forEach((uri, indice) => {
    const arquivo = new File(uri);
    if (!arquivo.exists) {
      throw new ApiError(t("cadastro.fotoSumiu"), 422);
    }
    dados.append("images", arquivo, `rosto-${indice + 1}.jpg`);
  });

  dados.append("consent_policy_version", versaoDoTermo);
  dados.append("consent_granted", "true");

  const corpo = await enviarMultipart<{
    created: unknown[];
    rejected: FotoRecusada[];
  }>("/me/face-templates", dados);

  return {
    criadas: corpo.created.length,
    recusadas: corpo.rejected ?? [],
  };
}
