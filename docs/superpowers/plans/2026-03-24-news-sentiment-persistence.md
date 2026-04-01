# News Sentiment Persistence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 `news_sentiment_agent` 用 LLM 分析新闻情感后，将结果持久化到 MySQL，并让后续读取时能正确返回 `sentiment` 字段，使 `sentiment_analyst_agent` 也能正常工作。

**Architecture:** 在 MySQL `company_news` 表增加 `sentiment` 列；`save_company_news` 存储时写入 sentiment；`get_company_news` 读取时返回 sentiment；`news_sentiment_agent` 完成 LLM 分析后将带 sentiment 的新闻回写缓存（L1+L2）。

**Tech Stack:** Python, SQLAlchemy, MySQL, Pydantic, pytest

---

## File Map

| 文件 | 变更类型 | 职责 |
|------|----------|------|
| `src/data/mysql_models.py` | Modify | 增加 `sentiment` 列到 `CompanyNewsItem` |
| `src/data/mysql_cache.py` | Modify | `save_company_news` 写入 sentiment；`get_company_news` 读取 sentiment |
| `src/agents/news_sentiment.py` | Modify | LLM 分析后回写缓存（调用 `set_company_news`） |
| `tests/data/test_news_sentiment_persistence.py` | Create | 单元测试覆盖上述三处变更 |

---

### Task 1: 给 `CompanyNewsItem` 增加 `sentiment` 列

**Files:**
- Modify: `src/data/mysql_models.py`
- Test: `tests/data/test_news_sentiment_persistence.py`

- [ ] **Step 1: 写失败测试**

新建文件 `tests/data/test_news_sentiment_persistence.py`：

```python
"""Tests for news sentiment persistence in MySQL cache."""
import pytest
from src.data.mysql_models import CompanyNewsItem


def test_company_news_item_has_sentiment_column():
    """CompanyNewsItem should have a sentiment column."""
    columns = [c.name for c in CompanyNewsItem.__table__.columns]
    assert "sentiment" in columns
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd /Users/luobotao/.openclaw/workspace/ai-hedge-fund
poetry run pytest tests/data/test_news_sentiment_persistence.py::test_company_news_item_has_sentiment_column -v
```

期望：FAIL，`AssertionError: assert 'sentiment' in [...]`

- [ ] **Step 3: 在 `mysql_models.py` 增加 `sentiment` 列**

文件：`src/data/mysql_models.py`，在 `CompanyNewsItem` 类的 `data_source` 列之后、`created_at` 之前添加：

```python
sentiment = Column(String(20), nullable=True)  # 'positive', 'negative', 'neutral'
```

完整的 `CompanyNewsItem` 类列定义应如下：
```python
class CompanyNewsItem(Base):
    __tablename__ = "company_news"

    id = Column(Integer if is_sqlite else BigInteger, primary_key=True, autoincrement=True)
    ticker = Column(String(20), nullable=False, index=True)
    date = Column(DateTime, nullable=False, index=True)
    title = Column(Text, nullable=True)
    content = Column(Text, nullable=True)
    url = Column(String(500), nullable=True)
    source = Column(String(100), nullable=True)
    data_source = Column(String(50), nullable=False)
    sentiment = Column(String(20), nullable=True)  # ← 新增
    created_at = Column(DateTime, default=dt.now if is_sqlite else func.now(), nullable=False)
    updated_at = Column(DateTime, default=dt.now if is_sqlite else func.now(), onupdate=dt.now if is_sqlite else func.now(), nullable=False)

    __table_args__ = (Index("idx_company_news_ticker_date", "ticker", "date"),)
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
poetry run pytest tests/data/test_news_sentiment_persistence.py::test_company_news_item_has_sentiment_column -v
```

期望：PASS

- [ ] **Step 5: 执行数据库迁移**

项目使用 `create_all` 方式建表（非 Alembic），已有数据库需手动加列。注意数据库名用反引号包裹（含连字符）：

```bash
mysql -u root -p -D `hedge-fund` -e "ALTER TABLE company_news ADD COLUMN sentiment VARCHAR(20) NULL AFTER data_source;"
```

如果表不存在（首次运行），`create_all` 会自动创建带 sentiment 列的表，无需手动迁移。

- [ ] **Step 6: Commit**

