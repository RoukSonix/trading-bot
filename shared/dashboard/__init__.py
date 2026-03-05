"""Streamlit dashboard for trading bot."""

__all__ = ["run_dashboard"]


def run_dashboard():
    """Run the Streamlit dashboard."""
    import subprocess
    import sys
    from pathlib import Path

    app_path = Path(__file__).parent / "app.py"
    subprocess.run([sys.executable, "-m", "streamlit", "run", str(app_path)])
