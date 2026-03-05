# Production Deployment Guide

This guide covers deploying the Trading Bot in a production environment with monitoring, logging, and backup procedures.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Environment Variables](#environment-variables)
- [Deployment Steps](#deployment-steps)
- [Monitoring Setup](#monitoring-setup)
- [Backup Procedures](#backup-procedures)
- [Troubleshooting](#troubleshooting)

## Prerequisites

- Docker and Docker Compose v2+
- At least 2GB RAM available
- Binance API keys (testnet or production)
- (Optional) Discord webhook for alerts
- (Optional) SMTP credentials for email alerts

## Environment Variables

Create a `.env` file from the example:

```bash
cp .env.example .env
```

### Required Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `BINANCE_API_KEY` | Binance API key | `your-api-key` |
| `BINANCE_SECRET_KEY` | Binance secret key | `your-secret-key` |
| `BINANCE_ENV` | Environment (`testnet` or `production`) | `testnet` |

### Optional Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `LOG_LEVEL` | Logging level | `INFO` |
| `LOG_FORMAT` | Log format (`text` or `json`) | `text` |
| `TRADING_MODE` | Trading mode (`paper` or `live`) | `paper` |
| `DISCORD_WEBHOOK_URL` | Discord webhook for alerts | - |
| `SMTP_HOST` | SMTP server for email alerts | `smtp.gmail.com` |
| `SMTP_PORT` | SMTP port | `587` |
| `SMTP_USER` | SMTP username | - |
| `SMTP_PASS` | SMTP password/app password | - |
| `ALERT_EMAIL` | Email for alerts | - |
| `GRAFANA_PASSWORD` | Grafana admin password | `admin` |

## Deployment Steps

### 1. Start the Main Application

For production deployment with resource limits and health checks:

```bash
# Start API and Dashboard
docker compose -f docker-compose.prod.yml up -d

# Verify services are healthy
docker compose -f docker-compose.prod.yml ps

# View logs
docker compose -f docker-compose.prod.yml logs -f
```

### 2. Start the Trading Bot (Optional)

The bot is in a separate profile to prevent accidental starts:

```bash
# Start bot with API and Dashboard
docker compose -f docker-compose.prod.yml --profile bot up -d

# Check bot status
docker compose -f docker-compose.prod.yml logs bot
```

### 3. Verify Health Endpoints

```bash
# Liveness check
curl http://localhost:8000/health/live

# Readiness check (includes exchange connectivity)
curl http://localhost:8000/health/ready

# Basic health
curl http://localhost:8000/health
```

## Monitoring Setup

### Start the Monitoring Stack

```bash
# Create the trading network first (if not exists)
docker network create trading-bot_trading-network 2>/dev/null || true

# Start Prometheus and Grafana
docker compose -f docker-compose.monitoring.yml up -d
```

### Access Points

| Service | URL | Credentials |
|---------|-----|-------------|
| Grafana | http://localhost:3000 | admin / (GRAFANA_PASSWORD) |
| Prometheus | http://localhost:9090 | - |
| API Metrics | http://localhost:8000/metrics | - |

### Grafana Dashboard

The Trading Bot dashboard is automatically provisioned. Find it at:

1. Open Grafana (http://localhost:3000)
2. Go to Dashboards → Browse
3. Select "Trading Bot Dashboard"

### Available Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `trading_bot_trades_total` | Counter | Total trades by side/symbol |
| `trading_bot_pnl_total` | Gauge | Current total PnL |
| `trading_bot_position_size` | Gauge | Current position size |
| `trading_bot_errors_total` | Counter | Errors by type |
| `trading_bot_api_requests_total` | Counter | API requests |
| `trading_bot_exchange_latency_seconds` | Histogram | Exchange latency |
| `trading_bot_uptime_seconds` | Gauge | Bot uptime |
| `trading_bot_status` | Gauge | Bot status (1=running) |

## Backup Procedures

### Manual Backup

```bash
# Create a backup
python scripts/backup_db.py

# List available backups
python scripts/backup_db.py list

# Restore from backup
python scripts/backup_db.py restore data/backups/trading_backup_YYYYMMDD_HHMMSS.db.gz
```

### Automated Backups (Cron)

Add to crontab (`crontab -e`):

```cron
# Daily backup at 3 AM
0 3 * * * cd /path/to/trading-bot && python scripts/backup_db.py >> logs/backup.log 2>&1

# Weekly backup on Sunday, keep 30 days
0 4 * * 0 cd /path/to/trading-bot && python scripts/backup_db.py --keep 30 >> logs/backup.log 2>&1
```

### Backup Options

```bash
# Keep last 30 backups
python scripts/backup_db.py --keep 30

# Custom database path
python scripts/backup_db.py --db /path/to/database.db

# Custom output directory
python scripts/backup_db.py --output /backups
```

## Troubleshooting

### Service Won't Start

```bash
# Check logs
docker compose -f docker-compose.prod.yml logs api

# Check health
docker compose -f docker-compose.prod.yml ps

# Restart service
docker compose -f docker-compose.prod.yml restart api
```

### Exchange Connection Issues

```bash
# Check exchange connectivity
curl http://localhost:8000/health/ready

# Check logs for exchange errors
docker compose -f docker-compose.prod.yml logs api | grep -i exchange
```

### Monitoring Not Working

```bash
# Check if metrics endpoint is accessible
curl http://localhost:8000/metrics

# Check Prometheus targets
# Open http://localhost:9090/targets

# Verify network connectivity
docker network inspect trading-bot_trading-network
```

### Database Issues

```bash
# Check database file
ls -la data/

# Restore from backup
python scripts/backup_db.py list
python scripts/backup_db.py restore data/backups/latest.db.gz --force
```

### Log Rotation

Logs are automatically rotated with the following settings:
- Max file size: 10MB
- Keep last 5 files
- JSON format in production

To view rotated logs:

```bash
ls -la logs/
```

## Resource Limits

Production containers have the following limits:

| Service | CPU Limit | Memory Limit |
|---------|-----------|--------------|
| API | 1.0 | 512MB |
| Dashboard | 1.0 | 512MB |
| Bot | 2.0 | 1GB |
| Prometheus | 0.5 | 512MB |
| Grafana | 0.5 | 256MB |

Adjust in `docker-compose.prod.yml` if needed.

## Security Notes

1. **Never commit `.env` file** - Contains API keys
2. **Use testnet first** - Always test on testnet before production
3. **Limit API exposure** - Don't expose port 8000 publicly without authentication
4. **Secure Grafana** - Change default password immediately
5. **Regular backups** - Set up automated backups for database
