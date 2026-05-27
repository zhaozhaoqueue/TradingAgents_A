from __future__ import annotations

import json
from dataclasses import asdict

from tradingagents.agents.utils.agent_utils import get_language_instruction
from tradingagents.llm_clients import create_llm_client

from .schemas import StockMoveAnalysis, StockMoveDataset, StockMoveFeatures


class LLMRoleRunner:
    def __init__(self, role_name: str, prompt_builder):
        self.role_name = role_name
        self.prompt_builder = prompt_builder

    def run(self, llm, dataset: StockMoveDataset, features: StockMoveFeatures) -> StockMoveAnalysis:
        prompt = self.prompt_builder(dataset, features) + "\n\n请输出一个简洁但具体的分析结果。"
        message = llm.invoke(prompt)
        return _parse_analysis(message.content, fallback_summary=f"{self.role_name} 输出解析失败。")


def build_default_llm():
    from tradingagents.dataflows.config import get_config

    config = get_config()
    client = create_llm_client(
        provider=config["llm_provider"],
        model=config["quick_think_llm"],
        base_url=config.get("backend_url"),
    )
    return client.get_llm()


def _parse_analysis(content: str, fallback_summary: str) -> StockMoveAnalysis:
    try:
        payload = json.loads(content)
        return StockMoveAnalysis(
            summary=payload.get("summary") or fallback_summary,
            bullets=[str(x) for x in payload.get("bullets", [])][:5],
            evidence=[str(x) for x in payload.get("evidence", [])][:5],
            risks=[str(x) for x in payload.get("risks", [])][:5],
        )
    except Exception:
        return StockMoveAnalysis(summary=str(content).strip() or fallback_summary)


def market_prompt(dataset: StockMoveDataset, features: StockMoveFeatures) -> str:
    feature_json = json.dumps(asdict(features), ensure_ascii=False, indent=2)
    return (
        "你是 A 股单股异动分析中的 Market Analyst。"
        "你的任务是只根据量价、成交额、近 20 日位置、均线关系和放量特征，判断这只股票当天是否构成明显异动。"
        "不要给出买卖建议，不要预测未来涨跌。"
        "请输出 JSON，字段为 summary、bullets、evidence、risks。"
        "bullets/evidence/risks 都是字符串数组。"
        f"{get_language_instruction()}\n\n"
        f"股票: {dataset.profile.name or dataset.profile.symbol}\n"
        f"交易日: {dataset.trade_date}\n"
        f"结构化特征:\n{feature_json}\n"
    )


def news_prompt(dataset: StockMoveDataset, features: StockMoveFeatures) -> str:
    return (
        "你是 A 股单股异动分析中的 News Analyst。"
        "你的任务是从新闻和政策信息里提取可能催化因素，并明确证据强弱。"
        "不要把没有明确来源的信息写成确定事实。"
        "请输出 JSON，字段为 summary、bullets、evidence、risks。"
        f"{get_language_instruction()}\n\n"
        f"股票: {dataset.profile.name or dataset.profile.symbol}\n"
        f"新闻窗口: {dataset.evidence_window_start} 到 {dataset.evidence_window_end}\n"
        f"新闻原文:\n{dataset.news_text}\n"
    )


def sector_prompt(dataset: StockMoveDataset, features: StockMoveFeatures) -> str:
    sector_json = json.dumps(asdict(dataset.sector_snapshot), ensure_ascii=False, indent=2)
    return (
        "你是 A 股单股异动分析中的 Sector Analyst。"
        "你的任务是判断这次异动更像板块共振还是个股独立事件。"
        "如果板块数据不足，必须明确写出证据不足。"
        "请输出 JSON，字段为 summary、bullets、evidence、risks。"
        f"{get_language_instruction()}\n\n"
        f"股票: {dataset.profile.name or dataset.profile.symbol}\n"
        f"板块快照:\n{sector_json}\n"
    )


def compliance_prompt(
    dataset: StockMoveDataset,
    features: StockMoveFeatures,
    analyses: dict[str, StockMoveAnalysis],
) -> str:
    analysis_json = json.dumps(
        {key: asdict(value) for key, value in analyses.items()},
        ensure_ascii=False,
        indent=2,
    )
    return (
        "你是 Risk / Compliance Editor。"
        "你的任务是检查以下分析是否存在证据过度外推、敏感表述、隐含荐股或过度确定性。"
        "输出 JSON，字段为 summary、bullets、evidence、risks。"
        "其中 summary 应描述整体证据质量，bullets 给出合规修正建议，risks 给出最终风险提示。"
        f"{get_language_instruction()}\n\n"
        f"综合分析:\n{analysis_json}\n"
    )
