#!/usr/bin/env bash
#
# start_live.sh — Pre-flight checks and live trading launcher for jesse-bot.
#
# Usage:
#   ./scripts/start_live.sh           # Run pre-flight checks then start
#   ./scripts/start_live.sh --check   # Run pre-flight checks only
#
# TESTNET ONLY. This script refuses to start if BINANCE_TESTNET is not true.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

pass() { echo -e "  ${GREEN}✓${NC} $1"; }
fail() { echo -e "  ${RED}✗${NC} $1"; ERRORS=$((ERRORS + 1)); }
warn() { echo -e "  ${YELLOW}!${NC} $1"; }

ERRORS=0
CHECK_ONLY=false

if [[ "${1:-}" == "--check" ]]; then
    CHECK_ONLY=true
fi

echo "========================================="
echo "  Jesse Bot — Live Trading Pre-Flight"
echo "========================================="
echo ""

# ── 1. Environment file ──────────────────────────────────────────────
echo "1. Environment Configuration"

if [[ -f "$PROJECT_DIR/.env" ]]; then
    # shellcheck source=/dev/null
    source "$PROJECT_DIR/.env"
    pass ".env file found"
else
    fail ".env file not found at $PROJECT_DIR/.env"
fi

# ── 2. API Keys ──────────────────────────────────────────────────────
echo "2. API Keys"

if [[ -n "${BINANCE_API_KEY:-}" && "${BINANCE_API_KEY}" != "your_api_key_here" ]]; then
    pass "BINANCE_API_KEY is set"
else
    fail "BINANCE_API_KEY is missing or placeholder"
fi

if [[ -n "${BINANCE_API_SECRET:-}" && "${BINANCE_API_SECRET}" != "your_api_secret_here" ]]; then
    pass "BINANCE_API_SECRET is set"
else
    fail "BINANCE_API_SECRET is missing or placeholder"
fi

# ── 3. Testnet safety ────────────────────────────────────────────────
echo "3. Testnet Safety"

TESTNET="${BINANCE_TESTNET:-true}"
if [[ "$TESTNET" == "true" || "$TESTNET" == "1" ]]; then
    pass "BINANCE_TESTNET=$TESTNET (testnet mode)"
else
    fail "BINANCE_TESTNET=$TESTNET — REFUSING to start on mainnet"
fi

MODE="${TRADING_MODE:-paper}"
if [[ "$MODE" == "paper" ]]; then
    pass "TRADING_MODE=$MODE"
elif [[ "$MODE" == "live" ]]; then
    warn "TRADING_MODE=live (ensure you are on testnet!)"
else
    fail "TRADING_MODE=$MODE is invalid (must be 'paper' or 'live')"
fi

# ── 4. Emergency stop ───────────────────────────────────────────────
echo "4. Emergency Stop"

STOP_FILE="${EMERGENCY_STOP_FILE:-EMERGENCY_STOP}"
if [[ -f "$PROJECT_DIR/$STOP_FILE" ]]; then
    fail "Emergency stop file exists: $PROJECT_DIR/$STOP_FILE — remove to proceed"
else
    pass "No emergency stop file"
fi

# ── 5. Docker services ──────────────────────────────────────────────
echo "5. Docker Services"

if command -v docker &>/dev/null; then
    pass "Docker is installed"
else
    fail "Docker is not installed"
fi

if docker info &>/dev/null 2>&1; then
    pass "Docker daemon is running"
else
    fail "Docker daemon is not running (try: sudo systemctl start docker)"
fi

# Check postgres and redis
if docker ps --format '{{.Names}}' 2>/dev/null | grep -q 'jesse-postgres'; then
    pass "PostgreSQL container is running"
else
    warn "PostgreSQL container is not running (will be started by docker compose)"
fi

if docker ps --format '{{.Names}}' 2>/dev/null | grep -q 'jesse-redis'; then
    pass "Redis container is running"
else
    warn "Redis container is not running (will be started by docker compose)"
fi

# ── 6. Network connectivity ─────────────────────────────────────────
echo "6. Network Connectivity"

if curl -s --connect-timeout 5 "https://testnet.binancefuture.com/fapi/v1/ping" &>/dev/null; then
    pass "Binance Futures Testnet is reachable"
else
    warn "Cannot reach Binance Futures Testnet (may work from Docker network)"
fi

if curl -s --connect-timeout 5 "https://testnet.binance.vision/api/v3/ping" &>/dev/null; then
    pass "Binance Spot Testnet is reachable"
else
    warn "Cannot reach Binance Spot Testnet"
fi

# ── 7. Risk limits ──────────────────────────────────────────────────
echo "7. Risk Limits"

MAX_POS="${RISK_MAX_POSITION_PCT:-10}"
DAILY_LOSS="${RISK_DAILY_LOSS_LIMIT_PCT:-5}"
MAX_DD="${RISK_MAX_DRAWDOWN_PCT:-10}"

pass "Max position size: ${MAX_POS}%"
pass "Daily loss limit: ${DAILY_LOSS}%"
pass "Max drawdown: ${MAX_DD}%"

if (( $(echo "$MAX_POS > 50" | bc -l 2>/dev/null || echo 0) )); then
    warn "Max position size >50% is very aggressive"
fi

# ── Summary ──────────────────────────────────────────────────────────
echo ""
echo "========================================="

if [[ $ERRORS -gt 0 ]]; then
    echo -e "${RED}  FAILED: $ERRORS error(s) found${NC}"
    echo "  Fix the issues above before starting live trading."
    echo "========================================="
    exit 1
else
    echo -e "${GREEN}  ALL CHECKS PASSED${NC}"
    echo "========================================="
fi

if [[ "$CHECK_ONLY" == "true" ]]; then
    echo "Pre-flight checks complete (--check mode)."
    exit 0
fi

# ── Start live trading ───────────────────────────────────────────────
echo ""
echo "Starting jesse-live service..."
cd "$PROJECT_DIR/docker"
docker compose up -d jesse-live
echo ""
echo "Jesse live trading started. Monitor with:"
echo "  docker logs -f jesse-live"
