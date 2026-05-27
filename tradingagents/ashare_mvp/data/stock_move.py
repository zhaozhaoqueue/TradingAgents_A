from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd

from tradingagents.dataflows.a_share_utils import normalize_a_share_symbol
from tradingagents.dataflows.akshare_data import get_ohlcv_dataframe as get_akshare_ohlcv
from tradingagents.dataflows.exceptions import DataVendorUnavailable
from tradingagents.dataflows.interface import route_to_vendor
from tradingagents.dataflows.tushare_pro import get_ohlcv_dataframe as get_tushare_ohlcv
from tradingagents.dataflows.tushare_pro import _pro as tushare_pro_client

from .board_data import AShareBoardDataFetcher
from ..schemas import SectorSnapshot, StockMoveDataset, StockProfile


class AShareStockMoveFetcher:
    """Fetch the minimum dataset required by the stock move MVP pipeline."""

    def __init__(self, board_fetcher: AShareBoardDataFetcher | None = None):
        self.board_fetcher = board_fetcher or AShareBoardDataFetcher()

    def fetch(self, symbol: str, trade_date: str) -> StockMoveDataset:
        ts_code = normalize_a_share_symbol(symbol)
        end_date = trade_date
        start_date = (datetime.strptime(trade_date, "%Y-%m-%d") - timedelta(days=40)).strftime("%Y-%m-%d")
        evidence_start = (datetime.strptime(trade_date, "%Y-%m-%d") - timedelta(days=7)).strftime("%Y-%m-%d")

        history = self._fetch_history(ts_code, start_date, end_date)
        if history.empty:
            raise RuntimeError(f"No A-share history data available for {ts_code} on or before {trade_date}")
        history = self._enrich_daily_basic(ts_code, history, start_date, end_date)

        latest_row = history.sort_values("Date").iloc[-1].to_dict()
        profile = self._fetch_profile(ts_code)
        news_text = self._fetch_news(ts_code, evidence_start, end_date)
        sector_snapshot = self._build_sector_snapshot(profile, trade_date)

        return StockMoveDataset(
            profile=profile,
            trade_date=trade_date,
            history=history.sort_values("Date").reset_index(drop=True),
            latest_row=latest_row,
            news_text=news_text,
            sector_snapshot=sector_snapshot,
            evidence_window_start=evidence_start,
            evidence_window_end=end_date,
        )

    def _fetch_history(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        errors: list[str] = []
        for loader in (get_tushare_ohlcv, get_akshare_ohlcv):
            try:
                return loader(symbol, start_date, end_date)
            except Exception as exc:  # pragma: no cover - best-effort fallback
                errors.append(str(exc))
        raise RuntimeError("; ".join(errors))

    def _enrich_daily_basic(self, symbol: str, history: pd.DataFrame, start_date: str, end_date: str) -> pd.DataFrame:
        if history.empty or "TurnoverRate" in history.columns:
            return history
        try:
            pro = tushare_pro_client()
            daily_basic = pro.daily_basic(
                ts_code=symbol,
                start_date=start_date.replace("-", ""),
                end_date=end_date.replace("-", ""),
                fields="ts_code,trade_date,turnover_rate,volume_ratio",
            )
        except Exception:
            return history
        if daily_basic is None or daily_basic.empty:
            return history

        metrics = daily_basic.rename(
            columns={
                "trade_date": "Date",
                "turnover_rate": "TurnoverRate",
                "volume_ratio": "VolumeRatio",
            }
        ).copy()
        keep = [col for col in ["Date", "TurnoverRate", "VolumeRatio"] if col in metrics.columns]
        if "Date" not in keep:
            return history
        metrics = metrics[keep]
        metrics["Date"] = pd.to_datetime(metrics["Date"].astype(str), format="%Y%m%d", errors="coerce")
        for col in ["TurnoverRate", "VolumeRatio"]:
            if col in metrics:
                metrics[col] = pd.to_numeric(metrics[col], errors="coerce")
        return history.merge(metrics.dropna(subset=["Date"]), on="Date", how="left")

    def _fetch_profile(self, symbol: str) -> StockProfile:
        try:
            pro = tushare_pro_client()
            basic = pro.stock_basic(
                exchange="",
                list_status="L",
                fields="ts_code,name,area,industry,market",
            )
            row = basic[basic["ts_code"] == symbol]
            if not row.empty:
                payload = row.iloc[0].to_dict()
                return StockProfile(
                    symbol=symbol,
                    name=payload.get("name"),
                    industry=payload.get("industry"),
                    market=payload.get("market"),
                    area=payload.get("area"),
                )
        except Exception:
            pass
        return StockProfile(symbol=symbol)

    def _fetch_news(self, symbol: str, start_date: str, end_date: str) -> str:
        try:
            return route_to_vendor("get_news", symbol, start_date, end_date)
        except (RuntimeError, DataVendorUnavailable, ValueError):
            return f"No reliable news evidence found for {symbol} between {start_date} and {end_date}"

    def _build_sector_snapshot(self, profile: StockProfile, trade_date: str) -> SectorSnapshot:
        notes = []
        if not profile.industry:
            notes.append("行业信息暂缺，板块联动判断可信度较低。")
            return SectorSnapshot(
                industry=profile.industry,
                concepts=profile.concepts,
                sector_performance=None,
                related_stock_performance=[],
                notes=notes,
            )

        board = None
        try:
            board = self.board_fetcher.fetch_industry_snapshot(profile.industry, trade_date)
        except Exception:
            board = None

        if board is None or board.pct_change is None:
            notes.append("行业板块涨跌数据暂缺，板块联动判断需保守处理。")
        if not board or not board.top_constituents:
            notes.append("行业板块成分股明细暂缺。")
        notes.append("概念板块数据仍未稳定接入，当前板块联动以行业板块为主。")
        return SectorSnapshot(
            industry=profile.industry,
            concepts=profile.concepts,
            sector_performance=f"{board.pct_change:.2f}%" if board and board.pct_change is not None else None,
            related_stock_performance=board.top_constituents if board and board.top_constituents else [],
            notes=notes,
        )
