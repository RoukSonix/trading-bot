#!/usr/bin/env python3
"""Run the trading bot dashboard.

This script starts both the FastAPI backend and Streamlit frontend.
"""

import subprocess
import sys
import time
import signal
import os
from pathlib import Path


def main():
    """Start dashboard components."""
    # Change to project root
    project_root = Path(__file__).parent.parent
    os.chdir(project_root)
    
    processes = []
    
    def cleanup(signum=None, frame=None):
        """Clean up processes on exit."""
        print("\n🛑 Shutting down dashboard...")
        for proc in processes:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)
    
    print("🚀 Starting Trading Bot Dashboard")
    print("=" * 50)
    
    # Start FastAPI backend
    print("📡 Starting API server on http://localhost:8000 ...")
    api_proc = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn",
            "shared.api.main:app",
            "--host", "0.0.0.0",
            "--port", "8000",
            "--reload",
        ],
        cwd=str(project_root.parent),
        env={**os.environ, "PYTHONPATH": f"{project_root.parent}:{project_root / 'src'}"},
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    processes.append(api_proc)
    
    # Wait for API to start
    time.sleep(2)
    
    # Start Streamlit frontend
    print("🎨 Starting Streamlit dashboard on http://localhost:8501 ...")
    dashboard_path = project_root.parent / "shared" / "dashboard" / "app.py"
    streamlit_proc = subprocess.Popen(
        [
            sys.executable, "-m", "streamlit", "run",
            str(dashboard_path),
            "--server.port", "8501",
            "--server.headless", "true",
            "--browser.gatherUsageStats", "false",
        ],
        cwd=str(project_root.parent),
        env={**os.environ, "PYTHONPATH": f"{project_root.parent}:{project_root / 'src'}"},
    )
    processes.append(streamlit_proc)
    
    print("")
    print("✅ Dashboard is running!")
    print("")
    print("📊 Dashboard URL: http://localhost:8501")
    print("📡 API URL:       http://localhost:8000")
    print("📖 API Docs:      http://localhost:8000/docs")
    print("")
    print("Press Ctrl+C to stop")
    print("=" * 50)
    
    # Wait for processes
    try:
        while True:
            # Check if processes are still running
            if api_proc.poll() is not None:
                print("⚠️ API server stopped unexpectedly")
                break
            if streamlit_proc.poll() is not None:
                print("⚠️ Streamlit stopped unexpectedly")
                break
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        cleanup()


if __name__ == "__main__":
    main()
