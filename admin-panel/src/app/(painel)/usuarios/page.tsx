"use client";

import { useCallback, useEffect, useState } from "react";

import {
  Alerta,
  Badge,
  Button,
  Card,
  Carregando,
  Field,
  Input,
  Select,
  Tabela,
  Td,
  Th,
  Vazio,
} from "@/components/ui";
import { useIdioma } from "@/i18n/contexto";
import { api } from "@/lib/api";
import type { AdminProfile, PanelUser, UserRole } from "@/lib/types";

const PAPEIS: UserRole[] = ["owner", "hr", "viewer"];

type Sessao = { subject_id: string; role: AdminProfile["role"] };

export default function UsuariosPage() {
  const { t, fmt } = useIdioma();
  const [usuarios, setUsuarios] = useState<PanelUser[] | null>(null);
  const [sessao, setSessao] = useState<Sessao | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [criando, setCriando] = useState(false);

  const carregar = useCallback(async () => {
    setCarregando(true);
    setErro(null);
    try {
      const [lista, quemSouEu] = await Promise.all([
        api.get<{ items: PanelUser[] }>("/users"),
        api.get<Sessao>("/auth/me"),
      ]);
      setUsuarios(lista.items);
      setSessao(quemSouEu);
    } catch (e) {
      setErro(e instanceof Error ? e.message : t("usuarios.falhaAoCarregar"));
    } finally {
      setCarregando(false);
    }
  }, [t]);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  // A API já recusa quem não é proprietário; esconder os controles aqui evita
  // oferecer um botão que só produziria 403.
  const podeGerenciar = sessao?.role === "owner";

  async function alternarSituacao(usuario: PanelUser) {
    setErro(null);
    setAviso(null);
    try {
      const atualizado = await api.patch<PanelUser>(`/users/${usuario.id}`, {
        is_active: !usuario.is_active,
      });
      setUsuarios((atuais) =>
        (atuais ?? []).map((u) => (u.id === atualizado.id ? atualizado : u)),
      );
    } catch (e) {
      setErro(e instanceof Error ? e.message : t("usuarios.falhaAoCarregar"));
    }
  }

  async function trocarPapel(usuario: PanelUser, papel: UserRole) {
    setErro(null);
    setAviso(null);
    try {
      const atualizado = await api.patch<PanelUser>(`/users/${usuario.id}`, {
        role: papel,
      });
      setUsuarios((atuais) =>
        (atuais ?? []).map((u) => (u.id === atualizado.id ? atualizado : u)),
      );
    } catch (e) {
      setErro(e instanceof Error ? e.message : t("usuarios.falhaAoCarregar"));
    }
  }

  async function definirSenha(usuario: PanelUser) {
    const senha = window.prompt(`${t("usuarios.novaSenha")}: ${usuario.name}`);
    if (!senha) return;

    setErro(null);
    setAviso(null);
    try {
      await api.post(`/users/${usuario.id}/password`, { password: senha });
      setAviso(t("usuarios.senhaTrocada"));
    } catch (e) {
      setErro(e instanceof Error ? e.message : t("usuarios.falhaAoCarregar"));
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold">{t("usuarios.titulo")}</h1>
          <p className="mt-1 max-w-xl text-sm text-zinc-500 dark:text-zinc-400">
            {t("usuarios.subtitulo")}
          </p>
        </div>
        {podeGerenciar && (
          <Button onClick={() => setCriando(true)}>{t("usuarios.novo")}</Button>
        )}
      </div>

      {!podeGerenciar && !carregando && (
        <Alerta tipo="info">{t("usuarios.soProprietario")}</Alerta>
      )}
      {erro && <Alerta tipo="erro">{erro}</Alerta>}
      {aviso && <Alerta tipo="sucesso">{aviso}</Alerta>}

      {carregando ? (
        <Carregando />
      ) : !usuarios?.length ? (
        <Vazio>{t("usuarios.nenhum")}</Vazio>
      ) : (
        <Card>
          <Tabela>
            <thead>
              <tr>
                <Th>{t("usuarios.nome")}</Th>
                <Th>{t("usuarios.papel")}</Th>
                <Th>{t("usuarios.situacao")}</Th>
                <Th>{t("usuarios.ultimoAcesso")}</Th>
                <Th> </Th>
              </tr>
            </thead>
            <tbody>
              {usuarios.map((usuario) => {
                const souEu = usuario.id === sessao?.subject_id;
                return (
                  <tr key={usuario.id}>
                    <Td>
                      <div className="font-medium">
                        {usuario.name}
                        {souEu && (
                          <span className="ml-2 text-xs font-normal text-zinc-500">
                            ({t("usuarios.voce")})
                          </span>
                        )}
                      </div>
                      <div className="text-xs text-zinc-500 dark:text-zinc-400">
                        {usuario.email}
                      </div>
                    </Td>
                    <Td>
                      {podeGerenciar && !souEu ? (
                        <Select
                          value={usuario.role}
                          onChange={(e) =>
                            void trocarPapel(usuario, e.target.value as UserRole)
                          }
                        >
                          {PAPEIS.map((papel) => (
                            <option key={papel} value={papel}>
                              {t(`papel.${papel}`)}
                            </option>
                          ))}
                        </Select>
                      ) : (
                        t(`papel.${usuario.role}`)
                      )}
                    </Td>
                    <Td>
                      <Badge
                        className={
                          usuario.is_active
                            ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300"
                            : "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400"
                        }
                      >
                        {usuario.is_active ? t("usuarios.ativo") : t("usuarios.inativo")}
                      </Badge>
                    </Td>
                    <Td className="text-zinc-500 dark:text-zinc-400">
                      {usuario.last_login_at
                        ? fmt.dataHora(usuario.last_login_at)
                        : t("usuarios.nuncaAcessou")}
                    </Td>
                    <Td>
                      {podeGerenciar && (
                        <div className="flex flex-wrap gap-2">
                          <Button
                            variant="secondary"
                            onClick={() => void definirSenha(usuario)}
                          >
                            {t("usuarios.novaSenha")}
                          </Button>
                          {!souEu && (
                            <Button
                              variant="secondary"
                              onClick={() => void alternarSituacao(usuario)}
                            >
                              {usuario.is_active
                                ? t("usuarios.desativar")
                                : t("usuarios.ativar")}
                            </Button>
                          )}
                        </div>
                      )}
                    </Td>
                  </tr>
                );
              })}
            </tbody>
          </Tabela>
        </Card>
      )}

      {criando && (
        <NovoUsuario
          onFechar={() => setCriando(false)}
          onCriado={(novo) => {
            setUsuarios((atuais) => [...(atuais ?? []), novo]);
            setCriando(false);
          }}
        />
      )}
    </div>
  );
}

function NovoUsuario({
  onFechar,
  onCriado,
}: {
  onFechar: () => void;
  onCriado: (usuario: PanelUser) => void;
}) {
  const { t } = useIdioma();
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  async function salvar(evento: React.FormEvent<HTMLFormElement>) {
    evento.preventDefault();
    setEnviando(true);
    setErro(null);

    const form = new FormData(evento.currentTarget);
    try {
      onCriado(
        await api.post<PanelUser>("/users", {
          email: String(form.get("email") ?? "").trim(),
          name: String(form.get("name") ?? "").trim(),
          role: form.get("role"),
          password: String(form.get("password") ?? ""),
        }),
      );
    } catch (e) {
      setErro(e instanceof Error ? e.message : t("usuarios.falhaAoCarregar"));
    } finally {
      setEnviando(false);
    }
  }

  return (
    <Card>
      <form onSubmit={salvar} className="space-y-4">
        <h2 className="font-semibold">{t("usuarios.novo")}</h2>

        {erro && <Alerta tipo="erro">{erro}</Alerta>}

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label={t("usuarios.nome")}>
            <Input name="name" required minLength={2} autoComplete="off" />
          </Field>
          <Field label={t("usuarios.email")}>
            <Input name="email" type="email" required autoComplete="off" />
          </Field>
          <Field label={t("usuarios.papel")}>
            <Select name="role" defaultValue="hr">
              {PAPEIS.map((papel) => (
                <option key={papel} value={papel}>
                  {t(`papel.${papel}`)}: {t(`papel.${papel}.desc`)}
                </option>
              ))}
            </Select>
          </Field>
          <Field label={t("usuarios.senha")} hint={t("usuarios.senhaAjuda")}>
            {/* `new-password` impede o navegador de oferecer a senha de quem
                está logado para uma conta que é de outra pessoa. */}
            <Input
              name="password"
              type="password"
              required
              minLength={12}
              autoComplete="new-password"
            />
          </Field>
        </div>

        <div className="flex gap-2">
          <Button type="submit" disabled={enviando}>
            {t("usuarios.salvar")}
          </Button>
          <Button type="button" variant="secondary" onClick={onFechar}>
            {t("usuarios.cancelar")}
          </Button>
        </div>
      </form>
    </Card>
  );
}
