/**
 * Caminhos das telas do painel, num lugar só.
 *
 * Existe porque os caminhos ainda estão em português (`/pontos`,
 * `/funcionarios`) e vão virar inglês junto com o resto. Espalhados por doze
 * arquivos, essa troca seria uma caçada a string; aqui é uma edição.
 *
 * O nome da pasta em `app/` precisa acompanhar o valor daqui — o Next deriva a
 * rota do diretório, então isto não é a fonte da verdade, é o índice dela.
 */

export const rotas = {
  pontos: "/pontos",
  funcionarios: "/funcionarios",
  locais: "/locais",
  configuracoes: "/configuracoes",
  usuarios: "/usuarios",
  login: "/login",
} as const;

export function funcionario(id: string) {
  return `${rotas.funcionarios}/${id}`;
}

export function local(id: string) {
  return `${rotas.locais}/${id}`;
}
