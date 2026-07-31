"use client";

import { useEffect, useState } from "react";

import { Alerta, Badge, Button, Field, Input, Textarea } from "@/components/ui";
import { api } from "@/lib/api";
import {
  corMetodo,
  corStatus,
  formatarDataHora,
  formatarMetros,
  formatarPercentual,
  paraInputDataHora,
  rotuloMetodo,
  rotuloStatus,
  rotuloTipo,
} from "@/lib/format";
import type { TimeEntryWithEmployee } from "@/lib/types";

/**
 * Detalhe de um registro e, quando pendente, a decisão do RH.
 *
 * Mostra a evidência inteira — foto, score do rosto, método de localização e o
 * motivo da pendência — porque aprovar sem ver o que sustentou o registro
 * transformaria a revisão em carimbo.
 */
export function RevisaoDialog({
  entrada,
  onFechar,
  onDecidido,
}: {
  entrada: TimeEntryWithEmployee;
  onFechar: () => void;
  onDecidido: () => void;
}) {
  const [foto, setFoto] = useState<string | null>(null);
  const [fotoIndisponivel, setFotoIndisponivel] = useState(false);
  const [nota, setNota] = useState("");
  const [horario, setHorario] = useState(paraInputDataHora(entrada.recorded_at));
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  const pendente = entrada.status === "pending_review";
  const horarioAlterado =
    horario !== paraInputDataHora(entrada.recorded_at) && horario !== "";

  useEffect(() => {
    let url: string | null = null;

    fetch(`/api/backend/time-entries/${entrada.id}/selfie`, { cache: "no-store" })
      .then((r) => (r.ok ? r.blob() : Promise.reject(new Error("indisponível"))))
      .then((blob) => {
        url = URL.createObjectURL(blob);
        setFoto(url);
      })
      .catch(() => setFotoIndisponivel(true));

    // Libera a imagem da memória ao fechar: são dados biométricos, não devem
    // ficar pendurados no objeto URL depois que a tela sai.
    return () => {
      if (url) URL.revokeObjectURL(url);
    };
  }, [entrada.id]);

  async function decidir(aprovado: boolean) {
    setEnviando(true);
    setErro(null);
    try {
      await api.patch(`/time-entries/${entrada.id}/review`, {
        approved: aprovado,
        note: nota.trim() || null,
        corrected_recorded_at: horarioAlterado
          ? new Date(horario).toISOString()
          : null,
      });
      onDecidido();
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao registrar a decisão");
    } finally {
      setEnviando(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/50 p-4 sm:items-center"
      onClick={onFechar}
      role="presentation"
    >
      <div
        className="w-full max-w-3xl rounded-lg bg-white shadow-xl dark:bg-zinc-900"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
      >
        <header className="flex items-center justify-between border-b border-zinc-200 px-6 py-4 dark:border-zinc-800">
          <div>
            <h2 className="font-semibold">{entrada.employee_name}</h2>
            <p className="text-sm text-zinc-500">
              {rotuloTipo[entrada.entry_type]} · {formatarDataHora(entrada.recorded_at)}
            </p>
          </div>
          <Badge className={corStatus[entrada.status]}>
            {rotuloStatus[entrada.status]}
          </Badge>
        </header>

        <div className="grid gap-6 p-6 sm:grid-cols-2">
          <div>
            <h3 className="mb-2 text-sm font-medium text-zinc-600 dark:text-zinc-400">
              Foto do registro
            </h3>
            {foto ? (
              // Imagem vinda de um blob temporário: `next/image` exigiria
              // domínio configurado e não traria ganho aqui.
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={foto}
                alt="Foto capturada no momento da batida"
                className="w-full rounded-md border border-zinc-200 dark:border-zinc-800"
              />
            ) : fotoIndisponivel ? (
              <p className="rounded-md border border-dashed border-zinc-300 p-8 text-center text-sm text-zinc-500 dark:border-zinc-700">
                Foto indisponível — pode ter expirado pela política de retenção.
              </p>
            ) : (
              <p className="text-sm text-zinc-500">Carregando…</p>
            )}
          </div>

          <div className="space-y-4">
            <div>
              <h3 className="mb-2 text-sm font-medium text-zinc-600 dark:text-zinc-400">
                Evidência
              </h3>
              <dl className="space-y-1.5 text-sm">
                <Linha rotulo="Reconhecimento facial">
                  {formatarPercentual(entrada.face_match_score)}
                </Linha>
                <Linha rotulo="Localização">
                  <Badge className={corMetodo[entrada.location_method]}>
                    {rotuloMetodo[entrada.location_method]}
                  </Badge>
                </Linha>
                <Linha rotulo="Confiança">
                  {formatarPercentual(entrada.location_confidence)}
                </Linha>
                {entrada.site_name && (
                  <Linha rotulo="Local">{entrada.site_name}</Linha>
                )}
                {entrada.beacon_rssi !== null && (
                  <Linha rotulo="Sinal do beacon">{entrada.beacon_rssi} dBm</Linha>
                )}
                {entrada.distance_to_site_m !== null && (
                  <Linha rotulo="Distância">
                    {formatarMetros(entrada.distance_to_site_m)}
                  </Linha>
                )}
                {entrada.client_recorded_at && (
                  <Linha rotulo="Horário do aparelho">
                    {formatarDataHora(entrada.client_recorded_at)}
                  </Linha>
                )}
              </dl>
            </div>

            {entrada.decision_reason && (
              <Alerta tipo={pendente ? "aviso" : "sucesso"}>
                {entrada.decision_reason}
              </Alerta>
            )}

            {entrada.review_note && (
              <div className="text-sm">
                <span className="text-zinc-500">Observação da revisão: </span>
                {entrada.review_note}
              </div>
            )}
          </div>
        </div>

        {pendente && (
          <div className="space-y-4 border-t border-zinc-200 p-6 dark:border-zinc-800">
            {erro && <Alerta>{erro}</Alerta>}

            <Field
              label="Horário da batida"
              hint="Ajuste quando o registro tiver sido enviado com atraso — o horário gravado é o do envio, e a correção fica registrada na auditoria."
            >
              <Input
                type="datetime-local"
                value={horario}
                onChange={(e) => setHorario(e.target.value)}
              />
            </Field>

            <Field label="Observação">
              <Textarea
                rows={2}
                value={nota}
                onChange={(e) => setNota(e.target.value)}
                placeholder="Ex.: confirmado com o supervisor do turno"
              />
            </Field>

            <div className="flex flex-wrap justify-end gap-2">
              <Button variant="ghost" onClick={onFechar} disabled={enviando}>
                Cancelar
              </Button>
              <Button
                variant="danger"
                onClick={() => decidir(false)}
                disabled={enviando}
              >
                Rejeitar
              </Button>
              <Button onClick={() => decidir(true)} disabled={enviando}>
                {enviando ? "Salvando…" : "Aprovar"}
              </Button>
            </div>
          </div>
        )}

        {!pendente && (
          <div className="flex justify-end border-t border-zinc-200 p-4 dark:border-zinc-800">
            <Button variant="secondary" onClick={onFechar}>
              Fechar
            </Button>
          </div>
        )}
      </div>
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
