# Hotfix: AI Timeout Resilience

**Branch:** `hotfix-ai-timeout-resilience`
**Date:** 2026-03-22
**Step:** 1 — Planning

---

## Problem

The bot is alive and trading, but periodic AI reviews frequently fail with
`LLM call timed out after 60s`. The previous hotfix raised the timeout from
30s to 60s, but OpenRouter latency spikes still exceed that. We need:

1. A modest timeout bump (60s -> 90s) for the LLM calls that genuinely
   benefit from more time.
2. Graceful degradation when AI reviews time out — skip cleanly without
   poisoning the main loop, error count, or trading state.
3. Preserved safety for startup and entry-check paths.
4. Test coverage for the new timeout-handling behavior.
5. (Optional) Fix empty `Reason:` log lines on successful reviews.

---

## Change 1: Raise LLM timeout from 60s to 90s

### File: `shared/constants.py` — line 60

```python
# before
LLM_TIMEOUT_SEC = 60

# after
LLM_TIMEOUT_SEC = 90
```

**Propagation:** Imported by `shared/ai/agent.py:22` and used in:
- `TradingAgent.__init__()` line 97 — `timeout=LLM_TIMEOUT_SEC` (ChatOpenAI constructor)
- `TradingAgent._call_llm()` line 124 — `asyncio.wait_for(..., timeout=LLM_TIMEOUT_SEC)`
- Error log message line 128

No other changes needed in `shared/ai/agent.py` — it reads from the constant.

### File: `jesse-bot/strategies/AIGridStrategy/ai_mixin.py` — line 27

```python
# before
AI_TIMEOUT = 60

# after
AI_TIMEOUT = 90
```

This is a separate constant (not imported from `shared/constants.py`). Used by
`AIMixin._run_ai_with_timeout()` line 270 as the default timeout parameter.

### File: `docs/BUGS.md`

Update BUG-002 fix description: `timeout=60` -> `timeout=90`.

---

## Change 2: Graceful handling for AI review timeout in main bot loop

### Problem detail

`TradingBot._maybe_ai_review()` (`bot.py:704-762`) has no try/except of its
own. When `periodic_review()` or `_fetch_market_data()` raises (including
`asyncio.TimeoutError` from the LLM call), the exception propagates to the
main loop catch-all (`bot.py:528`), which:
- Increments `self.errors`
- Sends an error alert
- Sleeps `tick_interval * 2` (10s)
- Does NOT update `self.last_review`, causing immediate retry next tick

This means a persistent AI timeout creates a tight retry loop, inflates the
error count, spams error alerts, and delays other main-loop work by 10s per
failure.

### File: `binance-bot/src/binance_bot/bot.py` — method `_maybe_ai_review` (lines 704-762)

Wrap the body after the interval guard in a try/except that:
1. Catches `Exception` (covers `asyncio.TimeoutError`, `TimeoutError`, network errors)
2. Logs a warning (not error) — this is expected/transient
3. Always updates `self.last_review` so the next retry respects the interval
4. Returns without raising — the main loop continues normally

```python
# BEFORE (bot.py lines 704-762)
async def _maybe_ai_review(self, current_price: float):
    """Run AI review if interval has passed."""
    if not self.config.ai_periodic_review:
        return

    if self.last_review is not None:
        interval = timedelta(minutes=self.config.review_interval_minutes)
        if datetime.now(timezone.utc) - self.last_review < interval:
            return

    data = await self._fetch_market_data()

    review = await self.strategy.periodic_review(
        current_price=current_price,
        indicators=data["indicators"],
        position_value=self.strategy.paper_holdings * current_price,
        unrealized_pnl=0,
    )

    self.last_review = datetime.now(timezone.utc)

    # Handle AI decision
    if review["action"] == "STOP":
        ...

# AFTER
async def _maybe_ai_review(self, current_price: float):
    """Run AI review if interval has passed."""
    if not self.config.ai_periodic_review:
        return

    if self.last_review is not None:
        interval = timedelta(minutes=self.config.review_interval_minutes)
        if datetime.now(timezone.utc) - self.last_review < interval:
            return

    try:
        data = await self._fetch_market_data()

        review = await self.strategy.periodic_review(
            current_price=current_price,
            indicators=data["indicators"],
            position_value=self.strategy.paper_holdings * current_price,
            unrealized_pnl=0,
        )
    except Exception as e:
        logger.warning(f"AI review skipped (will retry next interval): {e}")
        self.last_review = datetime.now(timezone.utc)
        return

    self.last_review = datetime.now(timezone.utc)

    # Handle AI decision (unchanged from here)
    if review["action"] == "STOP":
        ...
```

