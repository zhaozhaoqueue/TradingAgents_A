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
from tradingagents.ashare_mvp.analysis import _parse_analysis
from tradingagents.ashare_mvp.pipeline.stock_move_pipeline import StockMovePipeline
from tradingagents.ashare_mvp.renderers import render_stock_move_report
from tradingagents.dataflows.akshare_data import _normalize_hist
from tradingagents.dataflows.tushare_pro import _normalize_ohlcv as _normalize_tushare_ohlcv
from tradingagents.ashare_mvp.schemas import (
    SectorSnapshot,
    StockMoveAnalysis,
    StockMoveDataset,
    StockMoveFeatures,
    StockMoveInput,
    StockProfile,
    StockMoveReport,
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
                {
                    "Date": "2026-05-27",
                    "Open": 11.0,
                    "High": 11.6,
                    "Low": 10.9,
                    "Close": 11.5,
                    "Volume": 4200,
                    "Amount": 42000,
                    "TurnoverRate": 3.21,
                },
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

    def fetch_stock_concepts(self, symbol: str, top_n: int = 3):
        return [
            type(
                "ConceptBoard",
                (),
                {
                    "name": "储能",
                    "pct_change": 4.6,
                    "board_code": "GN1",
                    "top_constituents": [{"symbol": "300111.SZ", "name": "甲概念股", "pct_change": 8.8}],
                },
            )()
        ][:top_n]

    def fetch_stock_concepts_by_date(self, symbol: str, trade_date: str | None, top_n: int = 3):
        return self.fetch_stock_concepts(symbol, top_n=top_n)


class _FakeProClient:
    def daily_basic(self, **kwargs):
        return pd.DataFrame(
            [
                {"ts_code": "600000.SH", "trade_date": "20260526", "turnover_rate": 2.1, "volume_ratio": 1.2},
                {"ts_code": "600000.SH", "trade_date": "20260527", "turnover_rate": 3.4, "volume_ratio": 1.5},
            ]
        )


@pytest.mark.unit
class FeatureExtractorTests(unittest.TestCase):
    def test_extract_identifies_price_and_volume_move(self):
        dataset = _FakeFetcher().fetch("600000.SH", "2026-05-27")
        features = FeatureExtractor().extract(dataset)

        self.assertGreater(features.pct_change, 5)
        self.assertGreater(features.volume_ratio_vs_20d, 1.5)
        self.assertEqual(features.turnover_rate, 3.21)
        self.assertIn("price_move", features.flags)

    def test_akshare_history_preserves_turnover_rate(self):
        df = pd.DataFrame(
            [
                {
                    "日期": "2026-05-27",
                    "开盘": 10,
                    "最高": 11,
                    "最低": 9,
                    "收盘": 10.5,
                    "成交量": 1000,
                    "成交额": 2000,
                    "换手率": 4.56,
                }
            ]
        )

        normalized = _normalize_hist(df)

        self.assertEqual(normalized.iloc[0]["TurnoverRate"], 4.56)

    def test_tushare_history_normalizes_amount_to_yuan(self):
        df = pd.DataFrame(
            [
                {
                    "trade_date": "20260527",
                    "open": 10,
                    "high": 11,
                    "low": 9,
                    "close": 10.5,
                    "vol": 1000,
                    "amount": 22373358.9,
                }
            ]
        )

        normalized = _normalize_tushare_ohlcv(df)

        self.assertEqual(normalized.iloc[0]["Amount"], 22373358900.0)


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
        self.assertIn("## 2. 今天为什么这样走？", report.markdown)
        self.assertIn("### 2.1 先看盘面：有没有明显异常？", report.markdown)
        self.assertIn("### 2.4 最后判断：这个解释有多可靠？", report.markdown)
        self.assertIn("## 6. 后续怎么观察？", report.markdown)
        self.assertIn("### 6.2 接下来重点看什么？", report.markdown)
        self.assertIn("## 7. 社群短版", report.markdown)
        self.assertNotIn("买入", report.markdown)

    def test_parse_analysis_keeps_string_evidence_as_one_item(self):
        analysis = _parse_analysis('{"summary":"ok","evidence":"三条新闻均未直接提及个股"}', "fallback")

        self.assertEqual(analysis.evidence, ["三条新闻均未直接提及个股"])

    def test_parse_analysis_accepts_fenced_json(self):
        analysis = _parse_analysis(
            '```json\n{"summary":"ok","evidence":{"weak":["行业新闻未点名个股"]}}\n```',
            "fallback",
        )

        self.assertEqual(analysis.summary, "ok")
        self.assertEqual(analysis.evidence, ["weak: 行业新闻未点名个股"])

    def test_render_filters_internal_compliance_notes(self):
        report = StockMoveReport(
            input=StockMoveInput(symbol="600000.SH", trade_date="2026-05-27"),
            profile=StockProfile(symbol="600000.SH", name="测试股份", industry="新能源"),
            sector_snapshot=SectorSnapshot(industry="新能源"),
            features=StockMoveFeatures(pct_change=0.8, volume_ratio_vs_20d=0.9),
            market_analysis=StockMoveAnalysis(summary="盘面波动较弱。", bullets=["盘面波动较弱。"], evidence=[]),
            news_analysis=StockMoveAnalysis(
                summary="新闻未形成直接催化。",
                bullets=["测试股份相关消息未直接提及明确订单。"],
                evidence=["三条新闻均未直接提及个股"],
            ),
            sector_analysis=StockMoveAnalysis(summary="板块证据不足。", bullets=["板块数据暂缺，需复核。"], evidence=[]),
            compliance_notes=[
                "evidence 占位符显示编辑器未按照规范填充，存在合规审查漏洞。",
                "将行业信息直接外推到个股，可能带来误读风险。",
            ],
            markdown="",
        )

        markdown = render_stock_move_report(report)

        self.assertIn("# 测试股份（600000.SH）今日观察简报", markdown)
        self.assertIn("- 三条新闻均未直接提及个股", markdown)
        self.assertNotIn("\n- 三\n- 条\n- 新\n- 闻", markdown)
        self.assertNotIn("占位符", markdown)
        self.assertIn("可能带来误读风险", markdown)
        self.assertNotIn("合规审查", markdown)

    def test_observation_does_not_treat_negated_news_as_direct_evidence(self):
        report = StockMoveReport(
            input=StockMoveInput(symbol="600326.SH", trade_date="2026-05-26"),
            profile=StockProfile(symbol="600326.SH", name="西藏天路", industry="水泥"),
            sector_snapshot=SectorSnapshot(industry="水泥"),
            features=StockMoveFeatures(pct_change=-0.8, volume_ratio_vs_20d=0.7),
            market_analysis=StockMoveAnalysis(summary="小幅缩量。", bullets=["小幅缩量。"], evidence=[]),
            news_analysis=StockMoveAnalysis(
                summary="西藏天路未出现直接相关新闻。",
                bullets=[],
                evidence=["西藏天路未出现直接相关的公司新闻，仅有行业背景线索。"],
            ),
            sector_analysis=StockMoveAnalysis(summary="板块数据不足。", bullets=[], evidence=[]),
            compliance_notes=[],
            markdown="",
        )

        markdown = render_stock_move_report(report)

        self.assertIn("目前更多是行业或背景线索", markdown)
        self.assertNotIn("已经有个股相关公开信息", markdown)

    def test_render_filters_code_like_evidence_and_internal_review_notes(self):
        report = StockMoveReport(
            input=StockMoveInput(symbol="300750.SZ", trade_date="2026-05-27"),
            profile=StockProfile(symbol="300750.SZ", name="宁德时代", industry="电气设备"),
            sector_snapshot=SectorSnapshot(industry="电气设备"),
            features=StockMoveFeatures(amount=22_373_358_900.0, pct_change=3.06, volume_ratio_vs_20d=1.54),
            market_analysis=StockMoveAnalysis(
                summary="量价存在一定异动。",
                bullets=["close=414.8, pct_change=3.056%", "收盘高于5日均线。"],
                evidence=["rebound_from_20d_low=true", "收盘高于5日均线。"],
                risks=[],
            ),
            news_analysis=StockMoveAnalysis(
                summary="消息面存在公开线索。",
                bullets=["赛力斯蓝电增资，宁德时代参与入股。"],
                evidence=["证据强度: 强", "赛力斯蓝电增资，宁德时代参与入股。"],
                risks=[],
            ),
            sector_analysis=StockMoveAnalysis(summary="板块数据不足。", bullets=[], evidence=[]),
            compliance_notes=[
                "若未修正‘中等强度’等定性词汇，在合规审计中可能触发风险。",
                "行业板块涨跌数据暂缺，板块联动判断需要保守。",
            ],
            markdown="",
        )

        markdown = render_stock_move_report(report)

        self.assertIn("223.73亿元", markdown)
        self.assertNotIn("close=414.8", markdown)
        self.assertNotIn("rebound_from_20d_low", markdown)
        self.assertNotIn("证据强度", markdown)
        self.assertNotIn("若未修正", markdown)
        self.assertNotIn("强度: 中等", markdown)
        self.assertNotIn("price_move", markdown)
        self.assertIn("赛力斯蓝电增资，宁德时代参与入股。", markdown)


@pytest.mark.unit
class StockMoveFetcherBoardTests(unittest.TestCase):
    def test_enrich_daily_basic_merges_turnover_rate(self):
        fetcher = AShareStockMoveFetcher()
        history = pd.DataFrame(
            [
                {"Date": pd.Timestamp("2026-05-26"), "Close": 10.0},
                {"Date": pd.Timestamp("2026-05-27"), "Close": 10.5},
            ]
        )

        with unittest.mock.patch("tradingagents.ashare_mvp.data.stock_move.tushare_pro_client", return_value=_FakeProClient()):
            enriched = fetcher._enrich_daily_basic("600000.SH", history, "2026-05-26", "2026-05-27")

        self.assertEqual(enriched.iloc[-1]["TurnoverRate"], 3.4)

    def test_sector_snapshot_includes_board_data(self):
        fetcher = AShareStockMoveFetcher(board_fetcher=_FakeBoardFetcher())

        snapshot = fetcher._build_sector_snapshot(
            StockProfile(symbol="600000.SH", industry="新能源"),
            "2026-05-27",
        )

        self.assertEqual(snapshot.sector_performance, "2.40%")
        self.assertEqual(snapshot.related_stock_performance[0]["symbol"], "300001")
        self.assertEqual(snapshot.concepts, ["储能"])
        self.assertEqual(snapshot.concept_performances[0]["pct_change"], 4.6)
