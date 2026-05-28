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
    report_type = _movement_label(report)
    lines = [
        f"# {profile.name or profile.symbol}（{profile.symbol}）今日{report_type}",
        "",
        "## 1. 今日表现",
        "",
        f"- 涨跌幅：{_fmt_pct(features.pct_change)}",
        f"- 成交额：{_fmt_amount(features.amount)}",
        f"- 换手率：{_fmt_pct(features.turnover_rate)}",
        f"- 所属行业：{profile.industry or '暂缺'}",
        f"- 相关概念：{_concept_text(report)}",
        f"- 近 20 日位置：{_position_text(features)}",
        "",
        "## 2. 今天为什么这样走？",
        "",
    ]
    lines.extend(_attribution_section(report))
    lines.extend(
        [
            "",
            "## 3. 公开信息依据",
            "",
        ]
    )
    for item in _merged_evidence(report.market_analysis, report.news_analysis, report.sector_analysis):
        lines.append(f"- {_safe_text(item)}")
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
        risks.extend(item for item in analysis.risks if _is_reader_facing_risk(item))
        risks.extend(item for item in analysis.bullets if _looks_like_uncertainty(item))
    risks.extend(item for item in report.compliance_notes if _is_reader_facing_risk(item))
    risks.extend(_data_gap_notes(report))
    if not risks:
        risks.append("当前版本未发现强烈合规风险，但仍需结合原始公告、新闻和盘后数据复核。")
    for risk in dict.fromkeys(risks):
        lines.append(f"- {_safe_text(risk)}")
    lines.extend(
        [
            "",
            "## 6. 后续怎么观察？",
            "",
        ]
    )
    lines.extend(_observation_section(report))
    lines.extend(
        [
            "",
            "## 7. 社群短版",
            "",
            build_social_short(report),
            "",
            "## 8. 小红书/短视频版",
            "",
            build_short_video_copy(report),
            "",
            "> 本内容基于公开资料自动整理，仅供信息参考，不构成投资建议。",
        ]
    )
    return "\n".join(lines)


def _observation_section(report: StockMoveReport) -> list[str]:
    stance, reason = _observation_stance(report)
    return [
        "### 6.1 当前更适合怎么处理？",
        "",
        f"- 观察结论：{stance}",
        f"- 原因：{reason}",
        "",
        "### 6.2 接下来重点看什么？",
        "",
        f"- 看量能：{_volume_watch_text(report.features)}",
        f"- 看价格位置：{_price_watch_text(report.features)}",
        f"- 看板块：{_sector_watch_text(report)}",
        f"- 看消息：{_news_watch_text(report)}",
        "",
        "### 6.3 哪些情况会改变当前判断？",
        "",
        "- 如果后续量能明显放大，且价格重新站回短期均线，说明资金关注度可能回升。",
        "- 如果继续缩量并维持在主要均线下方，说明短期承接仍需观察。",
        "- 如果出现公司公告、订单、业绩或政策消息直接点名，需要重新评估消息面的解释力度。",
        "- 如果行业或概念板块同步走强，且相关个股也出现联动，板块共振解释会更有支撑。",
    ]


def _observation_stance(report: StockMoveReport) -> tuple[str, str]:
    features = report.features
    label = _movement_label(report)
    direct_news = _has_direct_news_evidence(report)
    has_sector_support = bool(report.sector_snapshot.sector_performance or report.sector_snapshot.related_stock_performance)
    volume_ratio = features.volume_ratio_vs_20d
    pct = abs(features.pct_change) if features.pct_change is not None else 0

    if label == "观察简报":
        return (
            "先放在观察池，等待更明确的量能、消息或板块信号。",
            "当天波动强度不高，且当前证据更多是背景线索，不适合把单日走势解释得过满。",
        )
    if direct_news and volume_ratio is not None and volume_ratio >= 1.3:
        return (
            "重点跟踪后续确认信号。",
            "消息面和量能都有一定线索，但仍需要观察后续是否延续，而不是只看单日变化。",
        )
    if has_sector_support and pct >= 3:
        return (
            "优先判断是否属于板块共振。",
            "价格波动已有一定强度，且板块侧存在可核对线索，后续要看行业和相关个股是否同步延续。",
        )
    return (
        "谨慎观察，先核对原始公告、新闻和板块数据。",
        "目前解释链条还不完整，单靠现有公开信息难以形成高可靠判断。",
    )


