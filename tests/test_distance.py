import pytest

from app.conversation import is_distance_in_range, parse_distance_input


@pytest.mark.parametrize(
    ("text", "expected_miles"),
    [
        ("3", 3),
        ("3 miles", 3),
        ("2,5 millas", 2.5),
        ("within 4 mi", 4),
        ("8 km", 4.971),
        ("10 kilómetros", 6.214),
    ],
)
def test_parse_distance_input_normalizes_to_miles(text, expected_miles):
    assert parse_distance_input(text) == expected_miles


@pytest.mark.parametrize(
    "text",
    [
        "somewhere nearby",
        "ten miles",
        "",
    ],
)
def test_parse_distance_input_rejects_unrecognized_values(text):
    assert parse_distance_input(text) is None


@pytest.mark.parametrize(
    ("distance", "expected"),
    [
        (0.09, False),
        (0.1, True),
        (31, True),
        (31.01, False),
    ],
)
def test_distance_range_includes_supported_boundaries(distance, expected):
    assert is_distance_in_range(distance) is expected
