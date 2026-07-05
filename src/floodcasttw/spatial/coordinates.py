"""Coordinate utilities for Taiwan flood-risk datasets."""

from __future__ import annotations

from math import cos, degrees, radians, sin, sqrt, tan

TAIWAN_WGS84_BOUNDS = {
    "west": 118.0,
    "south": 20.0,
    "east": 123.5,
    "north": 26.5,
}


def is_valid_taiwan_wgs84(latitude: float | None, longitude: float | None) -> bool:
    if latitude is None or longitude is None:
        return False
    return (
        TAIWAN_WGS84_BOUNDS["south"] <= latitude <= TAIWAN_WGS84_BOUNDS["north"]
        and TAIWAN_WGS84_BOUNDS["west"] <= longitude <= TAIWAN_WGS84_BOUNDS["east"]
    )


def parse_float(value: object) -> float | None:
    if value in ("", None):
        return None
    try:
        return float(str(value).replace(",", "").strip())
    except ValueError:
        return None


def twd97_tm2_to_wgs84(
    x: float,
    y: float,
    *,
    central_meridian: float = 121.0,
) -> tuple[float, float]:
    """Convert TWD97 TM2 coordinates to WGS84 latitude/longitude.

    The default central meridian is EPSG:3826, commonly used for Taiwan-wide public datasets.
    """

    semi_major_axis = 6378137.0
    semi_minor_axis = 6356752.314245
    scale_factor = 0.9999
    false_easting = 250000.0

    eccentricity = sqrt(1 - (semi_minor_axis / semi_major_axis) ** 2)
    e1 = (1 - sqrt(1 - eccentricity**2)) / (1 + sqrt(1 - eccentricity**2))
    x_adjusted = x - false_easting
    meridional_arc = y / scale_factor
    mu = meridional_arc / (
        semi_major_axis
        * (
            1
            - eccentricity**2 / 4
            - 3 * eccentricity**4 / 64
            - 5 * eccentricity**6 / 256
        )
    )

    footpoint_lat = (
        mu
        + (3 * e1 / 2 - 27 * e1**3 / 32) * sin(2 * mu)
        + (21 * e1**2 / 16 - 55 * e1**4 / 32) * sin(4 * mu)
        + (151 * e1**3 / 96) * sin(6 * mu)
        + (1097 * e1**4 / 512) * sin(8 * mu)
    )

    eccentricity_prime_sq = eccentricity**2 / (1 - eccentricity**2)
    sin_fp = sin(footpoint_lat)
    cos_fp = cos(footpoint_lat)
    tan_fp = tan(footpoint_lat)
    c1 = eccentricity_prime_sq * cos_fp**2
    t1 = tan_fp**2
    n1 = semi_major_axis / sqrt(1 - eccentricity**2 * sin_fp**2)
    r1 = (
        semi_major_axis
        * (1 - eccentricity**2)
        / (1 - eccentricity**2 * sin_fp**2) ** 1.5
    )
    d = x_adjusted / (n1 * scale_factor)

    lat_rad = footpoint_lat - (n1 * tan_fp / r1) * (
        d**2 / 2
        - (5 + 3 * t1 + 10 * c1 - 4 * c1**2 - 9 * eccentricity_prime_sq) * d**4 / 24
        + (
            61
            + 90 * t1
            + 298 * c1
            + 45 * t1**2
            - 252 * eccentricity_prime_sq
            - 3 * c1**2
        )
        * d**6
        / 720
    )

    lon_origin = radians(central_meridian)
    lon_rad = lon_origin + (
        d
        - (1 + 2 * t1 + c1) * d**3 / 6
        + (
            5
            - 2 * c1
            + 28 * t1
            - 3 * c1**2
            + 8 * eccentricity_prime_sq
            + 24 * t1**2
        )
        * d**5
        / 120
    ) / cos_fp

    return degrees(lat_rad), degrees(lon_rad)


def normalize_coordinates(
    latitude: object = None,
    longitude: object = None,
    twd97_x: object = None,
    twd97_y: object = None,
) -> tuple[str, str, str]:
    lat = parse_float(latitude)
    lon = parse_float(longitude)
    if is_valid_taiwan_wgs84(lat, lon):
        return f"{lat:.6f}", f"{lon:.6f}", "WGS84"

    x = parse_float(twd97_x)
    y = parse_float(twd97_y)
    if x is not None and y is not None:
        converted_lat, converted_lon = twd97_tm2_to_wgs84(x, y)
        if is_valid_taiwan_wgs84(converted_lat, converted_lon):
            return f"{converted_lat:.6f}", f"{converted_lon:.6f}", "TWD97_TM2_121"

    return "", "", ""
