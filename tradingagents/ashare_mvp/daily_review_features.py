from __future__ import annotations

from .schemas import DailyReviewDataset, DailyReviewFeatures


class DailyReviewFeatureExtractor:
    def extract(self, dataset: DailyReviewDataset) -> DailyReviewFeatures:
        rising = len([m for m in dataset.top_gainers if (m.pct_change or 0) > 0])
        falling = len([m for m in dataset.top_losers if (m.pct_change or 0) < 0])
        avg_gainer = _avg([m.pct_change for m in dataset.top_gainers])
        avg_loser = _avg([m.pct_change for m in dataset.top_losers])
        sentiment = _derive_sentiment(dataset, avg_gainer, avg_loser)
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


def _derive_sentiment(
    dataset: DailyReviewDataset,
    avg_gainer: float | None,
    avg_loser: float | None,
) -> str:
    index_moves = [idx.pct_change for idx in dataset.indices if idx.pct_change is not None]
    positive_indexes = len([move for move in index_moves if move > 0])
    negative_indexes = len([move for move in index_moves if move < 0])
    avg_index_move = _avg(index_moves)

    if avg_gainer is not None and avg_loser is not None and avg_gainer >= 4 and abs(avg_loser) >= 4:
        if negative_indexes >= 2:
            return "高波动分化"
        if positive_indexes >= 2 and (avg_index_move or 0) > 0.3:
            return "偏强"
        return "高波动分化"

    if positive_indexes >= 2 and (avg_index_move or 0) > 0.5:
        return "偏强"
    if negative_indexes >= 2 and (avg_index_move or 0) < -0.5:
        return "偏弱"
    return "震荡"
