"""Serve the message-only audit UI over a local HTTP server.

Starts a static file server rooted at ``src/msg/`` (so ``msg.html`` and the
generated ``tasks.js`` are same-origin) and opens the page in the browser.
Serving over HTTP avoids the ``file://`` restrictions some browsers place on
loading local scripts.

Run ``msg.build_msg`` first to generate ``tasks.js``; this server refuses to
start without it.

Usage:
    uv run python -m msg.serve
    uv run python -m msg.serve --port 8800 --no_open
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

MSG_DIR = Path(__file__).resolve().parent
DEFAULT_PORT = 8788


def serve(port: int = DEFAULT_PORT, open_browser: bool = True) -> None:
    """Serve ``src/msg/`` and open ``msg.html`` in the browser."""
    if not (MSG_DIR / "tasks.js").exists():
        raise FileNotFoundError(
            "tasks.js not found — run `uv run python -m msg.build_msg` first"
        )

    handler = functools.partial(http.server.SimpleHTTPRequestHandler,
                                directory=str(MSG_DIR))
    # Allow quick restarts without a TIME_WAIT bind error.
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("127.0.0.1", port), handler) as httpd:
        url = f"http://127.0.0.1:{port}/msg.html"
        logger.info("serving msg audit UI at %s (Ctrl-C to stop)", url)
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
