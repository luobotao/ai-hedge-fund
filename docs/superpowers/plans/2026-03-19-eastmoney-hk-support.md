# Eastmoney HK Stock Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the existing `EastmoneySource` to support Hong Kong stocks, then register it as a backup source in `HKStockAdapter`.

**Architecture:** The existing `EastmoneySource` already handles CN stocks via Eastmoney's K-line and financial APIs. The same APIs support HK stocks using a different `secid` prefix (`116.` for HK market). We extend `EastmoneySource` to detect HK tickers and convert them to the correct `secid`, then add `EastmoneySource` to `HKStockAdapter`'s source list as a backup between SinaFinance and AKShare.

**Tech Stack:** Python, `requests`, existing `DataSource` / `MarketAdapter` base classes, `pytest`

---

## File Map

| File | Action | Purpose |
|------|--------|---------|
| `src/markets/sources/eastmoney_source.py` | Modify | Add HK ticker detection, HK secid conversion, extend `supports_market` |
| `src/markets/hk_stock.py` | Modify | Add `EastmoneySource` to data_sources list (position 2, after SinaFinance) and update validator weights |
| `tests/markets/sources/test_eastmoney_source.py` | Modify | Add unit tests for HK ticker detection and secid conversion |
| `tests/markets/test_hk_stock.py` | Modify | Add test verifying EastmoneySource is in HK adapter's source list |
| `tests/integration/test_eastmoney_hk_e2e.py` | Create | End-to-end integration test hitting real Eastmoney API for a HK stock |

---

## Key Facts About Eastmoney HK API

Eastmoney uses `secid` format `116.XXXXX` for HK stocks (5-digit code, e.g., `116.03690` for Meituan 03690).

- K-line API: same `KLINE_API` endpoint, same params, just different `secid`
- Financial metrics API: same `FINANCE_API` endpoint, same params, same field names
- The existing `_parse_klines` and `_parse_financial_metrics` methods work unchanged for HK data
- Currency for HK stocks is HKD (not CNY)

## Pre-existing Test Issues (Known)

Before starting, be aware that these test files contain stale tests referencing removed `yfinance` code:
- `tests/markets/test_hk_stock.py` — has tests patching `yfinance`; skip stale tests, only run by test name
- `tests/markets/test_hk_stock_adapter.py` — has `test_get_prices_fallback` patching `YFinanceSource`; skip this file in regression runs

Also, `tests/markets/sources/test_eastmoney_source.py` has an existing test `test_supports_market` that asserts `supports_market("HK") is False`. **This must be updated in Task 1** when we change `supports_market`.

---

### Task 1: Add HK ticker detection to EastmoneySource

**Files:**
- Modify: `src/markets/sources/eastmoney_source.py`
- Modify: `tests/markets/sources/test_eastmoney_source.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/markets/sources/test_eastmoney_source.py`:

```python
def test_detect_hk_ticker_with_suffix():
    source = EastmoneySource()
    assert source._detect_hk_ticker("0700.HK") is True
    assert source._detect_hk_ticker("03690.HK") is True

def test_detect_hk_ticker_five_digit():
    source = EastmoneySource()
    assert source._detect_hk_ticker("00700") is True
    assert source._detect_hk_ticker("03690") is True

def test_detect_hk_ticker_four_digit():
    """4-digit codes (e.g., '0700') are also valid HK tickers."""
    source = EastmoneySource()
    assert source._detect_hk_ticker("0700") is True
    assert source._detect_hk_ticker("3690") is True

def test_detect_hk_ticker_rejects_cn():
    source = EastmoneySource()
    assert source._detect_hk_ticker("600000.SH") is False
    assert source._detect_hk_ticker("000001.SZ") is False
    assert source._detect_hk_ticker("AAPL") is False

def test_to_eastmoney_hk_secid():
    source = EastmoneySource()
    assert source._to_eastmoney_hk_secid("0700.HK") == "116.00700"
    assert source._to_eastmoney_hk_secid("03690.HK") == "116.03690"
    assert source._to_eastmoney_hk_secid("00700") == "116.00700"
    assert source._to_eastmoney_hk_secid("03690") == "116.03690"

def test_supports_market_hk():
    source = EastmoneySource()
    assert source.supports_market("HK") is True
    assert source.supports_market("CN") is True
    assert source.supports_market("US") is False
```

