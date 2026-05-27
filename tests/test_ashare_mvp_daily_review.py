from __future__ import annotations

import copy
import tempfile
import unittest

import pytest

import tradingagents.default_config as default_config
from tradingagents.ashare_mvp.data.board_data import IndustryBoardSnapshot
from tradingagents.ashare_mvp.daily_review_features import DailyReviewFeatureExtractor
from tradingagents.ashare_mvp.data.daily_review import AShareDailyReviewFetcher
from tradingagents.ashare_mvp.pipeline.daily_review_pipeline import DailyReviewPipeline
from tradingagents.ashare_mvp.schemas import (
    DailyIndexSnapshot,
    DailyMover,
    DailyReviewDataset,
    DailyReviewInput,
)
from tradingagents.dataflows.config import set_config


class _FakeDailyFetcher:
    def fetch(self, trade_date: str, top_n_movers: int = 10, top_n_sectors: int = 5) -> DailyReviewDataset:
        return DailyReviewDataset(
            trade_date=trade_date,
            indices=[
                DailyIndexSnapshot(symbol="000001.SH", name="上证指数", pct_change=0.8),
                DailyIndexSnapshot(symbol="399001.SZ", name="深证成指", pct_change=1.1),
                DailyIndexSnapshot(symbol="399006.SZ", name="创业板指", pct_change=1.6),
            ],
            market_turnover=1_250_000_000.0,
            top_gainers=[
                DailyMover(symbol="300001.SZ", name="甲公司", pct_change=9.8, amount=12000000, industry="机器人"),
                DailyMover(symbol="300002.SZ", name="乙公司", pct_change=7.2, amount=9000000, industry="机器人"),
            ],
            top_losers=[
                DailyMover(symbol="600001.SH", name="丙公司", pct_change=-6.1, amount=8000000, industry="消费"),
                DailyMover(symbol="600002.SH", name="丁公司", pct_change=-4.7, amount=7500000, industry="消费"),
            ],
            top_by_amount=[
                DailyMover(symbol="300001.SZ", name="甲公司", pct_change=9.8, amount=12000000, industry="机器人"),
                DailyMover(symbol="300010.SZ", name="戊公司", pct_change=3.1, amount=11000000, industry="机器人"),
                DailyMover(symbol="600010.SH", name="己公司", pct_change=2.5, amount=10500000, industry="算力"),
            ],
            hot_sectors=[
                {"name": "机器人", "count": 2, "symbols": ["300001.SZ", "300010.SZ"], "pct_change": 5.2},
                {"name": "算力", "count": 1, "symbols": ["600010.SH"], "pct_change": 3.1},
            ],
            important_news_text="## China Market News\n\n### 政策继续支持科技制造和机器人方向 (source: test)\n### 市场关注流动性预期变化 (source: test)\n",
            notes=[],
        )


class _FakeBoardFetcher:
    def fetch_hot_industry_boards(self, top_n: int = 5):
        return [
            IndustryBoardSnapshot(name="机器人", pct_change=5.2, top_constituents=[{"symbol": "300001.SZ"}]),
            IndustryBoardSnapshot(name="算力", pct_change=3.1, top_constituents=[{"symbol": "600010.SH"}]),
        ][:top_n]


@pytest.mark.unit
class DailyReviewFeatureTests(unittest.TestCase):
    def test_extract_derives_sentiment(self):
        dataset = _FakeDailyFetcher().fetch("2026-05-27")
        features = DailyReviewFeatureExtractor().extract(dataset)

        self.assertEqual(features.market_sentiment, "偏强")
        self.assertGreater(features.avg_gainer_move, 8.0)


@pytest.mark.unit
class DailyReviewPipelineTests(unittest.TestCase):
    def setUp(self):
        cfg = copy.deepcopy(default_config.DEFAULT_CONFIG)
        cfg["data_cache_dir"] = tempfile.mkdtemp()
        set_config(cfg)

    def test_pipeline_renders_markdown(self):
        pipeline = DailyReviewPipeline(fetcher=_FakeDailyFetcher(), llm=None)

        report = pipeline.run(DailyReviewInput(trade_date="2026-05-27"))

        self.assertIn("# A 股盘后复盘：2026-05-27", report.markdown)
        self.assertIn("## 2. 今天哪些方向更活跃？", report.markdown)
        self.assertIn("## 3. 哪些个股需要复盘？", report.markdown)
        self.assertIn("| 股票 | 涨跌幅 | 所属板块 | 观察线索 | 需要注意 |", report.markdown)
        self.assertIn("## 5. 明天重点观察什么？", report.markdown)
        self.assertIn("## 6. 输出边界", report.markdown)
        self.assertIn("机器人", report.markdown)
        self.assertIn("所属行业板块同步走强", report.markdown)
        self.assertNotIn("偏偏强", report.markdown)

    def test_pipeline_enriches_mover_reason_and_risk(self):
        pipeline = DailyReviewPipeline(fetcher=_FakeDailyFetcher(), llm=None)

        report = pipeline.run(DailyReviewInput(trade_date="2026-05-27"))

        top_gainer = report.dataset.top_gainers[0]
        self.assertIn("成交额活跃", top_gainer.reason)
        self.assertIn("机器人", top_gainer.reason)
        self.assertIn("分歧可能上升", top_gainer.risk)

    def test_real_fetcher_hot_sectors_prefers_board_data(self):
        fetcher = AShareDailyReviewFetcher(board_fetcher=_FakeBoardFetcher())
        result = fetcher._build_hot_sectors(
            top_by_amount=[
                DailyMover(symbol="300001.SZ", industry="机器人"),
                DailyMover(symbol="600010.SH", industry="算力"),
            ],
            top_n_sectors=2,
            notes=[],
        )

        self.assertEqual(result[0]["name"], "机器人")
        self.assertEqual(result[0]["symbols"], ["300001.SZ"])
