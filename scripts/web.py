"""`python scripts/web.py` — launch the web chat interface.

Opens a local Flask server with the AI search chat UI.
Default: http://localhost:5000
"""
from __future__ import annotations

import _path  # noqa: F401
import webbrowser
from threading import Timer

import click


@click.command()
@click.option("--port", default=5000, show_default=True, help="Port to serve on.")
@click.option("--host", default="127.0.0.1", show_default=True,
              help="Host (use 0.0.0.0 for network access).")
@click.option("--no-browser", is_flag=True, help="Don't auto-open a browser tab.")
@click.option("--debug", is_flag=True, help="Enable Flask debug/reload mode.")
def main(port: int, host: str, no_browser: bool, debug: bool) -> None:
    from web.app import app

    url = f"http://{'localhost' if host == '127.0.0.1' else host}:{port}"
    print(f"\n  Web UI: {url}\n")

    if not no_browser:
        Timer(1.5, lambda: webbrowser.open(url)).start()

    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    main()
