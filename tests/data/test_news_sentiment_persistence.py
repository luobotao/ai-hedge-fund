"""Tests for news sentiment persistence in MySQL cache."""
import pytest
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.data.database import Base
from src.data.mysql_models import CompanyNewsItem


@pytest.fixture
def db_session():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_company_news_item_sentiment_persistence(db_session):
    """Test that sentiment column is correctly persisted to and retrieved from database."""
    # Insert a news item with positive sentiment
    news_positive = CompanyNewsItem(
        ticker="AAPL",
        date=datetime(2024, 1, 1, 10, 0, 0),
        title="Apple Reports Record Earnings",
        content="Apple Inc. announced record earnings today...",
        url="https://example.com/news/1",
        source="Example News",
        data_source="test_source",
        sentiment="positive",
    )
    db_session.add(news_positive)

    # Insert a news item with None sentiment
    news_no_sentiment = CompanyNewsItem(
        ticker="MSFT",
        date=datetime(2024, 1, 2, 10, 0, 0),
        title="Microsoft Releases Update",
        content="Microsoft released a software update...",
        url="https://example.com/news/2",
        source="Example News",
        data_source="test_source",
        sentiment=None,
    )
    db_session.add(news_no_sentiment)
    db_session.commit()

    # Query them back from the database
    retrieved_positive = db_session.query(CompanyNewsItem).filter_by(ticker="AAPL").first()
    retrieved_no_sentiment = db_session.query(CompanyNewsItem).filter_by(ticker="MSFT").first()

    # Assert the sentiment values are correctly persisted and retrieved
    assert retrieved_positive is not None
    assert retrieved_positive.sentiment == "positive"

    assert retrieved_no_sentiment is not None
    assert retrieved_no_sentiment.sentiment is None


import os
from src.data.models import CompanyNews
from src.data.mysql_cache import MySQLCacheManager
import src.data.mysql_cache as _mc_module
import src.data.database as _db_module
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


@pytest.fixture
def cache():
    """SQLite in-memory cache for testing with proper schema recreation."""
    # Set up in-memory SQLite database
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"

    # Reset the database module state to force re-initialization
    _mc_module._db_initialized = False

    # Create a new engine and session for this test
    test_engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})

    # Update the database module's engine and SessionLocal
    original_engine = _db_module.engine
    original_session_local = _db_module.SessionLocal

    _db_module.engine = test_engine
    _db_module.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    # Import models and create tables
    from src.data.mysql_models import CompanyNewsItem
    _db_module.Base.metadata.create_all(bind=test_engine)

    # Create the cache manager
    mgr = MySQLCacheManager()

    yield mgr

    # Cleanup
    mgr.close()

    # Restore original engine and SessionLocal
    _db_module.engine = original_engine
    _db_module.SessionLocal = original_session_local


def test_save_company_news_persists_sentiment(cache):
    """save_company_news should store the sentiment field."""
    news = [
        CompanyNews(
            ticker="03690.HK",
            title="美团Q4业绩超预期",
            author="Reuters",
            source="Reuters",
            date="2026-03-24T10:00:00",
            url="https://example.com/1",
            sentiment="positive",
        )
    ]
    cache.save_company_news("03690.HK", news)

    retrieved = cache.get_company_news("03690.HK", "2026-03-24", "2026-03-24")
    assert len(retrieved) == 1
    assert retrieved[0].sentiment == "positive"


def test_save_company_news_none_sentiment(cache):
    """save_company_news should handle sentiment=None gracefully."""
    news = [
        CompanyNews(
            ticker="03690.HK",
            title="港股震荡",
            author="Bloomberg",
            source="Bloomberg",
            date="2026-03-24T11:00:00",
            url="https://example.com/2",
            sentiment=None,
        )
    ]
    cache.save_company_news("03690.HK", news)

    retrieved = cache.get_company_news("03690.HK", "2026-03-24", "2026-03-24")
    assert len(retrieved) == 1
    assert retrieved[0].sentiment is None


def test_save_company_news_updates_existing_sentiment(cache):
    """save_company_news should update sentiment on an existing record."""
    # First insert: no sentiment
    cache.save_company_news("03690.HK", [
        CompanyNews(
            ticker="03690.HK",
            title="美团发布新产品",
            author="Reuters",
            source="Reuters",
            date="2026-03-24T12:00:00",
            url="https://example.com/3",
            sentiment=None,
        )
    ])

    # Second insert: same record, now with sentiment
    cache.save_company_news("03690.HK", [
        CompanyNews(
            ticker="03690.HK",
            title="美团发布新产品",
            author="Reuters",
            source="Reuters",
            date="2026-03-24T12:00:00",
            url="https://example.com/3",
            sentiment="positive",
        )
    ])

    retrieved = cache.get_company_news("03690.HK", "2026-03-24", "2026-03-24")
    assert len(retrieved) == 1
    assert retrieved[0].sentiment == "positive"


from unittest.mock import patch, MagicMock


def _make_news(title: str, sentiment=None) -> CompanyNews:
    return CompanyNews(
        ticker="03690.HK",
        title=title,
        author="Test",
        source="AKShare",
        date="2026-03-24T10:00:00",
        url="https://example.com",
        sentiment=sentiment,
    )


def test_news_sentiment_agent_writes_back_to_cache():
    """After LLM analysis, news_sentiment_agent should persist enriched news to cache."""
    from src.agents.news_sentiment import news_sentiment_agent

    mock_news = [_make_news("美团Q4业绩超预期"), _make_news("港股下跌")]

    state = {
        "data": {
            "tickers": ["03690.HK"],
            "end_date": "2026-03-24",
            "analyst_signals": {},
        },
        "metadata": {"model_name": "test-model", "model_provider": "test"},
        "messages": [],
    }

    mock_sentiment_response = MagicMock()
    mock_sentiment_response.sentiment = "positive"
    mock_sentiment_response.confidence = 80

    mock_dual_cache = MagicMock()

    with patch("src.agents.news_sentiment.get_company_news", return_value=mock_news), \
         patch("src.agents.news_sentiment.call_llm", return_value=mock_sentiment_response), \
         patch("src.agents.news_sentiment._get_dual_cache", return_value=mock_dual_cache):

        news_sentiment_agent(state)

        # Verify set_company_news was called with sentiment-enriched news
        mock_dual_cache.set_company_news.assert_called_once()
        saved_news = mock_dual_cache.set_company_news.call_args.args[4]  # 5th positional arg
        assert any(n.sentiment is not None for n in saved_news), \
            "At least one news item should have sentiment set after LLM analysis"
