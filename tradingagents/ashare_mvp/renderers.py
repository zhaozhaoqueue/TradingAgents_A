from __future__ import annotations

from .schemas import (
    DailyReviewFeatures,
    DailyReviewReport,
    StockMoveAnalysis,
    StockMoveFeatures,
    StockMoveReport,
)


def render_stock_move_report(report: StockMoveReport) -> str:
    profile = report.profile
    features = report.features
    lines = [
        f"# {profile.name or profile.symbol}（{profile.symbol}）今日异动解读",
        "",
        "## 1. 今日表现",
        "",
        f"- 涨跌幅：{_fmt_pct(features.pct_change)}",
        f"- 成交额：{_fmt_num(features.amount)}",
        f"- 换手率：{_fmt_pct(features.turnover_rate)}",
        f"- 所属行业：{profile.industry or '暂缺'}",
        f"- 近 20 日位置：{_position_text(features)}",
        "",
        "## 2. 可能原因",
        "",
    ]
    lines.extend(_bullet_block(report.market_analysis))
    lines.extend(_bullet_block(report.news_analysis))
    lines.extend(_bullet_block(report.sector_analysis))
    lines.extend(
        [
            "",
            "## 3. 公开信息依据",
            "",
        ]
    )
    for item in _merged_evidence(report.market_analysis, report.news_analysis, report.sector_analysis):
        lines.append(f"- {item}")
    lines.extend(
        [
            "",
            "## 4. 技术与资金表现",
            "",
            f"- 成交量：{_fmt_num(features.volume)}",
            f"- 均线位置：{_moving_average_text(features)}",
            f"- 是否放量：{_volume_text(features)}",
            f"- 是否突破/回落：{_breakout_text(features)}",
            "",
            "## 5. 风险与不确定性",
            "",
        ]
    )
    risks = []
    for analysis in (report.market_analysis, report.news_analysis, report.sector_analysis):
        risks.extend(analysis.risks)
    risks.extend(report.compliance_notes)
    if not risks:
        risks.append("当前版本未发现强烈合规风险，但仍需结合原始公告、新闻和盘后数据复核。")
    for risk in dict.fromkeys(risks):
        lines.append(f"- {risk}")
    lines.extend(
        [
            "",
            "## 6. 社群短版",
            "",
            build_social_short(report),
            "",
            "## 7. 小红书/短视频版",
            "",
            build_short_video_copy(report),
            "",
            "> 本内容基于公开资料自动整理，仅供信息参考，不构成投资建议。",
        ]
    )
    return "\n".join(lines)


def build_social_short(report: StockMoveReport) -> str:
    summary = report.market_analysis.summary or report.news_analysis.summary
    return (
        f"{report.profile.name or report.profile.symbol} 今日出现明显异动。"
        f"{summary} 风险上主要关注：{'; '.join(report.compliance_notes[:2]) or '消息面和板块联动证据仍需复核。'}"
    )


def build_short_video_copy(report: StockMoveReport) -> str:
    return (
        f"今天看 {report.profile.name or report.profile.symbol}，"
        f"盘面上最明显的特征是{_volume_text(report.features)}，"
        f"同时{report.news_analysis.summary or '消息面没有看到特别强的单一催化'}。"
        "如果要理解这次异动，更重要的是区分它是板块共振还是个股事件，"
        "目前结论只基于公开资料整理。"
    )


def _merged_evidence(*analyses: StockMoveAnalysis) -> list[str]:
    merged: list[str] = []
    for analysis in analyses:
        merged.extend(analysis.evidence)
        merged.extend(analysis.bullets[:1])
    if not merged:
        return ["当前证据较弱，需进一步核对原始行情与新闻。"]
    return list(dict.fromkeys(merged))


def _bullet_block(analysis: StockMoveAnalysis) -> list[str]:
    items = analysis.bullets or ([analysis.summary] if analysis.summary else [])
    return [f"- {item}" for item in items]


def _fmt_num(value: float | None) -> str:
    if value is None:
        return "暂缺"
    return f"{value:,.2f}"


def _fmt_pct(value: float | None) -> str:
    if value is None:
        return "暂缺"
    return f"{value:.2f}%"


def _position_text(features: StockMoveFeatures) -> str:
    if features.position_vs_20d_high is None:
        return "样本不足"
    return f"约为近 20 日高点的 {features.position_vs_20d_high:.1f}%"


def _moving_average_text(features: StockMoveFeatures) -> str:
    parts = []
    if features.close_5ma is not None and features.close is not None:
        parts.append("站上 5 日线" if features.close >= features.close_5ma else "位于 5 日线下方")
    if features.close_20ma is not None and features.close is not None:
        parts.append("站上 20 日线" if features.close >= features.close_20ma else "位于 20 日线下方")
    return "，".join(parts) if parts else "样本不足"


