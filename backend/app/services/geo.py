"""Calculo de distancia geografica."""

import math

# Raio medio da Terra. A Terra nao e uma esfera perfeita, entao haversine erra
# ate ~0,5% — algo como 1 m num raio de 200 m. Irrelevante aqui, e muito mais
# barato que a formula de Vincenty.
EARTH_RADIUS_M = 6_371_000.0


def haversine_distance_m(
    lat1: float, lon1: float, lat2: float, lon2: float
) -> float:
    """Distancia em metros entre dois pontos, sobre a superficie da Terra.

    Haversine e nao a distancia euclidiana entre as coordenadas: um grau de
    longitude vale ~111 km no equador e ~0 nos polos, entao tratar lat/lon como
    plano cartesiano produz erro que cresce com a latitude.
    """
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(min(1.0, a)))
