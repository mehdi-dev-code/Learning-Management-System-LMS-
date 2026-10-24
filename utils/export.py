"""CSV export that is safe to open in Excel / Google Sheets."""

import pandas as pd

# A cell starting with one of these characters can be run as a formula by a spreadsheet
# ("CSV injection"). Prefixing an apostrophe makes the spreadsheet treat it as plain text.
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def sanitize_cell(value):
    if isinstance(value, str) and value.startswith(_FORMULA_PREFIXES):
        return "'" + value
    return value


def df_to_safe_csv(df: pd.DataFrame) -> bytes:
    safe = df.copy()
    for column in safe.columns:
        safe[column] = safe[column].map(sanitize_cell)
    return safe.to_csv(index=False).encode("utf-8")
