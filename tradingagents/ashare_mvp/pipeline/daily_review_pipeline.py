from __future__ import annotations

import re

from ..analysis import build_default_llm
from ..compliance import scan_prohibited_phrases
from ..daily_review_features import DailyReviewFeatureExtractor
from ..data.daily_review import AShareDailyReviewFetcher
from ..renderers import render_daily_review_report
from ..schemas import DailyMover, DailyReviewInput, DailyReviewReport, StockMoveAnalysis


class DailyReviewPipeline:
    def __init__(
        self,
        fetcher: AShareDailyReviewFetcher | None = None,
        extractor: DailyReviewFeatureExtractor | None = None,
        llm=None,
    ):
        self.fetcher = fetcher or AShareDailyReviewFetcher()
        self.extractor = extractor or DailyReviewFeatureExtractor()
        self.llm = llm

    def run(self, payload: DailyReviewInput) -> DailyReviewReport:
        dataset = self.fetcher.fetch(
            payload.trade_date,
            top_n_movers=payload.top_n_movers,
            top_n_sectors=payload.top_n_sectors,
        )
        features = self.extractor.extract(dataset)
        llm = self.llm
        if llm is None:
            try:
                llm = build_default_llm()
            except Exception:
                llm = None
        # 第一版先使用规则化摘要，后续再替换成更强的角色提示词。
        market = self._market_analysis(dataset, features)
        sector = self._sector_analysis(dataset, features)
        news = self._news_analysis(dataset)
        self._enrich_movers(dataset)
        compliance = self._compliance_notes(dataset, features)
        report = DailyReviewReport(
            input=payload,
            dataset=dataset,
            features=features,
            market_analysis=market,
            sector_analysis=sector,
            news_analysis=news,
            compliance_notes=compliance,
            markdown="",
        )
        report.markdown = render_daily_review_report(report)
        prohibited = scan_prohibited_phrases(report.markdown)
        if prohibited:
            report.compliance_notes.extend([f"检测到敏感表达，需要人工复核：{', '.join(prohibited)}"])
            report.markdown = render_daily_review_report(report)
        return report

    def _market_analysis(self, dataset, features) -> StockMoveAnalysis:
        index_moves = [idx.pct_change for idx in dataset.indices if idx.pct_change is not None]
        summary = "指数表现分化，复盘重点应放在结构而不是单一指数。"
        if index_moves and all(value > 0 for value in index_moves):
            summary = "三大指数普遍收涨，盘面整体偏强。"
        elif index_moves and all(value < 0 for value in index_moves):
            summary = "三大指数普遍承压，市场整体偏弱。"
        bullets = [
            f"市场成交额约为 {_fmt_num(dataset.market_turnover)}。",
            f"样本内上涨方向平均波动约为 {features.avg_gainer_move:.2f}%。" if features.avg_gainer_move is not None else "上涨方向样本不足。",
            f"样本内下跌方向平均波动约为 {features.avg_loser_move:.2f}%。" if features.avg_loser_move is not None else "下跌方向样本不足。",
        ]
        return StockMoveAnalysis(summary=summary, bullets=bullets, risks=dataset.notes[:2])

    def _sector_analysis(self, dataset, features) -> StockMoveAnalysis:
        if not dataset.hot_sectors:
            return StockMoveAnalysis(
                summary="热点板块数据不足，当前只能做弱判断。",
                bullets=["第一版板块判断基于成交额活跃个股的行业聚类。"],
                risks=["板块主线判断可信度有限。"],
            )
        names = [item["name"] for item in dataset.hot_sectors[:3]]
        return StockMoveAnalysis(
            summary=f"当前活跃方向主要集中在：{'、'.join(names)}。",
            bullets=[f"{item['name']} 在高成交额个股中出现 {item['count']} 次。" for item in dataset.hot_sectors[:3]],
            risks=["热点板块仍需结合更完整的概念和题材数据复核。"],
        )

    def _news_analysis(self, dataset) -> StockMoveAnalysis:
        titles = [line.strip("# ").strip() for line in dataset.important_news_text.splitlines() if line.strip().startswith("### ")]
        if not titles:
            return StockMoveAnalysis(
                summary="当前新闻摘要较弱，盘后消息面需要人工补充。",
                bullets=["重要新闻获取失败或结构化标题不足。"],
                risks=["若消息面有重大增量，当前报告可能未完整覆盖。"],
            )
        return StockMoveAnalysis(
            summary="盘后重要新闻已抓取，可用于解释市场主线和次级催化。",
            bullets=[f"已抓取 {len(titles)} 条盘后候选新闻。"] + titles[:2],
            evidence=titles[:5],
        )

    def _compliance_notes(self, dataset, features) -> list[str]:
        return list(
            dict.fromkeys(
                [
                    "本复盘仅整理公开信息，不构成投资建议。",
                    "热点主线和个股归因属于盘后信息整理，不等于后续走势判断。",
                    *dataset.notes,
                ]
            )
        )

    def _enrich_movers(self, dataset) -> None:
        news_titles = [
            line.strip("# ").strip()
            for line in dataset.important_news_text.splitlines()
            if line.strip().startswith("### ")
        ]
        amount_symbols = {m.symbol for m in dataset.top_by_amount}
        sector_map = {item.get("name"): item for item in dataset.hot_sectors}
        for bucket_name, movers in (
            ("gainer", dataset.top_gainers),
            ("loser", dataset.top_losers),
            ("amount", dataset.top_by_amount),
        ):
            for mover in movers:
                mover.is_amount_leader = mover.symbol in amount_symbols
                sector = sector_map.get(mover.industry or "")
                if sector and mover.industry_pct_change is None:
                    mover.industry_pct_change = _safe_float(sector.get("pct_change"))
                mover.reason = self._build_reason(mover, news_titles, bucket_name)
                mover.risk = self._build_risk(mover, bucket_name)

    def _build_reason(self, mover: DailyMover, news_titles: list[str], bucket_name: str) -> str:
        reasons: list[str] = []
        if mover.pct_change is not None:
            if bucket_name == "gainer" and mover.pct_change >= 7:
                reasons.append("涨幅较大，当日资金关注度明显提升")
            elif bucket_name == "loser" and mover.pct_change <= -5:
                reasons.append("跌幅较深，盘中承压明显")
        if mover.is_amount_leader:
            reasons.append("成交额活跃，说明资金参与度较高")
        if mover.industry_pct_change is not None:
            if mover.industry_pct_change >= 2:
                reasons.append(f"所属行业板块同步走强（{mover.industry_pct_change:.2f}%）")
            elif mover.industry_pct_change <= -2:
                reasons.append(f"所属行业板块同步承压（{mover.industry_pct_change:.2f}%）")

        keyword = self._match_news_keyword(mover, news_titles)
        if keyword:
            reasons.append(f"盘后新闻中出现与 {keyword} 相关的政策或市场线索")

        if not reasons:
            if bucket_name == "gainer":
                reasons.append("上涨居前，但当前公开信息仍不足以单独解释全部波动")
            elif bucket_name == "loser":
                reasons.append("跌幅居前，但当前缺少足够的公开信息确认单一原因")
            else:
                reasons.append("成交额居前，说明当日市场关注度较高")
        return "；".join(reasons)

    def _build_risk(self, mover: DailyMover, bucket_name: str) -> str:
        risks: list[str] = []
        if bucket_name == "gainer":
            risks.append("大幅波动后，次日分歧可能上升")
        elif bucket_name == "loser":
            risks.append("若无新增公开信息，仍需观察波动是否继续放大")
        else:
            risks.append("高成交额不等于趋势已确认")

        if mover.industry_pct_change is None:
            risks.append("行业板块数据不足，联动判断需保守")
        if mover.pct_change is not None and abs(mover.pct_change) >= 9:
            risks.append("单日波动较大，需结合公告和成交结构复核")
        return "；".join(dict.fromkeys(risks))

    def _match_news_keyword(self, mover: DailyMover, news_titles: list[str]) -> str | None:
        candidates = [mover.name or "", mover.industry or ""]
        for candidate in candidates:
            candidate = candidate.strip()
            if len(candidate) < 2:
                continue
            pattern = re.escape(candidate)
            if any(re.search(pattern, title, re.IGNORECASE) for title in news_titles):
                return candidate
        return None


def _safe_float(value) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def _fmt_num(value: float | None) -> str:
    if value is None:
        return "暂缺"
    return f"{value:,.2f}"
