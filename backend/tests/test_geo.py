"""haversine_km / check_delivery unit tests (no database needed)."""
import math
from types import SimpleNamespace

import pytest

from app.services.geo import ShopLocationNotSet, check_delivery, haversine_km


def test_one_degree_of_latitude():
    # hand-computed: 2*pi*6371/360 = 111.19 km
    assert haversine_km(0, 0, 1, 0) == pytest.approx(2 * math.pi * 6371 / 360, abs=0.01)


def test_london_to_paris():
    # known great-circle distance on a 6371 km sphere: ~343.6 km
    assert haversine_km(51.5074, -0.1278, 48.8566, 2.3522) == pytest.approx(343.6, abs=0.5)


def test_pune_points_match_spherical_law_of_cosines():
    # an independent formula for the same sphere must agree
    lat1, lng1, lat2, lng2 = 18.5074, 73.8077, 18.5204, 73.8567
    p1, p2, dl = math.radians(lat1), math.radians(lat2), math.radians(lng2 - lng1)
    expected = 6371 * math.acos(math.sin(p1) * math.sin(p2) + math.cos(p1) * math.cos(p2) * math.cos(dl))
    assert haversine_km(lat1, lng1, lat2, lng2) == pytest.approx(expected, abs=0.001)
    assert haversine_km(lat1, lng1, lat1, lng1) == 0


def shop(radius):
    return SimpleNamespace(lat=18.5074, lng=73.8077, delivery_radius_km=radius)


def test_boundary_is_inclusive():
    point = (18.5204, 73.8567)
    d = haversine_km(18.5074, 73.8077, *point)
    assert check_delivery(shop(d), *point).eligible is True  # exactly on the edge
    assert check_delivery(shop(d - 1e-6), *point).eligible is False  # just outside
    r = check_delivery(shop(6), *point)  # d is ~5.36 km
    assert r.eligible is True and r.radius_km == 6.0 and r.distance_km == pytest.approx(d)


def test_inside_and_outside():
    s = shop(3)
    assert check_delivery(s, 18.5164, 73.8077).eligible is True  # ~1 km north
    far = check_delivery(s, 18.5614, 73.8077)  # ~6 km north
    assert far.eligible is False and far.distance_km == pytest.approx(6.0, abs=0.05)


def test_location_not_set():
    with pytest.raises(ShopLocationNotSet):
        check_delivery(SimpleNamespace(lat=None, lng=None, delivery_radius_km=None), 18.5, 73.8)
