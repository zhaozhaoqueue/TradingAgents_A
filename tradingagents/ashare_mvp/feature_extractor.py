from __future__ import annotations

import math

import pandas as pd

from .schemas import StockMoveDataset, StockMoveFeatures


def _safe_float(value) -> float | None:
    try:
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return None
        return float(value)
    except Exception:
        return None


class FeatureExtractor:
    def extract(self, dataset: StockMoveDataset) -> StockMoveFeatures:
        history = dataset.history.copy().sort_values("Date").reset_index(drop=True)
        latest = history.iloc[-1]
        features = StockMoveFeatures(days_available=len(history))

        close = _safe_float(latest.get("Close"))
        prev_close = _safe_float(history.iloc[-2]["Close"]) if len(history) >= 2 else None
        amount = _safe_float(latest.get("Amount"))
        volume = _safe_float(latest.get("Volume"))

        history["close_5ma"] = history["Close"].rolling(5, min_periods=3).mean()
        history["close_10ma"] = history["Close"].rolling(10, min_periods=5).mean()
        history["close_20ma"] = history["Close"].rolling(20, min_periods=5).mean()
        history["vol_5ma"] = history["Volume"].rolling(5, min_periods=3).mean()
        history["vol_20ma"] = history["Volume"].rolling(20, min_periods=5).mean()

        latest_ma = history.iloc[-1]
        last_20 = history.tail(min(20, len(history)))
        high_20 = _safe_float(last_20["High"].max()) if not last_20.empty else None
        low_20 = _safe_float(last_20["Low"].min()) if not last_20.empty else None

        features.close = close
        features.amount = amount
        features.volume = volume
        features.turnover_rate = None
        features.close_5ma = _safe_float(latest_ma.get("close_5ma"))
        features.close_10ma = _safe_float(latest_ma.get("close_10ma"))
        features.close_20ma = _safe_float(latest_ma.get("close_20ma"))
        features.volume_ratio_vs_5d = _ratio(volume, _safe_float(latest_ma.get("vol_5ma")))
        features.volume_ratio_vs_20d = _ratio(volume, _safe_float(latest_ma.get("vol_20ma")))
        features.pct_change = ((close - prev_close) / prev_close * 100.0) if close and prev_close else None
        features.position_vs_20d_high = ((close / high_20) * 100.0) if close and high_20 else None
        features.position_vs_20d_low = ((close / low_20) * 100.0) if close and low_20 else None
        features.breakout_20d_high = bool(close and high_20 and close >= high_20)
        features.rebound_from_20d_low = bool(close and low_20 and prev_close and prev_close <= low_20 * 1.03 and close > prev_close)

        if features.pct_change is not None:
            if abs(features.pct_change) >= 7:
                features.flags.append("price_spike")
            elif abs(features.pct_change) >= 3:
                features.flags.append("price_move")

        if features.volume_ratio_vs_20d is not None:
            if features.volume_ratio_vs_20d >= 2:
                features.flags.append("volume_surge")
            elif features.volume_ratio_vs_20d >= 1.3:
                features.flags.append("volume_expansion")

        if features.breakout_20d_high:
            features.flags.append("breakout")
        if features.rebound_from_20d_low:
            features.flags.append("rebound")

        if features.close_20ma is None:
            features.notes.append("近 20 日样本不足，技术位置判断有限。")
        if amount is None:
            features.notes.append("成交额暂缺。")

        return features


def _ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator
