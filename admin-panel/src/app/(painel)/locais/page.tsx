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
import { useIdioma } from "@/i18n/contexto";
import { api } from "@/lib/api";
import type { Paginated, Site } from "@/lib/types";
import { local as rotaLocal } from "@/rotas";

// Limites do backend, em metros — a tela converte para a unidade do idioma.
const RAIO_MINIMO_M = 10;
const RAIO_MAXIMO_M = 5000;
const RAIO_PADRAO_M = 150;

export default function LocaisPage() {
  const { t, fmt } = useIdioma();
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
      setErro(e instanceof Error ? e.message : t("local.falhaAoCarregar"));
    } finally {
      setCarregando(false);
    }
  }, [t]);

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
        // O campo esta na unidade do idioma; o banco guarda metro, sempre.
        geofence_radius_m: fmt.distanciaEmMetros(
          numero("geofence_radius_m") ?? fmt.distanciaParaCampo(RAIO_PADRAO_M),
        ),
      });
      setCriando(false);
      await carregar();
    } catch (e) {
      setErro(e instanceof Error ? e.message : t("local.falhaAoCadastrar"));
    } finally {
      setEnviando(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-semibold">{t("local.titulo")}</h1>
        <Button onClick={() => setCriando((v) => !v)}>
          {criando ? t("geral.fechar") : t("local.cadastrar")}
        </Button>
      </div>

      {erro && <Alerta>{erro}</Alerta>}

      {criando && (
        <Card title={t("local.novo")}>
          <form onSubmit={salvar} className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label={t("local.nome")}>
                <Input
                  name="name"
                  required
                  minLength={2}
                  placeholder={t("local.nomeExemplo")}
                />
              </Field>
              <Field label={t("local.endereco")}>
                <Input name="address" />
              </Field>
              <Field label={t("local.latitude")} hint={t("local.latitudeAjuda")}>
                <Input name="latitude" type="number" step="any" placeholder="39.7392" />
              </Field>
              <Field label={t("local.longitude")}>
                <Input name="longitude" type="number" step="any" placeholder="-104.9903" />
              </Field>
              <Field
                label={t("local.raio", { unidade: fmt.unidadeDistancia })}
                hint={t("local.raioAjuda")}
              >
                <Input
                  name="geofence_radius_m"
                  type="number"
                  min={fmt.distanciaParaCampo(RAIO_MINIMO_M)}
                  max={fmt.distanciaParaCampo(RAIO_MAXIMO_M)}
                  defaultValue={fmt.distanciaParaCampo(RAIO_PADRAO_M)}
                />
              </Field>
            </div>
            <div className="flex justify-end">
              <Button type="submit" disabled={enviando}>
                {enviando ? t("geral.salvando") : t("local.cadastrar")}
              </Button>
            </div>
          </form>
        </Card>
      )}

      <Card title={t("local.total", { n: locais.length })}>
        {carregando ? (
          <Carregando />
        ) : !locais.length ? (
          <Vazio>{t("local.vazio")}</Vazio>
        ) : (
          <Tabela>
            <thead>
              <tr>
                <Th>{t("local.nome")}</Th>
                <Th>{t("local.endereco")}</Th>
                <Th>{t("local.coordenadas")}</Th>
                <Th>{t("local.raioColuna")}</Th>
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
                  <Td>{fmt.distancia(local.geofence_radius_m)}</Td>
                  <Td>
                    <Link
                      href={rotaLocal(local.id)}
                      className="text-sm text-zinc-600 underline-offset-2 hover:underline dark:text-zinc-300"
                    >
                      {t("local.beaconsEWifi")}
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
