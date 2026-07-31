"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { NovoFuncionarioDialog } from "@/components/NovoFuncionarioDialog";
import {
  Alerta,
  Badge,
  Button,
  Card,
  Carregando,
  Select,
  Tabela,
  Td,
  Th,
  Vazio,
} from "@/components/ui";
import { api, paramsDe } from "@/lib/api";
import { formatarData, rotuloStatusFuncionario } from "@/lib/format";
import type { EmployeeSummary, Paginated } from "@/lib/types";

export default function FuncionariosPage() {
  const [status, setStatus] = useState("");
  const [dados, setDados] = useState<Paginated<EmployeeSummary> | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState<string | null>(null);
  const [criando, setCriando] = useState(false);

  const carregar = useCallback(async () => {
    setCarregando(true);
    setErro(null);
    try {
      setDados(
        await api.get<Paginated<EmployeeSummary>>(
          `/employees${paramsDe({ status, limit: "200" })}`,
        ),
      );
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao carregar");
    } finally {
      setCarregando(false);
    }
  }, [status]);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-semibold">Funcionários</h1>
        <div className="flex gap-2">
          <Select
            value={status}
            onChange={(e) => setStatus(e.target.value)}
            className="w-auto"
          >
            <option value="">Todos</option>
            <option value="active">Ativos</option>
            <option value="inactive">Inativos</option>
          </Select>
          <Button onClick={() => setCriando(true)}>Cadastrar</Button>
        </div>
      </div>

      {erro && <Alerta>{erro}</Alerta>}

      <Card title={dados ? `${dados.total} cadastrado(s)` : "Funcionários"}>
        {carregando ? (
          <Carregando />
        ) : !dados?.items.length ? (
          <Vazio>Nenhum funcionário cadastrado ainda.</Vazio>
        ) : (
          <Tabela>
            <thead>
              <tr>
                <Th>Matrícula</Th>
                <Th>Nome</Th>
                <Th>Cargo</Th>
                <Th>Admissão</Th>
                <Th>Situação</Th>
                <Th>{""}</Th>
              </tr>
            </thead>
            <tbody>
              {dados.items.map((funcionario) => (
                <tr key={funcionario.id}>
                  <Td className="font-mono text-xs">{funcionario.external_code}</Td>
                  <Td className="font-medium">{funcionario.name}</Td>
                  <Td>{funcionario.job_title ?? "—"}</Td>
                  <Td>{formatarData(funcionario.hired_at)}</Td>
                  <Td>
                    <Badge
                      className={
                        funcionario.status === "active"
                          ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300"
                          : "bg-zinc-200 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300"
                      }
                    >
                      {rotuloStatusFuncionario[funcionario.status]}
                    </Badge>
                  </Td>
                  <Td>
                    <Link
                      href={`/funcionarios/${funcionario.id}`}
                      className="text-sm text-zinc-600 underline-offset-2 hover:underline dark:text-zinc-300"
                    >
                      Abrir
                    </Link>
                  </Td>
                </tr>
              ))}
            </tbody>
          </Tabela>
        )}
      </Card>

      {criando && (
        <NovoFuncionarioDialog
          onFechar={() => setCriando(false)}
          onCriado={() => {
            setCriando(false);
            void carregar();
          }}
        />
      )}
    </div>
  );
}
