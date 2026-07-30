"""Verificacao do modelo ArcFace de verdade.

Responde a pergunta que a engine stub nao consegue responder: **o modelo
separa mesmo duas pessoas?** Este e o criterio de pronto da Etapa 3.

Fica fora da suite padrao porque exige a imagem com `requirements-facial.txt`
(~1 GB) e o download do modelo buffalo_l (~300 MB). Pular quando ausente e
deliberado: amarrar o ciclo normal de testes a esse download tornaria cada
execucao lenta demais para ser util.

    docker compose -f docker-compose.yml -f docker-compose.facial.yml \
        exec api pytest tests/test_facial_real_model.py -v
"""

import io

import pytest

from app.facial import MatchOutcome, classify_score
from app.facial.errors import MultipleFacesError, NoFaceDetectedError

insightface = pytest.importorskip(
    "insightface",
    reason="Modelo real ausente. Rode com docker-compose.facial.yml.",
)

# Os mesmos limiares configurados na aplicacao (app/core/config.py).
MATCH_THRESHOLD = 0.40
REVIEW_THRESHOLD = 0.32


@pytest.fixture(scope="module")
def engine():
    """Engine real, carregada uma vez por modulo (o modelo demora a subir)."""
    from app.facial.insightface_engine import InsightFaceEngine

    real_engine = InsightFaceEngine()
    real_engine.warmup()
    return real_engine


@pytest.fixture(scope="module")
def faces() -> list[bytes]:
    """Recortes de rostos distintos, da foto de grupo que o InsightFace embarca.

    Usar a imagem do proprio pacote mantem o teste autocontido — sem baixar
    dataset nem versionar foto de pessoa real no repositorio.
    """
    from insightface.data import get_image
    from PIL import Image

    frame = get_image("t1")  # BGR, numpy
    rgb = Image.fromarray(frame[:, :, ::-1])

    from insightface.app import FaceAnalysis

    detector = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
    detector.prepare(ctx_id=0, det_size=(640, 640))
    detected = detector.get(frame)

    if len(detected) < 2:
        pytest.skip("A imagem de referencia precisa ter ao menos dois rostos")

    recortes: list[bytes] = []
    for face in detected:
        x1, y1, x2, y2 = (int(v) for v in face.bbox)
        # Margem generosa em volta: o detector precisa reencontrar o rosto no
        # recorte, e um corte justo no contorno atrapalha.
        largura, altura = x2 - x1, y2 - y1
        margem_x, margem_y = int(largura * 0.6), int(altura * 0.6)
        caixa = (
            max(x1 - margem_x, 0),
            max(y1 - margem_y, 0),
            min(x2 + margem_x, rgb.width),
            min(y2 + margem_y, rgb.height),
        )
        recorte = rgb.crop(caixa).resize((512, 512))
        buffer = io.BytesIO()
        recorte.save(buffer, format="JPEG", quality=95)
        recortes.append(buffer.getvalue())

    return recortes


def _outra_foto(imagem: bytes) -> bytes:
    """Simula uma segunda foto da mesma pessoa.

    Reduz o brilho e reencoda com compressao mais forte — variacoes que
    acontecem entre uma foto de cadastro e uma selfie batida no hangar. Nao e
    a mesma imagem: os bytes mudam e o modelo processa tudo de novo.

    **Limite deste teste, para nao concluir demais dele:** o mesmo rosto sob
    outra iluminacao rende score bem alto (~0.99). Uma foto de verdade tirada
    noutro dia, com outro angulo e outra luz, cai bem mais — a literatura do
    ArcFace trabalha na faixa de 0.5 a 0.7 nesses casos. Por isso o limiar de
    0.40 vem da recomendacao para o buffalo_l, e nao da margem medida aqui.
    O que este teste prova e que o modelo *discrimina* identidades; calibrar o
    limiar com rostos do hangar fica para a implantacao.
    """
    from PIL import Image, ImageEnhance

    with Image.open(io.BytesIO(imagem)) as original:
        alterada = ImageEnhance.Brightness(original.convert("RGB")).enhance(0.82)
        alterada = alterada.resize((420, 420)).resize((512, 512))

    buffer = io.BytesIO()
    alterada.save(buffer, format="JPEG", quality=70)
    return buffer.getvalue()


# --------------------------------------------------------------------------
# O criterio de pronto da etapa
# --------------------------------------------------------------------------


def test_duas_fotos_da_mesma_pessoa_ficam_acima_do_limiar(engine, faces):
    original = engine.extract_embedding(faces[0])
    segunda = engine.extract_embedding(_outra_foto(faces[0]))

    score = engine.verify(original.vector, segunda.vector)

    assert score >= MATCH_THRESHOLD, f"Mesma pessoa deu score baixo: {score:.3f}"
    assert (
        classify_score(
            score, match_threshold=MATCH_THRESHOLD, review_threshold=REVIEW_THRESHOLD
        )
        is MatchOutcome.MATCH
    )


def test_pessoas_diferentes_ficam_abaixo_do_limiar(engine, faces):
    a = engine.extract_embedding(faces[0])
    b = engine.extract_embedding(faces[1])

    score = engine.verify(a.vector, b.vector)

    assert score < REVIEW_THRESHOLD, f"Pessoas diferentes deram score alto: {score:.3f}"
    assert (
        classify_score(
            score, match_threshold=MATCH_THRESHOLD, review_threshold=REVIEW_THRESHOLD
        )
        is MatchOutcome.NO_MATCH
    )


def test_limiar_separa_os_dois_casos_com_folga(engine, faces):
    """A margem entre os casos e o que sustenta a escolha do limiar.

    Se a mesma pessoa e duas pessoas diferentes dessem scores proximos, o
    limiar seria arbitrario e o sistema erraria nos dois sentidos.
    """
    a = engine.extract_embedding(faces[0])
    a_outra_foto = engine.extract_embedding(_outra_foto(faces[0]))
    b = engine.extract_embedding(faces[1])

    mesma_pessoa = engine.verify(a.vector, a_outra_foto.vector)
    outra_pessoa = engine.verify(a.vector, b.vector)

    print(f"\n  mesma pessoa: {mesma_pessoa:.3f}")
    print(f"  pessoas diferentes: {outra_pessoa:.3f}")
    print(f"  margem: {mesma_pessoa - outra_pessoa:.3f}")

    assert mesma_pessoa > outra_pessoa
    assert mesma_pessoa - outra_pessoa > 0.30, "Margem estreita demais entre os casos"


def test_todos_os_pares_de_pessoas_distintas_sao_rejeitados(engine, faces):
    """Nao basta um par funcionar: nenhum par de pessoas distintas pode passar."""
    embeddings = [engine.extract_embedding(face) for face in faces[:4]]

    for i in range(len(embeddings)):
        for j in range(i + 1, len(embeddings)):
            score = engine.verify(embeddings[i].vector, embeddings[j].vector)
            assert score < MATCH_THRESHOLD, (
                f"Rostos {i} e {j} foram confundidos com score {score:.3f}"
            )


# --------------------------------------------------------------------------
# Contrato da engine, contra o modelo real
# --------------------------------------------------------------------------


def test_embedding_real_tem_512_dimensoes_normalizadas(engine, faces):
    embedding = engine.extract_embedding(faces[0])

    assert len(embedding.vector) == 512
    norma = sum(valor**2 for valor in embedding.vector) ** 0.5
    assert norma == pytest.approx(1.0, abs=1e-4)


def test_embedding_real_identifica_o_modelo(engine, faces):
    embedding = engine.extract_embedding(faces[0])
    assert embedding.model_name == "insightface"
    assert embedding.model_version == "buffalo_l"


def test_qualidade_avaliada_na_foto_real(engine, faces):
    embedding = engine.extract_embedding(faces[0])

    assert embedding.quality.detection_score > 0.6
    assert embedding.quality.sharpness > 0
    assert 0.0 <= embedding.quality.score <= 1.0


def test_imagem_sem_rosto_e_rejeitada(engine):
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (480, 480), (120, 120, 120)).save(buffer, format="JPEG")

    with pytest.raises(NoFaceDetectedError):
        engine.extract_embedding(buffer.getvalue())


def test_foto_de_grupo_e_rejeitada(engine):
    """Com varias pessoas no quadro nao da para saber quem esta batendo ponto."""
    from insightface.data import get_image
    from PIL import Image

    frame = get_image("t1")
    buffer = io.BytesIO()
    Image.fromarray(frame[:, :, ::-1]).save(buffer, format="JPEG")

    with pytest.raises(MultipleFacesError):
        engine.extract_embedding(buffer.getvalue())


def test_deteccao_encontra_varios_rostos(engine):
    from insightface.data import get_image
    from PIL import Image

    frame = get_image("t1")
    buffer = io.BytesIO()
    Image.fromarray(frame[:, :, ::-1]).save(buffer, format="JPEG")

    detectados = engine.detect(buffer.getvalue())
    assert len(detectados) > 1
    assert all(face.box.width > 0 and face.box.height > 0 for face in detectados)
