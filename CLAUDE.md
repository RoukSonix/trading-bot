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

### 4-Step Development Pipeline

Every feature/fix follows this pipeline:

**Step 1 — Planning (Claude ACP)**
Agent receives the task, creates a detailed implementation plan, finishes.

**Step 2 — Validation (Claude ACP)**
A different agent reviews the plan, simulates implementation to find potential issues, fixes the plan if needed, finishes.

**Step 3 — Implementation (Claude ACP)**
Agent implements according to the plan, updates `docs/STATUS.md`, commits to branch.

**Step 4 — Testing (Codex ACP)**
Agent tests the implementation. For UI changes, uses `playwright-interactive` skill.
For backend changes, runs `pytest tests/ -v`.

### Rules

1. **Bugs found during testing → GitHub Issues** in this repository
2. **Test coverage must be >80%**
3. **Code review** is done by a SEPARATE agent (not the developer)
4. **After merge** — rebuild Docker if code changed
5. **Update `docs/STATUS.md`** after completing any sprint or significant change

### Commit Convention

```
feat: description     — new feature
fix: description      — bug fix
test: description     — tests only
docs: description     — documentation
refactor: description — code restructure
chore: description    — maintenance
```
