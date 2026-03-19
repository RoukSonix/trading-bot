"""Unit tests for API bot control endpoints (shared/api/routes/bot.py)."""

import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from shared.api.routes.bot import router
from shared.api.auth import require_api_key
from shared.core.state import BotState as SharedBotState


@pytest.fixture
def client(tmp_path):
    """FastAPI TestClient with bot router mounted."""
    app = FastAPI()
    app.include_router(router, prefix="/api/bot")

    # Override auth dependency so tests don't need TRADING_API_KEY
    app.dependency_overrides[require_api_key] = lambda: "test-key"

    # Patch write_command and read_state to use tmp_path
    cmd_file = tmp_path / "bot_command.json"

    def fake_write_command(command, path=None):
        from shared.core.state import write_command as wc
        wc(command, path=cmd_file)

    fake_state = SharedBotState(status="running", state="trading", symbol="BTC/USDT")

    with patch("shared.api.routes.bot.write_command", side_effect=fake_write_command), \
         patch("shared.api.routes.bot.read_state", return_value=fake_state):
        yield TestClient(app), cmd_file


class TestAPIBotControl:
    """Tests for /api/bot/{pause,resume,stop} endpoints."""

    def test_pause_endpoint_writes_command(self, client):
        """POST /api/bot/pause → success=True + command file exists."""
        test_client, cmd_file = client
        response = test_client.post("/api/bot/pause")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["message"] == "Pause command sent"
        assert cmd_file.exists()

    def test_resume_endpoint_writes_command(self, client):
        """POST /api/bot/resume → success=True."""
        test_client, cmd_file = client
        response = test_client.post("/api/bot/resume")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["message"] == "Resume command sent"

    def test_stop_endpoint_writes_command(self, client):
        """POST /api/bot/stop → success=True."""
        test_client, cmd_file = client
        response = test_client.post("/api/bot/stop")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["message"] == "Stop command sent"
