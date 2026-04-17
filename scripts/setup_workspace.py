"""
Set up a fresh working directory (DELETE5-style) that points at an existing
bootstrap's secrets.

This does NOT re-run the bootstrap or create new GCP resources. It just
creates a clean working directory that the scripts can run from.

Usage:
    python scripts/setup_workspace.py D:\\LAB\\DELETE5 --from D:\\LAB\\DELETE4
"""
import argparse
import shutil
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Set up a fresh workspace directory.")
    parser.add_argument("target", type=Path, help="New workspace directory to create")
    parser.add_argument("--from", dest="source", type=Path, required=True,
                        help="Existing workspace to copy secrets from (e.g. D:\\LAB\\DELETE4)")
    args = parser.parse_args()

    target: Path = args.target.resolve()
    source: Path = args.source.resolve()

    src_secrets = source / "Phase3_Bootstrap" / "secrets"
    if not src_secrets.exists():
        print(f"✗ Source secrets folder not found: {src_secrets}")
        return 1

    src_env = src_secrets / ".env"
    src_sa = src_secrets / "service-account.json"
    if not src_env.exists():
        print(f"✗ Source .env not found: {src_env}")
        return 1
    if not src_sa.exists():
        print(f"✗ Source service-account.json not found: {src_sa}")
        return 1

    # Create target structure
    dst_secrets = target / "Phase3_Bootstrap" / "secrets"
    dst_secrets.mkdir(parents=True, exist_ok=True)
    print(f"✓ Created {dst_secrets}")

    # Copy secrets
    shutil.copy2(src_env, dst_secrets / ".env")
    shutil.copy2(src_sa, dst_secrets / "service-account.json")
    print(f"✓ Copied .env")
    print(f"✓ Copied service-account.json")

    print()
    print(f"Workspace ready at: {target}")
    print(f"Next steps:")
    print(f"  cd {target}")
    print(f"  python <repo>\\scripts\\diagnose.py         # verify config")
    print(f"  python <repo>\\scripts\\simple_web.py       # start web UI")
    print(f"  python <repo>\\scripts\\manual_sync.py      # sync Drive on demand")
    return 0


if __name__ == "__main__":
    sys.exit(main())
