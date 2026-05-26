import hashlib
import json
import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd

from .config import get_config
from .utils import safe_ticker_component


def _cache_root() -> Path:
    root = Path(get_config()["data_cache_dir"]) / "a_share"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _metadata_db() -> Path:
    return _cache_root() / "metadata.sqlite"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_metadata_db())
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS cache_entries (
            cache_key TEXT PRIMARY KEY,
            vendor TEXT NOT NULL,
            data_type TEXT NOT NULL,
            symbol TEXT NOT NULL,
            start_date TEXT,
            end_date TEXT,
            last_updated_at TEXT NOT NULL,
            expires_at TEXT,
            file_path TEXT NOT NULL,
            row_count INTEGER,
            checksum TEXT
        )
        """
    )
    return conn


def make_cache_key(
    vendor: str,
    data_type: str,
    symbol: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    extra: Optional[dict] = None,
) -> str:
    payload = {
        "vendor": vendor,
        "data_type": data_type,
        "symbol": symbol,
        "start_date": start_date,
        "end_date": end_date,
        "extra": extra or {},
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _is_fresh(expires_at: Optional[str]) -> bool:
    if not expires_at:
        return True
    return datetime.fromisoformat(expires_at) > datetime.utcnow()


def read_dataframe(
    vendor: str,
    data_type: str,
    symbol: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    extra: Optional[dict] = None,
) -> Optional[pd.DataFrame]:
    cache_key = make_cache_key(vendor, data_type, symbol, start_date, end_date, extra)
    with _connect() as conn:
        row = conn.execute(
            "SELECT file_path, expires_at FROM cache_entries WHERE cache_key = ?",
            (cache_key,),
        ).fetchone()
    if not row:
        return None
    file_path, expires_at = row
    if not _is_fresh(expires_at) or not os.path.exists(file_path):
        return None
    if file_path.endswith(".parquet"):
        return pd.read_parquet(file_path)
    return pd.read_csv(file_path)


def write_dataframe(
    df: pd.DataFrame,
    vendor: str,
    data_type: str,
    symbol: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    ttl_seconds: Optional[int] = None,
    extra: Optional[dict] = None,
) -> Path:
    safe_symbol = safe_ticker_component(symbol)
    cache_key = make_cache_key(vendor, data_type, symbol, start_date, end_date, extra)
    folder = _cache_root() / data_type / safe_symbol
    folder.mkdir(parents=True, exist_ok=True)
    file_stem = f"{cache_key}"
    file_path = folder / f"{file_stem}.parquet"
    try:
        df.to_parquet(file_path, index=False)
    except Exception:
        file_path = folder / f"{file_stem}.csv"
        df.to_csv(file_path, index=False, encoding="utf-8")

    expires_at = None
    if ttl_seconds is not None:
        expires_at = (datetime.utcnow() + timedelta(seconds=ttl_seconds)).isoformat()

    checksum = hashlib.sha256(
        pd.util.hash_pandas_object(df, index=True).values.tobytes()
    ).hexdigest()
    with _connect() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO cache_entries (
                cache_key, vendor, data_type, symbol, start_date, end_date,
                last_updated_at, expires_at, file_path, row_count, checksum
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                cache_key,
                vendor,
                data_type,
                symbol,
                start_date,
                end_date,
                datetime.utcnow().isoformat(),
                expires_at,
                str(file_path),
                len(df),
                checksum,
            ),
        )
    return file_path


def read_jsonl(
    vendor: str,
    data_type: str,
    symbol: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    extra: Optional[dict] = None,
) -> Optional[list[dict]]:
    cache_key = make_cache_key(vendor, data_type, symbol, start_date, end_date, extra)
    with _connect() as conn:
        row = conn.execute(
            "SELECT file_path, expires_at FROM cache_entries WHERE cache_key = ?",
            (cache_key,),
        ).fetchone()
    if not row:
        return None
    file_path, expires_at = row
    if not _is_fresh(expires_at) or not os.path.exists(file_path):
        return None
    with open(file_path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def write_jsonl(
    rows: list[dict],
    vendor: str,
    data_type: str,
    symbol: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    ttl_seconds: Optional[int] = None,
    extra: Optional[dict] = None,
) -> Path:
    safe_symbol = safe_ticker_component(symbol)
    cache_key = make_cache_key(vendor, data_type, symbol, start_date, end_date, extra)
    folder = _cache_root() / data_type / safe_symbol
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / f"{cache_key}.jsonl"
    with open(file_path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")

    expires_at = None
    if ttl_seconds is not None:
        expires_at = (datetime.utcnow() + timedelta(seconds=ttl_seconds)).isoformat()
    with _connect() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO cache_entries (
                cache_key, vendor, data_type, symbol, start_date, end_date,
                last_updated_at, expires_at, file_path, row_count, checksum
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                cache_key,
                vendor,
                data_type,
                symbol,
                start_date,
                end_date,
                datetime.utcnow().isoformat(),
                expires_at,
                str(file_path),
                len(rows),
                None,
            ),
        )
    return file_path

