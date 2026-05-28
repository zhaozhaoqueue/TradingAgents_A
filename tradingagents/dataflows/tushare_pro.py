from datetime import datetime, timedelta
from typing import Optional

import pandas as pd

from .a_share_utils import normalize_a_share_symbol
from .cache import read_dataframe, write_dataframe
from .config import get_config
from .exceptions import DataVendorUnavailable


def _date8(value: str) -> str:
    return datetime.strptime(value, "%Y-%m-%d").strftime("%Y%m%d")


def _date_dash(value: str) -> str:
    if not value:
        return value
    if "-" in value:
        return value
    try:
        return datetime.strptime(value, "%Y%m%d").strftime("%Y-%m-%d")
    except ValueError:
        return value


def _token() -> str:
    token = get_config().get("tushare_token")
    if not token:
        raise DataVendorUnavailable("TUSHARE_TOKEN is not configured")
    return token


def _tushare():
    try:
        import tushare as ts
    except ImportError as exc:
        raise DataVendorUnavailable(
            "tushare is not installed; install the optional A-share dependencies"
        ) from exc
    ts.set_token(_token())
    return ts


def _pro():
    return _tushare().pro_api(_token())


def _cache_ttl(end_date: Optional[str]) -> Optional[int]:
    config = get_config()
    if not end_date:
        return config["a_share_market_ttl_seconds"]
    end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
    if end_dt >= datetime.utcnow().date() - timedelta(days=3):
        return config["a_share_market_ttl_seconds"]
    return None


def _normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    rename = {
        "trade_date": "Date",
        "open": "Open",
        "high": "High",
        "low": "Low",
        "close": "Close",
        "vol": "Volume",
        "amount": "Amount",
    }
    out = df.rename(columns=rename).copy()
    keep = [c for c in ["Date", "Open", "High", "Low", "Close", "Volume", "Amount"] if c in out]
    out = out[keep]
    out["Date"] = pd.to_datetime(out["Date"].astype(str), format="%Y%m%d", errors="coerce")
    for col in ["Open", "High", "Low", "Close", "Volume", "Amount"]:
        if col in out:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    if "Amount" in out:
        # TuShare daily/pro_bar amount is reported in 千元; normalize to 元.
        out["Amount"] = out["Amount"] * 1000.0
    out = out.dropna(subset=["Date", "Close"])
    return out.sort_values("Date").reset_index(drop=True)


