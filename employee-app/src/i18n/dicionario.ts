/**
 * Catálogo de textos do app do funcionário.
 *
 * ## A garantia que este arquivo dá
 *
 * `en` é a fonte da verdade: o tipo `Chave` sai dele. `pt` é declarado como
 * `Record<Chave, string>`, então **esquecer uma chave é erro de compilação** —
 * não uma frase em português aparecendo no meio de uma tela em inglês, que é
 * o defeito que ninguém percebe revisando código. Mesma proteção do painel.
 *
 * ## Convenção das chaves
 *
 * `area.assunto`. Os prefixos `tipo.`, `status.` e `metodo.` espelham valores
 * que vêm do backend, e os nomes depois do ponto são os códigos dele — não
 * devem ser traduzidos nem "arrumados", porque é o que permite mapear direto
 * sem tabela intermediária.
 *
 * Interpolação usa `{nome}`.
 */

import type { Idioma } from "./idioma";

const en = {
  // --- login ---
  "login.subtitulo": "Sign in to record your time",
  "login.empresa": "Company code",
  "login.matricula": "Employee ID",
  "login.senha": "Password",
  "login.entrar": "Sign in",
  "login.ajuda": "Don't know your company code or password? Ask HR.",
  "login.diagnostico": "Site diagnostics",
  "login.falhou": "Could not sign in",

  // --- tela de ponto ---
  "ponto.verificandoPermissoes": "Checking permissions…",
  "ponto.procurandoBeacons": "Looking for site beacons…",
  "ponto.falhaSinais": "Could not read the site signals.",
  "ponto.falhaFoto": "Could not take the photo.",
  "ponto.entradaRegistrada": "Clock-in recorded",
  "ponto.saidaRegistrada": "Clock-out recorded",
  "ponto.registroRegistrado": "Entry recorded",
  "ponto.guardado": "Entry saved",
  "ponto.semConexao":
    "No connection right now. Your entry was saved with the current time and will be sent as soon as there is signal.",
  "ponto.naoRegistrado": "Could not record your entry",
  "ponto.enquadre": "Center your face in the frame and tap to record.",
  "ponto.registrar": "Record entry",
  "ponto.baterSaida": "Clock out (last of the day)",
  "ponto.meusRegistros": "My entries",
  "ponto.diagnostico": "Diagnostics",
  "ponto.sair": "Sign out",
  "ponto.voltar": "Back",
  "ponto.exemploRotulo": "e.g. Arrived at the hangar",
  "ponto.observacao": "Note",
  "ponto.observacaoOpcional": "Note (optional)",
  "ponto.obrigatorio": "Required",
  "ponto.opcional": "Optional",
  "ponto.fila.aguardando_um": "1 entry waiting to be sent. It will go out as soon as there is signal.",
  "ponto.fila.aguardando_varios": "{n} entries waiting to be sent. They will go out as soon as there is signal.",
  "ponto.fila.descartado_um": "1 saved entry could not be sent and left the queue. Ask HR to enter the time manually.",
  "ponto.fila.descartado_varios": "{n} saved entries could not be sent and left the queue. Ask HR to enter the times manually.",

  // --- permissões ---
  "permissao.camera.titulo": "Camera permission",
  "permissao.camera.explicacao":
    "Face recognition is what proves it was you who recorded the entry. Without camera access, the entry cannot be made.",
  "permissao.camera.permitir": "Allow camera",
  "permissao.local.titulo": "Location permission",
  "permissao.local.explicacao":
    "Location confirms you are at the worksite. It is used only at the moment you record an entry — the app does not track your movements.",
  "permissao.local.android":
    "On Android, this permission is also what allows reading the site beacons and Wi-Fi network.",
  "permissao.local.permitir": "Allow location",

  // --- cadastro do rosto ---
  "cadastro.verificandoCamera": "Checking the camera…",
  "cadastro.titulo": "Enroll your face",
  "cadastro.tituloPermissao": "Enroll your face",
  "cadastro.explicacaoCamera":
    "To enroll your face, the app needs the camera. It is used only for this enrollment and when you record your time.",
  "cadastro.contador": "Photo {atual} of {total} — {passo}",
  "cadastro.passo1.titulo": "Looking at the camera",
  "cadastro.passo1.instrucao":
    "Face centered, light on your face, no cap or sunglasses.",
  "cadastro.passo2.titulo": "A little closer",
  "cadastro.passo2.instrucao":
    "Bring the phone closer until your face nearly fills the circle.",
  "cadastro.passo3.titulo": "Natural expression",
  "cadastro.passo3.instrucao":
    "Move back again and relax your face, as you would look day to day.",
  "cadastro.tirarFoto": "Take photo",
  "cadastro.concluir": "Finish enrollment",
  "cadastro.enviando": "Sending…",
  "cadastro.recomecar": "Start over",
  "cadastro.falhou": "Could not enroll your face.",
  "cadastro.poucasFotos": "At least {minimo} photos are required.",
  "cadastro.fotoSumiu": "One of the photos is no longer on this device.",

  // --- termo de consentimento ---
  // Tradução fiel do texto em português, para o app ser utilizável já. O
  // conteúdo continua escrito sob a ótica da LGPD e **precisa de revisão por
  // advogado trabalhista americano**. Quando o texto mudar de substância,
  // `VERSAO_DO_TERMO` sobe junto — é ele que prova o que a pessoa aceitou.
  "termo.titulo": "How your data is used",
  "termo.imagem.titulo": "Your photo",
  "termo.imagem.corpo":
    "When you record your time, the app takes a photo of your face and compares it with the photos enrolled with HR. The comparison happens on the company server and serves only to confirm that it was you who recorded the entry.",
  "termo.local.titulo": "Your location",
  "termo.local.corpo1":
    "At the same moment, the app checks whether you are at the worksite — through the installed beacons, the company Wi-Fi network, or GPS.",
  "termo.local.destaque": "only when you record your time",
  "termo.local.corpo2":
    "This happens {destaque}. The app does not track your movements and collects nothing in the background.",
  "termo.direitos.titulo": "Your rights",
  "termo.direitos.corpo1":
    "You may ask HR at any time to see the data the company holds about you, to correct it, or to withdraw this consent.",
  "termo.direitos.corpo2":
    "Withdrawing prevents the use of face recognition for time tracking — in that case, arrange another way to record your hours with HR.",
  "termo.aceite":
    "I have read and agree to the use of my image and my location for time tracking.",
  "termo.versao": "Terms version {versao}",
  "termo.continuar": "Continue",

  // --- diagnóstico do local (ferramenta de instalação) ---
  "diag.titulo": "Site diagnostics",
  "diag.varrer": "Scan signals",
  "diag.procurando": "Scanning…",
  "diag.varreduraCrua": "Raw scan (12s)",
  "diag.varrerDeNovo": "Scan again (12s, raw)",
  "diag.compararParametros": "Compare parameters (2 × 8s)",
  "diag.atualizarCadastro": "Refresh site registration",
  "diag.falhaVarrer": "Could not scan the signals.",
  "diag.falhaAtualizar":
    "Could not refresh — no network? The previous cache is still valid.",
  "diag.resumoCadastro":
    "{locais} site(s), {beacons} registered beacon(s)",
  "diag.resumoUuids": " · {uuids} iBeacon UUID(s) to look for",
  "diag.semNome": "(no name)",
  "diag.semBssid": "BSSID unavailable",
  "diag.nenhumAnuncio": "No beacon advertisement among them",
  "diag.nenhum": "None",
  "diag.filtrar": "Filter by MAC, name or advertisement bytes",
  "diag.toqueParaCopiar": "Tap to copy",
  "diag.toqueParaCopiarMac": "Tap to copy the MAC",
  "diag.copiado": "Copied!",
  "diag.macCopiado": "MAC copied!",
  "diag.enderecoMac": "MAC ADDRESS",
  "diag.anuncios": "{n} advertisement(s)",
  "diag.macPublico": "public (fixed)",
  "diag.macFixoOuPublico": "fixed, or public",
  "diag.semPermissaoBluetooth": "No Bluetooth permission",
  "diag.legacyNaoEACausa":
    "No beacon recognized in either pass — the legacy parameter is not the cause. The advertisement is not reaching the app.",

  // --- histórico ---
  "historico.titulo": "My entries",
  "historico.vazio": "No entries yet.",
  "historico.falhaCarregar": "Could not load",
  "historico.porQueConferencia": "why is my entry under review?",

  // --- tipos de batida (códigos do backend) ---
  "tipo.in": "Clock in",
  "tipo.out": "Clock out",
  "tipo.intermediate": "During the day",
  "tipo.break_start": "Break start",
  "tipo.break_end": "Break end",

  // --- status (códigos do backend) ---
  "status.approved": "Approved",
  "status.pending_review": "Under review",
  "status.rejected": "Rejected",

  // --- método de localização (códigos do backend) ---
  "metodo.beacon": "Site beacon",
  "metodo.wifi": "Site Wi-Fi",
  "metodo.gps": "GPS",
  "metodo.none": "No site signal",

  // --- sinais e permissões do aparelho ---
  "sinal.bluetoothDesligado":
    "Bluetooth is off — turn it on to detect the site beacons.",
  "sinal.semPermissaoBluetooth": "Bluetooth permission denied.",
  "sinal.semPermissaoLocalizacao": "Location permission denied.",
  "sinal.wifiNaoIdentificado":
    "Wi-Fi network not identified — check the location permission.",
  "sinal.wifiSemEntitlement":
    "This iPhone cannot read the Wi-Fi network name. Beacons and GPS still work.",
  "sinal.gpsIndisponivel": "Could not get your location.",
  "sinal.gpsDemorou": "Could not get your location in time.",
  "sinal.falhaVarredura": "Bluetooth scan failed.",
  "sinal.nenhum": "No location signal detected",
  "sinal.verificandoWifi": "Checking the Wi-Fi network…",
  "sinal.obtendoLocalizacao": "Getting your location…",
  "sinal.faltaLocalParaBle":
    "Location permission is missing. Android requires it to deliver beacon advertisements — without it the scan finds phones and headphones, but no beacons.",
  "sinal.libereLocalNosAjustes":
    " Allow it in Settings → Apps → Waypoint → Permissions → Location.",
  "sinal.bluetoothNegadoAjustes":
    "Bluetooth permission denied. Allow it in Settings → Apps → Waypoint → Permissions.",
  "sinal.bluetoothNegado":
    "Without Bluetooth permission the site beacons cannot be detected.",
  "sinal.androidLocalLiberaBeacon":
    "On this version of Android, the location permission is what allows reading the beacons.",
  "sinal.semIBeaconCadastrado":
    "No iBeacon registered for this site. On iPhone the UUID must be known in advance — iOS does not scan for iBeacons generically.",
  "sinal.iBeaconIndisponivel": "iBeacon reading is unavailable in this version of the app.",
  "sinal.iosSemPermissaoLocal":
    "Without location permission, the iPhone does not deliver beacons. Allow it in Settings → Waypoint → Location.",

  // --- erros de rede e sessão ---
  "erro.semResposta": "The server did not respond. Check your connection.",
  "erro.sessaoExpirada": "Your session has expired. Sign in again.",
  "erro.inesperado": "Something went wrong. Try again.",
  "erro.httpGenerico": "Communication failed (HTTP {status})",
  "erro.semConexaoServidor": "No connection to the server",
  "erro.falhaEnvio": "Send failed",
  "erro.fotoSumiuDaBatida": "The photo for this entry is no longer on this device.",
  "campo.observacaoObrigatoria": "Write a note to continue.",
  "campo.tipoObrigatorio": "Choose the entry type to continue.",
} as const;

