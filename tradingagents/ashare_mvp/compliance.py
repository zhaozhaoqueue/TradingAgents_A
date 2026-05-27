from __future__ import annotations

PROHIBITED_PHRASES = (
    "买入",
    "卖出",
    "强烈推荐",
    "目标价",
    "必涨",
    "涨停预测",
    "仓位建议",
    "止损位",
    "收益率承诺",
    "准确率宣传",
    "跟单",
    "喊单",
)


def scan_prohibited_phrases(text: str) -> list[str]:
    return [phrase for phrase in PROHIBITED_PHRASES if phrase in text]
