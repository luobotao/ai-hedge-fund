# Financial Metrics Multi-Year & D/E Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix two data quality issues: (1) `get_financial_metrics()` returns only 1 period for HK/CN stocks even when `limit>1` is requested, causing Warren Buffett / Damodaran / Burry agents to report "缺乏历史数据"; (2) D/E ratio is computed as `total_liabilities / equity` (gross leverage ~0.9) instead of `total_debt / equity` (financial debt ~0.26), causing conflicting signals across agents.

**Architecture:** P1 fix: add a multi-year branch to `get_financial_metrics()` in `src/tools/api.py` that calls `adapter.get_historical_financial_metrics()` when `period="annual"` and `limit>1`, mirroring the existing pattern in `search_line_items()`. P2 fix: in `_compute_derived_metrics()` in `xueqiu_source.py`, compute a second ratio `debt_to_equity_financial` = `total_debt / shareholders_equity` when `total_debt` is available, and populate `debt_to_equity` with this more meaningful metric instead of the gross-liabilities version.

**Tech Stack:** Python, Pydantic, existing Xueqiu adapter stack

---

## File Map

| File | Change |
|------|--------|
| `src/tools/api.py:266-289` | Add multi-year branch to `get_financial_metrics()` for non-US stocks |
| `src/markets/router.py:136-154` | Add `get_historical_financial_metrics()` convenience method to `MarketRouter` |
| `src/markets/sources/xueqiu_source.py:153-155` | Fix `debt_to_equity` to use `total_debt` when available, fall back to `total_liabilities` |
| `tests/test_api_multi_year.py` | New test file for multi-year `get_financial_metrics` |
| `tests/markets/sources/test_xueqiu_source.py` | Add tests for corrected D/E calculation |

---

## Background Context

### P1: Why `get_financial_metrics()` only returns 1 period

Current flow for non-US stocks:
```
get_financial_metrics(ticker, end_date, period="ttm", limit=10)
  → _get_market_router().get_financial_metrics(ticker, end_date)   ← ignores period and limit!
  → adapter.get_financial_metrics(ticker, end_date)                ← single period
  → returns [single_metric]
```

The fix mirrors what `search_line_items()` already does at line 346-348:
```python
if period == "annual" and limit > 1:
    metrics_list = adapter.get_historical_financial_metrics(ticker, end_date, limit=limit)
```

### P2: Why D/E is 0.9 vs 0.26

`_compute_derived_metrics` currently computes:
```python
debt_to_equity = total_liabilities / shareholders_equity   # = 0.9 (gross leverage)
```

But `total_liabilities` includes operating liabilities (accounts payable, deferred revenue, etc.) — not just financial debt. The correct financial D/E uses only interest-bearing debt:
```python
debt_to_equity = total_debt / shareholders_equity          # = 0.26 (financial leverage)
```

`total_debt` (short_term + long_term debt) was added in the previous fix and is now available. When `total_debt` is present, use it. Fall back to `total_liabilities` when it's absent (e.g., for data sources that don't provide debt breakdown).

---

## Task 1: Fix D/E Ratio to Use total_debt When Available

**Files:**
- Modify: `src/markets/sources/xueqiu_source.py:153-155`
- Modify: `tests/markets/sources/test_xueqiu_source.py` (add to `TestXueqiuDerivedMetrics`)

- [ ] **Step 1: Write failing tests**

Add to `TestXueqiuDerivedMetrics` class in `tests/markets/sources/test_xueqiu_source.py`:

```python
def test_debt_to_equity_uses_total_debt_when_available(self):
    """When total_debt is present, D/E = total_debt / equity (not total_liabilities / equity)."""
    source = XueqiuSource()
    metrics = {
        "total_debt": 26000000000.0,        # 26B financial debt
        "total_liabilities": 90000000000.0,  # 90B gross liabilities
        "shareholders_equity": 100000000000.0,  # 100B equity
    }
    source._compute_derived_metrics(metrics)
    # Should use total_debt: 26B / 100B = 0.26
    assert metrics["debt_to_equity"] == pytest.approx(0.26)

def test_debt_to_equity_falls_back_to_total_liabilities_when_no_total_debt(self):
    """When total_debt is absent, fall back to total_liabilities / equity."""
    source = XueqiuSource()
    metrics = {
        "total_liabilities": 90000000000.0,
        "shareholders_equity": 100000000000.0,
    }
    source._compute_derived_metrics(metrics)
    # Falls back: 90B / 100B = 0.9
    assert metrics["debt_to_equity"] == pytest.approx(0.9)

def test_debt_to_equity_none_when_no_debt_data(self):
    """When neither total_debt nor total_liabilities is present, D/E is None."""
    source = XueqiuSource()
    metrics = {
        "shareholders_equity": 100000000000.0,
    }
    source._compute_derived_metrics(metrics)
    assert metrics.get("debt_to_equity") is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/luobotao/.openclaw/workspace/ai-hedge-fund
poetry run pytest tests/markets/sources/test_xueqiu_source.py::TestXueqiuDerivedMetrics::test_debt_to_equity_uses_total_debt_when_available -v
```
Expected: FAIL (currently uses `total_liabilities` always)

