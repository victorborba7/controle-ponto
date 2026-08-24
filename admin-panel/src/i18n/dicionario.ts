/**
 * Catálogo de textos do painel.
 *
 * ## A garantia que este arquivo dá
 *
 * `en` é a fonte da verdade: o tipo `Chave` sai dele. `pt` é declarado como
 * `Record<Chave, string>`, então **esquecer uma chave é erro de compilação**,
 * não uma frase em inglês que ninguém percebe no meio de uma tela em
 * português. É a mesma proteção que o backend tem em teste, aqui de graça no
 * `tsc`.
 *
 * Um idioma novo (espanhol é o próximo candidato num hangar americano) é um
 * objeto a mais aqui e nenhum arquivo tocado fora daqui.
 *
 * ## Convenção das chaves
 *
 * `area.assunto` — `nav.*` para navegação, `ponto.*` para a tela de pontos,
 * e assim por diante. Os prefixos `tipo.`, `status.`, `metodo.`, `situacao.`,
 * `qualidade.` e `recusa.` espelham valores que vêm do backend; os nomes
 * depois do ponto são os códigos dele, e não devem ser traduzidos nem
 * "arrumados" — é o que permite mapear direto, sem tabela intermediária.
 *
 * Interpolação usa `{nome}`.
 */

import type { Idioma } from "./idioma";

const en = {
  // --- produto e navegação ---
  "app.nome": "Waypoint",
  "app.painel": "Admin panel",
  "app.descricao": "Employee management and time entry records",
  "nav.pontos": "Time entries",
  "nav.funcionarios": "Employees",
  "nav.locais": "Sites",
  "nav.usuarios": "Portal users",

  // --- usuários do painel ---
  "usuarios.titulo": "Portal users",
  "usuarios.subtitulo": "Who can sign in to this portal. Employees who clock in are managed under Employees.",
  "usuarios.novo": "Add user",
  "usuarios.nenhum": "No users yet.",
  "usuarios.falhaAoCarregar": "Could not load the users.",
  "usuarios.nome": "Name",
  "usuarios.email": "Email",
  "usuarios.papel": "Role",
  "usuarios.situacao": "Status",
  "usuarios.ultimoAcesso": "Last sign-in",
  "usuarios.nuncaAcessou": "Never",
  "usuarios.ativo": "Active",
  "usuarios.inativo": "Inactive",
  "usuarios.ativar": "Activate",
  "usuarios.desativar": "Deactivate",
  "usuarios.novaSenha": "Set password",
  "usuarios.senha": "Password",
  "usuarios.senhaAjuda": "At least 12 characters. Give it to the person directly.",
  "usuarios.salvar": "Create user",
  "usuarios.cancelar": "Cancel",
  "usuarios.voce": "you",
  "usuarios.soProprietario": "Only owners can add or change portal users.",
  "usuarios.senhaTrocada": "Password updated.",
  "papel.owner": "Owner",
  "papel.hr": "HR",
  "papel.viewer": "Viewer",
  "papel.owner.desc": "Full access, including managing portal users",
  "papel.hr.desc": "Manages employees, sites and entries",
  "papel.viewer.desc": "Read-only",
  "nav.configuracoes": "Settings",
  "nav.sair": "Sign out",

  // --- estados genéricos ---
  "geral.carregando": "Loading…",
  "geral.salvar": "Save",
  "geral.salvando": "Saving…",
  "geral.cancelar": "Cancel",
  "geral.fechar": "Close",
  "geral.todos": "All",
  "geral.sim": "Yes",
  "geral.nao": "No",

  // --- login ---
  "login.empresa": "Company",
  "login.empresaAjuda": "Company code, provided during onboarding",
  "login.email": "Email",
  "login.senha": "Password",
  "login.entrar": "Sign in",
  "login.entrando": "Signing in…",
  "login.falhou": "We could not sign you in",
  "login.semServidor": "We could not reach the server",

  // --- lista de funcionários ---
  "func.titulo": "Employees",
  "func.cadastrar": "Add employee",
  "func.ativos": "Active",
  "func.inativos": "Inactive",
  "func.total": "{n} on file",
  "func.vazio": "No employees on file yet.",
  "func.matricula": "Employee ID",
  "func.nome": "Name",
  "func.cargo": "Job title",
  "func.admissao": "Hire date",
  "func.situacao": "Status",
  "func.abrir": "Open",
  "func.falhaAoCarregar": "Could not load employees",

  // --- locais ---
  "local.titulo": "Sites",
  "local.cadastrar": "Add site",
  "local.novo": "New site",
  "local.total": "{n} site(s)",
  "local.vazio": "No sites yet. Start here, before adding employees.",
  "local.nome": "Name",
  "local.nomeExemplo": "Main Hangar",
  "local.endereco": "Address",
  "local.coordenadas": "Coordinates",
  "local.latitude": "Latitude",
  "local.latitudeAjuda": "Optional — used only by the GPS fallback",
  "local.longitude": "Longitude",
  "local.raio": "Geofence radius ({unidade})",
  "local.raioAjuda": "A radius that is too tight rejects people who are on site, because GPS is imprecise.",
  "local.raioColuna": "Radius",
  "local.beaconsEWifi": "Beacons and Wi-Fi",
  "local.falhaAoCarregar": "Could not load sites",
  "local.falhaAoCadastrar": "Could not create the site",

  // --- tipos de batida (valores do backend) ---
  "tipo.in": "Clock in",
  "tipo.out": "Clock out",
  "tipo.break_start": "Break start",
  "tipo.break_end": "Break end",

  // --- situação do registro ---
  "status.approved": "Approved",
  "status.pending_review": "Pending review",
  "status.rejected": "Rejected",

  // --- método de localização ---
  "metodo.beacon": "Beacon",
  "metodo.wifi": "Wi-Fi",
  "metodo.gps": "GPS",
  "metodo.none": "None",

  // --- situação do funcionário ---
  "situacao.active": "Active",
  "situacao.inactive": "Inactive",
  "situacao.suspended": "Suspended",

  // --- orientação de qualidade de foto ---
  "qualidade.blurry": "out of focus — hold the camera steady and don't move when you click",
  "qualidade.face_too_small": "face too small — move closer to the camera",
  "qualidade.face_too_far": "too far away — the face should fill much of the frame",
  "qualidade.face_cropped": "face cut off — center it in the frame",
  "qualidade.low_detection_confidence":
    "face not clear enough — improve the lighting and look at the camera",

  // --- motivo de recusa (códigos do backend) ---
  "recusa.multiple_faces": "more than one face in the photo",
  "recusa.no_face_detected": "no face found in the photo",
  "recusa.image_invalid": "invalid or corrupted image",
  "recusa.image_too_large": "image too large",
  "recusa.image_unreadable": "the image could not be processed",
  "recusa.low_image_quality": "photo quality not good enough",
  "recusa.recognition_unavailable": "face recognition unavailable",
} as const;

