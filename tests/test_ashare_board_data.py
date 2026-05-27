from __future__ import annotations

import unittest

import pandas as pd
import pytest

from tradingagents.ashare_mvp.data.board_data import AShareBoardDataFetcher


class _FakeAk:
    def stock_board_industry_name_em(self):
        return pd.DataFrame(
            [
                {"板块名称": "机器人", "涨跌幅": 5.2, "板块代码": "BK1", "成交额": 100},
                {"板块名称": "算力", "涨跌幅": 3.1, "板块代码": "BK2", "成交额": 80},
                {"板块名称": "消费", "涨跌幅": -1.0, "板块代码": "BK3", "成交额": 60},
            ]
        )

    def stock_board_industry_hist_em(self, symbol: str, start_date: str, end_date: str, period: str, adjust: str):
        return pd.DataFrame(
            [
                {"日期": "2026-05-26", "涨跌幅": 1.2},
                {"日期": "2026-05-27", "涨跌幅": 2.8},
            ]
        )

    def stock_board_industry_cons_em(self, symbol: str):
        return pd.DataFrame(
            [
                {"代码": "300001", "名称": "甲公司", "涨跌幅": 9.8, "最新价": 12.3},
                {"代码": "300010", "名称": "乙公司", "涨跌幅": 6.5, "最新价": 11.1},
            ]
        )


@pytest.mark.unit
class BoardDataFetcherTests(unittest.TestCase):
    def test_fetch_hot_industry_boards(self):
        fetcher = AShareBoardDataFetcher(ak_client=_FakeAk())

        boards = fetcher.fetch_hot_industry_boards(top_n=2)

        self.assertEqual(len(boards), 2)
        self.assertEqual(boards[0].name, "机器人")
        self.assertGreater(boards[0].pct_change, boards[1].pct_change)

    def test_fetch_industry_snapshot(self):
        fetcher = AShareBoardDataFetcher(ak_client=_FakeAk())

        board = fetcher.fetch_industry_snapshot("机器人", "2026-05-27")

        self.assertIsNotNone(board)
        self.assertEqual(board.name, "机器人")
        self.assertEqual(board.pct_change, 2.8)
        self.assertEqual(board.top_constituents[0]["symbol"], "300001")