def _volume_watch_text(features: StockMoveFeatures) -> str:
    ratio = features.volume_ratio_vs_20d
    if ratio is None:
        return "当前量能口径不足，优先补齐成交量和成交额数据。"
    if ratio >= 2:
        return "已经明显放量，重点看后续是否继续维持在 20 日均量上方。"
    if ratio >= 1.3:
        return "已有温和放量，重点看是否进一步放大，还是快速回落到均量附近。"
    return "当前没有明显放量，重点看后续是否出现资金关注度回升。"


def _price_watch_text(features: StockMoveFeatures) -> str:
    if features.close is None:
        return "价格数据不足，暂时无法判断关键位置。"
    if features.close_5ma is not None and features.close < features.close_5ma:
        return "当前仍在 5 日线下方，重点看能否重新站回短期均线。"
    if features.breakout_20d_high:
        return "已经接近或突破近 20 日高点，重点看突破后是否能保持。"
    if features.rebound_from_20d_low:
        return "出现低位反弹迹象，重点看反弹是否伴随量能确认。"
    return "重点看价格是否继续围绕短期均线震荡，或出现新的突破/回落信号。"


def _sector_watch_text(report: StockMoveReport) -> str:
    if report.sector_snapshot.sector_performance or report.sector_snapshot.related_stock_performance:
        if report.sector_snapshot.concepts:
            return "观察所属行业、相关概念和联动个股是否同步延续，避免把个股单日波动误读成板块主线。"
        return "观察所属行业和相关个股是否同步延续，避免把个股单日波动误读成板块主线。"
    return "当前板块数据不足，优先补齐行业涨跌、成分股表现和概念板块线索。"


def _news_watch_text(report: StockMoveReport) -> str:
    if _has_direct_news_evidence(report):
        return "已经有个股相关公开信息，重点核对来源、发布时间和是否有后续公告确认。"
    if report.news_analysis.evidence:
        return "目前更多是行业或背景线索，重点看后续是否出现直接点名公司的公开信息。"
    return "暂未看到直接消息，重点关注公告、交易所互动、权威媒体和行业政策是否有新增。"


def _data_gap_notes(report: StockMoveReport) -> list[str]:
    notes: list[str] = []
    if not report.news_analysis.evidence:
        notes.append("新闻证据不足，当前归因不能完全依赖消息面解释。")
    if not report.sector_snapshot.sector_performance:
        notes.append("行业板块涨跌数据暂缺，板块联动判断需要保守。")
    if not report.sector_snapshot.concepts:
        notes.append("概念板块数据暂缺，题材共振仍需人工复核。")
    if not report.sector_snapshot.related_stock_performance:
        notes.append("行业或概念成分股横向对比不足，无法充分判断是否为板块共振。")
    return notes


def _concept_text(report: StockMoveReport) -> str:
    concepts = report.sector_snapshot.concepts
    if not concepts:
        return "暂缺"
    return "、".join(concepts[:3])


def build_social_short(report: StockMoveReport) -> str:
    summary = _public_summary(report.market_analysis, "从量价结构看，个股当天存在一定异动特征。")
    label = _movement_label(report)
    risk_text = "; ".join(_reader_facing_compliance_notes(report)[:2]) or "消息面和板块联动证据仍需复核。"
    return (
        f"{report.profile.name or report.profile.symbol} 今日{label}。"
        f"{_safe_text(summary)} 风险上主要关注：{_safe_text(risk_text)}"
    )


