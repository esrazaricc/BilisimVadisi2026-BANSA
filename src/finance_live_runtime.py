from __future__ import annotations

"""Runtime controls shared by official bank calculator adapters.

The live calculator layer must never make the jury-facing UI wait through the
sum of several long HTTP timeouts.  Each adapter therefore uses the same,
configurable request timeout.  A timeout/fetch failure remains UNVERIFIED and
callers fall back to the existing verified V43 deterministic layer.
"""

import os


def live_http_timeout() -> float:
    raw = str(os.getenv("BANSA_LIVE_CALCULATOR_TIMEOUT_SECONDS", "8") or "8").strip()
    try:
        value = float(raw)
    except Exception:
        value = 8.0
    return min(30.0, max(2.0, value))
