import { redirect } from "next/navigation";

/** A raiz não tem conteúdo próprio: o painel começa na lista de pontos. */
export default function Home() {
  redirect("/pontos");
}
