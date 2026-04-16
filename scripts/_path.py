"""Import this FIRST in every CLI script — it makes `from core import ...` work
when the script is launched as `python scripts/xxx.py` from anywhere.
"""
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
