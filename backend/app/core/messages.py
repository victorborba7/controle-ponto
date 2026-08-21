"""Catalogo das mensagens que chegam a tela de alguem.

## Por que simbolo, e nao o texto no ponto do `raise`

A mesma frase sai em dois clientes (app do funcionario e painel do RH) e em
mais de um idioma. Guardar o texto onde o erro nasce obrigaria o servico a
saber o idioma de quem fez o pedido — que ele nao sabe e nao deveria saber,
porque um servico chamado por um job noturno nao tem requisicao nenhuma.

Entao o servico levanta um simbolo com os parametros; a borda HTTP, que
enxerga o `Accept-Language`, resolve o texto. E o teste passa a afirmar sobre
o simbolo, que e o contrato de verdade — hoje varios testes afirmam sobre
pedacos de frase e quebram quando alguem corrige uma virgula.

## Por que dois idiomas se a operacao e so nos EUA

Ingles e o padrao porque e onde a ferramenta opera. O portugues fica por dois
motivos: o projeto nasceu nele, e um catalogo com um idioma so nao prova que
a estrutura aguenta dois — o segundo idioma e o que revela concatenacao
escondida e ordem de palavra presumida. Espanhol, quando entrar, e um dict a
mais e nenhum arquivo tocado fora daqui.

## Regra ao acrescentar mensagem

Todo idioma precisa da chave: `verificar_catalogo()` roda no teste e falha
com a lista do que faltou. Uma frase que existe so em ingles apareceria em
ingles no meio de uma tela em portugues, sem nenhum aviso.
"""

from enum import StrEnum
from typing import Final

IDIOMA_PADRAO: Final = "en"


class Msg(StrEnum):
    """Chave estavel de cada mensagem.

    O valor e o que vai no `code` de respostas de erro e no que o teste
    afirma. Renomear um valor e mudanca de contrato com os clientes.
    """

    # --- autenticacao e autorizacao -------------------------------------
    CREDENCIAIS_INVALIDAS = "invalid_credentials"
    SESSAO_EXPIRADA = "session_expired"
    SO_PAINEL = "admin_panel_only"
    SO_APP = "employee_app_only"
    SEM_PERMISSAO = "insufficient_permission"
    MUITAS_TENTATIVAS = "too_many_attempts"

    # --- recursos nao encontrados ---------------------------------------
    FUNCIONARIO_NAO_ENCONTRADO = "employee_not_found"
    TEMPLATE_NAO_ENCONTRADO = "face_template_not_found"
    LOCAL_NAO_ENCONTRADO = "site_not_found"
    BEACON_NAO_ENCONTRADO = "beacon_not_found"
    REDE_NAO_ENCONTRADA = "wifi_network_not_found"
    REGISTRO_NAO_ENCONTRADO = "time_entry_not_found"

    # --- imagem ----------------------------------------------------------
    # Duas mensagens parecidas, de camadas diferentes: a da borda HTTP sabe o
    # teto em MB e o diz; a do modulo facial so sabe que a imagem nao coube.
    FOTO_GRANDE_DEMAIS = "photo_too_large"
    FOTO_NOMEADA_GRANDE_DEMAIS = "named_photo_too_large"
    IMAGEM_GRANDE_DEMAIS = "image_too_large"
    IMAGEM_ILEGIVEL = "image_unreadable"
    IMAGEM_INVALIDA = "image_invalid"
    NENHUM_ROSTO = "no_face_detected"
    VARIOS_ROSTOS = "multiple_faces"
    QUALIDADE_INSUFICIENTE = "low_image_quality"
    RECONHECIMENTO_INDISPONIVEL = "recognition_unavailable"

    # --- batida de ponto -------------------------------------------------
    ROSTO_NAO_CADASTRADO = "face_not_enrolled"
    ROSTO_JA_CADASTRADO = "face_already_enrolled"
    SAIDA_SEM_ENTRADA = "clock_out_without_clock_in"
    LEMBRETE_TITULO = "reminder_title"
    LEMBRETE_CORPO = "reminder_body"
    ROSTO_NAO_RECONHECIDO = "face_not_recognized"
    CADASTRO_FACIAL_DESATUALIZADO = "face_enrollment_outdated"
    APARELHO_DESVINCULADO = "device_unlinked"
    FACA_LOGIN_DE_NOVO = "sign_in_again"
    BATIDA_REPETIDA = "punch_too_soon"
    PONTO_REGISTRADO = "punch_recorded"
    PONTO_EM_CONFERENCIA = "punch_pending_review"
    PONTO_JA_REGISTRADO = "punch_already_recorded"
    REGISTRO_NAO_PENDENTE = "entry_not_pending"
    FOTO_INDISPONIVEL = "entry_photo_unavailable"

    # --- cadastro biometrico (tela do RH) ---------------------------------
    CONSENTIMENTO_OBRIGATORIO = "consent_required"
    FOTOS_DE_MENOS = "too_few_photos"
    FOTOS_DE_MAIS = "too_many_photos"
    POUCAS_FOTOS_COM_QUALIDADE = "not_enough_usable_photos"
    PESSOAS_DIFERENTES = "photos_of_different_people"

    # Orientacao por problema de qualidade. Existe porque "qualidade
    # insuficiente" nao diz a ninguem se deve acender a luz, chegar mais perto
    # ou firmar a mao — e e a unica coisa que o RH le quando o lote e recusado.
    ORIENTACAO_DESFOCADA = "guidance_blurry"
    ORIENTACAO_ROSTO_PEQUENO = "guidance_face_too_small"
    ORIENTACAO_ROSTO_LONGE = "guidance_face_too_far"
    ORIENTACAO_ROSTO_CORTADO = "guidance_face_cropped"
    ORIENTACAO_POUCA_CONFIANCA = "guidance_low_detection_confidence"

    # --- configuracao de batida ------------------------------------------
    APP_DESATUALIZADO = "app_outdated"
    OBSERVACAO_NAO_ACEITA = "note_not_accepted"
    OBSERVACAO_OBRIGATORIA = "note_required"
    OBSERVACAO_LONGA = "note_too_long"
    TIPO_NAO_ACEITO = "label_not_accepted"
    TIPO_OBRIGATORIO = "label_required"
    TIPO_LONGO = "label_too_long"
    TIPO_INEXISTENTE = "label_no_longer_available"