```bash
git add src/data/mysql_models.py tests/data/test_news_sentiment_persistence.py
git commit -m "feat: add sentiment column to CompanyNewsItem MySQL model"
```

---

### Task 2: `mysql_cache.py` 存取时支持 `sentiment`

**Files:**
- Modify: `src/data/mysql_cache.py`
- Test: `tests/data/test_news_sentiment_persistence.py`

- [ ] **Step 1: 写失败测试**

在 `tests/data/test_news_sentiment_persistence.py` 追加（参考已有的 `tests/data/test_mysql_cache_manager.py` 中的 fixture 模式）：

```python
import os
from src.data.models import CompanyNews
from src.data.mysql_cache import MySQLCacheManager
import src.data.mysql_cache as _mc_module


@pytest.fixture
def cache():
    """SQLite in-memory cache for testing. Mirrors pattern in test_mysql_cache_manager.py."""
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"
    # Reset init flag so MySQLCacheManager re-runs init_db() with the new URL
    _mc_module._db_initialized = False
    mgr = MySQLCacheManager()
    yield mgr
    mgr.close()


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
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
poetry run pytest tests/data/test_news_sentiment_persistence.py -v -k "save_company_news"
```

期望：`test_save_company_news_persists_sentiment` FAIL（sentiment 未被存储/读取）

- [ ] **Step 3: 修改 `mysql_cache.py` 的 `save_company_news`**

文件：`src/data/mysql_cache.py`，`save_company_news` 方法中：

**原代码**（约 384-395 行）：
```python
if not existing:
    # Insert new record
    new_news = CompanyNewsItem(
        ticker=ticker,
        date=news_dt,
        title=news.title if hasattr(news, "title") else None,
        content=news.content if hasattr(news, "content") else None,
        url=news.url if hasattr(news, "url") else None,
        source=news.source if hasattr(news, "source") else None,
        data_source=data_source,
    )
    session.add(new_news)
```

**改为**：
```python
if not existing:
    # Insert new record
    new_news = CompanyNewsItem(
        ticker=ticker,
        date=news_dt,
        title=news.title if hasattr(news, "title") else None,
        content=news.content if hasattr(news, "content") else None,
        url=news.url if hasattr(news, "url") else None,
        source=news.source if hasattr(news, "source") else None,
        data_source=data_source,
        sentiment=news.sentiment if hasattr(news, "sentiment") else None,
    )
    session.add(new_news)
else:
    # Update sentiment whenever the new value differs (handles None→value and value→value)
    new_sentiment = news.sentiment if hasattr(news, "sentiment") else None
    if new_sentiment is not None and existing.sentiment != new_sentiment:
        existing.sentiment = new_sentiment
```

- [ ] **Step 4: 修改 `mysql_cache.py` 的 `get_company_news`**

文件：`src/data/mysql_cache.py`，`get_company_news` 方法中：

**原代码**（约 433-444 行）：
```python
news_list = [
    CompanyNews(
        ticker=result.ticker,
        date=result.date.isoformat(),
        title=result.title or "",
        author="Unknown",
        url=result.url or "",
        source=result.source or "Unknown",
        sentiment=None,  # ← 硬编码
    )
    for result in results
]
```

**改为**：
```python
news_list = [
    CompanyNews(
        ticker=result.ticker,
        date=result.date.isoformat(),
        title=result.title or "",
        author="Unknown",
        url=result.url or "",
        source=result.source or "Unknown",
        sentiment=result.sentiment,  # ← 从数据库读取
    )
    for result in results
]
```

- [ ] **Step 5: 运行测试，确认通过**

```bash
poetry run pytest tests/data/test_news_sentiment_persistence.py -v
```

期望：所有测试 PASS

- [ ] **Step 6: Commit**

```bash
git add src/data/mysql_cache.py tests/data/test_news_sentiment_persistence.py
git commit -m "feat: persist and retrieve sentiment in mysql_cache company_news"
```

---

### Task 3: `news_sentiment_agent` 分析后回写缓存

**Files:**
- Modify: `src/agents/news_sentiment.py`
- Test: `tests/data/test_news_sentiment_persistence.py`

- [ ] **Step 1: 写失败测试**

在 `tests/data/test_news_sentiment_persistence.py` 追加：

