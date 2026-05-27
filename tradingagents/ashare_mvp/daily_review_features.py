from __future__ import annotations

from .schemas import DailyReviewDataset, DailyReviewFeatures


class DailyReviewFeatureExtractor:
    def extract(self, dataset: DailyReviewDataset) -> DailyReviewFeatures:
        rising = len([m for m in dataset.top_gainers if (m.pct_change or 0) > 0])
        falling = len([m for m in dataset.top_losers if (m.pct_change or 0) < 0])
        avg_gainer = _avg([m.pct_change for m in dataset.top_gainers])
        avg_loser = _avg([m.pct_change for m in dataset.top_losers])
        sentiment = "震荡"
        if avg_gainer is not None and avg_loser is not None:
            if avg_gainer >= 6 and avg_gainer >= abs(avg_loser):
                sentiment = "偏强"
            elif abs(avg_loser) >= 6 and abs(avg_loser) > avg_gainer:
                sentiment = "偏弱"
            elif avg_gainer >= 4 and abs(avg_loser) >= 4:
                sentiment = "高波动分化"
        notes = list(dataset.notes)
        if not dataset.hot_sectors:
            notes.append("热点板块当前仅基于成交额活跃个股的行业聚类生成。")
        return DailyReviewFeatures(
            rising_count=rising,
            falling_count=falling,
            avg_gainer_move=avg_gainer,
            avg_loser_move=avg_loser,
            market_sentiment=sentiment,
            notes=notes,
        )


def _avg(values: list[float | None]) -> float | None:
    points = [value for value in values if value is not None]
    if not points:
        return None
    return sum(points) / len(points)
