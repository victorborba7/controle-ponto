"""Modulo facial: canalizacao, limiares e qualidade.

Estes testes usam a engine stub e verificam a *logica em volta* do modelo —
comparacao, escolha do melhor template, tratamento de erro, guarda de upload.
A capacidade do ArcFace de separar rostos de verdade e outra pergunta, testada
em `test_facial_real_model.py` com o modelo baixado.
"""

import io

import pytest
from PIL import Image

from app.facial import (
    ImageDecodeError,
    ImageTooLargeError,
    MatchCandidate,
    MatchOutcome,
    MultipleFacesError,
    NoFaceDetectedError,
    build_engine,
    classify_score,
    cosine_similarity,
)
from app.facial.base import BoundingBox
from app.facial.imaging import inspect_image
from app.facial.quality import QualityThresholds, assess_quality
from app.facial.stub import (
    StubFaceEngine,
    stub_image,
    stub_image_variant,
    stub_image_with_faces,
)

PESSOA_A = (200, 30, 30)
PESSOA_B = (30, 30, 200)
PESSOA_C = (30, 200, 30)

LIMIARES = {"match_threshold": 0.40, "review_threshold": 0.32}


@pytest.fixture
def engine() -> StubFaceEngine:
    return StubFaceEngine()


# --------------------------------------------------------------------------
# Similaridade e limiares
# --------------------------------------------------------------------------


def test_cosseno_de_vetores_identicos_e_um():
    vetor = [0.6, 0.8]
    assert cosine_similarity(vetor, vetor) == pytest.approx(1.0)


def test_cosseno_de_vetores_ortogonais_e_zero():
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)


def test_cosseno_normaliza_vetores_nao_normalizados():
    """Template gravado por versao antiga pode nao estar normalizado."""
    assert cosine_similarity([3.0, 0.0], [10.0, 0.0]) == pytest.approx(1.0)


def test_cosseno_com_dimensoes_diferentes_falha():
    with pytest.raises(ValueError, match="Dimensoes incompativeis"):
        cosine_similarity([1.0, 0.0], [1.0, 0.0, 0.0])


def test_cosseno_com_vetor_nulo_nao_divide_por_zero():
    assert cosine_similarity([0.0, 0.0], [1.0, 0.0]) == 0.0


@pytest.mark.parametrize(
    ("score", "esperado"),
    [
        (0.95, MatchOutcome.MATCH),
        (0.40, MatchOutcome.MATCH),  # exatamente no limiar aprova
        (0.39, MatchOutcome.REVIEW),
        (0.32, MatchOutcome.REVIEW),  # exatamente no limiar de revisao
        (0.31, MatchOutcome.NO_MATCH),
        (-1.0, MatchOutcome.NO_MATCH),
    ],
)
def test_classificacao_por_faixa(score: float, esperado: MatchOutcome):
    assert classify_score(score, **LIMIARES) is esperado


def test_limiares_invertidos_sao_erro_de_configuracao():
    with pytest.raises(ValueError, match="deve ser maior"):
        classify_score(0.5, match_threshold=0.30, review_threshold=0.40)


# --------------------------------------------------------------------------
# Extracao de embedding
# --------------------------------------------------------------------------


def test_embedding_sai_normalizado(engine: StubFaceEngine):
    """Norma L2 = 1 e o que mantem os scores comparaveis entre fotos."""
    embedding = engine.extract_embedding(stub_image(PESSOA_A))

    norma = sum(valor**2 for valor in embedding.vector) ** 0.5
    assert norma == pytest.approx(1.0, abs=1e-6)
    assert len(embedding.vector) == engine.embedding_dim


def test_embedding_carrega_a_identificacao_do_modelo(engine: StubFaceEngine):
    """Sem model_name/version nao da para conviver com duas geracoes de template."""
    embedding = engine.extract_embedding(stub_image(PESSOA_A))
    assert embedding.model_name == "stub"
    assert embedding.model_version == "1"


def test_mesma_imagem_gera_o_mesmo_embedding(engine: StubFaceEngine):
    primeiro = engine.extract_embedding(stub_image(PESSOA_A))
    segundo = engine.extract_embedding(stub_image(PESSOA_A))
    assert primeiro.vector == segundo.vector


def test_repr_do_embedding_nao_expoe_o_vetor(engine: StubFaceEngine):
    """Dado biometrico nao pode vazar por log de erro."""
    embedding = engine.extract_embedding(stub_image(PESSOA_A))
    texto = repr(embedding)

    assert "stub" in texto
    assert "0." not in texto  # nenhum componente do vetor


def test_imagem_sem_rosto(engine: StubFaceEngine):
    with pytest.raises(NoFaceDetectedError):
        engine.extract_embedding(stub_image((0, 0, 0)))


