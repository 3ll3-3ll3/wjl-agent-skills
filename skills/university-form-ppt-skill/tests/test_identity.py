import pytest

from scripts.random_identity import generate_identity


def test_default_student_id_is_7_or_8_digits_without_fixed_prefix():
    identity = generate_identity(seed=7)
    assert identity["student_id"].isdigit()
    assert len(identity["student_id"]) in (7, 8)
    assert len(identity["name"]) <= 11


def test_explicit_7_digit_id_is_supported():
    identity = generate_identity(seed=11, student_id_length=7)
    assert len(identity["student_id"]) == 7
    assert identity["student_id"].isdigit()


def test_explicit_8_digit_id_is_supported():
    identity = generate_identity(seed=12, student_id_length=8)
    assert len(identity["student_id"]) == 8
    assert identity["student_id"].isdigit()


def test_optional_prefix_must_be_explicit_and_numeric():
    identity = generate_identity(seed=13, student_id_length=8, id_prefix="20")
    assert identity["student_id"].startswith("20")
    with pytest.raises(ValueError):
        generate_identity(seed=13, student_id_length=8, id_prefix="AB")


def test_rejects_non_current_lengths():
    with pytest.raises(ValueError):
        generate_identity(seed=1, student_id_length=9)