- [ ] **Step 3: Fix `_compute_derived_metrics` in xueqiu_source.py**

Find the existing `debt_to_equity` block (around line 153-155):
```python
        # debt_to_equity = total_liabilities / shareholders_equity (direct calculation)
        if metrics.get("debt_to_equity") is None:
            metrics["debt_to_equity"] = safe_div(get("total_liabilities"), get("shareholders_equity"))
```

Replace with:
```python
        # debt_to_equity: prefer total_debt (financial debt only) over total_liabilities (gross)
        # total_debt = short-term + long-term interest-bearing debt (more meaningful for investors)
        # total_liabilities includes operating liabilities (AP, deferred revenue) — overstates leverage
        if metrics.get("debt_to_equity") is None:
            td = get("total_debt")
            eq = get("shareholders_equity")
            if td is not None and eq is not None:
                metrics["debt_to_equity"] = safe_div(td, eq)
            else:
                # Fall back to gross liabilities when debt breakdown unavailable
                metrics["debt_to_equity"] = safe_div(get("total_liabilities"), eq)
```

- [ ] **Step 4: Run all three new tests to verify they pass**

```bash
poetry run pytest tests/markets/sources/test_xueqiu_source.py::TestXueqiuDerivedMetrics::test_debt_to_equity_uses_total_debt_when_available tests/markets/sources/test_xueqiu_source.py::TestXueqiuDerivedMetrics::test_debt_to_equity_falls_back_to_total_liabilities_when_no_total_debt tests/markets/sources/test_xueqiu_source.py::TestXueqiuDerivedMetrics::test_debt_to_equity_none_when_no_debt_data -v
```
Expected: All PASS

- [ ] **Step 5: Run full xueqiu test suite to check no regressions**

```bash
poetry run pytest tests/markets/sources/test_xueqiu_source.py -v
```
Expected: All PASS — in particular, the **existing** `test_debt_to_equity_direct` test (in `TestXueqiuDerivedMetrics`) passes only `total_liabilities` without `total_debt`, which exercises the new fallback path and must continue to pass.

- [ ] **Step 6: Commit**

```bash
git add src/markets/sources/xueqiu_source.py tests/markets/sources/test_xueqiu_source.py
git commit -m "fix: compute debt_to_equity from total_debt (financial) not total_liabilities (gross)"
```

---

## Task 2: Add Multi-Year Path to MarketRouter

**Files:**
- Modify: `src/markets/router.py:136-154` (add `get_historical_financial_metrics` convenience method)

**Note:** `get_historical_financial_metrics` already exists on `MarketAdapter` (base class, `src/markets/base.py:230-249`) and is overridden by `HKStockAdapter` and `CNStockAdapter` with Xueqiu-backed implementations. What is missing is the **convenience proxy** on `MarketRouter` — without it, `api.py` cannot call it through the router. This task adds only that proxy.

- [ ] **Step 1: Write failing test**

Create `tests/test_api_multi_year.py`:

```python
from unittest.mock import MagicMock, patch
from src.markets.router import MarketRouter


def test_market_router_has_get_historical_financial_metrics():
    """MarketRouter should expose get_historical_financial_metrics."""
    router = MarketRouter.__new__(MarketRouter)
    router.adapters = []
    assert hasattr(router, "get_historical_financial_metrics")


def test_market_router_get_historical_routes_to_adapter():
    """get_historical_financial_metrics routes to the correct adapter."""
    mock_adapter = MagicMock()
    mock_adapter.supports_ticker.return_value = True
    mock_adapter.get_historical_financial_metrics.return_value = [
        {"ticker": "03690", "report_period": "2024-12-31"},
        {"ticker": "03690", "report_period": "2023-12-31"},
    ]

    router = MarketRouter.__new__(MarketRouter)
    router.adapters = [mock_adapter]

    results = router.get_historical_financial_metrics("3690.HK", "2025-01-01", limit=5)

    mock_adapter.get_historical_financial_metrics.assert_called_once_with(
        "3690.HK", "2025-01-01", limit=5
    )
    assert len(results) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
poetry run pytest tests/test_api_multi_year.py -v
```
Expected: FAIL (`AttributeError: 'MarketRouter' object has no attribute 'get_historical_financial_metrics'`)

