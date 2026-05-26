import copy
import tempfile
import unittest
from unittest.mock import Mock, patch

import pytest

import tradingagents.default_config as default_config
from tradingagents.dataflows.a_share_utils import (
    is_a_share_symbol,
    normalize_a_share_symbol,
    to_akshare_symbol,
)
from tradingagents.dataflows.config import get_config, set_config
from tradingagents.dataflows.exceptions import DataVendorUnavailable
from tradingagents.dataflows.interface import route_to_vendor


@pytest.mark.unit
class AShareDataflowTests(unittest.TestCase):
    def setUp(self):
        cfg = copy.deepcopy(default_config.DEFAULT_CONFIG)
        cfg["data_cache_dir"] = tempfile.mkdtemp()
        set_config(cfg)

    def test_normalize_a_share_symbol(self):
        self.assertEqual(normalize_a_share_symbol("600519"), "600519.SH")
        self.assertEqual(normalize_a_share_symbol("000001"), "000001.SZ")
        self.assertEqual(normalize_a_share_symbol("688981"), "688981.SH")
        self.assertEqual(normalize_a_share_symbol("830799"), "830799.BJ")
        self.assertEqual(normalize_a_share_symbol("600519.sh"), "600519.SH")

    def test_to_akshare_symbol(self):
        self.assertEqual(to_akshare_symbol("600519.SH"), "600519")
        self.assertEqual(to_akshare_symbol("000001"), "000001")

    def test_is_a_share_symbol(self):
        self.assertTrue(is_a_share_symbol("600519.SH"))
        self.assertTrue(is_a_share_symbol("600519"))
        self.assertFalse(is_a_share_symbol("AAPL"))

    def test_cn_market_region_applies_vendor_defaults(self):
        set_config({"market_region": "cn"})
        cfg = get_config()
        self.assertEqual(cfg["data_vendors"]["core_stock_apis"], "tushare_pro,akshare")
        self.assertEqual(cfg["data_vendors"]["technical_indicators"], "tushare_pro,akshare")
        self.assertEqual(cfg["data_vendors"]["fundamental_data"], "tushare_pro")
        self.assertEqual(cfg["data_vendors"]["news_data"], "search_news,akshare")

    def test_a_share_symbol_does_not_fallback_to_yfinance_news(self):
        set_config(
            {
                "market_region": "us",
                "data_vendors": {"news_data": "yfinance"},
                "search_news_api_key": None,
            }
        )
        yfinance_mock = Mock(return_value="yfinance should not be called")
        with patch.dict(
            "tradingagents.dataflows.interface.VENDOR_METHODS",
            {
                "get_news": {
                    "search_news": Mock(side_effect=DataVendorUnavailable("no key")),
                    "akshare": Mock(side_effect=DataVendorUnavailable("no news")),
                    "yfinance": yfinance_mock,
                }
            },
        ):
            with self.assertRaises(RuntimeError):
                route_to_vendor("get_news", "600326.SH", "2026-05-20", "2026-05-26")
        yfinance_mock.assert_not_called()

    def test_cn_keyword_news_query_does_not_parse_as_ticker(self):
        set_config(
            {
                "market_region": "cn",
                "search_news_api_key": None,
            }
        )
        with patch(
            "tradingagents.dataflows.akshare_data._get_keyword_news",
            return_value="keyword news",
        ) as keyword_news:
            result = route_to_vendor("get_news", "信托", "2026-05-20", "2026-05-26")
        self.assertEqual(result, "keyword news")
        keyword_news.assert_called_once_with("信托", "2026-05-20", "2026-05-26")
