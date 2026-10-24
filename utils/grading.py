"""
Grading rules in ONE place.
Total possible marks = GRADE_MAX_ASSIGNMENT + GRADE_MAX_QUIZ + GRADE_MAX_FINAL (see .env).
"""

import pandas as pd

from config import config

PASS_PERCENT = 50.0


def percentage(total_marks) -> float:
    return round(float(total_marks) / config.GRADE_TOTAL_MAX * 100, 1)


def letter_grade(pct: float) -> str:
    if pct >= 85:
        return "A"
    if pct >= 70:
        return "B"
    if pct >= 60:
        return "C"
    if pct >= PASS_PERCENT:
        return "D"
    return "F"


def add_grade_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Add 'percentage' and 'grade' columns computed from 'total_marks'."""
    if df.empty or "total_marks" not in df.columns:
        return df
    out = df.copy()
    out["percentage"] = out["total_marks"].map(percentage)
    out["grade"] = out["percentage"].map(letter_grade)
    return out
