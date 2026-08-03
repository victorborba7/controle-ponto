"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import {
  Alerta,
  Button,
  Card,
  Carregando,
  Field,
  Input,
  Select,
} from "@/components/ui";
import { api } from "@/lib/api";
import { rotuloTipo } from "@/lib/format";
import type {
  EntryType,
  LabelMode,
  NoteMode,
  PunchConfig,
  PunchLabelInput,
  PunchConfigUpdate,
} from "@/lib/types";

const MAX_ROTULOS = 20;

/**
 * Sequência sugerida ao ligar o modo de lista.
 *
 * Partir de uma lista pronta e não de uma tela vazia: a jornada com intervalo
 * é o caso da maioria, e quem tem outro basta editar. Uma tela em branco faz o
 * RH ter de adivinhar o que o campo espera.
 */
const SUGESTAO: PunchLabelInput[] = [
  { name: "Entrada", entry_type: "in", is_active: true },
  { name: "Início do almoço", entry_type: "break_start", is_active: true },
  { name: "Volta do almoço", entry_type: "break_end", is_active: true },
  { name: "Saída", entry_type: "out", is_active: true },
];

export default function ConfiguracoesPage() {
  const [carregando, setCarregando] = useState(true);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [salvo, setSalvo] = useState(false);

  const [noteMode, setNoteMode] = useState<NoteMode>("hidden");
  const [notePrompt, setNotePrompt] = useState("");
  const [labelMode, setLabelMode] = useState<LabelMode>("hidden");
  const [labelRequired, setLabelRequired] = useState(false);
  const [rotulos, setRotulos] = useState<PunchLabelInput[]>([]);

  const carregar = useCallback(async () => {
    setCarregando(true);
    try {
      const config = await api.get<PunchConfig>("/punch-config");
      setNoteMode(config.note_mode);
      setNotePrompt(config.note_prompt ?? "");
      setLabelMode(config.label_mode);
      setLabelRequired(config.label_required);
      setRotulos(
        config.labels.map((r) => ({
          name: r.name,
          entry_type: r.entry_type,
          is_active: r.is_active,
        })),
      );
      setErro(null);
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao carregar");
    } finally {
      setCarregando(false);
    }
  }, []);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  /**
   * O que impede de salvar, dito antes de tentar.
   *
   * O backend recusa as mesmas combinações, mas descobrir isso só depois de
   * clicar em Salvar faz o RH tentar às cegas. Aqui a mensagem aparece junto
   * do campo que a causou.
   */
  const impedimento = useMemo(() => {
    const ativos = rotulos.filter((r) => r.is_active);
    const nomes = rotulos.map((r) => r.name.trim().toLowerCase());

    if (rotulos.some((r) => !r.name.trim())) return "Há opção sem nome.";
    if (new Set(nomes).size !== nomes.length) return "Há duas opções com o mesmo nome.";
    if (labelMode === "list" && ativos.length === 0) {
      return "O modo de lista precisa de ao menos uma opção ativa — senão o funcionário vê uma tela de escolha sem nada para escolher.";
    }
    if (labelRequired && labelMode === "hidden") {
      return "Não dá para exigir o tipo da batida sem exibi-lo.";
    }
    return null;
  }, [rotulos, labelMode, labelRequired]);

  async function salvar() {
    if (impedimento) return;
    setSalvando(true);
    setErro(null);
    setSalvo(false);

    const corpo: PunchConfigUpdate = {
      note_mode: noteMode,
      note_prompt: notePrompt.trim() || null,
      label_mode: labelMode,
      label_required: labelRequired,
      // O modo oculto não leva opções: guardá-las faria o RH pensar que estão
      // valendo. Reativar o modo repropõe a sugestão.
      labels: labelMode === "hidden" ? [] : rotulos.map((r) => ({ ...r, name: r.name.trim() })),
    };

    try {
      await api.put("/punch-config", corpo);
      setSalvo(true);
      await carregar();
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao salvar");
    } finally {
      setSalvando(false);
    }
  }

  function trocarModoRotulo(modo: LabelMode) {
    setLabelMode(modo);
    // Entrar no modo de lista sem nenhuma opção deixaria uma tela vazia sem
    // pista do que preencher.
    if (modo === "list" && rotulos.length === 0) setRotulos(SUGESTAO);
    if (modo === "hidden") setLabelRequired(false);
  }

  function editar(indice: number, mudanca: Partial<PunchLabelInput>) {
    setRotulos((atual) =>
      atual.map((r, i) => (i === indice ? { ...r, ...mudanca } : r)),
    );
  }

  function mover(indice: number, direcao: -1 | 1) {
    const destino = indice + direcao;
    if (destino < 0 || destino >= rotulos.length) return;
    setRotulos((atual) => {
      const copia = [...atual];
      [copia[indice], copia[destino]] = [copia[destino], copia[indice]];
      return copia;
    });
  }

  if (carregando) return <Carregando />;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold">Configurações de batida</h1>
        <p className="mt-1 text-sm text-zinc-500">
          Define o que o funcionário preenche ao bater o ponto. Vale para a
          empresa inteira e passa a valer na próxima batida — registros
          anteriores não mudam.
        </p>
      </div>

      {erro && <Alerta tipo="erro">{erro}</Alerta>}
      {salvo && !erro && <Alerta tipo="sucesso">Configuração salva.</Alerta>}

      {/* ---------------- Observação ---------------- */}
      <Card title="Observação">
        <div className="space-y-4">
          <p className="text-sm text-zinc-500">
            Um campo de texto livre na tela de batida. Serve para justificar
            atraso, informar ordem de serviço, o que a empresa precisar.
          </p>

          <Field label="Quando pedir">
            <Select
              value={noteMode}
              onChange={(e) => setNoteMode(e.target.value as NoteMode)}
            >
              <option value="hidden">Não pedir</option>
              <option value="optional">Opcional — pode deixar em branco</option>
              <option value="required">Obrigatória — barra a batida se vazia</option>
            </Select>
          </Field>

          {noteMode !== "hidden" && (
            <Field
              label="Instrução para o funcionário"
              hint="Aparece acima do campo, e é a mensagem mostrada quando ele tenta bater sem preencher."
            >
              <Input
                value={notePrompt}
                onChange={(e) => setNotePrompt(e.target.value)}
                maxLength={120}
                placeholder="Ex.: Justifique o atraso"
              />
            </Field>
          )}

          {noteMode === "required" && (
            <Alerta tipo="aviso">
              Obrigatória significa que ninguém bate o ponto sem escrever algo.
              Se o campo não se aplicar a toda batida do dia, prefira opcional.
            </Alerta>
          )}
        </div>
      </Card>

      {/* ---------------- Tipo da batida ---------------- */}
      <Card title="Tipo da batida">
        <div className="space-y-4">
          <p className="text-sm text-zinc-500">
            Sem configuração, o sistema alterna entrada e saída sozinho a partir
            da última batida — o funcionário não escolhe, e não erra.
          </p>

          <Field label="Como o funcionário nomeia a batida">
            <Select
              value={labelMode}
              onChange={(e) => trocarModoRotulo(e.target.value as LabelMode)}
            >
              <option value="hidden">Não perguntar — entrada e saída automáticas</option>
              <option value="free">Texto livre — ele escreve o que quiser</option>
              <option value="list">Lista — ele escolhe entre as opções abaixo</option>
            </Select>
          </Field>

          {labelMode === "free" && (
            <Alerta tipo="aviso">
              O texto digitado é apenas descritivo: fica registrado ao lado do
              ponto, mas <strong>não</strong> altera a apuração de horas. Quem
              escrever &ldquo;saída para almoço&rdquo; numa batida que o sistema
              apurou como entrada continuará com uma entrada.
            </Alerta>
          )}

          {labelMode !== "hidden" && (
            <label className="flex items-start gap-2 text-sm">
              <input
                type="checkbox"
                className="mt-0.5"
                checked={labelRequired}
                onChange={(e) => setLabelRequired(e.target.checked)}
              />
              <span>
                Exigir o preenchimento
                <span className="block text-xs text-zinc-500">
                  Sem isso, quem não escolher cai na alternância automática.
                </span>
              </span>
            </label>
          )}

          {labelMode === "list" && (
            <EditorDeRotulos
              rotulos={rotulos}
              onEditar={editar}
              onMover={mover}
              onRemover={(i) => setRotulos((a) => a.filter((_, j) => j !== i))}
              onAdicionar={() =>
                setRotulos((a) => [
                  ...a,
                  { name: "", entry_type: "in", is_active: true },
                ])
              }
            />
          )}
        </div>
      </Card>

      {impedimento && <Alerta tipo="erro">{impedimento}</Alerta>}

      <div className="flex items-center gap-3">
        <Button onClick={salvar} disabled={salvando || impedimento !== null}>
          {salvando ? "Salvando…" : "Salvar"}
        </Button>
        <Button variant="secondary" onClick={carregar} disabled={salvando}>
          Descartar alterações
        </Button>
      </div>
    </div>
  );
}

