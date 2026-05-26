import re
from functools import lru_cache


_TS_CODE_RE = re.compile(r"^\d{6}\.(SH|SZ|BJ)$", re.IGNORECASE)
_PLAIN_A_RE = re.compile(r"^\d{6}$")


def is_a_share_symbol(symbol: str) -> bool:
    """Return True when ``symbol`` looks like an A-share code."""
    if not isinstance(symbol, str):
        return False
    value = symbol.strip().upper()
    return bool(_TS_CODE_RE.fullmatch(value) or _PLAIN_A_RE.fullmatch(value))


def normalize_a_share_symbol(symbol: str) -> str:
    """Normalize common A-share inputs to TuShare ``ts_code`` form."""
    if not isinstance(symbol, str) or not symbol.strip():
        raise ValueError(f"A-share symbol must be a non-empty string, got {symbol!r}")

    value = symbol.strip().upper()
    if _TS_CODE_RE.fullmatch(value):
        return value
    if not _PLAIN_A_RE.fullmatch(value):
        raise ValueError(f"Not an A-share symbol: {symbol!r}")

    if value.startswith(("60", "68", "90")):
        return f"{value}.SH"
    if value.startswith(("00", "30", "20")):
        return f"{value}.SZ"
    if value.startswith(("43", "83", "87", "88", "92")):
        return f"{value}.BJ"
    raise ValueError(f"Cannot infer A-share exchange for symbol: {symbol!r}")


def to_akshare_symbol(symbol: str) -> str:
    """Convert an A-share symbol to AkShare's six-digit code."""
    return normalize_a_share_symbol(symbol).split(".", 1)[0]


@lru_cache(maxsize=2048)
def default_search_aliases(symbol: str) -> tuple[str, ...]:
    """Return a conservative alias set for news search before metadata is loaded."""
    ts_code = normalize_a_share_symbol(symbol)
    code = ts_code.split(".", 1)[0]
    return (ts_code, code)

