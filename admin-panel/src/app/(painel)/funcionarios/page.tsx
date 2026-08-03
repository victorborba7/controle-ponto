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
import { useIdioma } from "@/i18n/contexto";
import { api, paramsDe } from "@/lib/api";
import type { EmployeeSummary, Paginated } from "@/lib/types";
import { funcionario as rotaFuncionario } from "@/rotas";

export default function FuncionariosPage() {
  const { t, fmt } = useIdioma();
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
      setErro(e instanceof Error ? e.message : t("func.falhaAoCarregar"));
    } finally {
      setCarregando(false);
    }
  }, [status, t]);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-semibold">{t("func.titulo")}</h1>
        <div className="flex gap-2">
          <Select
            value={status}
            onChange={(e) => setStatus(e.target.value)}
            className="w-auto"
          >
            <option value="">{t("geral.todos")}</option>
            <option value="active">{t("func.ativos")}</option>
            <option value="inactive">{t("func.inativos")}</option>
          </Select>
          <Button onClick={() => setCriando(true)}>{t("func.cadastrar")}</Button>
        </div>
      </div>

      {erro && <Alerta>{erro}</Alerta>}

      <Card title={dados ? t("func.total", { n: dados.total }) : t("func.titulo")}>
        {carregando ? (
          <Carregando />
        ) : !dados?.items.length ? (
          <Vazio>{t("func.vazio")}</Vazio>
        ) : (
          <Tabela>
            <thead>
              <tr>
                <Th>{t("func.matricula")}</Th>
                <Th>{t("func.nome")}</Th>
                <Th>{t("func.cargo")}</Th>
                <Th>{t("func.admissao")}</Th>
                <Th>{t("func.situacao")}</Th>
                <Th>{""}</Th>
              </tr>
            </thead>
            <tbody>
              {dados.items.map((funcionario) => (
                <tr key={funcionario.id}>
                  <Td className="font-mono text-xs">{funcionario.external_code}</Td>
                  <Td className="font-medium">{funcionario.name}</Td>
                  <Td>{funcionario.job_title ?? "—"}</Td>
                  <Td>{fmt.data(funcionario.hired_at)}</Td>
                  <Td>
                    <Badge
                      className={
                        funcionario.status === "active"
                          ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300"
                          : "bg-zinc-200 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300"
                      }
                    >
                      {fmt.situacao(funcionario.status)}
                    </Badge>
                  </Td>
                  <Td>
                    <Link
                      href={rotaFuncionario(funcionario.id)}
                      className="text-sm text-zinc-600 underline-offset-2 hover:underline dark:text-zinc-300"
                    >
                      {t("func.abrir")}
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
