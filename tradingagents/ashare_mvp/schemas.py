from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd


@dataclass(slots=True)
class StockMoveInput:
    symbol: str
    trade_date: str


@dataclass(slots=True)
class StockProfile:
    symbol: str
    name: str | None = None
    industry: str | None = None
    market: str | None = None
    area: str | None = None
    concepts: list[str] = field(default_factory=list)


@dataclass(slots=True)
class SectorSnapshot:
    industry: str | None = None
    concepts: list[str] = field(default_factory=list)
    sector_performance: str | None = None
    related_stock_performance: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class StockMoveDataset:
    profile: StockProfile
    trade_date: str
    history: pd.DataFrame
    latest_row: dict[str, Any]
    news_text: str
    sector_snapshot: SectorSnapshot
    evidence_window_start: str
    evidence_window_end: str


@dataclass(slots=True)
class StockMoveFeatures:
    close: float | None = None
    pct_change: float | None = None
    amount: float | None = None
    volume: float | None = None
    turnover_rate: float | None = None
    volume_ratio_vs_5d: float | None = None
    volume_ratio_vs_20d: float | None = None
    close_5ma: float | None = None
    close_10ma: float | None = None
    close_20ma: float | None = None
    position_vs_20d_high: float | None = None
    position_vs_20d_low: float | None = None
    breakout_20d_high: bool = False
    rebound_from_20d_low: bool = False
    days_available: int = 0
    flags: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class StockMoveAnalysis:
    summary: str
    bullets: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)


@dataclass(slots=True)
class StockMoveReport:
    input: StockMoveInput
    profile: StockProfile
    sector_snapshot: SectorSnapshot
    features: StockMoveFeatures
    market_analysis: StockMoveAnalysis
    news_analysis: StockMoveAnalysis
    sector_analysis: StockMoveAnalysis
    compliance_notes: list[str]
    markdown: str


@dataclass(slots=True)
class DailyReviewInput:
    trade_date: str
    top_n_sectors: int = 5
    top_n_movers: int = 10


@dataclass(slots=True)
class DailyIndexSnapshot:
    symbol: str
    name: str
    close: float | None = None
    pct_change: float | None = None
    amount: float | None = None


@dataclass(slots=True)
class DailyMover:
    symbol: str
    name: str | None = None
    pct_change: float | None = None
    amount: float | None = None
    industry: str | None = None
    industry_pct_change: float | None = None
    is_amount_leader: bool = False
    reason: str | None = None
    risk: str | None = None


@dataclass(slots=True)
class DailyReviewDataset:
    trade_date: str
    indices: list[DailyIndexSnapshot]
    market_turnover: float | None
    top_gainers: list[DailyMover]
    top_losers: list[DailyMover]
    top_by_amount: list[DailyMover]
    hot_sectors: list[dict[str, Any]] = field(default_factory=list)
    important_news_text: str = ""
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class DailyReviewFeatures:
    rising_count: int | None = None
    falling_count: int | None = None
    flat_count: int | None = None
    avg_gainer_move: float | None = None
    avg_loser_move: float | None = None
    market_sentiment: str | None = None
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class DailyReviewReport:
    input: DailyReviewInput
    dataset: DailyReviewDataset
    features: DailyReviewFeatures
    market_analysis: StockMoveAnalysis
    sector_analysis: StockMoveAnalysis
    news_analysis: StockMoveAnalysis
    compliance_notes: list[str]
    markdown: str
