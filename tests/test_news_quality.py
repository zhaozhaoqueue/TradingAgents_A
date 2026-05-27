from __future__ import annotations

import pytest

from tradingagents.dataflows.news_quality import filter_news_rows, is_high_quality_news


@pytest.mark.unit
def test_filters_generic_market_titles():
    rows = [
        {"title": "市场动态", "summary": "泛化栏目标题"},
        {"title": "证监会发布资本市场相关政策", "summary": "政策内容"},
        {"title": "今日热点", "summary": "泛化栏目标题"},
    ]

    filtered = filter_news_rows(rows)

    assert [row["title"] for row in filtered] == ["证监会发布资本市场相关政策"]


@pytest.mark.unit
def test_short_title_requires_high_value_keyword():
    assert is_high_quality_news("订单增长")
    assert not is_high_quality_news("商圈")
