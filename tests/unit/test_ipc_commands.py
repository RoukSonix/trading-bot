"""Unit tests for file-based IPC commands (shared/core/state.py)."""

import pytest
from pathlib import Path

from shared.core.state import write_command, read_command


@pytest.fixture
def cmd_file(tmp_path):
    """Provide a temporary command file path."""
    return tmp_path / "bot_command.json"


class TestIPCCommands:
    """Tests for write_command / read_command file-based IPC."""

    def test_write_and_read_command(self, cmd_file):
        """Write 'pause', read returns 'pause', file deleted."""
        write_command("pause", path=cmd_file)
        assert cmd_file.exists()

        result = read_command(path=cmd_file)
        assert result == "pause"
        assert not cmd_file.exists()

    def test_read_command_empty(self, cmd_file):
        """No file → returns None."""
        assert not cmd_file.exists()
        result = read_command(path=cmd_file)
        assert result is None

    def test_command_consumed_after_read(self, cmd_file):
        """Second read returns None (command consumed)."""
        write_command("pause", path=cmd_file)
        first = read_command(path=cmd_file)
        second = read_command(path=cmd_file)

        assert first == "pause"
        assert second is None

    def test_write_command_overwrites(self, cmd_file):
        """Write 'pause' then 'resume' → read returns 'resume'."""
        write_command("pause", path=cmd_file)
        write_command("resume", path=cmd_file)

        result = read_command(path=cmd_file)
        assert result == "resume"
