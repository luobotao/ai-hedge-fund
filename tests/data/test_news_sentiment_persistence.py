"""Tests for news sentiment persistence in MySQL cache."""
import pytest
from src.data.mysql_models import CompanyNewsItem


def test_company_news_item_has_sentiment_column():
    """CompanyNewsItem should have a sentiment column."""
    columns = [c.name for c in CompanyNewsItem.__table__.columns]
    assert "sentiment" in columns
