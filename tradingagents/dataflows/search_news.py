from datetime import datetime, timedelta
from urllib.parse import urlparse

import requests

from .a_share_utils import default_search_aliases, is_a_share_symbol, normalize_a_share_symbol
from .cache import read_jsonl, write_jsonl
from .config import get_config
from .exceptions import DataVendorUnavailable


def _api_key() -> str:
    key = get_config().get("search_news_api_key")
    if not key:
        raise DataVendorUnavailable("SEARCH_NEWS_API_KEY is not configured")
    return key


def _provider() -> str:
    return get_config().get("search_news_provider", "tavily").lower()


def _company_aliases(ticker: str) -> list[str]:
    if is_a_share_symbol(ticker):
        aliases = list(default_search_aliases(ticker))
        try:
            from .tushare_pro import _pro

            ts_code = normalize_a_share_symbol(ticker)
            basic = _pro().stock_basic(
                exchange="",
                list_status="L",
                fields="ts_code,symbol,name",
            )
            row = basic[basic["ts_code"] == ts_code]
            if not row.empty:
                aliases.insert(0, str(row.iloc[0]["name"]))
        except Exception:
            pass
        return list(dict.fromkeys([a for a in aliases if a]))
    return [ticker]


def _queries_for_ticker(ticker: str) -> list[str]:
    aliases = _company_aliases(ticker)
    primary = aliases[0]
    queries = [
        f"{primary} 股票 新闻",
        f"{primary} 业绩 公告",
        f"{primary} 行业 政策",
    ]
    if len(aliases) > 1:
        queries.append(f"{' OR '.join(aliases[:3])} 股票")
    return queries


def _search_tavily(query: str, limit: int) -> list[dict]:
    endpoint = get_config().get("search_news_endpoint") or "https://api.tavily.com/search"
    response = requests.post(
        endpoint,
        json={
            "api_key": _api_key(),
            "query": query,
            "topic": "news",
            "search_depth": "advanced",
            "max_results": limit,
            "include_answer": False,
        },
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    rows = []
    for item in payload.get("results", []):
        rows.append(
            {
                "title": item.get("title", ""),
                "summary": item.get("content", ""),
                "url": item.get("url", ""),
                "source": _source_from_url(item.get("url", "")),
                "published_at": item.get("published_date") or "",
                "query": query,
            }
        )
    return rows


def _search(query: str, limit: int) -> list[dict]:
    provider = _provider()
    if provider == "tavily":
        return _search_tavily(query, limit)
    raise DataVendorUnavailable(f"Unsupported SEARCH_NEWS_PROVIDER: {provider}")


def _source_from_url(url: str) -> str:
    try:
        host = urlparse(url).netloc
        return host.replace("www.", "") or "Search"
    except Exception:
        return "Search"


def _dedupe(rows: list[dict]) -> list[dict]:
    seen = set()
    out = []
    for row in rows:
        key = row.get("url") or row.get("title")
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def _format(title: str, rows: list[dict]) -> str:
    if not rows:
        return f"No news found for {title}"
    lines = [f"## {title}", ""]
    for row in rows:
        lines.append(f"### {row.get('title') or 'No title'} (source: {row.get('source') or 'Search'})")
        if row.get("published_at"):
            lines.append(f"Published: {row['published_at']}")
        if row.get("summary"):
            lines.append(str(row["summary"]))
        if row.get("url"):
            lines.append(f"Link: {row['url']}")
        lines.append("")
    return "\n".join(lines)


def get_news(ticker: str, start_date: str, end_date: str) -> str:
    cached = read_jsonl("search_news", "news", ticker, start_date, end_date)
    if cached is not None:
        return _format(f"{ticker} News, from {start_date} to {end_date}", cached)

    rows = []
    for query in _queries_for_ticker(ticker):
        rows.extend(_search(query, limit=5))
    rows = _dedupe(rows)[: get_config()["news_article_limit"]]
    write_jsonl(
        rows,
        "search_news",
        "news",
        ticker,
        start_date,
        end_date,
        ttl_seconds=get_config()["a_share_news_ttl_seconds"],
    )
    return _format(f"{ticker} News, from {start_date} to {end_date}", rows)


def get_global_news(curr_date: str, look_back_days: int = None, limit: int = None) -> str:
    config = get_config()
    look_back_days = look_back_days or config["global_news_lookback_days"]
    limit = limit or config["global_news_article_limit"]
    curr = datetime.strptime(curr_date, "%Y-%m-%d")
    start_date = (curr - timedelta(days=look_back_days)).strftime("%Y-%m-%d")

    cached = read_jsonl("search_news", "global_news", "CN", start_date, curr_date)
    if cached is not None:
        return _format(f"Global Market News, from {start_date} to {curr_date}", cached[:limit])

    rows = []
    for query in config.get("global_news_queries_cn", config["global_news_queries"]):
        rows.extend(_search(query, limit=4))
        if len(rows) >= limit:
            break
    rows = _dedupe(rows)[:limit]
    write_jsonl(
        rows,
        "search_news",
        "global_news",
        "CN",
        start_date,
        curr_date,
        ttl_seconds=config["a_share_news_ttl_seconds"],
    )
    return _format(f"Global Market News, from {start_date} to {curr_date}", rows)


def get_insider_transactions(symbol: str) -> str:
    raise DataVendorUnavailable("Search news does not provide insider transactions")

