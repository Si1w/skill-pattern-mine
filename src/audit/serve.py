"""Serve the human-audit UI over a local HTTP server.

Starts a static file server rooted at ``src/audit/`` (so ``audit.html`` and the
generated ``tasks.js`` are same-origin) and opens the page in the browser.
Serving over HTTP avoids the ``file://`` restrictions some browsers place on
loading local scripts.

Run ``audit.build_ui`` first to generate ``tasks.js``; this server refuses to
start without it.

Usage:
    uv run python -m audit.serve
    uv run python -m audit.serve --port 8800 --no_open
"""

import argparse
import functools
import http.server
import logging
import socketserver
import webbrowser
from pathlib import Path

logger = logging.getLogger(__name__)
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

AUDIT_DIR = Path(__file__).resolve().parent
DEFAULT_PORT = 8787


def serve(port: int = DEFAULT_PORT, open_browser: bool = True) -> None:
    """Serve ``src/audit/`` and open ``audit.html`` in the browser."""
    if not (AUDIT_DIR / "tasks.js").exists():
        raise FileNotFoundError(
            "tasks.js not found — run `uv run python -m audit.build_ui` first"
        )

    handler = functools.partial(http.server.SimpleHTTPRequestHandler,
                                directory=str(AUDIT_DIR))
    # Allow quick restarts without a TIME_WAIT bind error.
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("127.0.0.1", port), handler) as httpd:
        url = f"http://127.0.0.1:{port}/audit.html"
        logger.info("serving audit UI at %s (Ctrl-C to stop)", url)
        if open_browser:
            webbrowser.open(url)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            logger.info("stopped")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--no_open", action="store_true",
                        help="do not open the browser automatically")
    args = parser.parse_args()
    serve(args.port, open_browser=not args.no_open)


if __name__ == "__main__":
    main()
