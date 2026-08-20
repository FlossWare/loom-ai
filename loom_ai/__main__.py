"""Allow running loom-ai as a module: python -m loom_ai"""

from __future__ import annotations

import os

from loom_ai.security_bind import require_api_key_for_non_loopback
from loom_ai.server import main as _server_main


def main() -> None:
    host = os.environ.get("LOOM_HOST", "127.0.0.1")
    api_key = os.environ.get("LOOM_API_KEY")
    require_api_key_for_non_loopback(host, api_key)
    _server_main()


main()
