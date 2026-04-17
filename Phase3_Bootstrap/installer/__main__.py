"""Entry point: ``python -m installer``"""

import sys

from installer.main import cli

if __name__ == "__main__":
    sys.exit(cli())
