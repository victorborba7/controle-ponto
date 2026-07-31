"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

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
import type { Beacon, Paginated, SiteDetail, WifiNetwork } from "@/lib/types";

export default function LocalPage() {
  const { id } = useParams<{ id: string }>();

  const [local, setLocal] = useState<SiteDetail | null>(null);
  const [beacons, setBeacons] = useState<Beacon[]>([]);
  const [redes, setRedes] = useState<WifiNetwork[]>([]);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  const carregar = useCallback(async () => {
    setCarregando(true);
    try {
      const [ficha, listaBeacons, listaRedes] = await Promise.all([
        api.get<SiteDetail>(`/sites/${id}`),
        api.get<Paginated<Beacon>>(`/sites/${id}/beacons`),
        api.get<Paginated<WifiNetwork>>(`/sites/${id}/wifi-networks`),
      ]);
      setLocal(ficha);
      setBeacons(listaBeacons.items);
      setRedes(listaRedes.items);
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao carregar");
    } finally {
      setCarregando(false);
    }
  }, [id]);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  async function cadastrarBeacon(evento: React.FormEvent<HTMLFormElement>) {
    evento.preventDefault();
    setEnviando(true);
    setErro(null);

    const form = new FormData(evento.currentTarget);
    const formulario = evento.currentTarget;

    try {
      await api.post(`/sites/${id}/beacons`, {
        label: String(form.get("label")).trim(),
        protocol: "eddystone",
        eddystone_namespace: String(form.get("namespace")).trim(),
        eddystone_instance: String(form.get("instance")).trim(),
        min_rssi: Number(form.get("min_rssi")),
      });
      formulario.reset();
      await carregar();
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao cadastrar o beacon");
    } finally {
      setEnviando(false);
    }
  }

  async function cadastrarRede(evento: React.FormEvent<HTMLFormElement>) {
    evento.preventDefault();
    setEnviando(true);
    setErro(null);

    const form = new FormData(evento.currentTarget);
    const formulario = evento.currentTarget;

    try {
      await api.post(`/sites/${id}/wifi-networks`, {
        ssid: String(form.get("ssid")).trim(),
        bssid: String(form.get("bssid") ?? "").trim() || null,
        label: String(form.get("label") ?? "").trim() || null,
      });
      formulario.reset();
      await carregar();
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao cadastrar a rede");
    } finally {
      setEnviando(false);
    }
  }

  async function alternarBeacon(beacon: Beacon) {
    await api
      .patch(`/sites/${id}/beacons/${beacon.id}`, { is_active: !beacon.is_active })
      .then(carregar)
      .catch((e) => setErro(e instanceof Error ? e.message : "Falha"));
  }

  if (carregando) return <Carregando />;
  if (!local) return <Alerta>{erro ?? "Local não encontrado"}</Alerta>;

  return (
    <div className="space-y-6">
      <div>
        <Link
          href="/locais"
          className="text-sm text-zinc-500 underline-offset-2 hover:underline"
        >
          ← Locais
        </Link>
        <h1 className="mt-1 text-xl font-semibold">{local.name}</h1>
        <p className="text-sm text-zinc-500">
          {local.address ?? "Sem endereço"} · raio de {local.geofence_radius_m} m
        </p>
      </div>

      {erro && <Alerta>{erro}</Alerta>}

      <Card title="Beacons">
        <form onSubmit={cadastrarBeacon} className="mb-6 space-y-4">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Field label="Onde fica" hint='Como quem trabalha no local chama: "Portão A"'>
              <Input name="label" required minLength={2} />
            </Field>
            <Field label="Namespace" hint="10 bytes — pode colar como está na etiqueta">
              <Input name="namespace" required placeholder="edd1ebeac04e5defa017" />
            </Field>
            <Field label="Instance" hint="6 bytes">
              <Input name="instance" required placeholder="000000000001" />
            </Field>
            <Field
              label="RSSI mínimo"
              hint="Meça no ponto mais distante que ainda conta e deixe 5 dBm de folga"
            >
              <Input name="min_rssi" type="number" min={-100} max={-30} defaultValue={-80} />
            </Field>
          </div>
          <div className="flex justify-end">
            <Button type="submit" variant="secondary" disabled={enviando}>
              Adicionar beacon
            </Button>
          </div>
        </form>

        {!beacons.length ? (
          <Vazio>Nenhum beacon cadastrado neste local.</Vazio>
        ) : (
          <Tabela>
            <thead>
              <tr>
                <Th>Onde fica</Th>
                <Th>Identificador</Th>
                <Th>RSSI mínimo</Th>
                <Th>Situação</Th>
                <Th>{""}</Th>
              </tr>
            </thead>
            <tbody>
              {beacons.map((beacon) => (
                <tr key={beacon.id}>
                  <Td className="font-medium">{beacon.label}</Td>
                  <Td className="font-mono text-xs">
                    {beacon.protocol === "eddystone"
                      ? `${beacon.eddystone_namespace} / ${beacon.eddystone_instance}`
                      : `${beacon.ibeacon_uuid} ${beacon.ibeacon_major}:${beacon.ibeacon_minor}`}
                  </Td>
                  <Td>{beacon.min_rssi} dBm</Td>
                  <Td>
                    <Badge
                      className={
                        beacon.is_active
                          ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300"
                          : "bg-zinc-200 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300"
                      }
                    >
                      {beacon.is_active ? "Ativo" : "Inativo"}
                    </Badge>
                  </Td>
                  <Td>
                    <Button variant="ghost" onClick={() => alternarBeacon(beacon)}>
                      {beacon.is_active ? "Desativar" : "Reativar"}
                    </Button>
                  </Td>
                </tr>
              ))}
            </tbody>
          </Tabela>
        )}
      </Card>

      <Card title="Redes Wi-Fi">
        <form onSubmit={cadastrarRede} className="mb-6 space-y-4">
          <div className="grid gap-4 sm:grid-cols-3">
            <Field label="SSID">
              <Input name="ssid" required placeholder="EmpresaDemo-Corp" />
            </Field>
            <Field
              label="BSSID"
              hint="MAC do ponto de acesso. Sem ele, a rede vale bem menos: qualquer hotspot pode usar o mesmo nome."
            >
              <Input name="bssid" placeholder="a4:2b:8c:00:11:22" />
            </Field>
            <Field label="Identificação" hint="Ex.: AP do hangar, banda 5 GHz">
              <Input name="label" />
            </Field>
          </div>
          <div className="flex justify-end">
            <Button type="submit" variant="secondary" disabled={enviando}>
              Adicionar rede
            </Button>
          </div>
        </form>

        {!redes.length ? (
          <Vazio>Nenhuma rede cadastrada neste local.</Vazio>
        ) : (
          <Tabela>
            <thead>
              <tr>
                <Th>SSID</Th>
                <Th>BSSID</Th>
                <Th>Identificação</Th>
                <Th>Situação</Th>
              </tr>
            </thead>
            <tbody>
              {redes.map((rede) => (
                <tr key={rede.id}>
                  <Td className="font-medium">{rede.ssid}</Td>
                  <Td className="font-mono text-xs">{rede.bssid ?? "—"}</Td>
                  <Td>{rede.label ?? "—"}</Td>
                  <Td>
                    <Badge
                      className={
                        rede.is_active
                          ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300"
                          : "bg-zinc-200 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300"
                      }
                    >
                      {rede.is_active ? "Ativa" : "Inativa"}
                    </Badge>
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
