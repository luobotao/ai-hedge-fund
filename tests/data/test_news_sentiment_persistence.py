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
