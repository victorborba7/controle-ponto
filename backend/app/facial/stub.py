"""Engine de reconhecimento falsa, para desenvolvimento e testes.

Existe porque a engine real pesa ~1 GB em dependencias mais ~300 MB de modelo.
Sem uma substituta, toda a suite de testes das etapas seguintes (cadastro,
bater ponto, painel) ficaria refem desse download.

**Ficcao que ela implementa:** a identidade de um "rosto" e a cor dominante da
imagem. Imagens de cor parecida sao a mesma pessoa; cores distantes sao pessoas
distintas. Assim um teste monta cenarios de forma explicita:

    imagem_solida((200, 30, 30))          -> pessoa A
    imagem_solida((205, 35, 28))          -> pessoa A, outra foto
    imagem_solida((30, 30, 200))          -> pessoa B
    imagem_solida((0, 0, 0))              -> nenhum rosto (cor escura = fundo)
    imagem_faixas([(200,30,30), (30,30,200)]) -> duas pessoas no quadro

A identidade e continua, sem faixas de corte: cores proximas geram embeddings
proximos e cores dominadas por canais diferentes geram embeddings quase
ortogonais. Uma versao anterior agrupava cores em baldes fixos e tinha um
defeito sutil — duas fotos "da mesma pessoa" viravam pessoas diferentes ao
cruzarem a fronteira de um balde.

Isto NAO testa o modelo — testa a canalizacao em volta dele: qualidade,
limiares, escolha do melhor template, tratamento de erro. A capacidade do
ArcFace de separar rostos de verdade e verificada em
`tests/test_facial_real_model.py`, que roda com o modelo baixado.
"""

import hashlib
import math
import struct
from collections.abc import Sequence

from PIL import Image

from app.facial.base import BoundingBox, DetectedFace, FaceEmbedding, FaceEngine
from app.facial.errors import MultipleFacesError, NoFaceDetectedError
from app.facial.imaging import decode_rgb, inspect_image
from app.facial.quality import assess_quality

# Abaixo deste nivel em todos os canais a cor e fundo, nao pessoa.
_BACKGROUND_LEVEL = 32

# Expoente que "afia" a cor antes de virar identidade. Elevar os canais a
# quarta potencia faz o canal dominante engolir os outros: (200,30,30) vira
# praticamente (1, 0, 0). Sem isso, duas cores com o mesmo cinza de fundo
# ficariam parecidas demais e a separacao entre identidades encostaria no
# limiar de decisao.
_IDENTITY_SHARPNESS = 4

# Peso da variacao entre duas fotos da MESMA pessoa. Pequeno de proposito: a
# similaridade fica em torno de 0.99, como entre duas selfies boas de alguem.
_INTRA_IDENTITY_NOISE = 0.05

# Acima desta similaridade de cor, duas faixas da imagem sao a mesma pessoa.
_SAME_IDENTITY_COSINE = 0.90


