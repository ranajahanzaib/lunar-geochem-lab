"""Local Lunar Geochemistry Lab app and versioned read-only API."""

import os
from http.server import ThreadingHTTPServer

from lunar_lab.api import handler_class


if __name__ == "__main__":
    host = os.environ.get("LUNAR_LAB_HOST", "127.0.0.1")
    port = int(os.environ.get("LUNAR_LAB_PORT", "8000"))
    print(f"Lunar Geochemistry Lab: http://{host}:{port}")
    ThreadingHTTPServer((host, port), handler_class()).serve_forever()