def build_short_video_copy(report: StockMoveReport) -> str:
    label = _movement_label(report)
    news_summary = _safe_text(
        _public_summary(report.news_analysis, "消息面没有看到特别强的单一催化")
    ).rstrip("。；; ")
    return (
        f"今天看 {report.profile.name or report.profile.symbol}，"
        f"它更适合归类为{label}。盘面上最明显的特征是{_volume_text(report.features)}，"
        f"同时{news_summary}。"
        "如果要理解这次异动，更重要的是区分它是板块共振还是个股事件，"
        "目前结论只基于公开资料整理。"
    )


def _merged_evidence(*analyses: StockMoveAnalysis) -> list[str]:
    merged: list[str] = []
    for analysis in analyses:
        merged.extend(item for item in analysis.evidence if _is_report_evidence(item))
        visible_bullets = [
            item
            for item in analysis.bullets
            if _is_report_evidence(item) and not _looks_like_uncertainty(item)
        ]
        merged.extend(visible_bullets[:1])
    if not merged:
        return ["当前证据较弱，需进一步核对原始行情与新闻。"]
    return list(dict.fromkeys(merged))


def _attribution_section(report: StockMoveReport) -> list[str]:
    return [
        "### 2.1 先看盘面：有没有明显异常？",
        "",
        *_analysis_bullets(
            report.market_analysis,
            fallback="从价格和成交量看，今天没有特别突出的异常，需要结合消息和板块一起看。",
            exclude_uncertainty=True,
        ),
        "",
        "### 2.2 再看消息：有没有直接催化？",
        "",
        *_analysis_bullets(
            report.news_analysis,
            fallback="暂未看到能直接解释今天走势的公司公告、订单、政策或其他明确消息。",
            exclude_uncertainty=True,
        ),
        "",
        "### 2.3 再看板块：是不是行业或题材带动？",
        "",
        *_analysis_bullets(
            report.sector_analysis,
            fallback="目前还不能确认这是行业或题材共同带动，板块线索需要继续核对。",
            exclude_uncertainty=True,
        ),
        "",
        "### 2.4 最后判断：这个解释有多可靠？",
        "",
        *_attribution_confidence(report),
    ]


def _analysis_bullets(
    analysis: StockMoveAnalysis,
    *,
    fallback: str,
    exclude_uncertainty: bool = False,
) -> list[str]:
    items = analysis.bullets or ([analysis.summary] if analysis.summary else [])
    if exclude_uncertainty:
        items = [item for item in items if not _looks_like_uncertainty(item) and _is_public_reader_text(item)]
    else:
        items = [item for item in items if _is_public_reader_text(item)]
    if not items:
        items = [fallback]
    return [f"- {_safe_text(item)}" for item in items]


def _attribution_confidence(report: StockMoveReport) -> list[str]:
    score = 0
    reasons: list[str] = []
    counterpoints: list[str] = []

    if report.features.pct_change is not None and abs(report.features.pct_change) >= 5:
        score += 2
        reasons.append("价格波动达到 5% 以上，属于较明显的盘面变化。")
    elif report.features.pct_change is not None and abs(report.features.pct_change) >= 3:
        score += 1
        reasons.append("价格波动达到 3% 以上，具备一定观察价值。")
    elif report.features.pct_change is not None:
        counterpoints.append("价格波动未达到 3%，盘面异动强度偏弱。")

    if report.features.volume_ratio_vs_20d is not None and report.features.volume_ratio_vs_20d >= 2:
        score += 2
        reasons.append("量能达到 20 日均量 2 倍以上，资金参与度明显提升。")
    elif report.features.volume_ratio_vs_20d is not None and report.features.volume_ratio_vs_20d >= 1.3:
        score += 1
        reasons.append("量能较 20 日均量有所放大，资金参与度有一定提升。")
    elif report.features.volume_ratio_vs_20d is not None:
        counterpoints.append("量能未明显放大，资金层面的确认度不足。")

    if _has_direct_news_evidence(report):
        score += 2
        reasons.append("新闻/事件侧存在与个股直接相关的公开信息。")
    elif report.news_analysis.evidence:
        score += 1
        reasons.append("新闻/事件侧存在可引用信息，但更多属于行业或背景线索。")
    else:
        counterpoints.append("暂未发现与个股直接相关的新闻证据。")

    if report.sector_snapshot.sector_performance and report.sector_snapshot.related_stock_performance:
        score += 2
        reasons.append("行业板块和相关个股均提供了联动验证。")
    elif report.sector_snapshot.sector_performance or report.sector_snapshot.related_stock_performance:
        score += 1
        reasons.append("行业板块或相关个股存在可用于交叉验证的线索。")
    else:
        counterpoints.append("板块涨跌或成分股对比数据不足，难以确认板块共振。")

    if score >= 5:
        level = "中高"
    elif score >= 3:
        level = "中"
    else:
        level = "偏低"

    if not reasons:
        reasons.append("当前缺少量价、消息和板块的共同验证，这个解释只能作为观察线索。")

    lines = [f"- 解释可靠度：{level}"]
    lines.extend(f"- 判断依据：{reason}" for reason in reasons[:3])
    lines.extend(f"- 限制因素：{item}" for item in counterpoints[:3])
    return lines