- [ ] **Step 3: Add `get_historical_financial_metrics` to `MarketRouter`**

In `src/markets/router.py`, after the `get_financial_metrics` method (after line 154), add:

```python
    def get_historical_financial_metrics(
        self,
        ticker: str,
        end_date: str,
        limit: int = 10,
    ):
        """
        便捷方法：获取多年历史财务指标

        自动路由到对应适配器并获取多期数据。
        支持 HKStockAdapter 和 CNStockAdapter 的 Xueqiu 历史数据。

        Args:
            ticker: 股票代码
            end_date: 截止日期 "YYYY-MM-DD"
            limit: 最大返回期数

        Returns:
            List[Dict]: 多期财务指标列表，或 None 如果不可用
        """
        adapter = self.route(ticker)
        return adapter.get_historical_financial_metrics(ticker, end_date, limit=limit)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
poetry run pytest tests/test_api_multi_year.py -v
```
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/markets/router.py tests/test_api_multi_year.py
git commit -m "feat: add get_historical_financial_metrics to MarketRouter"
```

---

## Task 3: Fix `get_financial_metrics()` in api.py to Return Multi-Year Data

**Files:**
- Modify: `src/tools/api.py:266-289` (non-US branch of `get_financial_metrics`)
- Modify: `tests/test_api_multi_year.py` (add integration tests)

- [ ] **Step 1: Write failing tests**

Add to `tests/test_api_multi_year.py`:

```python
from unittest.mock import MagicMock
from src.tools.api import get_financial_metrics
from src.data.models import FinancialMetrics


def _make_metrics_dict(report_period: str) -> dict:
    return {
        "ticker": "3690.HK",
        "report_period": report_period,
        "period": "annual",
        "currency": "HKD",
        "revenue": 100000000000.0,
        "net_income": 10000000000.0,
    }


def _mock_cache(mocker):
    """Helper: patch the dual cache to always return None (cache miss)."""
    mock_cache = mocker.patch("src.tools.api._get_dual_cache")
    mock_cache.return_value.get_financial_metrics.return_value = None
    return mock_cache


def test_get_financial_metrics_returns_single_period_for_ttm(mocker):
    """period='ttm' still returns single-period data for non-US stocks."""
    mock_router = MagicMock()
    mock_router.return_value.get_financial_metrics.return_value = _make_metrics_dict("2024-12-31")

    mocker.patch("src.tools.api._get_market_router", mock_router)
    mocker.patch("src.tools.api._is_us_stock", return_value=False)
    _mock_cache(mocker)

    results = get_financial_metrics("3690.HK", "2025-01-01", period="ttm", limit=5)

    assert len(results) == 1
    assert isinstance(results[0], FinancialMetrics)
    mock_router.return_value.get_financial_metrics.assert_called_once()
    mock_router.return_value.get_historical_financial_metrics.assert_not_called()


def test_get_financial_metrics_returns_multi_year_for_annual_with_limit(mocker):
    """period='annual' + limit>1 calls get_historical_financial_metrics for non-US stocks."""
    mock_router = MagicMock()
    mock_router.return_value.get_historical_financial_metrics.return_value = [
        _make_metrics_dict("2024-12-31"),
        _make_metrics_dict("2023-12-31"),
        _make_metrics_dict("2022-12-31"),
    ]

    mocker.patch("src.tools.api._get_market_router", mock_router)
    mocker.patch("src.tools.api._is_us_stock", return_value=False)
    _mock_cache(mocker)

    results = get_financial_metrics("3690.HK", "2025-01-01", period="annual", limit=5)

    assert len(results) == 3
    assert all(isinstance(r, FinancialMetrics) for r in results)
    mock_router.return_value.get_historical_financial_metrics.assert_called_once_with(
        "3690.HK", "2025-01-01", limit=5
    )
    mock_router.return_value.get_financial_metrics.assert_not_called()


