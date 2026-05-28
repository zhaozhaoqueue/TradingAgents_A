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


@dataclass(slots=True)
class ConceptBoardSnapshot:
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
        df = self._industry_board_table(ak)
        if df is None or df.empty:
            return []

        name_col = _pick_column(df, ("板块名称", "名称"))
        change_col = _pick_column(df, ("涨跌幅",))
        code_col = _pick_column(df, ("板块代码", "代码"))
        turnover_col = _pick_optional_column(df, ("总市值", "成交额", "成交总额"))

        work = df.copy()
        work["_pct_change"] = pd.to_numeric(work[change_col], errors="coerce")
        work = work.sort_values("_pct_change", ascending=False).head(top_n)

        boards: list[IndustryBoardSnapshot] = []
        for row in work.to_dict("records"):
            name = str(row.get(name_col) or "").strip()
            boards.append(
                IndustryBoardSnapshot(
                    name=name,
                    pct_change=_safe_float(row.get(change_col)),
                    board_code=str(row.get(code_col)).strip() if code_col and row.get(code_col) is not None else None,
                    turnover=_safe_float(row.get(turnover_col)) if turnover_col else None,
                    top_constituents=self._fetch_constituents(ak, name, top_n_constituents=5),
                )
            )
        return boards

    def fetch_hot_concept_boards(self, top_n: int = 5) -> list[ConceptBoardSnapshot]:
        ak = self._ak()
        return self._iter_concept_board_rows(ak, top_n=top_n)

    def fetch_industry_snapshot(self, industry_name: str, trade_date: str, top_n_constituents: int = 5) -> IndustryBoardSnapshot | None:
        if not industry_name:
            return None
        ak = self._ak()
        matched_name = self._resolve_industry_name(ak, industry_name) or industry_name
        pct_change = None
        constituents: list[dict[str, Any]] = self._fetch_constituents(ak, matched_name, top_n_constituents)

        try:
            hist = ak.stock_board_industry_hist_em(
                symbol=matched_name,
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

        return IndustryBoardSnapshot(
            name=matched_name,
            pct_change=pct_change,
            top_constituents=constituents,
        )

    def fetch_stock_concepts(self, symbol: str, top_n: int = 3) -> list[ConceptBoardSnapshot]:
        return self.fetch_stock_concepts_by_date(symbol, trade_date=None, top_n=top_n)

    def fetch_stock_concepts_by_date(self, symbol: str, trade_date: str | None, top_n: int = 3) -> list[ConceptBoardSnapshot]:
        normalized_symbol = _to_ts_code(symbol)
        matches: list[ConceptBoardSnapshot] = []
        ak = self._ak()
        for board in self._iter_concept_board_rows(ak, top_n=max(top_n * 10, top_n)):
            members = board.top_constituents or []
            if any(_to_ts_code(str(item.get("symbol") or "")) == normalized_symbol for item in members):
                if trade_date:
                    board = self.fetch_concept_snapshot(board.name, trade_date, top_n_constituents=len(members) or 5) or board
                matches.append(board)
                if len(matches) >= top_n:
                    break
        return matches

    def fetch_concept_snapshot(
        self,
        concept_name: str,
        trade_date: str,
        top_n_constituents: int = 5,
    ) -> ConceptBoardSnapshot | None:
        if not concept_name:
            return None
        ak = self._ak()
        matched_name = self._resolve_concept_name(ak, concept_name) or concept_name
        pct_change = None
        board_code = None
        turnover = None
        constituents = self._fetch_concept_constituents(ak, matched_name, top_n_constituents)

        try:
            table = self._concept_board_table(ak)
            if table is not None and not table.empty:
                name_col = _pick_optional_column(table, ("板块名称", "名称"))
                code_col = _pick_optional_column(table, ("板块代码", "代码"))
                turnover_col = _pick_optional_column(table, ("成交额", "成交总额", "总市值"))
                if name_col:
                    row = table[table[name_col].astype(str).str.strip() == matched_name]
                    if not row.empty:
                        payload = row.iloc[0]
                        board_code = str(payload.get(code_col)).strip() if code_col and payload.get(code_col) is not None else None
                        turnover = _safe_float(payload.get(turnover_col)) if turnover_col else None
        except Exception:
            board_code = None
            turnover = None

        try:
            hist = ak.stock_board_concept_hist_em(
                symbol=matched_name,
                start_date=(datetime.strptime(trade_date, "%Y-%m-%d") - timedelta(days=20)).strftime("%Y%m%d"),
                end_date=trade_date.replace("-", ""),
                period="日k",
                adjust="",
            )
            pct_change = _extract_hist_pct_change(hist, trade_date)
        except Exception:
            pct_change = None

        return ConceptBoardSnapshot(
            name=matched_name,
            pct_change=pct_change,
            board_code=board_code,
            turnover=turnover,
            top_constituents=constituents,
        )

    def _industry_board_table(self, ak) -> pd.DataFrame:
        df = ak.stock_board_industry_name_em()
        if df is None:
            return pd.DataFrame()
        return df

    def _concept_board_table(self, ak) -> pd.DataFrame:
        df = ak.stock_board_concept_name_em()
        if df is None:
            return pd.DataFrame()
        return df

    def _resolve_industry_name(self, ak, industry_name: str) -> str | None:
        try:
            df = self._industry_board_table(ak)
        except Exception:
            return None
        if df is None or df.empty:
            return None
        name_col = _pick_optional_column(df, ("板块名称", "名称"))
        if not name_col:
            return None
        names = [str(value).strip() for value in df[name_col].dropna().tolist()]
        if industry_name in names:
            return industry_name
        compact = _compact_name(industry_name)
        for name in names:
            if _compact_name(name) == compact:
                return name
        for name in names:
            left = _compact_name(name)
            if compact and (compact in left or left in compact):
                return name
        return None

    def _resolve_concept_name(self, ak, concept_name: str) -> str | None:
        try:
            df = self._concept_board_table(ak)
        except Exception:
            return None
        if df is None or df.empty:
            return None
        name_col = _pick_optional_column(df, ("板块名称", "名称"))
        if not name_col:
            return None
        names = [str(value).strip() for value in df[name_col].dropna().tolist()]
        if concept_name in names:
            return concept_name
        compact = _compact_name(concept_name)
        for name in names:
            if _compact_name(name) == compact:
                return name
        for name in names:
            left = _compact_name(name)
            if compact and (compact in left or left in compact):
                return name
        return None

    def _iter_concept_board_rows(self, ak, top_n: int) -> list[ConceptBoardSnapshot]:
        df = self._concept_board_table(ak)
        if df is None or df.empty:
            return []

        name_col = _pick_column(df, ("板块名称", "名称"))
        change_col = _pick_column(df, ("涨跌幅",))
        code_col = _pick_optional_column(df, ("板块代码", "代码"))
        turnover_col = _pick_optional_column(df, ("成交额", "成交总额", "总市值"))

        work = df.copy()
        work["_pct_change"] = pd.to_numeric(work[change_col], errors="coerce")
        work = work.sort_values("_pct_change", ascending=False).head(top_n)

        boards: list[ConceptBoardSnapshot] = []
        for row in work.to_dict("records"):
            name = str(row.get(name_col) or "").strip()
            boards.append(
                ConceptBoardSnapshot(
                    name=name,
                    pct_change=_safe_float(row.get(change_col)),
                    board_code=str(row.get(code_col)).strip() if code_col and row.get(code_col) is not None else None,
                    turnover=_safe_float(row.get(turnover_col)) if turnover_col else None,
                    top_constituents=self._fetch_concept_constituents(ak, name, top_n_constituents=5),
                )
            )
        return boards

    def _fetch_constituents(self, ak, industry_name: str, top_n_constituents: int) -> list[dict[str, Any]]:
        constituents: list[dict[str, Any]] = []
        if not industry_name:
            return constituents
        try:
            cons = ak.stock_board_industry_cons_em(symbol=industry_name)
        except Exception:
            return constituents
        if cons is None or cons.empty:
            return constituents
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
                    "symbol": _to_ts_code(str(row.get(symbol_col) or "").strip()) if symbol_col else None,
                    "name": str(row.get(name_col) or "").strip() if name_col else None,
                    "pct_change": _safe_float(row.get(change_col)) if change_col else None,
                    "latest_price": _safe_float(row.get(latest_col)) if latest_col else None,
                }
            )
        return constituents

    def _fetch_concept_constituents(self, ak, concept_name: str, top_n_constituents: int) -> list[dict[str, Any]]:
        constituents: list[dict[str, Any]] = []
        if not concept_name:
            return constituents
        try:
            cons = ak.stock_board_concept_cons_em(symbol=concept_name)
        except Exception:
            return constituents
        if cons is None or cons.empty:
            return constituents
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
                    "symbol": _to_ts_code(str(row.get(symbol_col) or "").strip()) if symbol_col else None,
                    "name": str(row.get(name_col) or "").strip() if name_col else None,
                    "pct_change": _safe_float(row.get(change_col)) if change_col else None,
                    "latest_price": _safe_float(row.get(latest_col)) if latest_col else None,
                }
            )
        return constituents

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


def _extract_hist_pct_change(hist: pd.DataFrame | None, trade_date: str) -> float | None:
    if hist is None or hist.empty:
        return None
    change_col = _pick_optional_column(hist, ("涨跌幅",))
    if not change_col:
        return None
    date_col = _pick_optional_column(hist, ("日期", "时间"))
    if date_col:
        work = hist.copy()
        work["_date"] = pd.to_datetime(work[date_col], errors="coerce")
        matched = work[work["_date"] == pd.to_datetime(trade_date)]
        target = matched if not matched.empty else work.tail(1)
    else:
        target = hist.tail(1)
    return _safe_float(target.iloc[-1][change_col])


def _compact_name(value: str) -> str:
    return str(value).replace("行业", "").replace("板块", "").replace("Ⅱ", "").replace("I", "").strip()


def _to_ts_code(symbol: str) -> str:
    if "." in symbol:
        return symbol
    if symbol.startswith(("6", "9")):
        return f"{symbol}.SH"
    if symbol.startswith(("0", "2", "3")):
        return f"{symbol}.SZ"
    if symbol.startswith(("4", "8")):
        return f"{symbol}.BJ"
    return symbol
