"""Avaliacao da qualidade de uma foto de rosto.

Funcao pura de proposito: recebe medidas ja extraidas (tamanho do rosto,
nitidez, confianca da deteccao) em vez de pixels. Assim a regra de aceitacao
e testavel sem carregar modelo nenhum, e a mesma regra vale para qualquer
engine — o que muda entre elas e so como as medidas sao obtidas.
"""

from dataclasses import dataclass

from app.facial.base import BoundingBox, FaceQuality

# Rosto menor que isso perde detalhe demais para gerar embedding confiavel.
# ArcFace trabalha com recorte de 112x112, entao abaixo disso e interpolacao.
MIN_FACE_PIXELS = 80

# Fracao minima da imagem ocupada pelo rosto. Pega o caso do funcionario
# fotografando de longe, em que o rosto ate tem pixels suficientes mas vem
# cercado de fundo irrelevante.
MIN_FACE_RATIO = 0.02

# Variancia do laplaciano. Abaixo de ~60 a foto esta visivelmente tremida ou
# desfocada; e a metrica classica de nitidez e barata de calcular.
MIN_SHARPNESS = 60.0

MIN_DETECTION_SCORE = 0.60


@dataclass(frozen=True)
class QualityThresholds:
    """Limiares de aceitacao, para poderem variar por tenant no futuro."""

    min_face_pixels: int = MIN_FACE_PIXELS
    min_face_ratio: float = MIN_FACE_RATIO
    min_sharpness: float = MIN_SHARPNESS
    min_detection_score: float = MIN_DETECTION_SCORE


DEFAULT_THRESHOLDS = QualityThresholds()


def assess_quality(
    *,
    image_width: int,
    image_height: int,
    face_box: BoundingBox,
    sharpness: float,
    detection_score: float,
    thresholds: QualityThresholds = DEFAULT_THRESHOLDS,
) -> FaceQuality:
    """Pontua a foto de 0 a 1 e lista o que reprovou.

    O score serve para ordenar templates (na hora de escolher os melhores) e
    para explicar depois por que um match ficou fraco. A lista de problemas e
    o que vira orientacao na tela: dizer "foto tremida" e util, dizer
    "qualidade 0.31" nao e.
    """
    issues: list[str] = []

    smaller_side = min(face_box.width, face_box.height)
    if smaller_side < thresholds.min_face_pixels:
        issues.append("face_too_small")

    image_area = image_width * image_height
    face_ratio = (face_box.area / image_area) if image_area > 0 else 0.0
    if face_ratio < thresholds.min_face_ratio:
        issues.append("face_too_far")

    if sharpness < thresholds.min_sharpness:
        issues.append("blurry")

    if detection_score < thresholds.min_detection_score:
        issues.append("low_detection_confidence")

    if _is_cropped(face_box, image_width, image_height):
        issues.append("face_cropped")

    score = _compute_score(
        smaller_side=smaller_side,
        face_ratio=face_ratio,
        sharpness=sharpness,
        detection_score=detection_score,
        thresholds=thresholds,
    )

    return FaceQuality(
        score=score,
        sharpness=sharpness,
        face_ratio=face_ratio,
        detection_score=detection_score,
        issues=tuple(issues),
    )


def _is_cropped(box: BoundingBox, image_width: int, image_height: int) -> bool:
    """Rosto encostado na borda provavelmente esta cortado.

    Meio rosto gera embedding que parece valido mas nao representa a pessoa —
    pior que rejeitar, porque contamina a base silenciosamente.
    """
    margin = 2
    return (
        box.x <= margin
        or box.y <= margin
        or (box.x + box.width) >= (image_width - margin)
        or (box.y + box.height) >= (image_height - margin)
    )


def _compute_score(
    *,
    smaller_side: int,
    face_ratio: float,
    sharpness: float,
    detection_score: float,
    thresholds: QualityThresholds,
) -> float:
    """Media ponderada dos fatores, cada um saturando no dobro do limiar.

    Saturar evita que uma foto com nitidez excepcional compense um rosto
    pequeno demais: os fatores precisam ser todos razoaveis, e nao um deles
    excelente.
    """
    size_factor = _saturating_ratio(smaller_side, thresholds.min_face_pixels)
    ratio_factor = _saturating_ratio(face_ratio, thresholds.min_face_ratio)
    sharpness_factor = _saturating_ratio(sharpness, thresholds.min_sharpness)
    confidence_factor = min(detection_score, 1.0)

    score = (
        0.30 * size_factor
        + 0.15 * ratio_factor
        + 0.30 * sharpness_factor
        + 0.25 * confidence_factor
    )
    return round(max(0.0, min(1.0, score)), 4)


def _saturating_ratio(value: float, threshold: float) -> float:
    """Normaliza `value` para 0..1, chegando a 1 no dobro do limiar."""
    if threshold <= 0:
        return 1.0
    return min(value / (2 * threshold), 1.0)
