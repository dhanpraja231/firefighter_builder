"""Put `agents/` on sys.path so we can import assignments + glasser_briefing."""

from __future__ import annotations

import sys
from pathlib import Path

AGENTS_DIR = Path(__file__).resolve().parents[1]
if str(AGENTS_DIR) not in sys.path:
    sys.path.insert(0, str(AGENTS_DIR))