def _movement_label(report: StockMoveReport) -> str:
    features = report.features
    pct = abs(features.pct_change) if features.pct_change is not None else None
    vol = features.volume_ratio_vs_20d
    has_breakout = features.breakout_20d_high or features.rebound_from_20d_low

    if (pct is not None and pct >= 5) or (pct is not None and pct >= 3 and vol is not None and vol >= 1.3) or has_breakout:
        return "异动解读"
    if (pct is not None and pct >= 2) or (vol is not None and vol >= 1.3):
        return "波动复盘"
    return "观察简报"


def _has_direct_news_evidence(report: StockMoveReport) -> bool:
    name = report.profile.name or ""
    symbol = report.profile.symbol.split(".", 1)[0]
    candidates = [name, symbol]
    for text in report.news_analysis.evidence:
        if any(item and item in text for item in candidates) and not _contains_negated_direct_match(text):
            return True
    return False


def _looks_like_uncertainty(text: str) -> bool:
    markers = (
        "暂缺",
        "数据不足",
        "证据不足",
        "无法",
        "不能",
        "未稳定接入",
        "需复核",
        "需要人工",
        "可信度有限",
    )
    return any(marker in text for marker in markers)


def _reader_facing_compliance_notes(report: StockMoveReport) -> list[str]:
    return [item for item in report.compliance_notes if _is_reader_facing_risk(item)]


def _is_reader_facing_risk(text: str) -> bool:
    return _is_public_reader_text(text)


def _contains_negated_direct_match(text: str) -> bool:
    negation_markers = (
        "无。",
        "缺失",
        "无直接",
        "未提及",
        "未点名",
        "未包含",
        "未出现",
        "未获",
        "未有",
        "未列入",
        "未被列为",
        "未被点名",
        "未直接提及",
        "未直接证实",
        "未具体涉及",
        "无法构成明确催化",
    )
    return any(marker in text for marker in negation_markers)


def _is_report_evidence(text: str) -> bool:
    if not _is_public_reader_text(text):
        return False
    internal_markers = ("链接:", "证据强度:", "强（", "中（", "弱（", "强度:")
    return not any(marker in text for marker in internal_markers)