def get_ohlcv_dataframe(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    ts_code = normalize_a_share_symbol(symbol)
    adj = get_config().get("tushare_adj", "qfq")
    extra = {"adj": adj, "amount_unit": "cny_v2"}
    cached = read_dataframe("tushare_pro", "daily", ts_code, start_date, end_date, extra)
    if cached is not None:
        if "Date" in cached:
            cached["Date"] = pd.to_datetime(cached["Date"], errors="coerce")
        return cached

    ts = _tushare()
    df = ts.pro_bar(
        ts_code=ts_code,
        adj=adj,
        start_date=_date8(start_date),
        end_date=_date8(end_date),
    )
    if df is None or df.empty:
        raise DataVendorUnavailable(f"No TuShare pro_bar data for {ts_code}")
    out = _normalize_ohlcv(df)
    write_dataframe(
        out,
        "tushare_pro",
        "daily",
        ts_code,
        start_date,
        end_date,
        ttl_seconds=_cache_ttl(end_date),
        extra=extra,
    )
    return out


def get_stock(symbol: str, start_date: str, end_date: str) -> str:
    df = get_ohlcv_dataframe(symbol, start_date, end_date)
    header = (
        f"# A-share stock data for {normalize_a_share_symbol(symbol)} "
        f"from {start_date} to {end_date}\n"
        f"# Vendor: TuShare Pro, adjusted: {get_config().get('tushare_adj', 'qfq')}\n"
        f"# Total records: {len(df)}\n"
        f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    )
    return header + df.to_csv(index=False)


def _cached_pro_query(
    api_name: str,
    symbol: str,
    cache_start_date: Optional[str],
    cache_end_date: Optional[str],
    ttl_seconds: Optional[int],
    **params,
) -> pd.DataFrame:
    ts_code = normalize_a_share_symbol(symbol)
    cached = read_dataframe("tushare_pro", api_name, ts_code, cache_start_date, cache_end_date, params)
    if cached is not None:
        return cached
    pro = _pro()
    api = getattr(pro, api_name)
    df = api(ts_code=ts_code, **params)
    if df is None:
        df = pd.DataFrame()
    write_dataframe(
        df,
        "tushare_pro",
        api_name,
        ts_code,
        cache_start_date,
        cache_end_date,
        ttl_seconds=ttl_seconds,
        extra=params,
    )
    return df


def _latest_daily_basic(ts_code: str, curr_date: str) -> pd.DataFrame:
    curr = datetime.strptime(curr_date, "%Y-%m-%d")
    start = (curr - timedelta(days=30)).strftime("%Y%m%d")
    end = curr.strftime("%Y%m%d")
    cached = read_dataframe("tushare_pro", "daily_basic", ts_code, start, end)
    if cached is not None:
        return cached
    df = _pro().daily_basic(ts_code=ts_code, start_date=start, end_date=end)
    if df is None:
        df = pd.DataFrame()
    write_dataframe(
        df,
        "tushare_pro",
        "daily_basic",
        ts_code,
        start,
        end,
        ttl_seconds=_cache_ttl(curr_date),
    )
    return df


def get_fundamentals(ticker: str, curr_date: str = None) -> str:
    ts_code = normalize_a_share_symbol(ticker)
    curr_date = curr_date or datetime.utcnow().strftime("%Y-%m-%d")
    static_ttl = get_config()["a_share_static_ttl_seconds"]

    stock_basic = read_dataframe("tushare_pro", "stock_basic", "ALL", None, None)
    if stock_basic is None:
        stock_basic = _pro().stock_basic(
            exchange="",
            list_status="L",
            fields="ts_code,symbol,name,area,industry,market,list_date",
        )
        write_dataframe(
            stock_basic,
            "tushare_pro",
            "stock_basic",
            "ALL",
            ttl_seconds=static_ttl,
        )
    profile = stock_basic[stock_basic["ts_code"] == ts_code] if not stock_basic.empty else pd.DataFrame()
    daily_basic = _latest_daily_basic(ts_code, curr_date)
    fina_indicator = _cached_pro_query(
        "fina_indicator",
        ts_code,
        None,
        curr_date,
        ttl_seconds=static_ttl,
    )

    lines = [f"# A-share Fundamentals for {ts_code}", f"# Vendor: TuShare Pro", ""]
    if not profile.empty:
        row = profile.iloc[0].to_dict()
        lines.extend(
            [
                f"Name: {row.get('name')}",
                f"Industry: {row.get('industry')}",
                f"Area: {row.get('area')}",
                f"Market: {row.get('market')}",
                f"List Date: {_date_dash(str(row.get('list_date')))}",
                "",
            ]
        )
    if not daily_basic.empty:
        row = daily_basic.sort_values("trade_date").iloc[-1].to_dict()
        lines.append("## Latest Daily Basic")
        for field in ["trade_date", "close", "turnover_rate", "volume_ratio", "pe", "pe_ttm", "pb", "ps_ttm", "dv_ttm", "total_mv", "circ_mv"]:
            if field in row and pd.notna(row[field]):
                lines.append(f"{field}: {row[field]}")
        lines.append("")
    if not fina_indicator.empty:
        latest = fina_indicator.sort_values("end_date").tail(5)
        lines.append("## Recent Financial Indicators")
        lines.append(latest.to_csv(index=False))
    return "\n".join(lines)


def _statement(api_name: str, ticker: str, freq: str = "quarterly", curr_date: str = None) -> str:
    ts_code = normalize_a_share_symbol(ticker)
    curr_date = curr_date or datetime.utcnow().strftime("%Y-%m-%d")
    curr = datetime.strptime(curr_date, "%Y-%m-%d")
    start = (curr - timedelta(days=365 * 5)).strftime("%Y%m%d")
    end = curr.strftime("%Y%m%d")
    df = _cached_pro_query(
        api_name,
        ts_code,
        start,
        end,
        ttl_seconds=get_config()["a_share_static_ttl_seconds"],
        start_date=start,
        end_date=end,
    )
    if df.empty:
        return f"No {api_name} data found for {ts_code}"
    if "end_date" in df:
        df = df.sort_values("end_date", ascending=False)
    limit = 8 if freq.lower() == "quarterly" else 5
    header = f"# {api_name} for {ts_code} ({freq})\n# Vendor: TuShare Pro\n\n"
    return header + df.head(limit).to_csv(index=False)


def get_income_statement(ticker: str, freq: str = "quarterly", curr_date: str = None) -> str:
    return _statement("income", ticker, freq, curr_date)


def get_balance_sheet(ticker: str, freq: str = "quarterly", curr_date: str = None) -> str:
    return _statement("balancesheet", ticker, freq, curr_date)


def get_cashflow(ticker: str, freq: str = "quarterly", curr_date: str = None) -> str:
    return _statement("cashflow", ticker, freq, curr_date)
