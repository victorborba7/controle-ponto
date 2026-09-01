"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { CapturaWebcam } from "@/components/CapturaWebcam";
import {
  Alerta,
  Badge,
  Button,
  Card,
  Carregando,
  Field,
  Input,
  Tabela,
  Td,
  Th,
  Vazio,
} from "@/components/ui";
import { api } from "@/lib/api";
import {
  explicarRecusa,
  formatarData,
  formatarDataHora,
  formatarPercentual,
} from "@/lib/format";
import type {
  DeviceSummary,
  EmployeeDetail,
  EnrollmentResult,
  FaceTemplate,
  Paginated,
} from "@/lib/types";

/** Versão do termo de consentimento em vigor. Mudou o texto, mude aqui. */
const VERSAO_DO_TERMO = "2026.1";

const MIN_FOTOS = 3;
const MAX_FOTOS = 5;

export default function FuncionarioPage() {
  const { id } = useParams<{ id: string }>();

  const [funcionario, setFuncionario] = useState<EmployeeDetail | null>(null);
  const [templates, setTemplates] = useState<FaceTemplate[]>([]);
  const [aparelhos, setAparelhos] = useState<DeviceSummary[]>([]);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [capturando, setCapturando] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const [consentimento, setConsentimento] = useState(false);
  const [novaSenha, setNovaSenha] = useState("");

  const carregar = useCallback(async () => {
    setCarregando(true);
    try {
      const [ficha, lista, celulares] = await Promise.all([
        api.get<EmployeeDetail>(`/employees/${id}`),
        api.get<Paginated<FaceTemplate>>(`/employees/${id}/face-templates`),
        api.get<Paginated<DeviceSummary>>(`/employees/${id}/devices`),
      ]);
      setFuncionario(ficha);
      setTemplates(lista.items);
      setAparelhos(celulares.items);
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao carregar");
    } finally {
      setCarregando(false);
    }
  }, [id]);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  async function enviarFotos(fotos: Blob[]) {
    setEnviando(true);
    setErro(null);
    setAviso(null);

    const dados = new FormData();
    fotos.forEach((foto, indice) =>
      dados.append("images", foto, `foto-${indice + 1}.jpg`),
    );
    dados.append("consent_policy_version", VERSAO_DO_TERMO);
    dados.append("consent_granted", "true");

    try {
      const resultado = await api.upload<EnrollmentResult>(
        `/employees/${id}/face-templates`,
        dados,
      );

      if (resultado.rejected.length) {
        // Recusa parcial não é erro: o RH precisa saber quais fotos não
        // serviram e, principalmente, o que fazer para corrigir.
        setAviso(
          `${resultado.created.length} foto(s) aceita(s). Recusadas: ` +
            resultado.rejected
              .map((r) => `${r.filename}: ${explicarRecusa(r.reason, r.issues)}`)
              .join(" · "),
        );
      }

      setCapturando(false);
      setConsentimento(false);
      await carregar();
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha no cadastro biométrico");
    } finally {
      setEnviando(false);
    }
  }

  async function desativar() {
    try {
      setFuncionario(
        await api.post<EmployeeDetail>(`/employees/${id}/deactivate`),
      );
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao desativar");
    }
  }

  async function redefinirSenha() {
    try {
      await api.post(`/employees/${id}/password`, { new_password: novaSenha });
      setNovaSenha("");
      setAviso("Senha redefinida. O funcionário precisará trocá-la no primeiro acesso.");
      await carregar();
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao redefinir a senha");
    }
  }

  async function alternarAparelho(aparelho: DeviceSummary) {
    const acao = aparelho.revoked_at ? "authorize" : "revoke";
    try {
      await api.post(`/employees/${id}/devices/${aparelho.id}/${acao}`);
      setAviso(
        aparelho.revoked_at
          ? "Aparelho reautorizado. O funcionário precisa entrar de novo no app."
          : "Aparelho revogado. Ele não bate mais ponto e as sessões abertas caíram.",
      );
      await carregar();
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao alterar o aparelho");
    }
  }

  async function desativarTemplate(templateId: string) {
    try {
      await api.delete(`/employees/${id}/face-templates/${templateId}`);
      await carregar();
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao desativar o template");
    }
  }

  if (carregando) return <Carregando />;
  if (!funcionario) return <Alerta>{erro ?? "Funcionário não encontrado"}</Alerta>;

  return (
    <div className="space-y-6">
      <div>
        <Link
          href="/funcionarios"
          className="text-sm text-zinc-500 underline-offset-2 hover:underline"
        >
          ← Funcionários
        </Link>
        <h1 className="mt-1 text-xl font-semibold">{funcionario.name}</h1>
        <p className="text-sm text-zinc-500">
          Matrícula {funcionario.external_code}
          {funcionario.job_title && ` · ${funcionario.job_title}`}
        </p>
      </div>

      {erro && <Alerta>{erro}</Alerta>}
      {aviso && <Alerta tipo="aviso">{aviso}</Alerta>}

      <div className="grid gap-6 lg:grid-cols-3">
        <Card title="Cadastro">
          <dl className="space-y-2 text-sm">
            <Linha rotulo="CPF">{funcionario.cpf ?? "—"}</Linha>
            <Linha rotulo="E-mail">{funcionario.email ?? "—"}</Linha>
            <Linha rotulo="Admissão">{formatarData(funcionario.hired_at)}</Linha>
            <Linha rotulo="Situação">
              <Badge
                className={
                  funcionario.status === "active"
                    ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300"
                    : "bg-zinc-200 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300"
                }
              >
                {funcionario.status === "active" ? "Ativo" : "Inativo"}
              </Badge>
            </Linha>
            <Linha rotulo="Acesso ao app">
              {funcionario.has_app_credentials ? "Configurado" : "Sem senha"}
            </Linha>
            <Linha rotulo="Rosto cadastrado">
              {funcionario.active_face_templates > 0
                ? `${funcionario.active_face_templates} foto(s)`
                : "Não"}
            </Linha>
          </dl>

          {funcionario.status === "active" && (
            <div className="mt-4 border-t border-zinc-200 pt-4 dark:border-zinc-800">
              <Button variant="danger" onClick={desativar}>
                Desligar funcionário
              </Button>
              <p className="mt-2 text-xs text-zinc-500">
                O histórico de pontos é preservado.
              </p>
            </div>
          )}
        </Card>

        <Card title="Senha do aplicativo">
          <div className="space-y-3">
            <Field
              label="Nova senha"
              hint="Ao menos 12 caracteres. Provisória, o funcionário troca no primeiro acesso"
            >
              <Input
                type="text"
                value={novaSenha}
                minLength={12}
                onChange={(e) => setNovaSenha(e.target.value)}
              />
            </Field>
            <Button
              variant="secondary"
              onClick={redefinirSenha}
              disabled={novaSenha.length < 6}
            >
              Redefinir
            </Button>
          </div>
        </Card>

        <Card title="Cadastro biométrico">
          <p className="text-sm text-zinc-600 dark:text-zinc-400">
            {templates.length > 0
              ? `${templates.length} foto(s) de referência ativa(s).`
              : "Este funcionário ainda não tem rosto cadastrado e não conseguirá bater ponto."}
          </p>
          {!capturando && (
            <Button
              className="mt-4"
              onClick={() => setCapturando(true)}
              disabled={funcionario.status !== "active"}
            >
              {templates.length > 0 ? "Refazer cadastro" : "Cadastrar rosto"}
            </Button>
          )}
          {templates.length > 0 && (
            <p className="mt-2 text-xs text-zinc-500">
              Refazer substitui as fotos atuais. As anteriores são desativadas, não
              apagadas.
            </p>
          )}
        </Card>
      </div>

      {capturando && (
        <Card title="Capturar fotos de referência">
          <div className="space-y-4">
            <label className="flex items-start gap-3 rounded-md border border-amber-300 bg-amber-50 p-4 text-sm dark:border-amber-900 dark:bg-amber-950">
              <input
                type="checkbox"
                checked={consentimento}
                onChange={(e) => setConsentimento(e.target.checked)}
                className="mt-0.5"
              />
              <span className="text-amber-900 dark:text-amber-200">
                Confirmo que <strong>{funcionario.name}</strong> foi informado(a) sobre
                o uso da imagem facial para registro de ponto e deu consentimento
                expresso, conforme o termo versão {VERSAO_DO_TERMO}.
                <span className="mt-1 block text-xs">
                  Dado biométrico é dado pessoal sensível. Sem consentimento
                  registrado não há base legal para o tratamento, e o cadastro é
                  recusado.
                </span>
              </span>
            </label>

            {consentimento ? (
              <CapturaWebcam
                minimo={MIN_FOTOS}
                maximo={MAX_FOTOS}
                enviando={enviando}
                onConfirmar={enviarFotos}
                onCancelar={() => {
                  setCapturando(false);
                  setConsentimento(false);
                }}
              />
            ) : (
              <div className="flex justify-end">
                <Button variant="ghost" onClick={() => setCapturando(false)}>
                  Cancelar
                </Button>
              </div>
            )}
          </div>
        </Card>
      )}

      <Card title="Aparelhos pareados">
        <p className="text-sm text-zinc-600 dark:text-zinc-400">
          O ponto só é aceito do celular pareado. Revogue quando o aparelho for
          perdido, roubado ou devolvido; o funcionário continua entrando no app
          para ver o próprio histórico, mas para de bater ponto até o RH
          reautorizar.
        </p>

        {aparelhos.length === 0 ? (
          <div className="mt-4">
            <Vazio>Nenhum aparelho pareado. O pareamento acontece no primeiro login pelo app.</Vazio>
          </div>
        ) : (
          <div className="mt-4">
            <Tabela>
              <thead>
                <tr>
                  <Th>Aparelho</Th>
                  <Th>Último acesso</Th>
                  <Th>Situação</Th>
                  <Th>{""}</Th>
                </tr>
              </thead>
              <tbody>
                {aparelhos.map((aparelho) => (
                  <tr key={aparelho.id}>
                    <Td>
                      {aparelho.model ?? "Modelo não informado"}
                      <span className="block text-xs text-zinc-500">
                        {aparelho.platform === "ios" ? "iPhone" : "Android"}
                        {aparelho.os_version && ` ${aparelho.os_version}`}
                        {aparelho.app_version && ` · app ${aparelho.app_version}`}
                      </span>
                    </Td>
                    <Td>{formatarDataHora(aparelho.last_seen_at)}</Td>
                    <Td>
                      {aparelho.revoked_at ? (
                        <Badge className="bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300">
                          Revogado em {formatarData(aparelho.revoked_at)}
                        </Badge>
                      ) : (
                        <Badge className="bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300">
                          Ativo
                        </Badge>
                      )}
                    </Td>
                    <Td>
                      <Button
                        variant={aparelho.revoked_at ? "secondary" : "danger"}
                        onClick={() => alternarAparelho(aparelho)}
                      >
                        {aparelho.revoked_at ? "Reautorizar" : "Revogar"}
                      </Button>
                    </Td>
                  </tr>
                ))}
              </tbody>
            </Tabela>
          </div>
        )}
      </Card>

      <Card title="Fotos de referência">
        {templates.length === 0 ? (
          <Vazio>Nenhuma foto de referência ativa.</Vazio>
        ) : (
          <Tabela>
            <thead>
              <tr>
                <Th>Cadastrada em</Th>
                <Th>Qualidade</Th>
                <Th>Modelo</Th>
                <Th>{""}</Th>
              </tr>
            </thead>
            <tbody>
              {templates.map((template) => (
                <tr key={template.id}>
                  <Td>{formatarDataHora(template.created_at)}</Td>
                  <Td>{formatarPercentual(template.quality_score)}</Td>
                  <Td className="font-mono text-xs">
                    {template.model_name}/{template.model_version}
                  </Td>
                  <Td>
                    <Button
                      variant="ghost"
                      onClick={() => desativarTemplate(template.id)}
                    >
                      Desativar
                    </Button>
                  </Td>
                </tr>
              ))}
            </tbody>
          </Tabela>
        )}
      </Card>
    </div>
  );
}

function Linha({ rotulo, children }: { rotulo: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <dt className="text-zinc-500">{rotulo}</dt>
      <dd className="font-medium">{children}</dd>
    </div>
  );
}
