from math import radians, sin, cos, sqrt, atan2


def calculate_distance_miles(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float
) -> float:
    earth_radius_miles = 3958.8

    lat1_rad = radians(lat1)
    lon1_rad = radians(lon1)
    lat2_rad = radians(lat2)
    lon2_rad = radians(lon2)

    delta_lat = lat2_rad - lat1_rad
    delta_lon = lon2_rad - lon1_rad

    a = (
        sin(delta_lat / 2) ** 2
        + cos(lat1_rad)
        * cos(lat2_rad)
        * sin(delta_lon / 2) ** 2
    )

    c = 2 * atan2(sqrt(a), sqrt(1 - a))

    distance = earth_radius_miles * c

    return round(distance, 2)