Also **update the existing `test_supports_market` test** in `tests/markets/sources/test_eastmoney_source.py` — find the assertion `supports_market("HK") is False` and change it to `True`:

```python
# OLD line in existing test_supports_market:
assert source.supports_market("HK") is False

# NEW:
assert source.supports_market("HK") is True
```

- [ ] **Step 2: Run tests to verify new tests fail (existing test_supports_market will pass after edit)**

```bash
poetry run pytest tests/markets/sources/test_eastmoney_source.py::test_detect_hk_ticker_with_suffix tests/markets/sources/test_eastmoney_source.py::test_to_eastmoney_hk_secid tests/markets/sources/test_eastmoney_source.py::test_supports_market_hk -v
```

Expected: FAIL (methods don't exist yet)

- [ ] **Step 3: Add HK ticker detection methods to EastmoneySource**

In `src/markets/sources/eastmoney_source.py`:

1. Change `supports_market` to also return True for HK:

```python
def supports_market(self, market: str) -> bool:
    """Eastmoney supports CN and HK markets."""
    return market.upper() in ("CN", "HK")
```

2. Add `_detect_hk_ticker` method after `_detect_cn_ticker`:

```python
def _detect_hk_ticker(self, ticker: str) -> bool:
    """
    Detect if ticker is HK market format.

    HK market ticker formats:
    - 0700.HK  (with suffix)
    - 03690.HK (with suffix)
    - 00700    (5-digit code)
    - 03690    (5-digit code)

    Args:
        ticker: Stock ticker

    Returns:
        True if HK market ticker
    """
    ticker_upper = ticker.upper()

    # Check for .HK suffix
    if ticker_upper.endswith('.HK'):
        return True

    # Check for 4-5 digit pure numeric code (HK stock codes)
    # HKStockAdapter.supports_ticker accepts 4-5 digit codes; we match the same range
    code = ticker.split('.')[0]
    if code.isdigit() and 4 <= len(code) <= 5:
        return True

    return False
```

3. Add `_to_eastmoney_hk_secid` method after `_to_eastmoney_secid`:

```python
def _to_eastmoney_hk_secid(self, ticker: str) -> str:
    """
    Convert HK ticker to Eastmoney secid format.

    HK stocks use prefix 116:
    - 0700.HK  → 116.00700
    - 03690.HK → 116.03690
    - 00700    → 116.00700

    Args:
        ticker: HK ticker (e.g., '0700.HK', '03690.HK', '00700')

    Returns:
        Eastmoney secid format (e.g., '116.00700')
    """
    # Remove .HK suffix if present
    ticker_upper = ticker.upper()
    if ticker_upper.endswith('.HK'):
        code = ticker[:-3]
    else:
        code = ticker.split('.')[0]

    # Ensure 5-digit zero-padded code
    code = code.zfill(5)
    return f"116.{code}"
```

- [ ] **Step 4: Run new tests to verify they pass**

```bash
poetry run pytest tests/markets/sources/test_eastmoney_source.py::test_detect_hk_ticker_with_suffix tests/markets/sources/test_eastmoney_source.py::test_detect_hk_ticker_five_digit tests/markets/sources/test_eastmoney_source.py::test_detect_hk_ticker_four_digit tests/markets/sources/test_eastmoney_source.py::test_detect_hk_ticker_rejects_cn tests/markets/sources/test_eastmoney_source.py::test_to_eastmoney_hk_secid tests/markets/sources/test_eastmoney_source.py::test_supports_market_hk -v
```

Expected: All PASS

- [ ] **Step 5: Run full test_eastmoney_source.py to confirm no regressions**

```bash
poetry run pytest tests/markets/sources/test_eastmoney_source.py -v
```

Expected: All PASS (including the updated `test_supports_market`)

- [ ] **Step 6: Commit**

```bash
git add src/markets/sources/eastmoney_source.py tests/markets/sources/test_eastmoney_source.py
git commit -m "feat: add HK ticker detection and secid conversion to EastmoneySource"
```

---

### Task 2: Extend get_prices and get_financial_metrics to handle HK tickers

**Files:**
- Modify: `src/markets/sources/eastmoney_source.py`
- Modify: `tests/markets/sources/test_eastmoney_source.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/markets/sources/test_eastmoney_source.py`:

```python
from unittest.mock import patch, MagicMock

def test_get_prices_hk_uses_hk_secid():
    """Verify HK ticker is converted to 116.XXXXX secid."""
    source = EastmoneySource()
    mock_response = MagicMock()
    mock_response.json.return_value = {
        'rc': 0,
        'data': {
            'klines': ['2024-01-02,100.0,102.0,103.0,99.0,1000000,0,0,0,0,0']
        }
    }
    mock_response.raise_for_status = MagicMock()

    with patch.object(source.session, 'get', return_value=mock_response) as mock_get:
        prices = source.get_prices("0700.HK", "2024-01-01", "2024-01-31")
        call_kwargs = mock_get.call_args
        assert call_kwargs[1]['params']['secid'] == '116.00700'
        assert len(prices) == 1
        assert prices[0]['close'] == 102.0

def test_get_prices_hk_rejects_invalid():
    """Verify non-HK/CN ticker returns empty list."""
    source = EastmoneySource()
    prices = source.get_prices("AAPL", "2024-01-01", "2024-01-31")
    assert prices == []

def test_get_financial_metrics_hk_uses_hk_secid():
    """Verify HK ticker financial metrics use 116.XXXXX secid."""
    source = EastmoneySource()
    mock_response = MagicMock()
    mock_response.json.return_value = {
        'data': {'f116': 1000000, 'f162': 15.5, 'f167': 2.0, 'f173': 10.0, 'f187': 25.0}
    }
    mock_response.raise_for_status = MagicMock()

    with patch.object(source.session, 'get', return_value=mock_response) as mock_get:
        metrics = source.get_financial_metrics("03690.HK", "2024-01-31")
        call_kwargs = mock_get.call_args
        assert call_kwargs[1]['params']['secid'] == '116.03690'
        assert metrics is not None
        assert metrics['currency'] == 'HKD'

def test_get_financial_metrics_hk_currency_is_hkd():
    """Verify HK financial metrics return HKD currency."""
    source = EastmoneySource()
    mock_response = MagicMock()
    mock_response.json.return_value = {
        'data': {'f116': 500000, 'f162': 20.0, 'f167': 3.0}
    }
    mock_response.raise_for_status = MagicMock()

    with patch.object(source.session, 'get', return_value=mock_response):
        metrics = source.get_financial_metrics("00700", "2024-01-31")
        assert metrics['currency'] == 'HKD'
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
poetry run pytest tests/markets/sources/test_eastmoney_source.py::test_get_prices_hk_uses_hk_secid tests/markets/sources/test_eastmoney_source.py::test_get_financial_metrics_hk_uses_hk_secid tests/markets/sources/test_eastmoney_source.py::test_get_financial_metrics_hk_currency_is_hkd -v
```

Expected: FAIL

- [ ] **Step 3: Update get_prices to route HK tickers**

In `src/markets/sources/eastmoney_source.py`, update `get_prices`:

Replace the CN-only validation block at the start of `get_prices`:

```python
# OLD:
if not self._detect_cn_ticker(ticker):
    self.logger.warning(f"[Eastmoney] Ticker {ticker} is not CN market format")
    return []
secid = self._to_eastmoney_secid(ticker)
```

With:

```python
# NEW:
if self._detect_cn_ticker(ticker):
    secid = self._to_eastmoney_secid(ticker)
elif self._detect_hk_ticker(ticker):
    secid = self._to_eastmoney_hk_secid(ticker)
else:
    self.logger.warning(f"[Eastmoney] Ticker {ticker} is not CN or HK market format")
    return []
```

- [ ] **Step 4: Update get_financial_metrics to route HK tickers**

In `src/markets/sources/eastmoney_source.py`, update `get_financial_metrics`:

Replace the CN-only validation block at the start of `get_financial_metrics`:

```python
# OLD:
if not self._detect_cn_ticker(ticker):
    self.logger.warning(f"[Eastmoney] Ticker {ticker} is not CN market format")
    return None
secid = self._to_eastmoney_secid(ticker)
```

With:

```python
# NEW:
if self._detect_cn_ticker(ticker):
    secid = self._to_eastmoney_secid(ticker)
    currency = "CNY"
elif self._detect_hk_ticker(ticker):
    secid = self._to_eastmoney_hk_secid(ticker)
    currency = "HKD"
else:
    self.logger.warning(f"[Eastmoney] Ticker {ticker} is not CN or HK market format")
    return None
```

Then update `_parse_financial_metrics` signature and call to pass currency:

```python
# Change the call inside get_financial_metrics:
metrics = self._parse_financial_metrics(finance_data, ticker, end_date, period, currency)
```

Update `_parse_financial_metrics` signature:

```python
def _parse_financial_metrics(self, data: Dict, ticker: str, end_date: str, period: str, currency: str = "CNY") -> Optional[Dict]:
```

And change the hardcoded currency line inside it:

```python
# OLD:
"currency": "CNY",  # CN market uses CNY

# NEW:
"currency": currency,
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
poetry run pytest tests/markets/sources/test_eastmoney_source.py::test_get_prices_hk_uses_hk_secid tests/markets/sources/test_eastmoney_source.py::test_get_prices_hk_rejects_invalid tests/markets/sources/test_eastmoney_source.py::test_get_financial_metrics_hk_uses_hk_secid tests/markets/sources/test_eastmoney_source.py::test_get_financial_metrics_hk_currency_is_hkd -v
```

Expected: All PASS

- [ ] **Step 6: Run full existing test suite to confirm no regressions**

```bash
poetry run pytest tests/markets/sources/test_eastmoney_source.py -v
```

Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add src/markets/sources/eastmoney_source.py tests/markets/sources/test_eastmoney_source.py
git commit -m "feat: extend EastmoneySource get_prices/get_financial_metrics to support HK tickers"
```

---

### Task 3: Register EastmoneySource in HKStockAdapter

**Files:**
- Modify: `src/markets/hk_stock.py`
- Modify: `tests/markets/test_hk_stock.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/markets/test_hk_stock.py`:

```python
from src.markets.sources.eastmoney_source import EastmoneySource

def test_hk_adapter_includes_eastmoney_source():
    """EastmoneySource should be in HKStockAdapter's data sources."""
    adapter = HKStockAdapter()
    source_names = [s.name for s in adapter.active_sources]
    assert "Eastmoney" in source_names

def test_hk_adapter_eastmoney_after_sina():
    """EastmoneySource should come after SinaFinance in priority order."""
    adapter = HKStockAdapter()
    source_names = [s.name for s in adapter.active_sources]
    sina_idx = source_names.index("SinaFinance")
    eastmoney_idx = source_names.index("Eastmoney")
    assert sina_idx < eastmoney_idx, "SinaFinance should be before Eastmoney"

def test_hk_adapter_eastmoney_before_akshare():
    """EastmoneySource should come before AKShare in priority order."""
    adapter = HKStockAdapter()
    source_names = [s.name for s in adapter.active_sources]
    eastmoney_idx = source_names.index("Eastmoney")
    akshare_idx = source_names.index("AKShare")
    assert eastmoney_idx < akshare_idx, "Eastmoney should be before AKShare"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
poetry run pytest tests/markets/test_hk_stock.py::test_hk_adapter_includes_eastmoney_source tests/markets/test_hk_stock.py::test_hk_adapter_eastmoney_after_sina tests/markets/test_hk_stock.py::test_hk_adapter_eastmoney_before_akshare -v
```

Expected: FAIL

- [ ] **Step 3: Update HKStockAdapter to include EastmoneySource**

In `src/markets/hk_stock.py`:

1. Add import at top:

```python
from src.markets.sources.eastmoney_source import EastmoneySource
```

2. Update `data_sources` list in `__init__`:

```python
# OLD:
data_sources = [
    XueqiuSource(),      # Primary for financials: most complete statements
    SinaFinanceSource(), # Primary for prices: free, stable
    AKShareSource(),     # Fallback: Backup
]
```

```python
# NEW:
data_sources = [
    XueqiuSource(),       # Primary for financials: most complete statements
    SinaFinanceSource(),  # Primary for prices: free, stable
    EastmoneySource(),    # Backup for prices & financials: same API, HK secid 116.XXXXX
    AKShareSource(),      # Last resort: single-period data, lower reliability
]
```

3. Update validator weights to include Eastmoney:

```python
# OLD:
hk_validator = validator or DataValidator(
    source_weights={
        "Xueqiu": 1.0,
        "AKShare": 0.05,
        "SinaFinance": 0.5,
    }
)
```

```python
# NEW:
hk_validator = validator or DataValidator(
    source_weights={
        "Xueqiu": 1.0,       # Primary: TTM financials, real-time P/E
        "SinaFinance": 0.5,   # Primary for prices
        "Eastmoney": 0.4,     # Backup: same API quality as CN, reliable HK data
        "AKShare": 0.05,      # Minimal: single-period data, unreliable for financials
    }
)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
poetry run pytest tests/markets/test_hk_stock.py::test_hk_adapter_includes_eastmoney_source tests/markets/test_hk_stock.py::test_hk_adapter_eastmoney_after_sina tests/markets/test_hk_stock.py::test_hk_adapter_eastmoney_before_akshare -v
```

Expected: All PASS

- [ ] **Step 5: Patch EastmoneySource in the existing multi-source test**

`tests/markets/test_hk_stock_adapter.py::TestHKStockAdapter::test_get_prices_multi_source` patches only 3 sources (Xueqiu, Sina, AKShare). After Task 3 adds `EastmoneySource` as the 4th source, this test will make a live network call to Eastmoney. Add a patch for it.

Find the test (look for `test_get_prices_multi_source` in `tests/markets/test_hk_stock_adapter.py`) and add a patch for `EastmoneySource.get_prices` that returns `[]`:

```python
# Add this patch alongside the existing ones in test_get_prices_multi_source:
@patch("src.markets.sources.eastmoney_source.EastmoneySource.get_prices", return_value=[])
```

The exact edit depends on whether the test uses decorators or `with patch(...)` — read the file and add the patch in the same style as the existing ones.

- [ ] **Step 6: Run new tests and the patched multi-source test**

```bash
poetry run pytest \
  tests/markets/test_hk_stock.py::test_hk_adapter_includes_eastmoney_source \
  tests/markets/test_hk_stock.py::test_hk_adapter_eastmoney_after_sina \
  tests/markets/test_hk_stock.py::test_hk_adapter_eastmoney_before_akshare \
  tests/markets/test_hk_stock_adapter.py::TestHKStockAdapter::test_get_prices_multi_source \
  -v
```

Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add src/markets/hk_stock.py tests/markets/test_hk_stock.py tests/markets/test_hk_stock_adapter.py
git commit -m "feat: add EastmoneySource as backup data source in HKStockAdapter"
```

---

### Task 4: End-to-end integration test

**Files:**
- Create: `tests/integration/test_eastmoney_hk_e2e.py`

- [ ] **Step 1: Write integration tests**

Create `tests/integration/test_eastmoney_hk_e2e.py`:

```python
"""End-to-end integration tests for Eastmoney HK stock data.

These tests hit the real Eastmoney API. Run only when internet is available.
Mark with pytest.mark.integration to skip in CI if needed.
"""
import pytest
from src.markets.sources.eastmoney_source import EastmoneySource


@pytest.mark.integration
class TestEastmoneyHKPrices:
    """Test Eastmoney price fetching for HK stocks."""

    def setup_method(self):
        self.source = EastmoneySource()

    def test_get_prices_meituan_hk_suffix(self):
        """Fetch Meituan prices using .HK suffix format."""
        prices = self.source.get_prices("03690.HK", "2024-01-01", "2024-01-31")
        assert len(prices) > 0, "Should return price data for Meituan"
        price = prices[0]
        assert 'open' in price
        assert 'close' in price
        assert 'high' in price
        assert 'low' in price
        assert 'volume' in price
        assert 'time' in price
        assert price['close'] > 0

    def test_get_prices_tencent_five_digit(self):
        """Fetch Tencent prices using 5-digit format."""
        prices = self.source.get_prices("00700", "2024-01-01", "2024-01-31")
        assert len(prices) > 0, "Should return price data for Tencent"
        assert prices[0]['close'] > 0

    def test_price_data_within_date_range(self):
        """Prices should fall within requested date range."""
        prices = self.source.get_prices("03690.HK", "2024-06-01", "2024-06-30")
        assert len(prices) > 0
        for p in prices:
            date_str = p['time'][:10]  # YYYY-MM-DD
            assert "2024-06" in date_str, f"Date {date_str} outside June 2024"


@pytest.mark.integration
class TestEastmoneyHKFinancialMetrics:
    """Test Eastmoney financial metrics for HK stocks."""

    def setup_method(self):
        self.source = EastmoneySource()

    def test_get_financial_metrics_meituan(self):
        """Fetch Meituan financial metrics."""
        metrics = self.source.get_financial_metrics("03690.HK", "2024-01-31")
        assert metrics is not None, "Should return metrics for Meituan"
        assert metrics['ticker'] == '03690.HK'
        assert metrics['currency'] == 'HKD'

    def test_financial_metrics_has_key_fields(self):
        """Financial metrics should have required fields."""
        metrics = self.source.get_financial_metrics("00700", "2024-01-31")
        assert metrics is not None
        # These fields should be present (may be None if not available)
        for field in ['market_cap', 'price_to_earnings_ratio', 'price_to_book_ratio',
                      'return_on_equity', 'gross_margin']:
            assert field in metrics, f"Missing field: {field}"

    def test_market_cap_is_positive(self):
        """Market cap should be a positive number for major HK stocks."""
        metrics = self.source.get_financial_metrics("00700", "2024-01-31")
        assert metrics is not None
        if metrics.get('market_cap'):
            assert metrics['market_cap'] > 0
```

- [ ] **Step 2: Run integration tests (requires internet)**

```bash
poetry run pytest tests/integration/test_eastmoney_hk_e2e.py -v -m integration
```

Expected: All PASS (may see some None fields if Eastmoney API doesn't return them, that's acceptable)

- [ ] **Step 3: Run non-integration tests to confirm no regressions (skip stale yfinance test files)**

```bash
poetry run pytest tests/ --ignore=tests/integration --ignore=tests/markets/test_hk_stock.py --ignore=tests/markets/test_hk_stock_adapter.py -v -x
```

Note: `test_hk_stock.py` and `test_hk_stock_adapter.py` are skipped here because they contain pre-existing failures from stale yfinance patches — these are not caused by our changes.

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_eastmoney_hk_e2e.py
git commit -m "test: add end-to-end integration tests for Eastmoney HK stock support"
```

---

### Task 5: Merge to master

- [ ] **Step 1: Final full test run (skip stale yfinance test files)**

```bash
poetry run pytest tests/ --ignore=tests/integration --ignore=tests/markets/test_hk_stock.py --ignore=tests/markets/test_hk_stock_adapter.py -v
```

Expected: All PASS

- [ ] **Step 2: Merge worktree branch to master**

```bash
git checkout master
git merge --no-ff <worktree-branch-name> -m "feat: extend EastmoneySource to support HK stocks, add as backup in HKStockAdapter"
```

- [ ] **Step 3: Verify master is clean**

```bash
git log --oneline -5
poetry run pytest tests/ --ignore=tests/integration -v
```

Expected: All PASS on master