def _is_public_reader_text(text: str) -> bool:
    text = str(text or "").strip()
    if not text:
        return False
    internal_markers = (
        "占位符",
        "编辑器",
        "合规审查",
        "建议",
        "改为",
        "替换",
        "客户",
        "用户",
        "交易策略",
        "买入",
        "决策",
        "敏感表达",
        "可改为",
        "无需修改",
        "应明确",
        "需替换",
        "若未修正",
        "合规审计",
        "应附条件",
        "notes ",
        "evidence ",
        "summary ",
        "sector_performance",
        "related_stock_performance",
        "null",
        "为空值",
        "证据强度:",
    )
    if any(marker in text for marker in internal_markers):
        return False
    code_like_markers = (
        "close=",
        "pct_change=",
        "volume_ratio",
        "position_vs",
        "close_5ma",
        "close_10ma",
        "close_20ma",
        "rebound_from",
        "breakout_",
        "=true",
        "=false",
        "price_move",
        "volume_expansion",
        "volume_surge",
        "rebound",
    )
    return not any(marker in text for marker in code_like_markers)


def _public_summary(analysis: StockMoveAnalysis, fallback: str) -> str:
    summary = str(analysis.summary or "").strip()
    if not _is_public_reader_text(summary):
        return fallback
    return summary


def _safe_text(text: str) -> str:
    replacements = {
        "或受益于板块资金关注": "可能仅存在板块情绪关联",
        "受益于板块资金关注": "存在板块情绪关联",
        "利好催化": "背景线索",
        "明确催化": "直接线索",
        "或受到板块资金轮动情绪带动": "可能仅存在板块资金轮动的背景线索",
        "持续性机会": "后续持续性",
        "追高风险": "波动风险",
        "做多": "作出方向性判断",
        "买入": "交易",
    }
    result = text
    for old, new in replacements.items():
        result = result.replace(old, new)
    return result


def _bullet_block(analysis: StockMoveAnalysis) -> list[str]:
    items = analysis.bullets or ([analysis.summary] if analysis.summary else [])
    return [f"- {item}" for item in items]


def _fmt_num(value: float | None) -> str:
    if value is None:
        return "暂缺"
    return f"{value:,.2f}"


def _fmt_amount(value: float | None) -> str:
    if value is None:
        return "暂缺"
    abs_value = abs(value)
    if abs_value >= 1e8:
        return f"{value / 1e8:.2f}亿元"
    if abs_value >= 1e4:
        return f"{value / 1e4:.2f}万元"
    return f"{value:,.2f}元"


def _fmt_pct(value: float | None) -> str:
    if value is None:
        return "暂缺"
    return f"{value:.2f}%"


def _coerce_float(value) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


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
            f"- 市场成交额：{_fmt_amount(dataset.market_turnover)}",
            f"- 市场情绪：{features.market_sentiment or '暂缺'}",
            f"- 结构特征：{_daily_structure_text(report)}",
            "",
            "## 2. 今天哪些方向更活跃？",
            "",
        ]
    )
    if dataset.hot_sectors:
        for idx, sector in enumerate(dataset.hot_sectors, start=1):
            symbols = "、".join(sector.get("symbols", [])[:3])
            pct = _fmt_pct(_coerce_float(sector.get("pct_change")))
            board_type = "行业" if sector.get("board_type") == "industry" else "概念" if sector.get("board_type") == "concept" else "板块"
            lines.append(
                f"{idx}. {sector.get('name')}（{board_type}）：板块涨跌幅 {pct}，"
                f"高成交额样本中出现 {sector.get('count', '若干')} 次，代表个股包括 {symbols or '暂缺'}。"
            )
    else:
        lines.append("1. 当前板块数据不足，热点方向暂以高成交额个股和新闻线索辅助判断。")
    lines.extend(
        [
            "",
            "## 3. 哪些个股需要复盘？",
            "",
            "| 股票 | 涨跌幅 | 所属板块 | 观察线索 | 需要注意 |",
            "|---|---:|---|---|---|",
        ]
    )
    movers = (dataset.top_gainers[:5] + dataset.top_losers[:5])[:10]
    for mover in movers:
        lines.append(
            f"| {mover.name or mover.symbol} | {_fmt_pct(mover.pct_change)} | {_mover_board_text(mover)} | {_safe_text(mover.reason or '待补充')} | {_safe_text(mover.risk or '待复核')} |"
        )
    lines.extend(
        [
            "",
            "## 4. 重要新闻",
            "",
        ]
    )
    news_lines = _daily_news_titles(dataset.important_news_text)
    if news_lines:
        for item in news_lines[:8]:
            lines.append(f"- {item}")
    else:
        lines.append("- 当前未拿到高质量新闻标题，需人工补充盘后重点消息。")
    lines.extend(
        [
            "",
            "## 5. 明天重点观察什么？",
            "",
        ]
    )
    lines.extend(_daily_watch_section(report))
    lines.extend(
        [
            "",
            "## 6. 输出边界",
            "",
            "- 本复盘用于整理盘后公开信息和观察线索，不输出买卖建议、目标价、仓位或收益预测。",
            "- 热点方向只代表当日结构特征，不等于后续走势判断。",
            "- 个股表格中的内容是复盘线索，不是交易指令。",
            "",
            "## 7. 微信群版",
            "",
            build_daily_social_short(report),
            "",
            "## 8. 小红书版",
            "",
            build_daily_xiaohongshu(report),
            "",
            "## 9. 短视频口播版",
            "",
            build_daily_video_copy(report),
            "",
            "> 本内容基于公开资料自动整理，仅供信息参考，不构成投资建议。",
        ]
    )
    return "\n".join(lines)


