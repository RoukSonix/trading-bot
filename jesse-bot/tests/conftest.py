"""
Conftest for jesse-bot tests.

Adds the jesse-bot directory to PYTHONPATH so strategy imports work.
"""

import sys
import os

# Add jesse-bot root to path for strategy imports
jesse_bot_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if jesse_bot_dir not in sys.path:
    sys.path.insert(0, jesse_bot_dir)
