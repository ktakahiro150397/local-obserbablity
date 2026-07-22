from __future__ import annotations

import os
import sys
import time
from pathlib import Path


health_file = Path(os.environ.get("ROLLUP_HEALTH_FILE", "/tmp/rollup-last-success"))
interval = int(os.environ.get("ROLLUP_INTERVAL_SECONDS", "300"))
maximum_age = int(os.environ.get("ROLLUP_HEALTH_MAX_AGE_SECONDS", str(max(1200, interval * 4))))

try:
    age = time.time() - health_file.stat().st_mtime
except FileNotFoundError:
    sys.exit(1)

sys.exit(0 if age <= maximum_age else 1)