class StubFaceEngine(FaceEngine):
    name = "stub"
    version = "1"
    embedding_dim = 512

    def __init__(self, embedding_dim: int = 512) -> None:
        self.embedding_dim = embedding_dim

    def detect(self, image: bytes) -> list[DetectedFace]:
        info = inspect_image(image)
        identities = self._identities(image)

        faces: list[DetectedFace] = []
        count = len(identities)
        for index in range(count):
            box = self._box_for(index, count, info.width, info.height)
            detection_score = 0.99
            quality = assess_quality(
                image_width=info.width,
                image_height=info.height,
                face_box=box,
                sharpness=self._sharpness_for(image),
                detection_score=detection_score,
            )
            faces.append(
                DetectedFace(box=box, detection_score=detection_score, quality=quality)
            )
        return faces

    def extract_embedding(self, image: bytes) -> FaceEmbedding:
        info = inspect_image(image)
        identities = self._identities(image)

        if not identities:
            raise NoFaceDetectedError("Nenhum rosto na imagem")
        if len(identities) > 1:
            raise MultipleFacesError(f"{len(identities)} rostos na imagem")

        box = self._box_for(0, 1, info.width, info.height)
        quality = assess_quality(
            image_width=info.width,
            image_height=info.height,
            face_box=box,
            sharpness=self._sharpness_for(image),
            detection_score=0.99,
        )

        return FaceEmbedding(
            vector=self._vector_for(identities[0]),
            model_name=self.name,
            model_version=self.version,
            quality=quality,
            box=box,
        )

    # ---- Mecanica interna da ficcao ----

    def _identities(self, image: bytes) -> list[tuple[int, int, int]]:
        """Cores dominantes distintas da imagem, uma por "pessoa".

        Varre faixas verticais e agrupa cores pela direcao afiada. Imagem
        solida da uma identidade, imagem dividida em duas cores da duas,
        imagem escura nao da nenhuma.

        Reamostragem NEAREST e obrigatoria: qualquer interpolacao inventaria
        cores intermediarias na fronteira entre faixas, e cada tom inventado
        viraria uma pessoa a mais no quadro.
        """
        picture = decode_rgb(image).resize((16, 16), Image.Resampling.NEAREST)
        pixels = picture.load()

        identities: list[tuple[int, int, int]] = []
        for column in range(16):
            # Amostra o meio vertical da coluna: e onde estaria o rosto.
            color = pixels[column, 8]
            if max(color) < _BACKGROUND_LEVEL:
                continue

            direction = _color_direction(color)
            ja_vista = any(
                _dot3(direction, _color_direction(known)) >= _SAME_IDENTITY_COSINE
                for known in identities
            )
            if not ja_vista:
                identities.append(color)

        return identities

    def _vector_for(self, color: tuple[int, int, int]) -> tuple[float, ...]:
        """Vetor deterministico e normalizado para uma cor.

        Duas partes somadas:

        - **Identidade** — a direcao da cor projetada numa base ortonormal de
          tres vetores em 512 dimensoes. Continua, sem fronteiras: cores
          proximas geram vetores proximos, cores dominadas por canais
          diferentes geram vetores quase ortogonais.
        - **Variacao** — um ruido derivado da cor exata, com peso pequeno, que
          faz duas fotos da mesma pessoa nao saírem identicas.
        """
        direction = _color_direction(color)
        basis = _identity_basis(self.embedding_dim)

        identity = [
            direction[0] * basis[0][i]
            + direction[1] * basis[1][i]
            + direction[2] * basis[2][i]
            for i in range(self.embedding_dim)
        ]

        seed = f"{color[0]}:{color[1]}:{color[2]}".encode()
        noise = _normalized_vector_from_seed(seed, self.embedding_dim)

        combined = [
            (1.0 - _INTRA_IDENTITY_NOISE) * identity[i] + _INTRA_IDENTITY_NOISE * noise[i]
            for i in range(self.embedding_dim)
        ]
        return _normalize(combined)

    def _sharpness_for(self, image: bytes) -> float:
        """Nitidez ficticia, estavel para a mesma imagem.

        Uma imagem minuscula (<128px) devolve valor abaixo do limiar, o que da
        aos testes um jeito de exercitar o caminho de "foto tremida".
        """
        info = inspect_image(image)
        if min(info.width, info.height) < 128:
            return 10.0
        return 150.0

    def _box_for(
        self, index: int, total: int, image_width: int, image_height: int
    ) -> BoundingBox:
        """Caixa plausivel: rosto centralizado, ou lado a lado se houver varios."""
        slot_width = image_width // max(total, 1)
        face_width = max(int(slot_width * 0.5), 1)
        face_height = max(int(image_height * 0.5), 1)
        x = index * slot_width + (slot_width - face_width) // 2
        y = (image_height - face_height) // 2
        return BoundingBox(x=x, y=y, width=face_width, height=face_height)


def _color_direction(color: tuple[int, int, int]) -> tuple[float, float, float]:
    """Direcao unitaria da cor, com o canal dominante realcado.

    E o que define a identidade: (200,30,30) e (206,36,36) apontam praticamente
    para o mesmo lugar, enquanto (30,30,200) aponta para outro eixo.
    """
    sharpened = [float(channel) ** _IDENTITY_SHARPNESS for channel in color]
    norm = math.sqrt(sum(value * value for value in sharpened))
    if norm == 0.0:
        return (0.0, 0.0, 0.0)
    return (sharpened[0] / norm, sharpened[1] / norm, sharpened[2] / norm)