def test_imagem_com_dois_rostos(engine: StubFaceEngine):
    """Com duas pessoas no quadro nao da para saber quem esta batendo ponto."""
    with pytest.raises(MultipleFacesError):
        engine.extract_embedding(stub_image_with_faces([PESSOA_A, PESSOA_B]))


def test_deteccao_conta_os_rostos(engine: StubFaceEngine):
    assert len(engine.detect(stub_image(PESSOA_A))) == 1
    assert len(engine.detect(stub_image_with_faces([PESSOA_A, PESSOA_B]))) == 2
    assert engine.detect(stub_image((0, 0, 0))) == []


# --------------------------------------------------------------------------
# Comparacao 1:1 e 1:N
# --------------------------------------------------------------------------


def test_duas_fotos_da_mesma_pessoa_batem(engine: StubFaceEngine):
    original = engine.extract_embedding(stub_image(PESSOA_A))
    outra_foto = engine.extract_embedding(stub_image_variant(PESSOA_A))

    score = engine.verify(original.vector, outra_foto.vector)

    assert score >= 0.40
    assert classify_score(score, **LIMIARES) is MatchOutcome.MATCH


def test_pessoas_diferentes_nao_batem(engine: StubFaceEngine):
    a = engine.extract_embedding(stub_image(PESSOA_A))
    b = engine.extract_embedding(stub_image(PESSOA_B))

    score = engine.verify(a.vector, b.vector)

    assert score < 0.32
    assert classify_score(score, **LIMIARES) is MatchOutcome.NO_MATCH


def test_limiar_separa_os_dois_casos(engine: StubFaceEngine):
    """O criterio de pronto da etapa, no nivel da canalizacao.

    A mesma pergunta contra o modelo real esta em test_facial_real_model.py.
    """
    a1 = engine.extract_embedding(stub_image(PESSOA_A))
    a2 = engine.extract_embedding(stub_image_variant(PESSOA_A))
    b1 = engine.extract_embedding(stub_image(PESSOA_B))

    mesma_pessoa = engine.verify(a1.vector, a2.vector)
    outra_pessoa = engine.verify(a1.vector, b1.vector)

    assert mesma_pessoa > outra_pessoa
    assert mesma_pessoa >= 0.40 > 0.32 >= outra_pessoa


def test_escolhe_o_melhor_entre_varios_templates(engine: StubFaceEngine):
    """Basta um dos templates da pessoa bater (decisao D4)."""
    probe = engine.extract_embedding(stub_image_variant(PESSOA_A))

    candidatos = [
        MatchCandidate(template_id="foto-antiga", vector=engine.extract_embedding(
            stub_image(PESSOA_B)).vector),
        MatchCandidate(template_id="foto-certa", vector=engine.extract_embedding(
            stub_image(PESSOA_A)).vector),
        MatchCandidate(template_id="outra-pessoa", vector=engine.extract_embedding(
            stub_image(PESSOA_C)).vector),
    ]

    resultado = engine.verify_against_templates(probe.vector, candidatos, **LIMIARES)

    assert resultado.template_id == "foto-certa"
    assert resultado.is_match


def test_identificacao_sem_candidatos(engine: StubFaceEngine):
    probe = engine.extract_embedding(stub_image(PESSOA_A))
    resultado = engine.identify(probe.vector, [], **LIMIARES)

    assert resultado.outcome is MatchOutcome.NO_MATCH
    assert resultado.template_id is None


def test_identificacao_com_base_so_de_desconhecidos(engine: StubFaceEngine):
    """Rosto que nao esta na base nao pode ser atribuido a ninguem."""
    probe = engine.extract_embedding(stub_image(PESSOA_A))
    candidatos = [
        MatchCandidate(template_id="b", vector=engine.extract_embedding(
            stub_image(PESSOA_B)).vector),
        MatchCandidate(template_id="c", vector=engine.extract_embedding(
            stub_image(PESSOA_C)).vector),
    ]

    resultado = engine.identify(probe.vector, candidatos, **LIMIARES)
    assert resultado.outcome is MatchOutcome.NO_MATCH


# --------------------------------------------------------------------------
# Qualidade da foto
# --------------------------------------------------------------------------


def _box(size: int, *, x: int = 200, y: int = 200) -> BoundingBox:
    return BoundingBox(x=x, y=y, width=size, height=size)


def test_foto_boa_nao_tem_ressalvas():
    qualidade = assess_quality(
        image_width=1000,
        image_height=1000,
        face_box=_box(400),
        sharpness=180.0,
        detection_score=0.98,
    )
    assert qualidade.is_acceptable
    assert qualidade.score > 0.8


def test_rosto_pequeno_demais_e_reprovado():
    qualidade = assess_quality(
        image_width=1000,
        image_height=1000,
        face_box=_box(40),
        sharpness=180.0,
        detection_score=0.98,
    )
    assert "face_too_small" in qualidade.issues
    assert not qualidade.is_acceptable


