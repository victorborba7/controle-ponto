"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { Alerta, Button } from "@/components/ui";

/**
 * Captura das fotos de referência pela webcam.
 *
 * Cuidados que a tela precisa ter, e o porquê de cada um:
 *
 * - **A câmera é desligada ao sair.** Um `MediaStream` esquecido deixa a luz do
 *   equipamento acesa e o microfone/câmera ativos depois que o RH mudou de tela.
 * - **Espelhada na exibição, normal no arquivo.** Sem o espelho, enquadrar-se é
 *   confuso; com o espelho no arquivo, o modelo receberia uma imagem invertida.
 * - **Fotos variadas, não repetidas.** Templates de fotos idênticas não trazem
 *   robustez nenhuma — o texto orienta a variar ângulo e expressão, que é o
 *   ponto de exigir várias.
 */
export function CapturaWebcam({
  minimo,
  maximo,
  onConfirmar,
  onCancelar,
  enviando,
}: {
  minimo: number;
  maximo: number;
  onConfirmar: (fotos: Blob[]) => void;
  onCancelar: () => void;
  enviando: boolean;
}) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const [pronto, setPronto] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [fotos, setFotos] = useState<{ blob: Blob; url: string }[]>([]);

  useEffect(() => {
    let cancelado = false;

    navigator.mediaDevices
      .getUserMedia({ video: { facingMode: "user", width: 1280, height: 720 } })
      .then((stream) => {
        if (cancelado) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }
        streamRef.current = stream;
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          setPronto(true);
        }
      })
      .catch(() =>
        setErro(
          "Não foi possível acessar a câmera. Verifique a permissão no navegador.",
        ),
      );

    return () => {
      cancelado = true;
      streamRef.current?.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    };
  }, []);

  // Libera as pré-visualizações ao desmontar: são imagens de rosto e não devem
  // ficar retidas na memória depois que a tela fecha.
  useEffect(() => {
    return () => {
      fotos.forEach((f) => URL.revokeObjectURL(f.url));
    };
    // Intencionalmente sem dependências: roda uma vez, no desmonte.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const capturar = useCallback(() => {
    const video = videoRef.current;
    if (!video || fotos.length >= maximo) return;

    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;

    const contexto = canvas.getContext("2d");
    if (!contexto) return;

    // Sem espelhar aqui: o espelho é só da exibição, para o RH se enquadrar.
    contexto.drawImage(video, 0, 0);

    canvas.toBlob(
      (blob) => {
        if (!blob) return;
        setFotos((atual) => [...atual, { blob, url: URL.createObjectURL(blob) }]);
      },
      "image/jpeg",
      0.92,
    );
  }, [fotos.length, maximo]);

  function remover(indice: number) {
    setFotos((atual) => {
      URL.revokeObjectURL(atual[indice].url);
      return atual.filter((_, i) => i !== indice);
    });
  }

  const suficiente = fotos.length >= minimo;

  return (
    <div className="space-y-4">
      {erro && <Alerta>{erro}</Alerta>}

      <div className="overflow-hidden rounded-lg border border-zinc-200 bg-black dark:border-zinc-800">
        <video
          ref={videoRef}
          autoPlay
          playsInline
          muted
          className="aspect-video w-full -scale-x-100 object-cover"
        />
      </div>

      <p className="text-sm text-zinc-600 dark:text-zinc-400">
        Tire de {minimo} a {maximo} fotos, <strong>variando levemente o ângulo e a
        expressão</strong>. Fotos idênticas não tornam o reconhecimento mais
        robusto — a variação é justamente o que absorve mudança de luz, óculos e
        barba depois.
      </p>

      {fotos.length > 0 && (
        <div className="grid grid-cols-3 gap-3 sm:grid-cols-5">
          {fotos.map((foto, indice) => (
            <div key={foto.url} className="relative">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={foto.url}
                alt={`Foto ${indice + 1}`}
                className="aspect-square w-full rounded-md object-cover"
              />
              <button
                type="button"
                onClick={() => remover(indice)}
                disabled={enviando}
                className="absolute -right-1.5 -top-1.5 flex h-6 w-6 items-center justify-center rounded-full bg-zinc-900 text-xs text-white shadow disabled:opacity-50"
                aria-label={`Remover foto ${indice + 1}`}
              >
                ×
              </button>
            </div>
          ))}
        </div>
      )}

      <div className="flex flex-wrap items-center justify-between gap-3">
        <span className="text-sm text-zinc-500">
          {fotos.length} de {maximo} · mínimo {minimo}
        </span>
        <div className="flex gap-2">
          <Button variant="ghost" onClick={onCancelar} disabled={enviando}>
            Cancelar
          </Button>
          <Button
            variant="secondary"
            onClick={capturar}
            disabled={!pronto || fotos.length >= maximo || enviando}
          >
            Tirar foto
          </Button>
          <Button
            onClick={() => onConfirmar(fotos.map((f) => f.blob))}
            disabled={!suficiente || enviando}
          >
            {enviando ? "Enviando…" : "Cadastrar rosto"}
          </Button>
        </div>
      </div>
    </div>
  );
}