def test_get_financial_metrics_annual_limit_1_uses_single_period(mocker):
    """period='annual' + limit=1 still uses single-period path."""
    mock_router = MagicMock()
    mock_router.return_value.get_financial_metrics.return_value = _make_metrics_dict("2024-12-31")

    mocker.patch("src.tools.api._get_market_router", mock_router)
    mocker.patch("src.tools.api._is_us_stock", return_value=False)
    _mock_cache(mocker)

    results = get_financial_metrics("3690.HK", "2025-01-01", period="annual", limit=1)

    assert len(results) == 1
    mock_router.return_value.get_financial_metrics.assert_called_once()
    mock_router.return_value.get_historical_financial_metrics.assert_not_called()


def test_get_financial_metrics_returns_empty_when_historical_returns_none(mocker):
    """Returns [] when historical data source returns None."""
    mock_router = MagicMock()
    mock_router.return_value.get_historical_financial_metrics.return_value = None

    mocker.patch("src.tools.api._get_market_router", mock_router)
    mocker.patch("src.tools.api._is_us_stock", return_value=False)
    _mock_cache(mocker)

    results = get_financial_metrics("3690.HK", "2025-01-01", period="annual", limit=5)

    assert results == []
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
poetry run pytest tests/test_api_multi_year.py::test_get_financial_metrics_returns_multi_year_for_annual_with_limit -v
```
Expected: FAIL (currently only returns 1 period regardless of period/limit)

- [ ] **Step 3: Fix the non-US branch of `get_financial_metrics()` in `src/tools/api.py`**

Find the `else:` branch at line 266 (non-US path). Replace lines 266-289:

```python
    else:
        # 非美股：使用 MarketRouter
        try:
            if period == "annual" and limit > 1:
                # 多期年度数据：使用历史数据接口（与 search_line_items 相同的路径）
                metrics_list = _get_market_router().get_historical_financial_metrics(
                    ticker, end_date, limit=limit
                )
                if not metrics_list:
                    return []

                # 将每个 dict 转换为 Pydantic 模型
                result = []
                for metrics_dict in metrics_list:
                    try:
                        result.append(FinancialMetrics(**metrics_dict))
                    except Exception as e:
                        logger.warning(
                            "Failed to parse historical metrics for %s period %s: %s",
                            ticker, metrics_dict.get("report_period", "?"), e
                        )
                if not result:
                    return []

                # Cache the results in dual-layer cache (L1 + L2)
                _get_dual_cache().set_financial_metrics(ticker, end_date, period, limit, result)
                return result
            else:
                # 单期 TTM 数据（向后兼容）
                metrics_dict = _get_market_router().get_financial_metrics(ticker, end_date)

                if not metrics_dict:
                    return []

                # 将字典转换为 Pydantic 模型
                metric = FinancialMetrics(**metrics_dict)
                metrics = [metric]

                # Cache the results in dual-layer cache (L1 + L2)
                _get_dual_cache().set_financial_metrics(ticker, end_date, period, limit, metrics)

                return metrics
        except ValueError as e:
            # 未找到支持该ticker的适配器
            logger.warning("MarketRouter error for %s: %s", ticker, e)
            return []
        except Exception as e:
            logger.warning("Failed to fetch financial metrics via MarketRouter for %s: %s", ticker, e)
            return []
```

- [ ] **Step 4: Run all api_multi_year tests to verify they pass**

```bash
poetry run pytest tests/test_api_multi_year.py -v
```
Expected: All PASS

- [ ] **Step 5: Run full test suite for regressions**

```bash
poetry run pytest tests/markets/sources/test_xueqiu_source.py tests/test_models.py tests/test_api_multi_year.py -v
```
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/tools/api.py tests/test_api_multi_year.py
git commit -m "feat: get_financial_metrics returns multi-year data for non-US stocks when period='annual' and limit>1"
```

---

## Task 4: Update Agent Calls to Use period="annual"

Warren Buffett and Aswath Damodaran currently call `get_financial_metrics(period="ttm", limit=10)` — the TTM path always returns 1 period. They need to use `period="annual"` to get multi-year data.

**Files:**
- Modify: `src/agents/warren_buffett.py:32`
- Modify: `src/agents/aswath_damodaran.py:47`
- Modify: `src/agents/michael_burry.py` (find the `get_financial_metrics` call)

- [ ] **Step 1: Find and verify the calls**

```bash
cd /Users/luobotao/.openclaw/workspace/ai-hedge-fund
grep -n "get_financial_metrics" src/agents/warren_buffett.py src/agents/aswath_damodaran.py src/agents/michael_burry.py
```

- [ ] **Step 2: Update Warren Buffett agent**