def _volume_text(features: StockMoveFeatures) -> str:
    ratio = features.volume_ratio_vs_20d
    if ratio is None:
        return "量能数据不足"
    if ratio >= 2:
        return f"明显放量，约为 20 日均量的 {ratio:.2f} 倍"
    if ratio >= 1.3:
        return f"温和放量，约为 20 日均量的 {ratio:.2f} 倍"
    return f"量能未明显放大，约为 20 日均量的 {ratio:.2f} 倍"


def _breakout_text(features: StockMoveFeatures) -> str:
    flags = []
    if features.breakout_20d_high:
        flags.append("接近或突破近 20 日高点")
    if features.rebound_from_20d_low:
        flags.append("存在低位反弹迹象")
    return "；".join(flags) if flags else "未见明确突破或回落形态"


def render_daily_review_report(report: DailyReviewReport) -> str:
    dataset = report.dataset
    features = report.features
    lines = [
        f"# A 股盘后复盘：{dataset.trade_date}",
        "",
        "## 1. 今日市场概览",
        "",
    ]
    for index in dataset.indices:
        lines.append(f"- {index.name}：{_fmt_pct(index.pct_change)}")
    lines.extend(
        [
            f"- 市场成交额：{_fmt_num(dataset.market_turnover)}",
            f"- 市场情绪：{features.market_sentiment or '暂缺'}",
            "",
            "## 2. 今日热点板块",
            "",
        ]
    )
    if dataset.hot_sectors:
        for idx, sector in enumerate(dataset.hot_sectors, start=1):
            symbols = "、".join(sector.get("symbols", [])[:3])
            lines.append(f"{idx}. {sector.get('name')}：成交额活跃个股集中，代表个股包括 {symbols or '暂缺'}")
    else:
        lines.append("1. 当前板块数据不足，热点板块判断暂以新闻和活跃个股线索为主。")
    lines.extend(
        [
            "",
            "## 3. 异动个股",
            "",
            "| 股票 | 涨跌幅 | 所属板块 | 可能原因 | 风险 |",
            "|---|---:|---|---|---|",
        ]
    )
    movers = (dataset.top_gainers[:5] + dataset.top_losers[:5])[:10]
    for mover in movers:
        lines.append(
            f"| {mover.name or mover.symbol} | {_fmt_pct(mover.pct_change)} | {mover.industry or '暂缺'} | {mover.reason or '待补充'} | {mover.risk or '待复核'} |"
        )
    lines.extend(
        [
            "",
            "## 4. 重要新闻",
            "",
        ]
    )
    news_lines = [line.strip("# ").strip() for line in dataset.important_news_text.splitlines() if line.strip().startswith("### ")]
    if news_lines:
        for item in news_lines[:8]:
            lines.append(f"- {item}")
    else:
        lines.append("- 当前未拿到稳定的新闻摘要，需人工补充盘后重点消息。")
    lines.extend(
        [
            "",
            "## 5. 明日观察",
            "",
            f"- 观察点一：市场情绪当前偏 {features.market_sentiment or '中性'}，需观察高成交额方向是否延续。",
            "- 观察点二：重点跟踪涨跌幅居前个股是否出现公开信息增量。",
            "- 风险事件：若板块数据仍不足，热点主线判断可能偏保守。",
            "",
            "## 6. 微信群版",
            "",
            build_daily_social_short(report),
            "",
            "## 7. 小红书版",
            "",
            build_daily_xiaohongshu(report),
            "",
            "## 8. 短视频口播版",
            "",
            build_daily_video_copy(report),
            "",
            "> 本内容基于公开资料自动整理，仅供信息参考，不构成投资建议。",
        ]
    )
    return "\n".join(lines)


def build_daily_social_short(report: DailyReviewReport) -> str:
    return (
        f"{report.dataset.trade_date} 盘后复盘："
        f"市场整体情绪偏{report.features.market_sentiment or '中性'}，"
        f"活跃方向主要集中在{_top_sector_name(report) or '若干高成交额行业'}。"
        "当前版本基于公开数据自动整理，适合做盘后信息汇总。"
    )


def build_daily_xiaohongshu(report: DailyReviewReport) -> str:
    return (
        f"今天 A 股盘后看点不在结论，而在结构。"
        f"{_top_sector_name(report) or '活跃行业'}的成交额更突出，"
        "涨跌幅居前个股分化也比较明显。"
        "如果你只看指数，很容易忽略盘面的实际主线。"
    )


def build_daily_video_copy(report: DailyReviewReport) -> str:
    return (
        f"今天盘后复盘，先看指数，再看结构。"
        f"市场情绪大致是{report.features.market_sentiment or '中性'}，"
        f"资金活跃方向更多集中在{_top_sector_name(report) or '高成交额行业'}。"
        "明天重点不是追结论，而是看这些方向有没有持续的公开信息支撑。"
    )


def _top_sector_name(report: DailyReviewReport) -> str | None:
    if not report.dataset.hot_sectors:
        return None
    return report.dataset.hot_sectors[0].get("name")