**Key behavior changes:**
- AI timeout no longer increments `self.errors`
- AI timeout no longer sends error alert (warning log only)
- AI timeout no longer sleeps 2x tick interval
- Retry is deferred to next review interval instead of next tick

### Not changed (already resilient):

| Component | Why it's fine |
|-----------|--------------|
| `ai_grid.py:periodic_review()` lines 298-307 | Already has try/except, returns `{"action": "CONTINUE"}` on error |
| `jesse-bot/__init__.py:_run_ai_analysis()` lines 414-466 | Already has try/except, logs warning and continues |
| `jesse-bot/__init__.py:_run_ai_position_review()` lines 468-509 | Already has try/except, logs warning and continues |
| `jesse-bot/ai_mixin.py` methods lines 57-137 | All three public methods catch `Exception` from `_run_ai_with_timeout` and fall back |

---

## Change 3: Preserve startup and entry-check behavior safety

### Analysis

- **`bot.py:start()`** line 297-300: Initial `_check_entry_conditions()` is
  already wrapped in try/except with a warning log. Safe.
- **`bot.py:_maybe_check_entry()`** line 542-549: Calls
  `_check_entry_conditions()` which calls `strategy.analyze_and_setup()`.
  If the AI times out inside `analyze_and_setup()`, the exception propagates
  to the main loop catch-all. This is acceptable because:
  - Entry checks are critical path — we want to know if they fail
  - The bot stays in `WAITING` state and retries after `entry_check_interval` (5 min)
  - The main loop catch-all properly handles this

**No changes needed.** Entry-check exceptions should remain visible errors
because they indicate the bot cannot determine market conditions. The AI review
path (Change 2) is different: it's advisory, and the bot can safely continue
trading without it.

### Verification

Confirm in code review that `start()` line 297-300 still has:
```python
try:
    await self._check_entry_conditions()
except Exception as e:
    logger.warning(f"Initial entry check failed (will retry in main loop): {e}")
```

---

## Change 4: Add/update tests for timeout handling

### File: `tests/unit/test_bug_fixes.py` — add new test class after `TestBug002LLMTimeout`

Add `TestAIReviewTimeoutResilience` testing that `_maybe_ai_review` handles
timeout without raising:

```python
class TestAIReviewTimeoutResilience:
    """Verify AI review timeout doesn't poison the main loop."""

    @pytest.mark.asyncio
    async def test_ai_review_timeout_does_not_raise(self):
        """_maybe_ai_review should catch timeout and update last_review."""
        # Create a TradingBot with mocked strategy
        # Mock _fetch_market_data to raise asyncio.TimeoutError
        # Call _maybe_ai_review
        # Assert: no exception raised
        # Assert: bot.last_review is updated (not None)
        # Assert: bot.errors unchanged (still 0)

    @pytest.mark.asyncio
    async def test_ai_review_timeout_respects_interval(self):
        """After timeout, next review should wait for the full interval."""
        # Trigger timeout in _maybe_ai_review
        # Call _maybe_ai_review again immediately
        # Assert: second call returns without attempting review (interval guard)
```

### File: `tests/unit/test_bug_fixes.py` — update `TestBug002LLMTimeout`

Update `test_agent_has_timeout` to verify the timeout value is 90:

