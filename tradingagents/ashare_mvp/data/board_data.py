from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import pandas as pd


@dataclass(slots=True)
class IndustryBoardSnapshot:
    name: str
    pct_change: float | None = None
    board_code: str | None = None
    turnover: float | None = None
    top_constituents: list[dict[str, Any]] | None = None


class AShareBoardDataFetcher:
    """Best-effort board data fetcher built on AkShare Eastmoney board APIs."""

    def __init__(self, ak_client=None):
        self._ak_client = ak_client

    def fetch_hot_industry_boards(self, top_n: int = 5) -> list[IndustryBoardSnapshot]:
        ak = self._ak()
        df = ak.stock_board_industry_name_em()
        if df is None or df.empty:
            return []

        name_col = _pick_column(df, ("板块名称", "名称"))
        change_col = _pick_column(df, ("涨跌幅",))
        code_col = _pick_column(df, ("板块代码", "代码"))
        turnover_col = _pick_column(df, ("总市值", "成交额", "成交总额"))

        work = df.copy()
        work["_pct_change"] = pd.to_numeric(work[change_col], errors="coerce")
        work = work.sort_values("_pct_change", ascending=False).head(top_n)

        boards: list[IndustryBoardSnapshot] = []
        for row in work.to_dict("records"):
            boards.append(
                IndustryBoardSnapshot(
                    name=str(row.get(name_col) or "").strip(),
                    pct_change=_safe_float(row.get(change_col)),
                    board_code=str(row.get(code_col)).strip() if code_col and row.get(code_col) is not None else None,
                    turnover=_safe_float(row.get(turnover_col)) if turnover_col else None,
                    top_constituents=[],
                )
            )
        return boards

    def fetch_industry_snapshot(self, industry_name: str, trade_date: str, top_n_constituents: int = 5) -> IndustryBoardSnapshot | None:
        if not industry_name:
            return None
        ak = self._ak()
        pct_change = None
        constituents: list[dict[str, Any]] = []

        try:
            hist = ak.stock_board_industry_hist_em(
                symbol=industry_name,
                start_date=(datetime.strptime(trade_date, "%Y-%m-%d") - timedelta(days=20)).strftime("%Y%m%d"),
                end_date=trade_date.replace("-", ""),
                period="日k",
                adjust="",
            )
            if hist is not None and not hist.empty:
                change_col = _pick_optional_column(hist, ("涨跌幅",))
                date_col = _pick_optional_column(hist, ("日期", "时间"))
                if date_col:
                    hist = hist.copy()
                    hist["_date"] = pd.to_datetime(hist[date_col], errors="coerce")
                    matched = hist[hist["_date"] == pd.to_datetime(trade_date)]
                    target = matched if not matched.empty else hist.tail(1)
                else:
                    target = hist.tail(1)
                if change_col:
                    pct_change = _safe_float(target.iloc[-1][change_col])
        except Exception:
            pct_change = None

        try:
            cons = ak.stock_board_industry_cons_em(symbol=industry_name)
            if cons is not None and not cons.empty:
                name_col = _pick_optional_column(cons, ("名称",))
                symbol_col = _pick_optional_column(cons, ("代码",))
                change_col = _pick_optional_column(cons, ("涨跌幅",))
                latest_col = _pick_optional_column(cons, ("最新价",))
                cons = cons.copy()
                if change_col:
                    cons["_pct_change"] = pd.to_numeric(cons[change_col], errors="coerce")
                    cons = cons.sort_values("_pct_change", ascending=False)
                for row in cons.head(top_n_constituents).to_dict("records"):
                    constituents.append(
                        {
                            "symbol": str(row.get(symbol_col) or "").strip() if symbol_col else None,
                            "name": str(row.get(name_col) or "").strip() if name_col else None,
                            "pct_change": _safe_float(row.get(change_col)) if change_col else None,
                            "latest_price": _safe_float(row.get(latest_col)) if latest_col else None,
                        }
                    )
        except Exception:
            constituents = []

        return IndustryBoardSnapshot(
            name=industry_name,
            pct_change=pct_change,
            top_constituents=constituents,
        )

    def _ak(self):
        if self._ak_client is not None:
            return self._ak_client
        import akshare as ak

        return ak


def _pick_column(df: pd.DataFrame, candidates: tuple[str, ...]) -> str:
    for candidate in candidates:
        if candidate in df.columns:
            return candidate
    raise KeyError(f"None of columns {candidates!r} found in dataframe columns {list(df.columns)!r}")


def _pick_optional_column(df: pd.DataFrame, candidates: tuple[str, ...]) -> str | None:
    for candidate in candidates:
        if candidate in df.columns:
            return candidate
    return None


def _safe_float(value) -> float | None:
    try:
        if value is None or pd.isna(value):
            return None
        return float(value)
    except Exception:
        return None
