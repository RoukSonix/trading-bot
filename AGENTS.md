# AGENTS.md — AI Agent Instructions

> Read this file before making any changes to the codebase.

## Project Overview

**What:** AI-assisted crypto trading bot with grid trading, multi-strategy engine, and risk management.
**Stack:** Python 3.12, CCXT, LangChain + OpenRouter, SQLite, FastAPI, Streamlit, Docker
**Repo:** https://github.com/RoukSonix/trading-bot

## Repository Structure

```
trading-bots/
├── binance-bot/          # Main trading bot
│   └── src/binance_bot/  # Bot source (strategies, core, etc.)
├── shared/               # Shared library (all bots use this)
│   ├── ai/               # LLM integration
│   ├── alerts/            # Discord, email notifications
│   ├── api/               # FastAPI REST API
│   ├── backtest/          # Backtesting engine
│   ├── config/            # Settings (Pydantic)
│   ├── core/              # Database, state, indicators
│   ├── dashboard/         # Streamlit dashboard
│   ├── indicators/        # 50+ technical indicators
│   ├── optimization/      # Optuna hyperparameter optimization
│   ├── risk/              # Position sizing, TP/SL, limits
│   ├── strategies/        # Multi-strategy engine, regime detector
│   └── vector_db/         # News sentiment + ChromaDB
├── jesse-bot/            # Jesse framework bot
├── polymarket-bot/       # Prediction markets (scaffold)
├── tests/                # Test suite
├── scripts/              # Automation scripts
└── docs/                 # Documentation
    ├── STATUS.md         # Current project state
    ├── SPRINT_PLAN.md    # Sprint roadmap (24-31)
    ├── AUDIT_V2.md       # Code audit report (118 issues)
    ├── BUGS.md           # Bug tracking
    └── RESEARCH.md       # Research notes
```

## Running the Project

```bash
# Docker (production)
cd binance-bot
docker compose --profile bot up -d --build

# Containers:
#   centric-void-01-app-service   — trading bot
#   centric-void-01-app-api       — REST API (:8000)
#   centric-void-01-app-dashboard — Streamlit UI (:8501)

# Local development
pip install -r binance-bot/requirements.txt
pip install -e binance-bot/
pytest tests/ -v
```

## Development Workflow (MANDATORY)

### Branch + Worktree

All work MUST use branches. Never commit directly to main.

```bash
./scripts/worktree.sh create <task-name>   # create branch + worktree
cd ../trading-bots-<task-name>             # work here
# ... develop, commit, push ...
./scripts/worktree.sh cleanup <task-name>  # merge + cleanup
```

### 5-Step Sprint Pipeline

Every feature/fix follows this pipeline. Each step = separate ACP agent.

**Step 1 — Planning (Claude ACP)**
Agent receives the task, reads AGENTS.md and project docs.
Creates plan in `docs/<sprint>-plan.md` — files, changes, test cases.
Commits plan to branch, finishes.

**Step 2 — Validation (Claude ACP)**
A DIFFERENT agent validates the plan: simulates implementation, looks for problems.
Checks: will it break anything? Are tests sufficient? Missing edge cases?
If OK — writes "APPROVED". If not — fixes the plan.
Commits, finishes.

**Step 3 — Implementation (Claude ACP)**
Agent implements strictly according to the plan.
Writes code + tests, updates `docs/STATUS.md`.
Runs `pytest tests/ -v`, commits to branch.

**Step 4 — Testing (E2E / Codex ACP)**
Verification via Playwright E2E or manual smoke test.
Bugs → GitHub Issues.

**Step 5 — Merge**
PR → code review → merge to main.
Worktree deleted, MONITOR.md deleted.
Final message posted to channel.

### Infrastructure

- **Worktree:** `git worktree add ../repo-<task> -b <branch> main` — agents work in isolated copy, never in main
- **MONITOR.md** — flag file in repo root: current step, agent session key, start time. Zmywarka reads it every 5 min
- **Zmywarka** — separate monitoring bot, checks MONITOR.md every 5 min via cron. If agent stuck >15 min → sends alert for check and restart
- **GitHub Issues** — for bugs and tracking
- **docs/** — plans, statuses, retrospectives

### Rules

1. **Code is written ONLY by ACP agents**, never directly
2. **Each step = separate ACP agent** (cannot combine steps)
3. **Work only in branches**, never in main
4. **After merge** — always post message to channel
5. **Bugs found during testing → GitHub Issues** in this repository
6. **Test coverage must be >80%**
7. **Update `docs/STATUS.md`** after completing any sprint or significant change

### Commit Convention

```
feat: description     — new feature
fix: description      — bug fix
test: description     — tests only
docs: description     — documentation
refactor: description — code restructure
chore: description    — maintenance
```
