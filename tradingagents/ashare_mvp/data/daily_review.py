from __future__ import annotations

from datetime import datetime

import pandas as pd

from tradingagents.dataflows.exceptions import DataVendorUnavailable
from tradingagents.dataflows.interface import route_to_vendor
from tradingagents.dataflows.tushare_pro import _pro as tushare_pro_client

from .board_data import AShareBoardDataFetcher
from ..schemas import DailyIndexSnapshot, DailyMover, DailyReviewDataset

_INDEXES = (
    ("000001.SH", "上证指数"),
    ("399001.SZ", "深证成指"),
    ("399006.SZ", "创业板指"),
)


class AShareDailyReviewFetcher:
    def __init__(self, board_fetcher: AShareBoardDataFetcher | None = None):
        self.board_fetcher = board_fetcher or AShareBoardDataFetcher()

    def fetch(self, trade_date: str, top_n_movers: int = 10, top_n_sectors: int = 5) -> DailyReviewDataset:
        notes: list[str] = []
        indices = self._fetch_indices(trade_date, notes)
        market_df = self._fetch_market_snapshot(trade_date, notes)
        profile_map = self._fetch_profile_map(notes)
        top_gainers, top_losers, top_by_amount, market_turnover = self._build_movers(
            market_df, profile_map, top_n_movers, trade_date
        )
        important_news_text = self._fetch_news(trade_date, notes)
        hot_sectors = self._build_hot_sectors(top_by_amount, top_n_sectors, notes)
        self._annotate_movers(top_gainers, top_by_amount, hot_sectors)
        self._annotate_movers(top_losers, top_by_amount, hot_sectors)
        self._annotate_movers(top_by_amount, top_by_amount, hot_sectors)
        return DailyReviewDataset(
            trade_date=trade_date,
            indices=indices,
            market_turnover=market_turnover,
            top_gainers=top_gainers,
            top_losers=top_losers,
            top_by_amount=top_by_amount,
            hot_sectors=hot_sectors,
            important_news_text=important_news_text,
            notes=notes,
        )

    def _fetch_indices(self, trade_date: str, notes: list[str]) -> list[DailyIndexSnapshot]:
        snapshots: list[DailyIndexSnapshot] = []
        try:
            pro = tushare_pro_client()
            ymd = trade_date.replace("-", "")
            for symbol, name in _INDEXES:
                df = pro.index_daily(ts_code=symbol, start_date=ymd, end_date=ymd)
                if df is None or df.empty:
                    snapshots.append(DailyIndexSnapshot(symbol=symbol, name=name))
                    notes.append(f"{name} 指数数据暂缺。")
                    continue
                row = df.iloc[0].to_dict()
                snapshots.append(
                    DailyIndexSnapshot(
                        symbol=symbol,
                        name=name,
                        close=_safe_float(row.get("close")),
                        pct_change=_safe_pct_from_change(row.get("change"), row.get("pre_close")),
                        amount=_coerce_tushare_amount(row.get("amount")),
                    )
                )
        except Exception:
            notes.append("指数数据获取失败，市场概览将降级为弱信息模式。")
            snapshots = [DailyIndexSnapshot(symbol=s, name=n) for s, n in _INDEXES]
        return snapshots

    def _fetch_market_snapshot(self, trade_date: str, notes: list[str]) -> pd.DataFrame:
        try:
            pro = tushare_pro_client()
            ymd = trade_date.replace("-", "")
            df = pro.daily(trade_date=ymd)
            if df is None or df.empty:
                notes.append("全市场日行情暂缺。")
                return pd.DataFrame()
            if "amount" in df.columns:
                df = df.copy()
                df["amount"] = pd.to_numeric(df["amount"], errors="coerce") * 1000.0
            daily_basic = pro.daily_basic(
                trade_date=ymd,
                fields="ts_code,turnover_rate,volume_ratio,total_mv,circ_mv",
            )
            if daily_basic is not None and not daily_basic.empty:
                df = df.merge(daily_basic, on="ts_code", how="left")
            return df
        except Exception:
            notes.append("全市场日行情获取失败。")
            return pd.DataFrame()

    def _fetch_profile_map(self, notes: list[str]) -> dict[str, dict]:
        try:
            pro = tushare_pro_client()
            basic = pro.stock_basic(
                exchange="",
                list_status="L",
                fields="ts_code,name,industry,list_date",
            )
            if basic is None or basic.empty:
                return {}
            return {row["ts_code"]: row for row in basic.to_dict("records")}
        except Exception:
            notes.append("股票基础资料获取失败，名称/行业可能缺失。")
            return {}

    def _build_movers(
        self,
        df: pd.DataFrame,
        profile_map: dict[str, dict],
        top_n_movers: int,
        trade_date: str,
    ) -> tuple[list[DailyMover], list[DailyMover], list[DailyMover], float | None]:
        if df.empty:
            return [], [], [], None
        work = df.copy()
        work["pct_change"] = work.apply(
            lambda row: _safe_pct_from_change(row.get("change"), row.get("pre_close")),
            axis=1,
        )
        work["amount"] = pd.to_numeric(work.get("amount"), errors="coerce")
        market_turnover = _safe_float(work["amount"].sum())
        excluded_mask = work["ts_code"].apply(
            lambda symbol: self._is_excluded_security(symbol, profile_map, trade_date)
        )
        work = work.loc[~excluded_mask].copy()
        if work.empty:
            return [], [], [], market_turnover

        gainers = work.sort_values("pct_change", ascending=False).head(top_n_movers)
        losers = work.sort_values("pct_change", ascending=True).head(top_n_movers)
        active = work.sort_values("amount", ascending=False).head(top_n_movers)
        return (
            self._to_movers(gainers, profile_map, "上涨居前，短线关注度较高。", "需警惕高位波动放大。"),
            self._to_movers(losers, profile_map, "跌幅居前，需检查是否有基本面或情绪扰动。", "下跌原因若无明确公开信息，需警惕资金踩踏。"),
            self._to_movers(active, profile_map, "成交额居前，说明资金活跃。", "高成交额不等于趋势确认。"),
            market_turnover,
        )

    def _to_movers(
        self,
        df: pd.DataFrame,
        profile_map: dict[str, dict],
        default_reason: str,
        default_risk: str,
    ) -> list[DailyMover]:
        movers: list[DailyMover] = []
        for row in df.to_dict("records"):
            profile = profile_map.get(row.get("ts_code"), {})
            movers.append(
                DailyMover(
                    symbol=row.get("ts_code"),
                    name=profile.get("name"),
                    pct_change=_safe_float(row.get("pct_change")),
                    amount=_safe_float(row.get("amount")),
                    industry=profile.get("industry"),
                    concepts=[],
                    reason=default_reason,
                    risk=default_risk,
                )
            )
        return movers

    def _is_excluded_security(self, symbol: str, profile_map: dict[str, dict], trade_date: str) -> bool:
        profile = profile_map.get(symbol, {})
        name = str(profile.get("name") or "").strip().upper()
        if not name:
            return False
        if name.startswith(("*ST", "ST", "S*ST", "SST", "N", "C")):
            return True

        list_date = str(profile.get("list_date") or "").strip()
        if list_date and list_date.isdigit() and len(list_date) == 8:
            try:
                listed_days = (datetime.strptime(trade_date, "%Y-%m-%d") - datetime.strptime(list_date, "%Y%m%d")).days
                if listed_days <= 30:
                    return True
            except ValueError:
                pass
        return False

    def _fetch_news(self, trade_date: str, notes: list[str]) -> str:
        try:
            return route_to_vendor("get_global_news", trade_date, 3, 12)
        except (RuntimeError, DataVendorUnavailable, ValueError):
            notes.append("重要新闻获取失败。")
            return f"No reliable global news found for {trade_date}"

    def _build_hot_sectors(self, top_by_amount: list[DailyMover], top_n_sectors: int, notes: list[str]) -> list[dict]:
        merged_boards: list[dict] = []
        try:
            industry_boards = self.board_fetcher.fetch_hot_industry_boards(top_n_sectors)
            concept_boards = self.board_fetcher.fetch_hot_concept_boards(top_n_sectors)
            if industry_boards or concept_boards:
                industry_rows = [
                    {
                        "name": board.name,
                        "board_type": "industry",
                        "pct_change": board.pct_change,
                        "turnover": board.turnover,
                        "count": len(board.top_constituents or []),
                        "symbols": [item.get("symbol") for item in (board.top_constituents or []) if item.get("symbol")],
                    }
                    for board in industry_boards
                ]
                concept_rows = [
                    {
                        "name": board.name,
                        "board_type": "concept",
                        "pct_change": board.pct_change,
                        "turnover": board.turnover,
                        "count": len(board.top_constituents or []),
                        "symbols": [item.get("symbol") for item in (board.top_constituents or []) if item.get("symbol")],
                    }
                    for board in concept_boards
                ]
                industry_rows.sort(
                    key=lambda item: item.get("pct_change") if item.get("pct_change") is not None else float("-inf"),
                    reverse=True,
                )
                concept_rows.sort(
                    key=lambda item: item.get("pct_change") if item.get("pct_change") is not None else float("-inf"),
                    reverse=True,
                )
                industry_limit = max(1, (top_n_sectors + 1) // 2)
                concept_limit = max(0, top_n_sectors - industry_limit)
                merged_boards.extend(industry_rows[:industry_limit])
                merged_boards.extend(concept_rows[:concept_limit])
                return merged_boards[:top_n_sectors]
        except Exception:
            notes.append("行业/概念板块实时排行获取失败，已退回行业聚类逻辑。")

        counts: dict[str, dict] = {}
        for mover in top_by_amount:
            industry = mover.industry or "未知行业"
            bucket = counts.setdefault(industry, {"name": industry, "count": 0, "symbols": [], "_pct_values": []})
            bucket["count"] += 1
            bucket["symbols"].append(mover.symbol)
            if mover.pct_change is not None:
                bucket["_pct_values"].append(mover.pct_change)
        ranked = sorted(counts.values(), key=lambda item: item["count"], reverse=True)
        for item in ranked:
            values = item.pop("_pct_values", [])
            item["pct_change"] = sum(values) / len(values) if values else None
            item["source"] = "top_by_amount_industry_cluster"
        return ranked[:top_n_sectors]

    def _annotate_movers(self, movers: list[DailyMover], amount_leaders: list[DailyMover], hot_sectors: list[dict]) -> None:
        amount_symbols = {m.symbol for m in amount_leaders}
        sector_map = {
            item.get("name"): item
            for item in hot_sectors
            if item.get("board_type") in (None, "industry")
        }
        concept_membership = self._build_concept_membership(hot_sectors)
        for mover in movers:
            mover.is_amount_leader = mover.symbol in amount_symbols
            sector = sector_map.get(mover.industry or "")
            if sector:
                mover.industry_pct_change = _safe_float(sector.get("pct_change"))
            mover.concepts = concept_membership.get(mover.symbol, [])

    def _build_concept_membership(self, hot_sectors: list[dict]) -> dict[str, list[str]]:
        membership: dict[str, list[str]] = {}
        for item in hot_sectors:
            if item.get("board_type") != "concept":
                continue
            for symbol in item.get("symbols", []):
                membership.setdefault(symbol, []).append(item.get("name"))
        return membership


def _safe_float(value) -> float | None:
    try:
        if value is None or pd.isna(value):
            return None
        return float(value)
    except Exception:
        return None


def _safe_pct_from_change(change, pre_close) -> float | None:
    change = _safe_float(change)
    pre_close = _safe_float(pre_close)
    if change is None or pre_close in (None, 0):
        return None
    return change / pre_close * 100.0


def _coerce_tushare_amount(value) -> float | None:
    amount = _safe_float(value)
    if amount is None:
        return None
    return amount * 1000.0
