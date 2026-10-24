"""Unit tests - no database needed."""

import pandas as pd
import pytest

from security import (MAX_PASSWORD_BYTES, burn_time, hash_password, validate_password_strength,
                      verify_password)
from utils.export import df_to_safe_csv, sanitize_cell
from utils.grading import add_grade_columns, letter_grade, percentage
from utils.text import clean_text, escape_like, normalize_email
from utils.validators import validate_email, validate_phone, validate_required, validate_username


# ------------------------------------------------------------ validators ----
@pytest.mark.parametrize("email,ok", [
    ("a@b.com", True), ("first.last+tag@sub.example.org", True),
    ("no-at-sign.com", False), ("a@b", False), ("a b@c.com", False), ("@b.com", False),
])
def test_email(email, ok):
    errors = []
    validate_email(email, errors)
    assert (errors == []) == ok


def test_email_required_and_length():
    errors = []
    validate_email("", errors)
    assert errors == ["Email is required."]
    errors = []
    validate_email("", errors, required=False)
    assert errors == []
    errors = []
    validate_email("a" * 150 + "@b.com", errors)
    assert errors


@pytest.mark.parametrize("phone,ok", [
    ("", True), ("+92 312 7627983", True), ("(042) 111-2222", True),
    ("()()()()", False), ("+++++++", False), ("12345", False), ("abc1234567", False),
    ("1" * 21, False),
])
def test_phone(phone, ok):
    errors = []
    validate_phone(phone, errors)
    assert (errors == []) == ok


def test_required_and_username():
    errors = []
    validate_required("", "Name", errors)
    validate_required("x" * 101, "Name", errors, 100)
    assert len(errors) == 2
    for name, ok in [("abc", True), ("a.b-c_d", True), ("ab", False), ("has space", False), ("x" * 51, False)]:
        errors = []
        validate_username(name, errors)
        assert (errors == []) == ok, name


# ------------------------------------------------------------------ text ----
def test_text_helpers():
    assert clean_text(None) == ""
    assert clean_text("  hi  ") == "hi"
    assert normalize_email("  A@B.COM ") == "a@b.com"
    assert escape_like("50%_off\\") == "50\\%\\_off\\\\"


# -------------------------------------------------------------- security ----
def test_hash_and_verify():
    h = hash_password("CorrectHorse9")
    assert h != "CorrectHorse9" and verify_password("CorrectHorse9", h)
    assert not verify_password("wrong", h)
    assert not verify_password("x", "not-a-valid-hash")


def test_long_passwords_rejected_not_truncated():
    too_long = "a1" * 40  # 80 bytes
    with pytest.raises(ValueError):
        hash_password(too_long)
    assert not verify_password(too_long, hash_password("CorrectHorse9"))
    assert any(str(MAX_PASSWORD_BYTES) in p for p in validate_password_strength(too_long))


def test_password_policy():
    assert validate_password_strength("CorrectHorse9", 10) == []
    assert validate_password_strength("short1", 10)
    assert validate_password_strength("onlyletters!!", 10)
    assert validate_password_strength("1234567890123", 10)


def test_burn_time_runs():
    burn_time()  # just must not raise


# ---------------------------------------------------------------- export ----
def test_csv_formula_injection_is_neutralised():
    assert sanitize_cell("=SUM(A1)") == "'=SUM(A1)"
    assert sanitize_cell("@cmd") == "'@cmd"
    assert sanitize_cell("+1") == "'+1" and sanitize_cell("-1+2") == "'-1+2"
    assert sanitize_cell("Ali") == "Ali" and sanitize_cell(-5) == -5
    df = pd.DataFrame({"name": ["=HYPERLINK(\"x\")", "Bob"], "n": [-1, 2]})
    csv = df_to_safe_csv(df).decode()
    assert "'=HYPERLINK" in csv and "Bob" in csv and "-1" in csv


# --------------------------------------------------------------- grading ----
def test_grading_scale():
    assert percentage(100) == 100.0 and percentage(50) == 50.0
    assert [letter_grade(p) for p in (95, 85, 84.9, 70, 60, 50, 49.9, 0)] == list("AABBCDFF")
    assert letter_grade(85) == "A" and letter_grade(84.9) == "B" and letter_grade(70) == "B"
    assert letter_grade(60) == "C" and letter_grade(50) == "D" and letter_grade(49.9) == "F"


def test_add_grade_columns():
    df = add_grade_columns(pd.DataFrame({"total_marks": [90, 55, 20]}))
    assert list(df["grade"]) == ["A", "D", "F"]
    assert add_grade_columns(pd.DataFrame()).empty
