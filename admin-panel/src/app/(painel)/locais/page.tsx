"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import {
  Alerta,
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
import type { Paginated, Site } from "@/lib/types";

export default function LocaisPage() {
  const [locais, setLocais] = useState<Site[]>([]);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState<string | null>(null);
  const [criando, setCriando] = useState(false);
  const [enviando, setEnviando] = useState(false);

  const carregar = useCallback(async () => {
    setCarregando(true);
    try {
      setLocais((await api.get<Paginated<Site>>("/sites")).items);
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao carregar");
    } finally {
      setCarregando(false);
    }
  }, []);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  async function salvar(evento: React.FormEvent<HTMLFormElement>) {
    evento.preventDefault();
    setEnviando(true);
    setErro(null);

    const form = new FormData(evento.currentTarget);
    const numero = (campo: string) => {
      const valor = String(form.get(campo) ?? "").trim();
      return valor === "" ? null : Number(valor);
    };

    try {
      await api.post("/sites", {
        name: String(form.get("name")).trim(),
        address: String(form.get("address") ?? "").trim() || null,
        latitude: numero("latitude"),
        longitude: numero("longitude"),
        geofence_radius_m: numero("geofence_radius_m") ?? 150,
      });
      setCriando(false);
      await carregar();
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao cadastrar o local");
    } finally {
      setEnviando(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-semibold">Locais</h1>
        <Button onClick={() => setCriando((v) => !v)}>
          {criando ? "Fechar" : "Cadastrar local"}
        </Button>
      </div>

      {erro && <Alerta>{erro}</Alerta>}

      {criando && (
        <Card title="Novo local">
          <form onSubmit={salvar} className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Nome">
                <Input name="name" required minLength={2} placeholder="Hangar Principal" />
              </Field>
              <Field label="Endereço">
                <Input name="address" />
              </Field>
              <Field label="Latitude" hint="Opcional — usada apenas no fallback por GPS">
                <Input name="latitude" type="number" step="any" placeholder="-23.4356" />
              </Field>
              <Field label="Longitude">
                <Input name="longitude" type="number" step="any" placeholder="-46.4731" />
              </Field>
              <Field
                label="Raio do geofence (m)"
                hint="Entre 10 e 5000. Um raio apertado demais rejeita quem está no local, por imprecisão do GPS."
              >
                <Input
                  name="geofence_radius_m"
                  type="number"
                  min={10}
                  max={5000}
                  defaultValue={150}
                />
              </Field>
            </div>
            <div className="flex justify-end">
              <Button type="submit" disabled={enviando}>
                {enviando ? "Salvando…" : "Cadastrar"}
              </Button>
            </div>
          </form>
        </Card>
      )}

      <Card title={`${locais.length} local(is)`}>
        {carregando ? (
          <Carregando />
        ) : !locais.length ? (
          <Vazio>Nenhum local cadastrado. Comece por aqui antes dos funcionários.</Vazio>
        ) : (
          <Tabela>
            <thead>
              <tr>
                <Th>Nome</Th>
                <Th>Endereço</Th>
                <Th>Coordenadas</Th>
                <Th>Raio</Th>
                <Th>{""}</Th>
              </tr>
            </thead>
            <tbody>
              {locais.map((local) => (
                <tr key={local.id}>
                  <Td className="font-medium">{local.name}</Td>
                  <Td>{local.address ?? "—"}</Td>
                  <Td className="font-mono text-xs">
                    {local.latitude !== null
                      ? `${local.latitude.toFixed(5)}, ${local.longitude?.toFixed(5)}`
                      : "—"}
                  </Td>
                  <Td>{local.geofence_radius_m} m</Td>
                  <Td>
                    <Link
                      href={`/locais/${local.id}`}
                      className="text-sm text-zinc-600 underline-offset-2 hover:underline dark:text-zinc-300"
                    >
                      Beacons e Wi-Fi
                    </Link>
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