def _dot3(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _normalize(vector: list[float]) -> tuple[float, ...]:
    norm = math.sqrt(sum(component * component for component in vector))
    if norm == 0.0:
        raise ValueError("Nao e possivel normalizar o vetor nulo")
    return tuple(component / norm for component in vector)


def _identity_basis(dimension: int) -> tuple[tuple[float, ...], ...]:
    """Tres vetores ortonormais fixos em `dimension` dimensoes.

    Ortonormais para que a projecao da direcao da cor preserve os angulos:
    cores ortogonais entre si viram embeddings ortogonais entre si, e a
    similaridade final reflete a similaridade das cores.
    """
    if dimension in _BASIS_CACHE:
        return _BASIS_CACHE[dimension]

    vectors: list[list[float]] = []
    for axis in range(3):
        candidate = list(_normalized_vector_from_seed(f"eixo-{axis}".encode(), dimension))
        # Gram-Schmidt contra os eixos ja fixados.
        for existing in vectors:
            projection = sum(c * e for c, e in zip(candidate, existing, strict=True))
            candidate = [c - projection * e for c, e in zip(candidate, existing, strict=True)]
        vectors.append(list(_normalize(candidate)))

    basis = tuple(tuple(vector) for vector in vectors)
    _BASIS_CACHE[dimension] = basis
    return basis


_BASIS_CACHE: dict[int, tuple[tuple[float, ...], ...]] = {}


def _normalized_vector_from_seed(seed: bytes, dimension: int) -> tuple[float, ...]:
    """Vetor pseudoaleatorio deterministico, com norma L2 igual a 1."""
    raw: list[float] = []
    counter = 0
    while len(raw) < dimension:
        digest = hashlib.sha256(seed + counter.to_bytes(4, "big")).digest()
        # 8 floats por digest: 4 bytes viram um inteiro sem sinal, mapeado
        # para [-1, 1].
        for offset in range(0, 32, 4):
            (value,) = struct.unpack(">I", digest[offset : offset + 4])
            raw.append((value / 0xFFFFFFFF) * 2.0 - 1.0)
        counter += 1

    return _normalize(raw[:dimension])


def stub_image(
    color: tuple[int, int, int],
    *,
    size: tuple[int, int] = (480, 480),
    image_format: str = "PNG",
) -> bytes:
    """Gera uma imagem solida — uma "foto" da pessoa daquela cor.

    Ajudante dos testes, exposto aqui para que a convencao de cores fique
    junto de quem a interpreta.
    """
    return _encode(Image.new("RGB", size, color), image_format)


def stub_image_variant(
    color: tuple[int, int, int],
    *,
    shift: int = 6,
    size: tuple[int, int] = (480, 480),
) -> bytes:
    """Outra foto da MESMA pessoa: mesma cor, levemente deslocada.

    O deslocamento fica dentro do balde de identidade, entao o embedding sai
    parecido mas nao identico — como duas selfies boas da mesma pessoa.
    """
    shifted = tuple(min(255, max(0, channel + shift)) for channel in color)
    return stub_image(shifted, size=size)  # type: ignore[arg-type]


def stub_image_with_faces(
    colors: Sequence[tuple[int, int, int]],
    *,
    size: tuple[int, int] = (480, 480),
) -> bytes:
    """Imagem em faixas verticais — uma pessoa por cor."""
    picture = Image.new("RGB", size, (0, 0, 0))
    band_width = size[0] // max(len(colors), 1)
    for index, color in enumerate(colors):
        for x in range(index * band_width, min((index + 1) * band_width, size[0])):
            for y in range(size[1]):
                picture.putpixel((x, y), color)
    return _encode(picture, "PNG")


def _encode(picture: Image.Image, image_format: str) -> bytes:
    import io

    buffer = io.BytesIO()
    picture.save(buffer, format=image_format)
    return buffer.getvalue()
