"use client";

import { useCallback, useEffect, useState } from "react";

import { RevisaoDialog } from "@/components/RevisaoDialog";
import {
  Alerta,
  Badge,
  Button,
  Card,
  Carregando,
  Field,
  Select,
  Input,
  Tabela,
  Td,
  Th,
  Vazio,
} from "@/components/ui";
import { api, paramsDe } from "@/lib/api";
import {
  corMetodo,
  corStatus,
  formatarDataHora,
  formatarMetros,
  formatarPercentual,
  rotuloMetodo,
  rotuloStatus,
  rotuloTipo,
} from "@/lib/format";
import type {
  EmployeeSummary,
  Paginated,
  Site,
  TimeEntryWithEmployee,
} from "@/lib/types";

type Filtros = {
  employee_id: string;
  site_id: string;
  status: string;
  location_method: string;
  start: string;
  end: string;
};

const filtrosVazios: Filtros = {
  employee_id: "",
  site_id: "",
  status: "",
  location_method: "",
  start: "",
  end: "",
};

/** Converte `datetime-local` para ISO com fuso, que é o que a API espera. */
function paraIso(valor: string) {
  return valor ? new Date(valor).toISOString() : "";
}

export default function PontosPage() {
  const [filtros, setFiltros] = useState<Filtros>(filtrosVazios);
  const [dados, setDados] = useState<Paginated<TimeEntryWithEmployee> | null>(null);
  const [funcionarios, setFuncionarios] = useState<EmployeeSummary[]>([]);
  const [locais, setLocais] = useState<Site[]>([]);
  const [erro, setErro] = useState<string | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [emRevisao, setEmRevisao] = useState<TimeEntryWithEmployee | null>(null);

  const consulta = useCallback(
    () =>
      paramsDe({
        ...filtros,
        start: paraIso(filtros.start),
        end: paraIso(filtros.end),
        limit: "100",
      }),
    [filtros],
  );

  const carregar = useCallback(async () => {
    setCarregando(true);
    setErro(null);
    try {
      setDados(
        await api.get<Paginated<TimeEntryWithEmployee>>(`/time-entries${consulta()}`),
      );
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao carregar");
    } finally {
      setCarregando(false);
    }
  }, [consulta]);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  useEffect(() => {
    api
      .get<Paginated<EmployeeSummary>>("/employees?limit=200")
      .then((r) => setFuncionarios(r.items))
      .catch(() => setFuncionarios([]));
    api
      .get<Paginated<Site>>("/sites")
      .then((r) => setLocais(r.items))
      .catch(() => setLocais([]));
  }, []);

  async function exportar() {
    try {
      await api.download(`/time-entries/export/csv${consulta()}`, "pontos.csv");
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao exportar");
    }
  }

  function alterar(campo: keyof Filtros, valor: string) {
    setFiltros((atual) => ({ ...atual, [campo]: valor }));
  }

  const pendentes = dados?.items.filter((e) => e.status === "pending_review").length ?? 0;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Registros de ponto</h1>
          {pendentes > 0 && (
            <p className="mt-1 text-sm text-amber-700 dark:text-amber-400">
              {pendentes} {pendentes === 1 ? "registro aguarda" : "registros aguardam"}{" "}
              conferência
            </p>
          )}
        </div>
        <Button variant="secondary" onClick={exportar}>
          Exportar CSV
        </Button>
      </div>

      <Card
        title="Filtros"
        actions={
          <Button variant="ghost" onClick={() => setFiltros(filtrosVazios)}>
            Limpar
          </Button>
        }
      >
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <Field label="Funcionário">
            <Select
              value={filtros.employee_id}
              onChange={(e) => alterar("employee_id", e.target.value)}
            >
              <option value="">Todos</option>
              {funcionarios.map((f) => (
                <option key={f.id} value={f.id}>
                  {f.external_code}: {f.name}
                </option>
              ))}
            </Select>
          </Field>

          <Field label="Local">
            <Select
              value={filtros.site_id}
              onChange={(e) => alterar("site_id", e.target.value)}
            >
              <option value="">Todos</option>
              {locais.map((l) => (
                <option key={l.id} value={l.id}>
                  {l.name}
                </option>
              ))}
            </Select>
          </Field>

          <Field label="Situação">
            <Select
              value={filtros.status}
              onChange={(e) => alterar("status", e.target.value)}
            >
              <option value="">Todas</option>
              <option value="pending_review">Em revisão</option>
              <option value="approved">Aprovado</option>
              <option value="rejected">Rejeitado</option>
            </Select>
          </Field>

          <Field label="Método de localização">
            <Select
              value={filtros.location_method}
              onChange={(e) => alterar("location_method", e.target.value)}
            >
              <option value="">Todos</option>
              <option value="beacon">Beacon</option>
              <option value="wifi">Wi-Fi</option>
              <option value="gps">GPS</option>
              <option value="none">Nenhum</option>
            </Select>
          </Field>

          <Field label="De">
            <Input
              type="datetime-local"
              value={filtros.start}
              onChange={(e) => alterar("start", e.target.value)}
            />
          </Field>

          <Field label="Até">
            <Input
              type="datetime-local"
              value={filtros.end}
              onChange={(e) => alterar("end", e.target.value)}
            />
          </Field>
        </div>
      </Card>

      {erro && <Alerta>{erro}</Alerta>}

      <Card title={dados ? `${dados.total} registro(s)` : "Registros"}>
        {carregando ? (
          <Carregando />
        ) : !dados?.items.length ? (
          <Vazio>Nenhum registro no período.</Vazio>
        ) : (
          <Tabela>
            <thead>
              <tr>
                <Th>Data/hora</Th>
                <Th>Funcionário</Th>
                <Th>Tipo</Th>
                <Th>Localização</Th>
                <Th>Rosto</Th>
                <Th>Situação</Th>
                <Th>{""}</Th>
              </tr>
            </thead>
            <tbody>
              {dados.items.map((entrada) => (
                <tr key={entrada.id}>
                  <Td className="whitespace-nowrap">
                    {formatarDataHora(entrada.recorded_at)}
                  </Td>
                  <Td>
                    <div className="font-medium">{entrada.employee_name}</div>
                    <div className="text-xs text-zinc-500">{entrada.employee_code}</div>
                  </Td>
                  {/* O que o funcionário escolheu vem primeiro, porque é o que
                      ele viu na tela; o tipo apurado fica abaixo, porque é o
                      que entra na conta de horas. Quando não há rótulo, só o
                      tipo — sem linha vazia ocupando espaço. */}
                  <Td className="whitespace-nowrap">
                    {entrada.label ? (
                      <div>
                        <div>{entrada.label}</div>
                        <div className="text-xs text-zinc-500">
                          {rotuloTipo[entrada.entry_type]}
                        </div>
                      </div>
                    ) : (
                      rotuloTipo[entrada.entry_type]
                    )}
                  </Td>
                  <Td>
                    <div className="flex flex-col gap-1">
                      <Badge className={corMetodo[entrada.location_method]}>
                        {rotuloMetodo[entrada.location_method]}
                      </Badge>
                      <span className="text-xs text-zinc-500">
                        {entrada.site_name ?? "—"}
                        {entrada.location_confidence !== null &&
                          ` · ${formatarPercentual(entrada.location_confidence)}`}
                        {entrada.beacon_rssi !== null && ` · ${entrada.beacon_rssi} dBm`}
                        {entrada.distance_to_site_m !== null &&
                          ` · ${formatarMetros(entrada.distance_to_site_m)}`}
                      </span>
                    </div>
                  </Td>
                  <Td>{formatarPercentual(entrada.face_match_score)}</Td>
                  <Td>
                    <Badge className={corStatus[entrada.status]}>
                      {rotuloStatus[entrada.status]}
                    </Badge>
                  </Td>
                  <Td>
                    <Button variant="ghost" onClick={() => setEmRevisao(entrada)}>
                      Detalhes
                    </Button>
                  </Td>
                </tr>
              ))}
            </tbody>
          </Tabela>
        )}
      </Card>

      {emRevisao && (
        <RevisaoDialog
          entrada={emRevisao}
          onFechar={() => setEmRevisao(null)}
          onDecidido={() => {
            setEmRevisao(null);
            void carregar();
          }}
        />
      )}
    </div>
  );
}