def test_foto_tremida_e_reprovada():
    qualidade = assess_quality(
        image_width=1000,
        image_height=1000,
        face_box=_box(400),
        sharpness=12.0,
        detection_score=0.98,
    )
    assert "blurry" in qualidade.issues


def test_deteccao_incerta_e_reprovada():
    qualidade = assess_quality(
        image_width=1000,
        image_height=1000,
        face_box=_box(400),
        sharpness=180.0,
        detection_score=0.35,
    )
    assert "low_detection_confidence" in qualidade.issues


def test_rosto_encostado_na_borda_e_tratado_como_cortado():
    """Meio rosto gera embedding plausivel mas errado — pior que rejeitar."""
    qualidade = assess_quality(
        image_width=1000,
        image_height=1000,
        face_box=BoundingBox(x=0, y=200, width=300, height=300),
        sharpness=180.0,
        detection_score=0.98,
    )
    assert "face_cropped" in qualidade.issues


def test_rosto_longe_demais_na_foto():
    """Pixels suficientes, mas perdido num mar de fundo."""
    qualidade = assess_quality(
        image_width=4000,
        image_height=4000,
        face_box=_box(100, x=1000, y=1000),
        sharpness=180.0,
        detection_score=0.98,
    )
    assert "face_too_far" in qualidade.issues


def test_score_de_qualidade_fica_entre_zero_e_um():
    pessima = assess_quality(
        image_width=1000,
        image_height=1000,
        face_box=_box(10),
        sharpness=0.0,
        detection_score=0.0,
    )
    otima = assess_quality(
        image_width=1000,
        image_height=1000,
        face_box=_box(600, x=200, y=200),
        sharpness=9999.0,
        detection_score=1.0,
    )
    assert 0.0 <= pessima.score <= 1.0
    assert 0.0 <= otima.score <= 1.0
    assert otima.score > pessima.score


def test_limiares_de_qualidade_sao_configuraveis():
    """Preparado para variar por tenant sem mexer no codigo."""
    frouxo = QualityThresholds(min_face_pixels=20, min_sharpness=5.0, min_face_ratio=0.001)
    qualidade = assess_quality(
        image_width=1000,
        image_height=1000,
        face_box=_box(40),
        sharpness=12.0,
        detection_score=0.98,
        thresholds=frouxo,
    )
    assert qualidade.is_acceptable


# --------------------------------------------------------------------------
# Guarda de upload
# --------------------------------------------------------------------------


def test_imagem_valida_e_inspecionada():
    info = inspect_image(stub_image(PESSOA_A, size=(640, 480)))
    assert (info.width, info.height, info.format) == (640, 480, "PNG")


def test_bytes_vazios():
    with pytest.raises(ImageDecodeError):
        inspect_image(b"")


def test_arquivo_que_nao_e_imagem():
    with pytest.raises(ImageDecodeError):
        inspect_image(b"nao sou uma imagem, sou um texto qualquer")


def test_upload_grande_demais_e_barrado_antes_de_decodificar():
    with pytest.raises(ImageTooLargeError):
        inspect_image(b"\xff\xd8\xff" + b"\x00" * (13 * 1024 * 1024))


def test_imagem_pequena_demais():
    with pytest.raises(ImageDecodeError, match="pequena demais"):
        inspect_image(stub_image(PESSOA_A, size=(32, 32)))


def test_formato_nao_suportado():
    buffer = io.BytesIO()
    Image.new("RGB", (200, 200), PESSOA_A).save(buffer, format="BMP")
    with pytest.raises(ImageDecodeError, match="nao suportado"):
        inspect_image(buffer.getvalue())


def test_jpeg_e_aceito():
    info = inspect_image(stub_image(PESSOA_A, size=(300, 300), image_format="JPEG"))
    assert info.format == "JPEG"


# --------------------------------------------------------------------------
# Fabrica de engines
# --------------------------------------------------------------------------


def test_fabrica_constroi_a_stub():
    assert build_engine("stub").name == "stub"


def test_fabrica_rejeita_engine_desconhecida():
    from app.facial import EngineUnavailableError

    with pytest.raises(EngineUnavailableError, match="desconhecida"):
        build_engine("modelo-que-nao-existe")


def test_engine_real_pode_ser_construida_sem_o_modelo_instalado():
    """Instanciar nao pode exigir insightface — a carga e preguicosa.

    E o que permite este modulo ser importado na imagem de desenvolvimento,
    que nao tem o ~1 GB de dependencias.
    """
    from app.facial.insightface_engine import InsightFaceEngine

    engine = InsightFaceEngine()
    assert engine.name == "insightface"
    assert engine.embedding_dim == 512
