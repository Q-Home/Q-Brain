import json
import logging
from datetime import datetime, timezone


def setup_logging():
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    # HTTP URLs may include Loxone control names. Never log HTTP request details.
    for name in ("httpx", "httpcore", "mcp", "uvicorn.access"):
        logging.getLogger(name).setLevel(logging.WARNING)


def event(name: str, **fields):
    logging.getLogger("qbox").info(json.dumps({"time": datetime.now(timezone.utc).isoformat(), "event": name, **fields}))