In `src/agents/warren_buffett.py` line 32, change:
```python
metrics = get_financial_metrics(ticker, end_date, period="ttm", limit=10, api_key=api_key)
```
to:
```python
metrics = get_financial_metrics(ticker, end_date, period="annual", limit=10, api_key=api_key)
```

**Why:** Warren Buffett's `analyze_consistency()` at line 207 requires `len(financial_line_items) >= 4` for trend analysis. With `period="annual"`, he gets up to 10 annual periods instead of 1 TTM snapshot.

- [ ] **Step 3: Update Aswath Damodaran agent**

In `src/agents/aswath_damodaran.py` line 47, change:
```python
metrics = get_financial_metrics(ticker, end_date, period="ttm", limit=5, api_key=api_key)
```
to:
```python
metrics = get_financial_metrics(ticker, end_date, period="annual", limit=5, api_key=api_key)
```

- [ ] **Step 4: Update Michael Burry agent**

In `src/agents/michael_burry.py` line 50, change:
```python
metrics = get_financial_metrics(ticker, end_date, period="ttm", limit=5, api_key=api_key)
```
to:
```python
metrics = get_financial_metrics(ticker, end_date, period="annual", limit=5, api_key=api_key)
```

- [ ] **Step 5: Verify no test regressions**

```bash
poetry run pytest tests/markets/sources/test_xueqiu_source.py tests/test_models.py tests/test_api_multi_year.py -v
```
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/agents/warren_buffett.py src/agents/aswath_damodaran.py src/agents/michael_burry.py
git commit -m "fix: use period='annual' in Warren Buffett, Damodaran, Burry agents to get multi-year historical data"
```

---

## Task 5: Smoke Test Verification

- [ ] **Step 1: Run a quick smoke test to verify agents now get multi-year data**

```bash
cd /Users/luobotao/.openclaw/workspace/ai-hedge-fund
poetry run python -c "
from src.tools.api import get_financial_metrics
from datetime import date

ticker = '3690.HK'
end_date = str(date.today())

# Test multi-year path
metrics = get_financial_metrics(ticker, end_date, period='annual', limit=5)
print(f'Multi-year periods returned: {len(metrics)}')
for m in metrics:
    print(f'  {m.report_period}: revenue={m.revenue}, net_income={m.net_income}, debt_to_equity={m.debt_to_equity}')

# Verify D/E is now using total_debt
print()
print(f'Latest D/E (should be ~0.26 using total_debt): {metrics[0].debt_to_equity}')
print(f'Latest total_debt: {metrics[0].total_debt}')
print(f'Latest total_liabilities: {metrics[0].total_liabilities}')
print(f'Latest shareholders_equity: {metrics[0].shareholders_equity}')
"
```

Expected:
- `Multi-year periods returned: 5` (not 1)
- D/E ~0.26 (using total_debt, not total_liabilities)
- Each period has a different `report_period`

- [ ] **Step 2: If multi-year returns only 1 period, debug**

```bash
poetry run python -c "
from src.markets.router import MarketRouter
router = MarketRouter()
results = router.get_historical_financial_metrics('3690.HK', '2025-01-01', limit=5)
print(f'Historical periods from router: {len(results) if results else 0}')
if results:
    for r in results:
        print(f'  {r.get(\"report_period\")}: revenue={r.get(\"revenue\")}')
"
```

- [ ] **Step 3: Final full test run**

```bash
poetry run pytest tests/markets/sources/test_xueqiu_source.py tests/test_models.py tests/test_api_multi_year.py -v
```

- [ ] **Step 4: Final commit if any field corrections were needed**

```bash
git add -A
git commit -m "fix: smoke test corrections for multi-year financial metrics"
```

---

## Summary

| Task | Fix | Impact |
|------|-----|--------|
| 1 | D/E uses `total_debt` not `total_liabilities` | Warren Buffett, Burry, Damodaran see consistent D/E ~0.26 |
| 2 | Add `get_historical_financial_metrics` to `MarketRouter` | Enables api.py to call it |
| 3 | `get_financial_metrics()` multi-year branch for non-US | Agents get 5-10 annual periods instead of 1 TTM |
| 4 | Update agent calls to `period="annual"` | Buffett/Damodaran/Burry can do trend analysis |
| 5 | Smoke test | Verify live data flows correctly |

**Expected outcome:** Warren Buffett's `analyze_consistency()` will have 10 data points (currently 1, needs ≥4). Damodaran can compute 5-year revenue CAGR. Burry can see historical FCF trends. D/E will be consistent at ~0.26 across all agents.