export type Chave = keyof typeof en;

// Tipado como `Record<Chave, string>` de propósito: é o que faz o `tsc`
// recusar um catálogo incompleto.
const pt: Record<Chave, string> = {
  "login.subtitulo": "Entre para registrar seu ponto",
  "login.empresa": "Código da empresa",
  "login.matricula": "Matrícula",
  "login.senha": "Senha",
  "login.entrar": "Entrar",
  "login.ajuda": "Não sabe seu código de empresa ou senha? Procure o RH.",
  "login.diagnostico": "Diagnóstico do local",
  "login.falhou": "Não foi possível entrar",

  "ponto.verificandoPermissoes": "Verificando permissões…",
  "ponto.procurandoBeacons": "Procurando beacons do local…",
  "ponto.falhaSinais": "Falha ao ler os sinais do local.",
  "ponto.falhaFoto": "Não foi possível capturar a foto.",
  "ponto.entradaRegistrada": "Entrada registrada",
  "ponto.saidaRegistrada": "Saída registrada",
  "ponto.registroRegistrado": "Ponto registrado",
  "ponto.guardado": "Ponto guardado",
  "ponto.semConexao":
    "Sem conexão agora. O registro foi salvo com o horário de agora e será enviado assim que houver sinal.",
  "ponto.naoRegistrado": "Não foi possível registrar",
  "ponto.enquadre": "Centralize o rosto na moldura e toque em registrar.",
  "ponto.registrar": "Registrar ponto",
  "ponto.baterSaida": "Bater saída (última do dia)",
  "ponto.meusRegistros": "Meus registros",
  "ponto.diagnostico": "Diagnóstico",
  "ponto.sair": "Sair",
  "ponto.voltar": "Voltar",
  "ponto.exemploRotulo": "Ex.: Chegada ao hangar",
  "ponto.observacao": "Observação",
  "ponto.observacaoOpcional": "Observação (opcional)",
  "ponto.obrigatorio": "Obrigatório",
  "ponto.opcional": "Opcional",
  "ponto.fila.aguardando_um": "1 registro aguardando envio. Será enviado assim que houver sinal.",
  "ponto.fila.aguardando_varios": "{n} registros aguardando envio. Serão enviados assim que houver sinal.",
  "ponto.fila.descartado_um": "1 registro guardado não pôde ser enviado e saiu da fila. Avise o RH para lançar o horário manualmente.",
  "ponto.fila.descartado_varios": "{n} registros guardados não puderam ser enviados e saíram da fila. Avise o RH para lançar os horários manualmente.",

  "permissao.camera.titulo": "Permissão da câmera",
  "permissao.camera.explicacao":
    "O reconhecimento facial é o que comprova que foi você quem bateu o ponto. Sem acesso à câmera, o registro não pode ser feito.",
  "permissao.camera.permitir": "Permitir câmera",
  "permissao.local.titulo": "Permissão de localização",
  "permissao.local.explicacao":
    "A localização confirma que você está no local de trabalho. Ela é usada apenas no momento da batida — o app não acompanha seus deslocamentos.",
  "permissao.local.android":
    "No Android, esta permissão também é o que libera a leitura dos beacons e da rede Wi-Fi do local.",
  "permissao.local.permitir": "Permitir localização",

  "cadastro.verificandoCamera": "Verificando a câmera…",
  "cadastro.titulo": "Cadastre seu rosto",
  "cadastro.tituloPermissao": "Cadastro do seu rosto",
  "cadastro.explicacaoCamera":
    "Para cadastrar seu rosto, o aplicativo precisa da câmera. Ela é usada só neste cadastro e no momento de bater o ponto.",
  "cadastro.contador": "Foto {atual} de {total} — {passo}",
  "cadastro.passo1.titulo": "Olhando para a câmera",
  "cadastro.passo1.instrucao":
    "Rosto centralizado, luz no rosto e sem boné ou óculos escuros.",
  "cadastro.passo2.titulo": "Um pouco mais perto",
  "cadastro.passo2.instrucao":
    "Aproxime o celular até o rosto ocupar quase todo o círculo.",
  "cadastro.passo3.titulo": "Expressão natural",
  "cadastro.passo3.instrucao":
    "Afaste de novo e relaxe o rosto, como você estaria no dia a dia.",
  "cadastro.tirarFoto": "Tirar foto",
  "cadastro.concluir": "Concluir cadastro",
  "cadastro.enviando": "Enviando…",
  "cadastro.recomecar": "Recomeçar",
  "cadastro.falhou": "Não foi possível cadastrar seu rosto.",
  "cadastro.poucasFotos": "São necessárias ao menos {minimo} fotos.",
  "cadastro.fotoSumiu": "Uma das fotos não está mais no aparelho.",

  "termo.titulo": "Como seus dados são usados",
  "termo.imagem.titulo": "Sua imagem",
  "termo.imagem.corpo":
    "No momento de bater o ponto, o aplicativo tira uma foto do seu rosto e a compara com as fotos que você cadastrou com o RH. A comparação acontece no servidor da empresa e serve apenas para confirmar que foi você quem registrou o ponto.",
  "termo.local.titulo": "Sua localização",
  "termo.local.corpo1":
    "No mesmo momento, o aplicativo verifica se você está no local de trabalho — pelos beacons instalados, pela rede Wi-Fi da empresa ou pelo GPS.",
  "termo.local.destaque": "apenas quando você bate o ponto",
  "termo.local.corpo2":
    "Isso acontece {destaque}. O aplicativo não acompanha seus deslocamentos e não coleta nada em segundo plano.",
  "termo.direitos.titulo": "Seus direitos",
  "termo.direitos.corpo1":
    "Você pode pedir ao RH, a qualquer momento, para ver os dados que a empresa tem sobre você, corrigi-los ou revogar este consentimento.",
  "termo.direitos.corpo2":
    "Revogar impede o uso do ponto por reconhecimento facial — nesse caso, combine com o RH outra forma de registrar sua jornada.",
  "termo.aceite":
    "Li e concordo com o uso da minha imagem e da minha localização para registro de ponto.",
  "termo.versao": "Termo versão {versao}",
  "termo.continuar": "Continuar",

  "diag.titulo": "Diagnóstico do local",
  "diag.varrer": "Varrer sinais",
  "diag.procurando": "Procurando…",
  "diag.varreduraCrua": "Varredura crua (12s)",
  "diag.varrerDeNovo": "Varrer de novo (12s, cru)",
  "diag.compararParametros": "Comparar parâmetros (2 × 8s)",
  "diag.atualizarCadastro": "Atualizar cadastro do local",
  "diag.falhaVarrer": "Falha ao varrer os sinais.",
  "diag.falhaAtualizar":
    "Não foi possível atualizar — sem rede? O cache anterior segue valendo.",
  "diag.resumoCadastro":
    "{locais} local(is), {beacons} beacon(s) cadastrado(s)",
  "diag.resumoUuids": " · {uuids} UUID(s) de iBeacon para procurar",
  "diag.semNome": "(sem nome)",
  "diag.semBssid": "BSSID não disponível",
  "diag.nenhumAnuncio": "Nenhum anúncio de beacon entre eles",
  "diag.nenhum": "Nenhum",
  "diag.filtrar": "Filtrar por MAC, nome ou bytes do anúncio",
  "diag.toqueParaCopiar": "Toque para copiar",
  "diag.toqueParaCopiarMac": "Toque para copiar o MAC",
  "diag.copiado": "Copiado!",
  "diag.macCopiado": "MAC copiado!",
  "diag.enderecoMac": "ENDEREÇO MAC",
  "diag.anuncios": "{n} anúncio(s)",
  "diag.macPublico": "público (fixo)",
  "diag.macFixoOuPublico": "fixo, ou público",
  "diag.semPermissaoBluetooth": "Sem permissão de Bluetooth",
  "diag.legacyNaoEACausa":
    "Nenhum beacon reconhecido em nenhuma das duas passadas — o parâmetro legacy não é a causa. O anúncio não está chegando ao app.",

  "historico.titulo": "Meus registros",
  "historico.vazio": "Nenhum registro ainda.",
  "historico.falhaCarregar": "Falha ao carregar",
  "historico.porQueConferencia": "por que meu ponto está em conferência?",

  "tipo.in": "Entrada",
  "tipo.out": "Saída",
  "tipo.intermediate": "Durante o dia",
  "tipo.break_start": "Início do intervalo",
  "tipo.break_end": "Fim do intervalo",

  "status.approved": "Aprovado",
  "status.pending_review": "Em conferência",
  "status.rejected": "Rejeitado",

  "metodo.beacon": "Beacon do local",
  "metodo.wifi": "Wi-Fi do local",
  "metodo.gps": "GPS",
  "metodo.none": "Sem sinal de local",

  "sinal.bluetoothDesligado":
    "Bluetooth desligado — ligue para detectar os beacons do local.",
  "sinal.semPermissaoBluetooth": "Permissão de Bluetooth negada.",
  "sinal.semPermissaoLocalizacao": "Permissão de localização negada.",
  "sinal.wifiNaoIdentificado":
    "Rede Wi-Fi não identificada — verifique a permissão de localização.",
  "sinal.wifiSemEntitlement":
    "Este iPhone não consegue ler o nome da rede Wi-Fi. Beacons e GPS continuam funcionando.",
  "sinal.gpsIndisponivel": "Não foi possível obter sua localização.",
  "sinal.gpsDemorou": "Não foi possível obter a localização a tempo.",
  "sinal.falhaVarredura": "Falha na varredura Bluetooth.",
  "sinal.nenhum": "Nenhum sinal de localização detectado",
  "sinal.verificandoWifi": "Verificando a rede Wi-Fi…",
  "sinal.obtendoLocalizacao": "Obtendo a localização…",
  "sinal.faltaLocalParaBle":
    "Falta a permissão de localização. O Android a exige para entregar os anúncios dos beacons — sem ela a varredura acha celulares e fones, mas nenhum beacon.",
  "sinal.libereLocalNosAjustes":
    " Libere em Ajustes → Aplicativos → Waypoint → Permissões → Localização.",
  "sinal.bluetoothNegadoAjustes":
    "Permissão de Bluetooth negada. Libere em Ajustes → Aplicativos → Waypoint → Permissões.",
  "sinal.bluetoothNegado":
    "Sem permissão de Bluetooth não é possível detectar os beacons do local.",
  "sinal.androidLocalLiberaBeacon":
    "Nesta versão do Android, a permissão de localização é o que libera a leitura dos beacons.",
  "sinal.semIBeaconCadastrado":
    "Nenhum iBeacon cadastrado neste local. No iPhone é preciso conhecer o UUID de antemão — o iOS não varre iBeacon genericamente.",
  "sinal.iBeaconIndisponivel": "Leitura de iBeacon indisponível nesta versão do app.",
  "sinal.iosSemPermissaoLocal":
    "Sem permissão de localização, o iPhone não entrega os beacons. Libere em Ajustes → Waypoint → Localização.",

  "erro.semResposta": "O servidor não respondeu. Verifique sua conexão.",
  "erro.sessaoExpirada": "Sua sessão expirou. Entre novamente.",
  "erro.inesperado": "Algo deu errado. Tente de novo.",
  "erro.httpGenerico": "Falha na comunicação (HTTP {status})",
  "erro.semConexaoServidor": "Sem conexão com o servidor",
  "erro.falhaEnvio": "Falha no envio",
  "erro.fotoSumiuDaBatida": "A foto desta batida não está mais no aparelho.",
  "campo.observacaoObrigatoria": "Escreva uma observação para continuar.",
  "campo.tipoObrigatorio": "Escolha o tipo da batida para continuar.",
};

export const dicionario: Record<Idioma, Record<Chave, string>> = { en, pt };
