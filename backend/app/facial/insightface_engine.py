"""Engine real: ArcFace, via InsightFace sobre onnxruntime.

O import de `insightface` e `cv2` e preguicoso de proposito. Essas libs pesam
~1 GB e nao estao na imagem de desenvolvimento; se fossem importadas no topo,
este modulo nao carregaria e derrubaria o `app.facial` inteiro junto — mesmo
para quem so quer usar a engine stub.

O modelo (buffalo_l, ~300 MB) tambem nao vai na imagem: e baixado no primeiro
uso para um volume nomeado. Empacota-lo triplicaria o tamanho da imagem e
tornaria cada deploy uma transferencia de 1,3 GB (risco R5).
"""

import threading
from typing import TYPE_CHECKING, Any

from app.facial.base import (
    BoundingBox,
    DetectedFace,
    FaceEmbedding,
    FaceEngine,
    FaceQuality,
)
from app.facial.errors import (
    EngineUnavailableError,
    MultipleFacesError,
    NoFaceDetectedError,
)
from app.facial.imaging import decode_rgb, inspect_image
from app.facial.quality import assess_quality

if TYPE_CHECKING:
    import numpy as np

# buffalo_l: pacote padrao do InsightFace com deteccao (SCRFD) e
# reconhecimento (ArcFace R100) treinado em WebFace600K. Produz 512 dimensoes.
DEFAULT_MODEL = "buffalo_l"
EMBEDDING_DIM = 512

# Resolucao de trabalho do detector. 640 equilibra achar rosto pequeno com
# custo de CPU; abaixo disso o detector comeca a perder rosto de longe.
DETECTION_SIZE = (640, 640)

# Tamanho canonico para medir nitidez. 112 e o mesmo recorte que o ArcFace usa
# internamente — a resolucao em que o detalhe do rosto de fato importa.
SHARPNESS_CROP_SIZE = 112


class InsightFaceEngine(FaceEngine):
    name = "insightface"
    version = DEFAULT_MODEL
    embedding_dim = EMBEDDING_DIM

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        *,
        detection_size: tuple[int, int] = DETECTION_SIZE,
        providers: list[str] | None = None,
    ) -> None:
        self.version = model_name
        self._model_name = model_name
        self._detection_size = detection_size
        self._providers = providers or ["CPUExecutionProvider"]
        self._app: Any | None = None
        # A carga do modelo demora alguns segundos e nao e reentrante; o lock
        # impede que duas requisicoes simultaneas iniciem duas cargas.
        self._lock = threading.Lock()

    # ---- Carga preguicosa ----

    def _ensure_loaded(self) -> Any:
        if self._app is not None:
            return self._app

        with self._lock:
            if self._app is not None:  # outra thread carregou enquanto esperavamos
                return self._app
            self._app = self._build_app()
            return self._app

    def _build_app(self) -> Any:
        try:
            from insightface.app import FaceAnalysis
        except ImportError as exc:
            raise EngineUnavailableError(
                "insightface nao esta instalado. Use a imagem com "
                "requirements-facial.txt ou configure FACE_ENGINE=stub."
            ) from exc

        try:
            analysis = FaceAnalysis(name=self._model_name, providers=self._providers)
            analysis.prepare(ctx_id=0, det_size=self._detection_size)
        except Exception as exc:
            raise EngineUnavailableError(
                f"Falha ao carregar o modelo {self._model_name}: {exc}"
            ) from exc

        return analysis

    def warmup(self) -> None:
        """Forca a carga do modelo.

        Chamar no start da aplicacao para que o primeiro funcionario do dia nao
        pague os segundos de inicializacao ao bater ponto.
        """
        self._ensure_loaded()

    # ---- Inferencia ----

    def detect(self, image: bytes) -> list[DetectedFace]:
        info = inspect_image(image)
        frame = self._to_bgr(image)
        faces = self._ensure_loaded().get(frame)

        return [
            DetectedFace(
                box=self._to_box(face),
                detection_score=float(face.det_score),
                quality=self._quality_for(face, frame, info.width, info.height),
            )
            for face in faces
        ]

    def extract_embedding(self, image: bytes) -> FaceEmbedding:
        info = inspect_image(image)
        frame = self._to_bgr(image)
        faces = self._ensure_loaded().get(frame)

        if not faces:
            raise NoFaceDetectedError("Nenhum rosto identificado na imagem")
        if len(faces) > 1:
            raise MultipleFacesError(
                f"{len(faces)} rostos na imagem; e preciso exatamente um"
            )

        face = faces[0]
        quality = self._quality_for(face, frame, info.width, info.height)

        return FaceEmbedding(
            # `normed_embedding` ja vem com norma L2 = 1, que e o que mantem os
            # scores de cosseno comparaveis entre fotos.
            vector=tuple(float(value) for value in face.normed_embedding),
            model_name=self.name,
            model_version=self.version,
            quality=quality,
            box=self._to_box(face),
        )

    # ---- Auxiliares ----

    def _to_bgr(self, image: bytes) -> "np.ndarray":
        """Converte os bytes para o array BGR que o InsightFace espera.

        BGR, e nao RGB: e a convencao do OpenCV, que o InsightFace herdou.
        Inverter isso degrada silenciosamente o reconhecimento, sem erro algum.
        """
        import numpy as np

        rgb = np.asarray(decode_rgb(image), dtype=np.uint8)
        # `ascontiguousarray` porque a inversao de canais gera uma view com
        # stride negativo, que o onnxruntime nao aceita.
        return np.ascontiguousarray(rgb[:, :, ::-1])

    def _to_box(self, face: Any) -> BoundingBox:
        x1, y1, x2, y2 = (int(value) for value in face.bbox)
        return BoundingBox(x=x1, y=y1, width=max(x2 - x1, 0), height=max(y2 - y1, 0))

    def _quality_for(
        self, face: Any, frame: "np.ndarray", image_width: int, image_height: int
    ) -> FaceQuality:
        box = self._to_box(face)
        return assess_quality(
            image_width=image_width,
            image_height=image_height,
            face_box=box,
            sharpness=self._sharpness(frame, box),
            detection_score=float(face.det_score),
        )

    def _sharpness(self, frame: "np.ndarray", box: BoundingBox) -> float:
        """Nitidez do rosto: variancia do laplaciano, normalizada.

        Duas normalizacoes, e as duas sao necessarias:

        **Tamanho.** A variancia do laplaciano cai quando a mesma imagem e
        ampliada — a borda se espalha por mais pixels. Sem redimensionar para
        um tamanho canonico, a metrica mede resolucao e nao foco: medido aqui,
        o MESMO rosto a 1,5x do tamanho passava de 220 para 59, cruzando o
        limiar sem a foto ter piorado em nada.

        **Contraste.** A variancia tambem cai com pouca luz, porque as bordas
        ficam menos marcadas. Equalizar o histograma separa "sem foco" de
        "mal iluminado" — a segunda e recuperavel, a primeira nao.

        Medida so no recorte do rosto: fundo com textura (grade, parede de
        tijolo) inflaria a nitidez de uma selfie tremida.
        """
        import cv2

        crop = frame[
            max(box.y, 0) : box.y + box.height,
            max(box.x, 0) : box.x + box.width,
        ]
        if crop.size == 0:
            return 0.0

        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        canonico = cv2.resize(
            gray, (SHARPNESS_CROP_SIZE, SHARPNESS_CROP_SIZE), interpolation=cv2.INTER_AREA
        )
        return float(cv2.Laplacian(cv2.equalizeHist(canonico), cv2.CV_64F).var())