# Cada texto e uma frase completa: nada de montar por concatenacao, porque a
# ordem das partes muda de idioma para idioma. Parametros entram por `format`.
CATALOGO: Final[dict[str, dict[Msg, str]]] = {
    "en": {
        Msg.CREDENCIAIS_INVALIDAS: "Invalid credentials.",
        Msg.SESSAO_EXPIRADA: "Your session has expired. Please sign in again.",
        Msg.SO_PAINEL: "This resource is restricted to the admin panel.",
        Msg.SO_APP: "This resource is restricted to the employee app.",
        Msg.SEM_PERMISSAO: "You do not have permission for this operation.",
        Msg.MUITAS_TENTATIVAS: (
            "Too many failed sign-in attempts. Try again in about {minutes} min."
        ),
        Msg.FUNCIONARIO_NAO_ENCONTRADO: "Employee not found.",
        Msg.TEMPLATE_NAO_ENCONTRADO: "Face template not found.",
        Msg.LOCAL_NAO_ENCONTRADO: "Site not found.",
        Msg.BEACON_NAO_ENCONTRADO: "Beacon not found.",
        Msg.REDE_NAO_ENCONTRADA: "Wi-Fi network not found.",
        Msg.REGISTRO_NAO_ENCONTRADO: "Time entry not found.",
        Msg.FOTO_GRANDE_DEMAIS: "The photo exceeds the {limit} MB limit.",
        Msg.FOTO_NOMEADA_GRANDE_DEMAIS: ("Photo {filename} exceeds the {limit} MB limit."),
        Msg.IMAGEM_GRANDE_DEMAIS: "The image is too large.",
        Msg.IMAGEM_ILEGIVEL: "We could not process the image.",
        Msg.IMAGEM_INVALIDA: "The image is invalid or corrupted.",
        Msg.NENHUM_ROSTO: "No face found in the photo.",
        Msg.VARIOS_ROSTOS: "More than one face in the photo. Frame only yourself.",
        Msg.QUALIDADE_INSUFICIENTE: "The photo quality is not good enough.",
        Msg.RECONHECIMENTO_INDISPONIVEL: "Face recognition is unavailable.",
        Msg.ROSTO_NAO_CADASTRADO: (
            "Your face has not been enrolled yet. Enroll it in the app to start "
            "clocking in."
        ),
        Msg.ROSTO_JA_CADASTRADO: (
            "Your face is already enrolled. Contact HR to have it redone."
        ),
        Msg.SAIDA_SEM_ENTRADA: (
            "You have not clocked in today, so there is no shift to close."
        ),
        Msg.LEMBRETE_TITULO: "Time to check in",
        Msg.LEMBRETE_CORPO: (
            "You clocked in {horas}h ago. Record what you are working on."
        ),
        Msg.ROSTO_NAO_RECONHECIDO: (
            "We did not recognize your face. Try again with better lighting."
        ),
        Msg.CADASTRO_FACIAL_DESATUALIZADO: (
            "Your face enrollment needs to be redone. Please see HR."
        ),
        Msg.APARELHO_DESVINCULADO: ("This device has been unlinked. Please see HR."),
        Msg.FACA_LOGIN_DE_NOVO: "Please sign in again on the app.",
        Msg.BATIDA_REPETIDA: "You just clocked in. Please wait a moment.",
        Msg.PONTO_REGISTRADO: "Time entry recorded.",
        Msg.PONTO_EM_CONFERENCIA: "Time entry recorded and sent to HR for review.",
        Msg.PONTO_JA_REGISTRADO: "This time entry had already been recorded.",
        Msg.REGISTRO_NAO_PENDENTE: ("This entry is not pending review (current status: {status})."),
        Msg.FOTO_INDISPONIVEL: "The photo for this entry is no longer available.",
        Msg.CONSENTIMENTO_OBRIGATORIO: (
            "Face enrollment requires the employee's explicit written consent."
        ),
        Msg.FOTOS_DE_MENOS: (
            "Send at least {minimum} photos ({quantity} received). Several photos "
            "absorb changes in lighting, glasses and facial hair without a re-enrollment."
        ),
        Msg.FOTOS_DE_MAIS: "Send at most {maximum} photos ({quantity} received).",
        Msg.POUCAS_FOTOS_COM_QUALIDADE: (
            "Only {accepted} of {total} photos are usable; enrollment requires "
            "{minimum}. Problems: {problems}"
        ),
        Msg.PESSOAS_DIFERENTES: (
            "The photos do not appear to be of the same person " "(lowest similarity {score})."
        ),
        Msg.ORIENTACAO_DESFOCADA: "out of focus, hold the camera steady",
        Msg.ORIENTACAO_ROSTO_PEQUENO: "face too small, move closer",
        Msg.ORIENTACAO_ROSTO_LONGE: "too far away, the face should fill much of the frame",
        Msg.ORIENTACAO_ROSTO_CORTADO: "face cut off, center it in the frame",
        Msg.ORIENTACAO_POUCA_CONFIANCA: "improve the lighting and look at the camera",
        Msg.APP_DESATUALIZADO: (
            "This time clock does not accept a note or an entry type. " "Please update the app."
        ),
        Msg.OBSERVACAO_NAO_ACEITA: "This time clock does not accept a note.",
        Msg.OBSERVACAO_OBRIGATORIA: "Enter a note to continue.",
        Msg.OBSERVACAO_LONGA: "The note is longer than {limit} characters.",
        Msg.TIPO_NAO_ACEITO: "This time clock does not accept an entry type.",
        Msg.TIPO_OBRIGATORIO: "Choose the entry type to continue.",
        Msg.TIPO_LONGO: "The entry type is longer than {limit} characters.",
        Msg.TIPO_INEXISTENTE: ("That entry type no longer exists. Update the app and try again."),
    },
    "pt": {
        Msg.CREDENCIAIS_INVALIDAS: "Credenciais inválidas.",
        Msg.SESSAO_EXPIRADA: "Sua sessão expirou. Entre novamente.",
        Msg.SO_PAINEL: "Este recurso é restrito ao painel administrativo.",
        Msg.SO_APP: "Este recurso é restrito ao app do funcionário.",
        Msg.SEM_PERMISSAO: "Você não tem permissão para esta operação.",
        Msg.MUITAS_TENTATIVAS: (
            "Tentativas de entrada demais. Tente de novo em cerca de {minutes} min."
        ),
        Msg.FUNCIONARIO_NAO_ENCONTRADO: "Funcionário não encontrado.",
        Msg.TEMPLATE_NAO_ENCONTRADO: "Cadastro facial não encontrado.",
        Msg.LOCAL_NAO_ENCONTRADO: "Local não encontrado.",
        Msg.BEACON_NAO_ENCONTRADO: "Beacon não encontrado.",
        Msg.REDE_NAO_ENCONTRADA: "Rede Wi-Fi não encontrada.",
        Msg.REGISTRO_NAO_ENCONTRADO: "Registro não encontrado.",
        Msg.FOTO_GRANDE_DEMAIS: "A foto passa do limite de {limit} MB.",
        Msg.FOTO_NOMEADA_GRANDE_DEMAIS: ("A foto {filename} passa do limite de {limit} MB."),
        Msg.IMAGEM_GRANDE_DEMAIS: "Imagem grande demais.",
        Msg.IMAGEM_ILEGIVEL: "Não foi possível processar a imagem.",
        Msg.IMAGEM_INVALIDA: "Imagem inválida ou corrompida.",
        Msg.NENHUM_ROSTO: "Nenhum rosto identificado na foto.",
        Msg.VARIOS_ROSTOS: "Mais de um rosto na foto. Enquadre apenas você.",
        Msg.QUALIDADE_INSUFICIENTE: "Qualidade da foto insuficiente.",
        Msg.RECONHECIMENTO_INDISPONIVEL: "Serviço de reconhecimento indisponível.",
        Msg.ROSTO_NAO_CADASTRADO: (
            "Seu rosto ainda não foi cadastrado. Faça o cadastro no aplicativo "
            "para começar a bater ponto."
        ),
        Msg.ROSTO_JA_CADASTRADO: (
            "Seu rosto já está cadastrado. Procure o RH para refazer."
        ),
        Msg.SAIDA_SEM_ENTRADA: (
            "Você ainda não bateu entrada hoje, então não há jornada para encerrar."
        ),
        Msg.LEMBRETE_TITULO: "Hora de registrar",
        Msg.LEMBRETE_CORPO: (
            "Você entrou há {horas}h. Registre o que está fazendo."
        ),
        Msg.ROSTO_NAO_RECONHECIDO: (
            "Não reconhecemos seu rosto. Tente novamente com melhor iluminação."
        ),
        Msg.CADASTRO_FACIAL_DESATUALIZADO: (
            "Seu cadastro facial precisa ser refeito. Procure o RH."
        ),
        Msg.APARELHO_DESVINCULADO: "Este aparelho foi desvinculado. Procure o RH.",
        Msg.FACA_LOGIN_DE_NOVO: "Faça login novamente no aplicativo.",
        Msg.BATIDA_REPETIDA: "Você acabou de bater o ponto. Aguarde um momento.",
        Msg.PONTO_REGISTRADO: "Ponto registrado.",
        Msg.PONTO_EM_CONFERENCIA: "Ponto registrado e enviado para conferência do RH.",
        Msg.PONTO_JA_REGISTRADO: "Este ponto já havia sido registrado.",
        Msg.REGISTRO_NAO_PENDENTE: ("Este registro não está pendente (situação atual: {status})."),
        Msg.FOTO_INDISPONIVEL: "A foto deste registro não está mais disponível.",
        Msg.CONSENTIMENTO_OBRIGATORIO: (
            "O cadastro biométrico exige consentimento explícito e escrito do " "funcionário."
        ),
        Msg.FOTOS_DE_MENOS: (
            "Envie ao menos {minimum} fotos ({quantity} recebidas). Várias fotos "
            "absorvem mudança de luz, óculos e barba sem precisar recadastrar."
        ),
        Msg.FOTOS_DE_MAIS: "Envie no máximo {maximum} fotos ({quantity} recebidas).",
        Msg.POUCAS_FOTOS_COM_QUALIDADE: (
            "Apenas {accepted} de {total} fotos servem; o cadastro exige "
            "{minimum}. Problemas: {problems}"
        ),
        Msg.PESSOAS_DIFERENTES: (
            "As fotos não parecem ser da mesma pessoa " "(menor semelhança {score})."
        ),
        Msg.ORIENTACAO_DESFOCADA: "foto desfocada, firme a câmera",
        Msg.ORIENTACAO_ROSTO_PEQUENO: "rosto pequeno demais, chegue mais perto",
        Msg.ORIENTACAO_ROSTO_LONGE: "muito longe, o rosto precisa ocupar boa parte do quadro",
        Msg.ORIENTACAO_ROSTO_CORTADO: "rosto cortado, centralize no enquadramento",
        Msg.ORIENTACAO_POUCA_CONFIANCA: "melhore a iluminação e olhe para a câmera",
        Msg.APP_DESATUALIZADO: ("Este ponto não aceita observação nem tipo. Atualize o app."),
        Msg.OBSERVACAO_NAO_ACEITA: "Este ponto não aceita observação.",
        Msg.OBSERVACAO_OBRIGATORIA: "Escreva uma observação para continuar.",
        Msg.OBSERVACAO_LONGA: "A observação passa de {limit} caracteres.",
        Msg.TIPO_NAO_ACEITO: "Este ponto não aceita tipo de batida.",
        Msg.TIPO_OBRIGATORIO: "Escolha o tipo da batida para continuar.",
        Msg.TIPO_LONGO: "O tipo da batida passa de {limit} caracteres.",
        Msg.TIPO_INEXISTENTE: (
            "Este tipo de batida não existe mais. Atualize o app e tente de novo."
        ),
    },
}


