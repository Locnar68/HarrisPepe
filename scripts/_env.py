"""Shared .env + service-account.json discovery for all CLI scripts.

Looks in this order, first hit wins:
  1. $VERTEX_ENV_FILE              — explicit override (absolute path to .env)
  2. <cwd>/Phase3_Bootstrap/secrets/.env
                                   — running from a workspace dir (e.g. D:\\LAB\\DELETE4)
  3. <cwd>/.env                    — user put .env next to them
  4. <repo>/Phase3_Bootstrap/secrets/.env
                                   — developer running from the repo itself

The service-account.json is expected to live next to the .env.

Usage:
    from _env import load_or_die
    env_path, sa_key = load_or_die()
    # os.getenv("GCP_PROJECT_ID") etc. now work
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _candidates() -> list[Path]:
    cands: list[Path] = []
    override = os.environ.get("VERTEX_ENV_FILE")
    if override:
        cands.append(Path(override))
    cwd = Path.cwd()
    cands.append(cwd / "Phase3_Bootstrap" / "secrets" / ".env")
    cands.append(cwd / ".env")
    cands.append(_REPO_ROOT / "Phase3_Bootstrap" / "secrets" / ".env")
    return cands


def discover_env() -> tuple[Optional[Path], Optional[Path]]:
    """Return (env_path, sa_key_path) for the first existing .env.

    sa_key_path is None if the .env exists but service-account.json doesn't.
    Returns (None, None) if no .env was found anywhere.
    """
    for c in _candidates():
        try:
            if c.exists():
                sa_key = c.parent / "service-account.json"
                return c, (sa_key if sa_key.exists() else None)
        except Exception:
            continue
    return None, None


def load_or_die(*, require_sa_key: bool = True, quiet: bool = False) -> tuple[Path, Optional[Path]]:
    """Discover + load .env, exit with a helpful message if not found.

    Prints '✓ loaded from <path>' unless quiet=True so the user always
    knows which workspace they're operating against.
    """
    env_path, sa_key = discover_env()

    if env_path is None:
        print("✗ No .env file found. Searched (in order):")
        for c in _candidates():
            print(f"    - {c}")
        print()
        print("Fix one of:")
        print("  1. cd into your workspace (where Phase3_Bootstrap/secrets/.env lives)")
        print("  2. Set VERTEX_ENV_FILE to the absolute path of your .env, e.g.")
        print("       $env:VERTEX_ENV_FILE = 'D:\\LAB\\DELETE4\\Phase3_Bootstrap\\secrets\\.env'")
        sys.exit(1)

    if require_sa_key and sa_key is None:
        print(f"✗ Found .env at {env_path}")
        print(f"  but service-account.json is missing at "
              f"{env_path.parent / 'service-account.json'}")
        print("  Copy the SA key there or re-run the bootstrap service-account step.")
        sys.exit(1)

    load_dotenv(env_path)
    if not quiet:
        print(f"✓ env loaded from: {env_path}")
        if sa_key:
            print(f"✓ SA key:          {sa_key}")
        print()
    return env_path, sa_key
