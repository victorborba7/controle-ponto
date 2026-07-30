"""Erros do modulo facial.

Separados por causa porque cada um vira uma orientacao diferente na tela do
funcionario: "nenhum rosto" pede reenquadrar, "foto tremida" pede firmar a
mao, "mais de um rosto" pede se afastar de quem esta atras.
"""


class FacialError(Exception):
    """Base de todas as falhas do reconhecimento facial."""

    # Mensagem pronta para exibir ao usuario final. As subclasses sobrescrevem.
    user_message = "Nao foi possivel processar a imagem."


class ImageDecodeError(FacialError):
    user_message = "Imagem invalida ou corrompida."


class ImageTooLargeError(FacialError):
    user_message = "Imagem grande demais."


class NoFaceDetectedError(FacialError):
    user_message = "Nenhum rosto identificado na foto."


class MultipleFacesError(FacialError):
    user_message = "Mais de um rosto na foto. Enquadre apenas voce."


class LowQualityImageError(FacialError):
    """Rosto encontrado, mas fraco demais para virar template confiavel."""

    user_message = "Qualidade da foto insuficiente."

    def __init__(self, message: str, issues: tuple[str, ...] = ()) -> None:
        super().__init__(message)
        self.issues = issues


class EngineUnavailableError(FacialError):
    """A engine configurada nao pode ser carregada (dependencia ou modelo ausente)."""

    user_message = "Servico de reconhecimento indisponivel."