```python
from unittest.mock import patch, MagicMock
from src.data.models import CompanyNews


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
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
poetry run pytest tests/data/test_news_sentiment_persistence.py::test_news_sentiment_agent_writes_back_to_cache -v
```

期望：FAIL，`AssertionError: Expected 'set_company_news' to have been called once`

- [ ] **Step 3: 修改 `news_sentiment.py` 回写缓存**

文件：`src/agents/news_sentiment.py`：

**1. 修改导入行**（原有 `from src.tools.api import get_company_news`）：

```python
from src.tools.api import get_company_news, _get_dual_cache
```

**2. 在 `if articles_without_sentiment:` 块末尾**（LLM 分析循环结束后、`# Aggregate sentiment` 注释之前）添加：

```python
                # Persist sentiment-enriched news back to cache (L1 + L2).
                # Uses end_date as start_date to match the agent's query window
                # (no start_date was passed to get_company_news above).
                _get_dual_cache().set_company_news(
                    ticker,
                    end_date,
                    end_date,
                    100,
                    company_news,
                )
```

完整的 `if company_news:` 块修改后如下：

```python
        if company_news:
            recent_articles = company_news[:10]
            articles_without_sentiment = [news for news in recent_articles if news.sentiment is None]

            if articles_without_sentiment:
                num_articles_to_analyze = 5
                articles_to_analyze = articles_without_sentiment[:num_articles_to_analyze]
                progress.update_status(agent_id, ticker, f"Analyzing sentiment for {len(articles_to_analyze)} articles")

                for idx, news in enumerate(articles_to_analyze):
                    progress.update_status(agent_id, ticker, f"Analyzing sentiment for article {idx + 1} of {len(articles_to_analyze)}")
                    prompt = (
                        f"Please analyze the sentiment of the following news headline "
                        f"with the following context: "
                        f"The stock is {ticker}. "
                        f"Determine if sentiment is 'positive', 'negative', or 'neutral' for the stock {ticker} only. "
                        f"Also provide a confidence score for your prediction from 0 to 100. "
                        f"Respond in JSON format.\n\n"
                        f"Headline: {news.title}"
                    )
                    response = call_llm(prompt, Sentiment, agent_name=agent_id, state=state)
                    if response:
                        news.sentiment = response.sentiment.lower()
                        sentiment_confidences[id(news)] = response.confidence
                    else:
                        news.sentiment = "neutral"
                        sentiment_confidences[id(news)] = 0
                    sentiments_classified_by_llm += 1

                # Persist sentiment-enriched news back to cache (L1 + L2).
                # Uses end_date as start_date to match the agent's query window
                # (no start_date was passed to get_company_news above).
                _get_dual_cache().set_company_news(
                    ticker,
                    end_date,
                    end_date,
                    100,
                    company_news,
                )

            # Aggregate sentiment across all articles
            sentiment = pd.Series([n.sentiment for n in company_news]).dropna()
            news_signals = np.where(sentiment == "negative", "bearish",
                                  np.where(sentiment == "positive", "bullish", "neutral")).tolist()
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
poetry run pytest tests/data/test_news_sentiment_persistence.py -v
```

期望：所有测试 PASS

- [ ] **Step 5: 运行全量测试，确认无回归**

```bash
poetry run pytest -v --timeout=60
```

期望：所有已有测试仍然 PASS

- [ ] **Step 6: Commit**

```bash
git add src/agents/news_sentiment.py tests/data/test_news_sentiment_persistence.py
git commit -m "feat: write back LLM-analyzed sentiment to cache in news_sentiment_agent"
```

---

## 验证端到端流程

完成上述三个 Task 后，手动运行一次分析验证：

```bash
poetry run python src/main.py --tickers 03690.HK --analysts "news_sentiment,sentiment" --model "MiniMax-M2.5" --end-date 2026-03-24
```

预期结果：
1. 日志出现 `[AKShareNews] ✓ Got N news from AKShareNews`
2. Sentiment Analyst 的 `total_articles` > 0
3. MySQL `company_news` 表中 `sentiment` 列有值（非全 NULL）

```sql
SELECT ticker, title, sentiment, date FROM company_news WHERE ticker = '03690.HK' ORDER BY date DESC LIMIT 10;
```
