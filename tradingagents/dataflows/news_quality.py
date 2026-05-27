from __future__ import annotations

GENERIC_TITLES = {
    "市场动态",
    "今日热点",
    "商圈",
    "华尔街原声",
    "霍尔木兹日报",
    "No title",
}

HIGH_VALUE_KEYWORDS = (
    "政策",
    "公告",
    "业绩",
    "订单",
    "并购",
    "重组",
    "监管",
    "证监会",
    "交易所",
    "央行",
    "发改委",
    "工信部",
    "财政部",
    "商务部",
    "资金",
    "主力",
    "行业",
    "板块",
    "指数",
    "利率",
    "汇率",
)


def clean_news_title(title: str) -> str:
    return str(title or "").split("(source:", 1)[0].strip("# ").strip()


def is_high_quality_news(title: str, content: str = "") -> bool:
    clean = clean_news_title(title)
    if not clean or clean in GENERIC_TITLES:
        return False
    text = f"{clean} {content or ''}"
    if len(clean) >= 12:
        return True
    return any(keyword in text for keyword in HIGH_VALUE_KEYWORDS)


def filter_news_rows(rows: list[dict], limit: int | None = None) -> list[dict]:
    filtered: list[dict] = []
    seen: set[str] = set()
    for row in rows:
        title = (
            row.get("title")
            or row.get("标题")
            or row.get("新闻标题")
            or row.get("tag")
            or ""
        )
        content = row.get("summary") or row.get("content") or row.get("新闻内容") or row.get("内容") or ""
        if not is_high_quality_news(str(title), str(content)):
            continue
        key = clean_news_title(str(title))
        if key in seen:
            continue
        seen.add(key)
        filtered.append(row)
        if limit is not None and len(filtered) >= limit:
            break
    return filtered
