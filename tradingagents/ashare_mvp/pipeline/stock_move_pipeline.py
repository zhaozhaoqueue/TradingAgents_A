from __future__ import annotations

from tradingagents.dataflows.a_share_utils import normalize_a_share_symbol

from ..analysis import (
    LLMRoleRunner,
    build_default_llm,
    compliance_prompt,
    market_prompt,
    news_prompt,
    sector_prompt,
)
from ..compliance import scan_prohibited_phrases
from ..data.stock_move import AShareStockMoveFetcher
from ..feature_extractor import FeatureExtractor
from ..renderers import render_stock_move_report
from ..schemas import StockMoveAnalysis, StockMoveInput, StockMoveReport


class StockMovePipeline:
    def __init__(
        self,
        fetcher: AShareStockMoveFetcher | None = None,
        extractor: FeatureExtractor | None = None,
        llm=None,
    ):
        self.fetcher = fetcher or AShareStockMoveFetcher()
        self.extractor = extractor or FeatureExtractor()
        self.llm = llm
        self.market_runner = LLMRoleRunner("Market Analyst", market_prompt)
        self.news_runner = LLMRoleRunner("News Analyst", news_prompt)
        self.sector_runner = LLMRoleRunner("Sector Analyst", sector_prompt)
        self.compliance_runner = LLMRoleRunner(
            "Risk / Compliance Editor",
            lambda dataset, features: compliance_prompt(
                dataset,
                features,
                {
                    "market": self._last_market,
                    "news": self._last_news,
                    "sector": self._last_sector,
                },
            ),
        )
        self._last_market = StockMoveAnalysis(summary="")
        self._last_news = StockMoveAnalysis(summary="")
        self._last_sector = StockMoveAnalysis(summary="")

    def run(self, payload: StockMoveInput) -> StockMoveReport:
        payload = StockMoveInput(
            symbol=normalize_a_share_symbol(payload.symbol),
            trade_date=payload.trade_date,
        )
        dataset = self.fetcher.fetch(payload.symbol, payload.trade_date)
        features = self.extractor.extract(dataset)
        llm = self.llm
        if llm is None:
            try:
                llm = build_default_llm()
            except Exception:
                llm = None

        if llm is None:
            market, news, sector, compliance = self._run_rule_fallback(dataset, features)
        else:
            try:
                market = self.market_runner.run(llm, dataset, features)
                news = self.news_runner.run(llm, dataset, features)
                sector = self.sector_runner.run(llm, dataset, features)
                self._last_market = market
                self._last_news = news
                self._last_sector = sector
                compliance_analysis = self.compliance_runner.run(llm, dataset, features)
                compliance = compliance_analysis.risks + compliance_analysis.bullets
            except Exception:
                market, news, sector, compliance = self._run_rule_fallback(dataset, features)

        report = StockMoveReport(
            input=payload,
            profile=dataset.profile,
            sector_snapshot=dataset.sector_snapshot,
            features=features,
            market_analysis=market,
            news_analysis=news,
            sector_analysis=sector,
            compliance_notes=compliance,
            markdown="",
        )
        report.markdown = render_stock_move_report(report)
        prohibited = scan_prohibited_phrases(report.markdown)
        if prohibited:
            report.compliance_notes.extend([f"检测到敏感表达，需要人工复核：{', '.join(prohibited)}"])
            report.markdown = render_stock_move_report(report)
        return report

    def _rule_market_analysis(self, features) -> StockMoveAnalysis:
        bullets = []
        evidence = []
        risks = []
        if features.pct_change is not None:
            bullets.append(f"当日涨跌幅约为 {features.pct_change:.2f}%，已达到需要关注的价格波动级别。")
            evidence.append(f"价格波动：{features.pct_change:.2f}%")
        if features.volume_ratio_vs_20d is not None:
            bullets.append(f"量能约为 20 日均量的 {features.volume_ratio_vs_20d:.2f} 倍。")
            evidence.append(f"量比（vs 20 日均量）：{features.volume_ratio_vs_20d:.2f}")
        if features.breakout_20d_high:
            bullets.append("价格接近或突破近 20 日高点，说明短期走势较强。")
        if not bullets:
            bullets.append("量价特征暂不充分，当前更像常规波动。")
            risks.append("技术信号不强，异动归因可能偏弱。")
        return StockMoveAnalysis(
            summary="从量价结构看，个股当天存在一定异动特征。" if bullets else "量价特征不强。",
            bullets=bullets,
            evidence=evidence,
            risks=risks,
        )

    def _rule_news_analysis(self, news_text: str) -> StockMoveAnalysis:
        summary = "新闻面存在可参考的公开信息，但需要区分直接催化与背景噪音。"
        if news_text.startswith("No reliable news evidence found"):
            summary = "新闻证据较弱，当前缺少高质量公开信息支撑。"
            return StockMoveAnalysis(summary=summary, bullets=[summary], risks=["新闻证据不足，异动原因可能更多来自盘面资金行为。"])
        lines = [line.strip("# ").strip() for line in news_text.splitlines() if line.strip().startswith("### ")]
        evidence = lines[:3]
        bullets = [f"近 7 日内抓取到 {len(lines)} 条候选新闻标题。" if lines else "已抓取新闻，但结构化标题不足。"]
        return StockMoveAnalysis(summary=summary, bullets=bullets, evidence=evidence, risks=[])

    def _rule_sector_analysis(self, notes: list[str]) -> StockMoveAnalysis:
        summary = "当前板块联动判断偏保守，更多依赖行业线索和新闻交叉验证。"
        return StockMoveAnalysis(
            summary=summary,
            bullets=["第一版板块数据仍在补齐中，暂以行业信息作为板块代理。"],
            evidence=notes[:2],
            risks=["板块共振判断可信度有限。"],
        )

    def _rule_compliance(self, *analyses: StockMoveAnalysis) -> list[str]:
        notes = ["本报告仅整理公开信息，不构成投资建议。"]
        for analysis in analyses:
            notes.extend(analysis.risks)
        return list(dict.fromkeys(notes))

    def _run_rule_fallback(self, dataset, features):
        market = self._rule_market_analysis(features)
        news = self._rule_news_analysis(dataset.news_text)
        sector = self._rule_sector_analysis(dataset.sector_snapshot.notes)
        compliance = self._rule_compliance(market, news, sector)
        return market, news, sector, compliance
