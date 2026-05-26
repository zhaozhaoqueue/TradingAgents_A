from datetime import datetime, timedelta

import pandas as pd

from .a_share_utils import normalize_a_share_symbol, to_akshare_symbol
from .cache import read_dataframe, write_dataframe
from .config import get_config
from .exceptions import DataVendorUnavailable


def _akshare():
    try:
        import akshare as ak
    except ImportError as exc:
        raise DataVendorUnavailable(
            "akshare is not installed; install the optional A-share dependencies"
        ) from exc
    return ak


def _normalize_hist(df: pd.DataFrame) -> pd.DataFrame:
    rename = {
        "日期": "Date",
        "开盘": "Open",
        "最高": "High",
        "最低": "Low",
        "收盘": "Close",
        "成交量": "Volume",
        "成交额": "Amount",
    }
    out = df.rename(columns=rename).copy()
    keep = [c for c in ["Date", "Open", "High", "Low", "Close", "Volume", "Amount"] if c in out]
    out = out[keep]
    out["Date"] = pd.to_datetime(out["Date"], errors="coerce")
    for col in ["Open", "High", "Low", "Close", "Volume", "Amount"]:
        if col in out:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    return out.dropna(subset=["Date", "Close"]).sort_values("Date").reset_index(drop=True)


def get_ohlcv_dataframe(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    ts_code = normalize_a_share_symbol(symbol)
    cached = read_dataframe("akshare", "daily", ts_code, start_date, end_date)
    if cached is not None:
        if "Date" in cached:
            cached["Date"] = pd.to_datetime(cached["Date"], errors="coerce")
        return cached

    ak = _akshare()
    df = ak.stock_zh_a_hist(
        symbol=to_akshare_symbol(ts_code),
        period="daily",
        start_date=start_date.replace("-", ""),
        end_date=end_date.replace("-", ""),
        adjust=get_config().get("tushare_adj", "qfq"),
    )
    if df is None or df.empty:
        raise DataVendorUnavailable(f"No AkShare history data for {ts_code}")
    out = _normalize_hist(df)
    write_dataframe(
        out,
        "akshare",
        "daily",
        ts_code,
        start_date,
        end_date,
        ttl_seconds=get_config()["a_share_market_ttl_seconds"],
    )
    return out


def get_stock(symbol: str, start_date: str, end_date: str) -> str:
    df = get_ohlcv_dataframe(symbol, start_date, end_date)
    header = (
        f"# A-share stock data for {normalize_a_share_symbol(symbol)} "
        f"from {start_date} to {end_date}\n"
        f"# Vendor: AkShare\n"
        f"# Total records: {len(df)}\n"
        f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    )
    return header + df.to_csv(index=False)


def get_news(ticker: str, start_date: str, end_date: str) -> str:
    try:
        ts_code = normalize_a_share_symbol(ticker)
    except ValueError:
        return _get_keyword_news(ticker, start_date, end_date)

    cached = read_dataframe("akshare", "news", ts_code, start_date, end_date)
    if cached is not None:
        return _format_news(ts_code, cached.to_dict("records"), start_date, end_date)

    ak = _akshare()
    try:
        # AkShare currently trips over pandas 3's pyarrow-backed string regex
        # path in stock_news_em. Force Python strings for this call only.
        with pd.option_context("mode.string_storage", "python"):
            df = ak.stock_news_em(symbol=to_akshare_symbol(ts_code))
    except Exception as exc:
        raise DataVendorUnavailable(f"AkShare stock news failed for {ts_code}: {exc}") from exc
    if df is None or df.empty:
        raise DataVendorUnavailable(f"No AkShare news found for {ts_code}")

    if "发布时间" in df:
        dates = pd.to_datetime(df["发布时间"], errors="coerce")
        mask = (dates >= pd.to_datetime(start_date)) & (dates <= pd.to_datetime(end_date) + pd.Timedelta(days=1))
        df = df[mask]
    write_dataframe(
        df,
        "akshare",
        "news",
        ts_code,
        start_date,
        end_date,
        ttl_seconds=get_config()["a_share_news_ttl_seconds"],
    )
    return _format_news(ts_code, df.to_dict("records"), start_date, end_date)


def _get_keyword_news(query: str, start_date: str, end_date: str) -> str:
    query = str(query).strip()
    if not query:
        return f"No news found for empty query between {start_date} and {end_date}"

    cached = read_dataframe("akshare", "keyword_news", query, start_date, end_date)
    if cached is not None:
        return _format_keyword_news(query, cached.to_dict("records"), start_date, end_date)

    ak = _akshare()
    rows = []
    try:
        df = ak.stock_news_main_cx()
        if df is not None and not df.empty:
            text = df.astype(str).agg(" ".join, axis=1)
            matched = df[text.str.contains(query, case=False, na=False, regex=False)].copy()
            if not matched.empty:
                matched["source"] = "Caixin/AkShare"
                rows.extend(matched.to_dict("records"))
    except Exception:
        pass

    if not rows:
        return f"No AkShare keyword news found for '{query}' between {start_date} and {end_date}"

    out = pd.DataFrame(rows[:20])
    write_dataframe(
        out,
        "akshare",
        "keyword_news",
        query,
        start_date,
        end_date,
        ttl_seconds=get_config()["a_share_news_ttl_seconds"],
    )
    return _format_keyword_news(query, out.to_dict("records"), start_date, end_date)


def _format_news(ts_code: str, rows: list[dict], start_date: str, end_date: str) -> str:
    if not rows:
        return f"No news found for {ts_code} between {start_date} and {end_date}"
    lines = [f"## {ts_code} News, from {start_date} to {end_date}:", ""]
    for row in rows[:20]:
        title = row.get("新闻标题") or row.get("标题") or row.get("title") or "No title"
        source = row.get("文章来源") or row.get("source") or "Eastmoney/AkShare"
        when = row.get("发布时间") or row.get("publish_time") or ""
        url = row.get("新闻链接") or row.get("url") or ""
        lines.append(f"### {title} (source: {source})")
        if when:
            lines.append(f"Published: {when}")
        if url:
            lines.append(f"Link: {url}")
        lines.append("")
    return "\n".join(lines)


def _format_keyword_news(query: str, rows: list[dict], start_date: str, end_date: str) -> str:
    if not rows:
        return f"No news found for '{query}' between {start_date} and {end_date}"
    lines = [f"## Keyword News for '{query}', from {start_date} to {end_date}:", ""]
    for row in rows[:20]:
        title = row.get("title") or row.get("标题") or row.get("新闻标题") or row.get("tag") or query
        content = row.get("summary") or row.get("content") or row.get("新闻内容") or row.get("内容") or ""
        source = row.get("source") or row.get("文章来源") or "AkShare"
        url = row.get("url") or row.get("新闻链接") or ""
        when = row.get("发布时间") or row.get("date") or row.get("日期") or ""
        lines.append(f"### {title} (source: {source})")
        if when:
            lines.append(f"Published: {when}")
        if content and content != title:
            lines.append(str(content))
        if url:
            lines.append(f"Link: {url}")
        lines.append("")
    return "\n".join(lines)


def get_global_news(curr_date: str, look_back_days: int = 7, limit: int = 20) -> str:
    cache_extra = {"source": "market_v2"}
    cached = read_dataframe("akshare", "global_news", "CN", None, curr_date, cache_extra)
    if cached is not None:
        return _format_global_news(cached.to_dict("records"), curr_date, limit)

    ak = _akshare()
    try:
        df = ak.stock_news_main_cx()
        if df is not None and not df.empty:
            df = df.head(limit).copy()
            df["source"] = "Caixin/AkShare"
            write_dataframe(
                df,
                "akshare",
                "global_news",
                "CN",
                None,
                curr_date,
                ttl_seconds=get_config()["a_share_news_ttl_seconds"],
                extra=cache_extra,
            )
            return _format_global_news(df.to_dict("records"), curr_date, limit)
    except Exception:
        pass

    rows = []
    curr = datetime.strptime(curr_date, "%Y-%m-%d")
    for offset in range(look_back_days):
        day = curr - timedelta(days=offset)
        try:
            df = ak.news_cctv(date=day.strftime("%Y%m%d"))
        except Exception:
            continue
        if df is not None and not df.empty:
            df = df.copy()
            df["date"] = day.strftime("%Y-%m-%d")
            rows.extend(df.to_dict("records"))
        if len(rows) >= limit:
            break

    if not rows:
        raise DataVendorUnavailable("No AkShare global news found")
    out = pd.DataFrame(rows[:limit])
    write_dataframe(
        out,
        "akshare",
        "global_news",
        "CN",
        None,
        curr_date,
        ttl_seconds=get_config()["a_share_news_ttl_seconds"],
        extra=cache_extra,
    )
    return _format_global_news(out.to_dict("records"), curr_date, limit)


def _format_global_news(rows: list[dict], curr_date: str, limit: int) -> str:
    if not rows:
        return f"No global news found for {curr_date}"
    lines = [f"## China Market News up to {curr_date} (AkShare)", ""]
    for row in rows[:limit]:
        title = row.get("title") or row.get("标题") or row.get("新闻标题") or row.get("tag") or "No title"
        content = row.get("summary") or row.get("content") or row.get("新闻内容") or row.get("内容") or ""
        date_value = row.get("date") or row.get("日期") or ""
        source = row.get("source") or "CCTV/AkShare"
        url = row.get("url") or row.get("新闻链接") or ""
        lines.append(f"### {title} (source: {source})")
        if date_value:
            lines.append(f"Published: {date_value}")
        if content and content != title:
            lines.append(str(content))
        if url:
            lines.append(f"Link: {url}")
        lines.append("")
    return "\n".join(lines)


def get_insider_transactions(symbol: str) -> str:
    raise DataVendorUnavailable("A-share insider transactions are not available via AkShare fallback")