export type Chave = keyof typeof en;

// Tipado como `Record<Chave, string>` de propósito: é o que faz o `tsc`
// recusar o build quando uma chave nova entra só no inglês.
const pt: Record<Chave, string> = {
  "app.nome": "Waypoint",
  "app.painel": "Painel administrativo",
  "app.descricao": "Gestão de funcionários e registros de ponto",
  "nav.pontos": "Pontos",
  "nav.funcionarios": "Funcionários",
  "nav.locais": "Locais",
  "nav.usuarios": "Usuários do painel",

  "usuarios.titulo": "Usuários do painel",
  "usuarios.subtitulo": "Quem pode entrar neste painel. Os funcionários que batem ponto ficam em Funcionários.",
  "usuarios.novo": "Adicionar usuário",
  "usuarios.nenhum": "Nenhum usuário ainda.",
  "usuarios.falhaAoCarregar": "Não foi possível carregar os usuários.",
  "usuarios.nome": "Nome",
  "usuarios.email": "E-mail",
  "usuarios.papel": "Papel",
  "usuarios.situacao": "Situação",
  "usuarios.ultimoAcesso": "Último acesso",
  "usuarios.nuncaAcessou": "Nunca",
  "usuarios.ativo": "Ativo",
  "usuarios.inativo": "Inativo",
  "usuarios.ativar": "Ativar",
  "usuarios.desativar": "Desativar",
  "usuarios.novaSenha": "Definir senha",
  "usuarios.senha": "Senha",
  "usuarios.senhaAjuda": "Ao menos 12 caracteres. Entregue à pessoa diretamente.",
  "usuarios.salvar": "Criar usuário",
  "usuarios.cancelar": "Cancelar",
  "usuarios.voce": "você",
  "usuarios.soProprietario": "Só proprietários podem adicionar ou alterar usuários do painel.",
  "usuarios.senhaTrocada": "Senha atualizada.",
  "papel.owner": "Proprietário",
  "papel.hr": "RH",
  "papel.viewer": "Leitura",
  "papel.owner.desc": "Acesso total, inclusive gerenciar usuários do painel",
  "papel.hr.desc": "Gerencia funcionários, locais e pontos",
  "papel.viewer.desc": "Somente leitura",
  "nav.configuracoes": "Configurações",
  "nav.sair": "Sair",

  "geral.carregando": "Carregando…",
  "geral.salvar": "Salvar",
  "geral.salvando": "Salvando…",
  "geral.cancelar": "Cancelar",
  "geral.fechar": "Fechar",
  "geral.todos": "Todos",
  "geral.sim": "Sim",
  "geral.nao": "Não",

  "login.empresa": "Empresa",
  "login.empresaAjuda": "Código da empresa, informado na implantação",
  "login.email": "E-mail",
  "login.senha": "Senha",
  "login.entrar": "Entrar",
  "login.entrando": "Entrando…",
  "login.falhou": "Não foi possível entrar",
  "login.semServidor": "Não foi possível falar com o servidor",

  "func.titulo": "Funcionários",
  "func.cadastrar": "Cadastrar",
  "func.ativos": "Ativos",
  "func.inativos": "Inativos",
  "func.total": "{n} cadastrado(s)",
  "func.vazio": "Nenhum funcionário cadastrado ainda.",
  "func.matricula": "Matrícula",
  "func.nome": "Nome",
  "func.cargo": "Cargo",
  "func.admissao": "Admissão",
  "func.situacao": "Situação",
  "func.abrir": "Abrir",
  "func.falhaAoCarregar": "Falha ao carregar os funcionários",

  "local.titulo": "Locais",
  "local.cadastrar": "Cadastrar local",
  "local.novo": "Novo local",
  "local.total": "{n} local(is)",
  "local.vazio": "Nenhum local cadastrado. Comece por aqui antes dos funcionários.",
  "local.nome": "Nome",
  "local.nomeExemplo": "Hangar Principal",
  "local.endereco": "Endereço",
  "local.coordenadas": "Coordenadas",
  "local.latitude": "Latitude",
  "local.latitudeAjuda": "Opcional — usada apenas no fallback por GPS",
  "local.longitude": "Longitude",
  "local.raio": "Raio do geofence ({unidade})",
  "local.raioAjuda": "Um raio apertado demais rejeita quem está no local, por imprecisão do GPS.",
  "local.raioColuna": "Raio",
  "local.beaconsEWifi": "Beacons e Wi-Fi",
  "local.falhaAoCarregar": "Falha ao carregar os locais",
  "local.falhaAoCadastrar": "Falha ao cadastrar o local",

  "tipo.in": "Entrada",
  "tipo.out": "Saída",
  "tipo.break_start": "Início do intervalo",
  "tipo.break_end": "Fim do intervalo",

  "status.approved": "Aprovado",
  "status.pending_review": "Em revisão",
  "status.rejected": "Rejeitado",

  "metodo.beacon": "Beacon",
  "metodo.wifi": "Wi-Fi",
  "metodo.gps": "GPS",
  "metodo.none": "Nenhum",

  "situacao.active": "Ativo",
  "situacao.inactive": "Inativo",
  "situacao.suspended": "Suspenso",

  "qualidade.blurry": "foto desfocada — firme a câmera e evite mexer ao clicar",
  "qualidade.face_too_small": "rosto pequeno demais — chegue mais perto da câmera",
  "qualidade.face_too_far": "muito longe — o rosto precisa ocupar boa parte do quadro",
  "qualidade.face_cropped": "rosto cortado — centralize no enquadramento",
  "qualidade.low_detection_confidence":
    "rosto pouco nítido para o sistema — melhore a iluminação e olhe para a câmera",

  "recusa.multiple_faces": "mais de um rosto na foto",
  "recusa.no_face_detected": "nenhum rosto identificado na foto",
  "recusa.image_invalid": "imagem inválida ou corrompida",
  "recusa.image_too_large": "imagem grande demais",
  "recusa.image_unreadable": "não foi possível processar a imagem",
  "recusa.low_image_quality": "qualidade da foto insuficiente",
  "recusa.recognition_unavailable": "serviço de reconhecimento indisponível",
};

export const dicionario: Record<Idioma, Record<Chave, string>> = { en, pt };
