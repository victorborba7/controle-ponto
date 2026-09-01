"use client";

import { useEffect, useState } from "react";

import { Alerta, Button, Field, Input, Select } from "@/components/ui";
import { api } from "@/lib/api";
import type { EmployeeDetail, Paginated, Site } from "@/lib/types";

export function NovoFuncionarioDialog({
  onFechar,
  onCriado,
}: {
  onFechar: () => void;
  onCriado: (funcionario: EmployeeDetail) => void;
}) {
  const [locais, setLocais] = useState<Site[]>([]);
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    api
      .get<Paginated<Site>>("/sites?only_active=true")
      .then((r) => setLocais(r.items))
      .catch(() => setLocais([]));
  }, []);

  async function salvar(evento: React.FormEvent<HTMLFormElement>) {
    evento.preventDefault();
    setEnviando(true);
    setErro(null);

    const form = new FormData(evento.currentTarget);
    const texto = (campo: string) => {
      const valor = String(form.get(campo) ?? "").trim();
      return valor === "" ? null : valor;
    };

    try {
      const criado = await api.post<EmployeeDetail>("/employees", {
        external_code: texto("external_code"),
        name: texto("name"),
        cpf: texto("cpf"),
        email: texto("email"),
        job_title: texto("job_title"),
        hired_at: texto("hired_at"),
        default_site_id: texto("default_site_id"),
        initial_password: texto("initial_password"),
      });
      onCriado(criado);
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao cadastrar");
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
      <form
        onSubmit={salvar}
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-lg space-y-4 rounded-lg bg-white p-6 shadow-xl dark:bg-zinc-900"
      >
        <h2 className="text-lg font-semibold">Cadastrar funcionário</h2>

        {erro && <Alerta>{erro}</Alerta>}

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Matrícula" hint="É por ela que o funcionário entra no app">
            <Input name="external_code" required maxLength={50} />
          </Field>
          <Field label="Nome completo">
            <Input name="name" required minLength={2} maxLength={200} />
          </Field>
          <Field label="CPF">
            <Input name="cpf" placeholder="000.000.000-00" maxLength={14} />
          </Field>
          <Field label="Cargo">
            <Input name="job_title" maxLength={120} />
          </Field>
          <Field label="E-mail">
            <Input name="email" type="email" />
          </Field>
          <Field label="Data de admissão">
            <Input name="hired_at" type="date" />
          </Field>
          <Field label="Local padrão">
            <Select name="default_site_id" defaultValue="">
              <option value="">Nenhum</option>
              {locais.map((local) => (
                <option key={local.id} value={local.id}>
                  {local.name}
                </option>
              ))}
            </Select>
          </Field>
          <Field
            label="Senha inicial do app"
            hint="Ao menos 12 caracteres. Provisória: o funcionário troca no primeiro acesso"
          >
            <Input name="initial_password" minLength={12} />
          </Field>
        </div>

        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" variant="ghost" onClick={onFechar} disabled={enviando}>
            Cancelar
          </Button>
          <Button type="submit" disabled={enviando}>
            {enviando ? "Salvando…" : "Cadastrar"}
          </Button>
        </div>
      </form>
    </div>
  );
}
