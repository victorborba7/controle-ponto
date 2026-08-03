"""Erros do modulo facial.

Separados por causa porque cada um vira uma orientacao diferente na tela do
funcionario: "nenhum rosto" pede reenquadrar, "foto tremida" pede firmar a
mao, "mais de um rosto" pede se afastar de quem esta atras.

Cada classe carrega a *chave* da mensagem, nao o texto: quem levanta o erro
esta no meio do processamento de imagem e nao faz ideia do idioma de quem
enviou a foto. Ver `app.core.messages`.
"""

from app.core.messages import Msg


class FacialError(Exception):
    """Base de todas as falhas do reconhecimento facial."""

    # Chave da mensagem exibida ao usuario final. As subclasses sobrescrevem.
    chave: Msg = Msg.IMAGEM_ILEGIVEL


class ImageDecodeError(FacialError):
    chave = Msg.IMAGEM_INVALIDA


class ImageTooLargeError(FacialError):
    chave = Msg.IMAGEM_GRANDE_DEMAIS


class NoFaceDetectedError(FacialError):
    chave = Msg.NENHUM_ROSTO


class MultipleFacesError(FacialError):
    chave = Msg.VARIOS_ROSTOS


class LowQualityImageError(FacialError):
    """Rosto encontrado, mas fraco demais para virar template confiavel."""

    chave = Msg.QUALIDADE_INSUFICIENTE

    def __init__(self, message: str, issues: tuple[str, ...] = ()) -> None:
        super().__init__(message)
        self.issues = issues


class EngineUnavailableError(FacialError):
    """A engine configurada nao pode ser carregada (dependencia ou modelo ausente)."""

    chave = Msg.RECONHECIMENTO_INDISPONIVEL