function EditorDeRotulos({
  rotulos,
  onEditar,
  onMover,
  onRemover,
  onAdicionar,
}: {
  rotulos: PunchLabelInput[];
  onEditar: (indice: number, mudanca: Partial<PunchLabelInput>) => void;
  onMover: (indice: number, direcao: -1 | 1) => void;
  onRemover: (indice: number) => void;
  onAdicionar: () => void;
}) {
  return (
    <div className="space-y-3">
      <div className="text-sm">
        <p className="font-medium">Opções</p>
        <p className="text-xs text-zinc-500">
          Cada opção diz ao sistema o que ela significa na jornada. O
          funcionário escolhe pelo nome; a tradução é esta coluna, e é o que
          torna a apuração de horas somável.
        </p>
      </div>

      <div className="space-y-2">
        {rotulos.map((rotulo, indice) => (
          <div
            key={indice}
            className="flex flex-wrap items-center gap-2 rounded-md border border-zinc-200 p-2 dark:border-zinc-800"
          >
            <div className="flex flex-col">
              <button
                type="button"
                onClick={() => onMover(indice, -1)}
                disabled={indice === 0}
                aria-label="Mover para cima"
                className="px-1 text-xs text-zinc-500 disabled:opacity-30"
              >
                ▲
              </button>
              <button
                type="button"
                onClick={() => onMover(indice, 1)}
                disabled={indice === rotulos.length - 1}
                aria-label="Mover para baixo"
                className="px-1 text-xs text-zinc-500 disabled:opacity-30"
              >
                ▼
              </button>
            </div>

            <Input
              value={rotulo.name}
              onChange={(e) => onEditar(indice, { name: e.target.value })}
              maxLength={60}
              placeholder="Nome que o funcionário vê"
              className="min-w-40 flex-1"
            />

            <Select
              value={rotulo.entry_type}
              onChange={(e) =>
                onEditar(indice, { entry_type: e.target.value as EntryType })
              }
              className="w-48"
            >
              {(Object.keys(rotuloTipo) as EntryType[]).map((tipo) => (
                <option key={tipo} value={tipo}>
                  {rotuloTipo[tipo]}
                </option>
              ))}
            </Select>

            <label className="flex items-center gap-1 text-xs text-zinc-500">
              <input
                type="checkbox"
                checked={rotulo.is_active}
                onChange={(e) => onEditar(indice, { is_active: e.target.checked })}
              />
              Ativa
            </label>

            <button
              type="button"
              onClick={() => onRemover(indice)}
              className="px-2 text-xs text-red-600 hover:underline"
            >
              Remover
            </button>
          </div>
        ))}
      </div>

      <Button
        variant="secondary"
        onClick={onAdicionar}
        disabled={rotulos.length >= MAX_ROTULOS}
      >
        Adicionar opção
      </Button>

      <Alerta tipo="info">
        Para tirar uma opção de circulação, <strong>desmarque &ldquo;Ativa&rdquo;
        </strong> em vez de remover. Ela some da tela do funcionário e continua
        legível nos pontos antigos — remover não apaga o histórico, mas
        desativar deixa claro que a opção existiu.
      </Alerta>
    </div>
  );
}
