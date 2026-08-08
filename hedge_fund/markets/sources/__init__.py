"""Data sources for different markets."""

from hedge_fund.markets.sources.akshare_source import AKShareSource
from hedge_fund.markets.sources.akshare_news_source import AKShareNewsSource
from hedge_fund.markets.sources.yfinance_source import YFinanceSource
from hedge_fund.markets.sources.newsnow_source import NewsNowSource
from hedge_fund.markets.sources.sina_finance_source import SinaFinanceSource
from hedge_fund.markets.sources.xueqiu_source import XueqiuSource

__all__ = [
    "AKShareSource",
    "AKShareNewsSource",
    "YFinanceSource",
    "NewsNowSource",
    "SinaFinanceSource",
    "XueqiuSource",
]
