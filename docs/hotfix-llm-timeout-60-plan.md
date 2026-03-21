# Hotfix: Raise LLM timeout from 30s to 60s

**Branch:** `hotfix-llm-timeout-60`
**Date:** 2026-03-21
**Step:** 1 — Planning

---

## Problem

LLM calls (via OpenRouter) are timing out at 30s during periods of provider
latency, causing `asyncio.TimeoutError` in `_call_llm()` and
`_run_ai_with_timeout()`.  The bot treats these as hard failures, which blocks
AI-assisted trading decisions unnecessarily.

## Files to change

### 1. `shared/constants.py` — line 60

```python
# before
LLM_TIMEOUT_SEC = 30

# after
LLM_TIMEOUT_SEC = 60
```

This constant is imported by `shared/ai/agent.py:22` and used in:
- `TradingAgent.__init__()` → `timeout=LLM_TIMEOUT_SEC` (line 97, ChatOpenAI constructor)
- `TradingAgent._call_llm()` → `asyncio.wait_for(..., timeout=LLM_TIMEOUT_SEC)` (line 124)
- Error log message (line 128)

No other changes needed in `shared/ai/agent.py` — it reads from the constant.

### 2. `jesse-bot/strategies/AIGridStrategy/ai_mixin.py` — line 27

```python
# before
AI_TIMEOUT = 30

# after
AI_TIMEOUT = 60
```

This is a separate constant (not imported from `shared/constants.py`). Used by
`AIMixin._run_ai_with_timeout()` (line 270) as the default timeout parameter.

### Files that do NOT need changes

| File | Reason |
|------|--------|
| `shared/ai/agent.py` | Reads `LLM_TIMEOUT_SEC` from constants — auto-updated |
| `tests/unit/test_bug_fixes.py` | Tests check for `wait_for` and `timeout` keywords in source, not the numeric value; SMTP test checks `timeout=30` in `email.py` (unrelated) |
| `docs/BUGS.md` | BUG-002 entry mentions `timeout=30` — cosmetic, not blocking |

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Bot loop blocked up to 60s instead of 30s during LLM stall | Low | Bot loop already handles timeout gracefully; 60s still well below the 5-min Zmywarka alert threshold |
| Higher tail latency on AI-assisted decisions | Low | Acceptable trade-off vs. false timeout failures; no real-time trading depends on sub-30s LLM response |
| jesse-bot `_run_ai_with_timeout` uses `ThreadPoolExecutor` with `future.result(timeout=60)` | Low | Thread pool timeout matches asyncio timeout — no deadlock risk |

## Tests / checks to run

```bash
# Unit tests — verify timeout tests still pass
pytest tests/unit/test_bug_fixes.py::TestBug002LLMTimeout -v

# Full test suite
pytest tests/ -v

# Manual verification
grep -n 'LLM_TIMEOUT_SEC\|AI_TIMEOUT' shared/constants.py jesse-bot/strategies/AIGridStrategy/ai_mixin.py
```

## Deployment note

After merge to main, **restart the bot service** so the new constant is loaded:

```bash
cd binance-bot && docker compose --profile bot up -d --build
```

Jesse-bot (if running) also needs restart to pick up the `AI_TIMEOUT` change.