def idiomas_disponiveis() -> tuple[str, ...]:
    return tuple(CATALOGO)


def negociar_idioma(accept_language: str | None) -> str:
    """Escolhe o idioma a partir do cabecalho `Accept-Language`.

    Implementacao curta de proposito: le a lista, respeita o `q`, e cai no
    padrao. Nao trata subtags regionais separadamente — `pt-BR` e `pt-PT`
    caem ambos em `pt`, que e o certo enquanto nao houver texto que difira
    entre as duas variantes.
    """
    if not accept_language:
        return IDIOMA_PADRAO

    preferencias: list[tuple[float, str]] = []
    for parte in accept_language.split(","):
        pedaco = parte.strip()
        if not pedaco:
            continue

        idioma, _, resto = pedaco.partition(";")
        idioma = idioma.strip().lower()
        if not idioma:
            continue

        peso = 1.0
        if resto.strip().startswith("q="):
            try:
                peso = float(resto.strip()[2:])
            except ValueError:
                peso = 0.0

        # `*` significa "qualquer um serve": nao ganha do padrao.
        if idioma == "*":
            continue

        preferencias.append((peso, idioma.split("-")[0]))

    # `sorted` e estavel, entao empate em `q` preserva a ordem do cabecalho —
    # que e exatamente o desempate que a especificacao pede.
    for _, base in sorted(preferencias, key=lambda p: p[0], reverse=True):
        if base in CATALOGO:
            return base

    return IDIOMA_PADRAO


def traduzir(chave: Msg, idioma: str = IDIOMA_PADRAO, /, **parametros: object) -> str:
    """Resolve o texto de uma chave.

    Idioma desconhecido cai no padrao em vez de estourar: uma mensagem em
    ingles inesperado e ruim, mas um 500 no lugar de um 404 e pior.
    """
    tabela = CATALOGO.get(idioma) or CATALOGO[IDIOMA_PADRAO]
    modelo = tabela.get(chave) or CATALOGO[IDIOMA_PADRAO][chave]
    return modelo.format(**parametros) if parametros else modelo


def verificar_catalogo() -> dict[str, set[Msg]]:
    """Chaves que faltam em cada idioma. Vazio quando esta tudo traduzido.

    Devolve em vez de levantar para o teste conseguir mostrar a lista inteira
    de uma vez — descobrir uma chave faltante por execucao seria tedioso.
    """
    todas = set(Msg)
    faltando = {idioma: todas - set(tabela.keys()) for idioma, tabela in CATALOGO.items()}
    return {idioma: chaves for idioma, chaves in faltando.items() if chaves}