```python
def test_timeout_value(self):
    """Verify LLM_TIMEOUT_SEC is 90."""
    from shared.constants import LLM_TIMEOUT_SEC
    assert LLM_TIMEOUT_SEC == 90
```

### File: `jesse-bot/tests/test_integration.py` — existing tests

No changes needed. `test_mixin_handles_ai_timeout_gracefully` (line 345)
and `test_mixin_handles_ai_error_gracefully` (line 361) already verify the
jesse-bot fallback behavior.

### Tests/checks to run

```bash
# Unit tests
pytest tests/unit/test_bug_fixes.py -v

# Jesse-bot integration tests
cd jesse-bot && python -m pytest tests/test_integration.py::TestAIIntegration -v

# Full test suite
pytest tests/ -v

# Manual verification of constants
grep -n 'LLM_TIMEOUT_SEC\|AI_TIMEOUT' shared/constants.py jesse-bot/strategies/AIGridStrategy/ai_mixin.py
```

---

## Change 5 (Optional): Avoid empty `Reason:` logs on successful review

### Problem

In `ai_grid.py:300-301`, the periodic review logs:
```python
logger.info(f"   Reason: {result['reason']}")
```

When the LLM returns a JSON with `"reason": ""` or `"reason": " "`, or the
line-parsing fallback hits `REASON:` with nothing after the colon
(`ai_grid.py:461`), the log output is `Reason:` with nothing useful.

### File: `binance-bot/src/binance_bot/strategies/ai_grid.py` — lines 300-301

```python
# before
logger.info(f"📋 AI Review: {result['action']} (Risk: {result['risk']})")
logger.info(f"   Reason: {result['reason']}")

# after
logger.info(f"📋 AI Review: {result['action']} (Risk: {result['risk']})")
if result.get('reason', '').strip():
    logger.info(f"   Reason: {result['reason']}")
```

**Risk:** Negligible. Only suppresses a log line when reason is empty/whitespace.

---

## Files changed (summary)

| File | Change | Lines |
|------|--------|-------|
| `shared/constants.py` | `LLM_TIMEOUT_SEC = 60` -> `90` | 60 |
| `jesse-bot/strategies/AIGridStrategy/ai_mixin.py` | `AI_TIMEOUT = 60` -> `90` | 27 |
| `binance-bot/src/binance_bot/bot.py` | Wrap `_maybe_ai_review` body in try/except | 704-762 |
| `binance-bot/src/binance_bot/strategies/ai_grid.py` | Skip blank `Reason:` log | 300-301 |
| `docs/BUGS.md` | Update BUG-002 timeout value | ~18 |
| `tests/unit/test_bug_fixes.py` | Add timeout resilience tests, timeout value test | new |

## Files NOT changed

| File | Reason |
|------|--------|
| `shared/ai/agent.py` | Reads `LLM_TIMEOUT_SEC` from constants — auto-updated |
| `jesse-bot/strategies/AIGridStrategy/__init__.py` | Already has try/except in `_run_ai_analysis` and `_run_ai_position_review` |
| `jesse-bot/tests/test_integration.py` | Existing tests already cover mixin timeout fallback |
| `binance-bot/scripts/run_ai_grid.py` | Demo script, not production path |

---

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Bot loop blocked up to 90s during LLM stall | Low | Only entry-check path waits full 90s; periodic review path now returns immediately on timeout |
| AI review silently skipped on timeout | Low | Warning log emitted; review retries on next interval; trading continues safely without AI advice |
| Higher tail latency on AI-assisted startup | Low | Acceptable — startup is one-time; 90s still well below operator alerting thresholds |
| jesse-bot `_run_ai_with_timeout` ThreadPoolExecutor timeout mismatch | None | Both `AI_TIMEOUT` and `future.result(timeout=)` use the same constant |

---

## Deployment note

After merge to main, **restart the bot service** so the new constants and
error handling are loaded:

```bash
cd binance-bot && docker compose --profile bot up -d --build
```

Jesse-bot (if running) also needs restart to pick up the `AI_TIMEOUT` change.
