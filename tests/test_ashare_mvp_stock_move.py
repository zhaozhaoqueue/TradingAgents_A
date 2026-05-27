from __future__ import annotations

import copy
import tempfile
import unittest

import pandas as pd
import pytest

import tradingagents.default_config as default_config
from tradingagents.ashare_mvp.data.board_data import IndustryBoardSnapshot
from tradingagents.ashare_mvp.data.stock_move import AShareStockMoveFetcher
from tradingagents.ashare_mvp.feature_extractor import FeatureExtractor
from tradingagents.ashare_mvp.pipeline.stock_move_pipeline import StockMovePipeline
from tradingagents.ashare_mvp.schemas import (
    SectorSnapshot,
    StockMoveDataset,
    StockMoveInput,
    StockProfile,
)
from tradingagents.dataflows.config import set_config


class _FakeFetcher:
    def fetch(self, symbol: str, trade_date: str) -> StockMoveDataset:
        history = pd.DataFrame(
            [
                {"Date": "2026-05-20", "Open": 10.0, "High": 10.3, "Low": 9.9, "Close": 10.1, "Volume": 1000, "Amount": 10000},
                {"Date": "2026-05-21", "Open": 10.1, "High": 10.4, "Low": 10.0, "Close": 10.2, "Volume": 1200, "Amount": 12000},
                {"Date": "2026-05-22", "Open": 10.2, "High": 10.5, "Low": 10.1, "Close": 10.3, "Volume": 1300, "Amount": 13000},
                {"Date": "2026-05-23", "Open": 10.4, "High": 10.7, "Low": 10.3, "Close": 10.5, "Volume": 1500, "Amount": 15000},
                {"Date": "2026-05-26", "Open": 10.6, "High": 11.0, "Low": 10.5, "Close": 10.9, "Volume": 2600, "Amount": 26000},
                {"Date": "2026-05-27", "Open": 11.0, "High": 11.6, "Low": 10.9, "Close": 11.5, "Volume": 4200, "Amount": 42000},
            ]
        )
        history["Date"] = pd.to_datetime(history["Date"])
        return StockMoveDataset(
            profile=StockProfile(symbol=symbol, name="测试股份", industry="新能源"),
            trade_date=trade_date,
            history=history,
            latest_row=history.iloc[-1].to_dict(),
            news_text="## 600000.SH\n\n### 公司发布新产线规划 (source: test)\n### 行业政策继续加码 (source: test)\n",
            sector_snapshot=SectorSnapshot(
                industry="新能源",
                concepts=["储能"],
                notes=["行业景气线索存在。"],
            ),
            evidence_window_start="2026-05-20",
            evidence_window_end=trade_date,
        )


class _FakeBoardFetcher:
    def fetch_industry_snapshot(self, industry_name: str, trade_date: str):
        return IndustryBoardSnapshot(
            name=industry_name,
            pct_change=2.4,
            top_constituents=[
                {"symbol": "300001", "name": "甲公司", "pct_change": 9.8},
                {"symbol": "300010", "name": "乙公司", "pct_change": 6.5},
            ],
        )


@pytest.mark.unit
class FeatureExtractorTests(unittest.TestCase):
    def test_extract_identifies_price_and_volume_move(self):
        dataset = _FakeFetcher().fetch("600000.SH", "2026-05-27")
        features = FeatureExtractor().extract(dataset)

        self.assertGreater(features.pct_change, 5)
        self.assertGreater(features.volume_ratio_vs_20d, 1.5)
        self.assertIn("price_move", features.flags)


@pytest.mark.unit
class StockMovePipelineTests(unittest.TestCase):
    def setUp(self):
        cfg = copy.deepcopy(default_config.DEFAULT_CONFIG)
        cfg["data_cache_dir"] = tempfile.mkdtemp()
        set_config(cfg)

    def test_pipeline_renders_markdown_without_llm(self):
        pipeline = StockMovePipeline(fetcher=_FakeFetcher(), llm=None)

        report = pipeline.run(StockMoveInput(symbol="600000.SH", trade_date="2026-05-27"))

        self.assertEqual(report.profile.name, "测试股份")
        self.assertIn("# 测试股份（600000.SH）今日异动解读", report.markdown)
        self.assertIn("## 6. 社群短版", report.markdown)
        self.assertNotIn("买入", report.markdown)


@pytest.mark.unit
class StockMoveFetcherBoardTests(unittest.TestCase):
    def test_sector_snapshot_includes_board_data(self):
        fetcher = AShareStockMoveFetcher(board_fetcher=_FakeBoardFetcher())

        snapshot = fetcher._build_sector_snapshot(
            StockProfile(symbol="600000.SH", industry="新能源"),
            "2026-05-27",
        )

        self.assertEqual(snapshot.sector_performance, "2.40%")
        self.assertEqual(snapshot.related_stock_performance[0]["symbol"], "300001")