def _daily_structure_text(report: DailyReviewReport) -> str:
    top_sector = _top_sector_name(report)
    sentiment = _sentiment_text(report.features.market_sentiment)
    if top_sector:
        return f"市场情绪{sentiment}，高成交额方向相对集中在{top_sector}等板块。"
    return f"市场情绪{sentiment}，热点方向仍需结合新闻和成交额榜继续核对。"


def _mover_board_text(mover) -> str:
    parts = []
    if mover.industry:
        parts.append(mover.industry)
    if mover.concepts:
        parts.append("/".join(mover.concepts[:2]))
    return " + ".join(parts) if parts else "暂缺"


def _daily_watch_section(report: DailyReviewReport) -> list[str]:
    return [
        "### 5.1 看市场情绪是否延续",
        "",
        f"- 当前情绪：{report.features.market_sentiment or '中性'}",
        "- 观察重点：成交额能否维持，指数表现是否继续和个股活跃度匹配。",
        "",
        "### 5.2 看热点方向是否扩散",
        "",
        f"- 当前活跃方向：{_top_sector_name(report) or '暂未形成清晰主线'}",
        "- 观察重点：高成交额个股是否继续集中在同一行业，还是快速轮动到其他方向。",
        "",
        "### 5.3 看异动个股是否有公开信息确认",
        "",
        "- 观察重点：涨跌幅居前个股是否出现公告、行业政策、订单、业绩或权威媒体报道。",
        "- 如果只有价格变化、没有公开信息支撑，个股归因需要保持保守。",
        "",
        "### 5.4 看风险点有没有放大",
        "",
        "- 如果热点方向只靠单日成交额支撑，次日分歧可能上升。",
        "- 如果重要新闻缺失或板块数据不完整，需要避免把弱线索写成确定主线。",
    ]


def build_daily_social_short(report: DailyReviewReport) -> str:
    return (
        f"{report.dataset.trade_date} 盘后复盘："
        f"市场整体情绪{_sentiment_text(report.features.market_sentiment)}，"
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


def _sentiment_text(sentiment: str | None) -> str:
    if not sentiment:
        return "中性"
    if sentiment.startswith(("偏", "较")):
        return sentiment
    return f"偏{sentiment}" if sentiment not in ("中性", "暂缺") else sentiment


def _daily_news_titles(text: str) -> list[str]:
    generic_titles = {"市场动态", "今日热点", "商圈", "华尔街原声", "霍尔木兹日报"}
    titles: list[str] = []
    for line in text.splitlines():
        if not line.strip().startswith("### "):
            continue
        title = line.strip("# ").strip()
        plain = title.split("(source:", 1)[0].strip()
        if plain in generic_titles:
            continue
        if title not in titles:
            titles.append(title)
    return titles
