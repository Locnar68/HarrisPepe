"""`python scripts/web.py` — launch the web chat interface."""
from __future__ import annotations

import _path  # noqa: F401
import webbrowser
from threading import Timer

import click


@click.command()
@click.option("--port", default=5000, show_default=True)
@click.option("--host", default="0.0.0.0", show_default=True,
              help="0.0.0.0 = accessible on LAN. 127.0.0.1 = localhost only.")
@click.option("--no-browser", is_flag=True)
@click.option("--debug", is_flag=True)
def main(port: int, host: str, no_browser: bool, debug: bool) -> None:
    from web.app import app

    url = f"http://localhost:{port}"
    print(f"\n  Local:   http://localhost:{port}")
    print(f"  Network: http://0.0.0.0:{port}  (use your LAN IP, e.g. http://10.0.0.54:{port})")
    print()

    if not no_browser:
        Timer(1.5, lambda: webbrowser.open(url)).start()

    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    main()
