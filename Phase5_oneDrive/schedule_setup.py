#!/usr/bin/env python3
"""
Phase5_OneDrive/schedule_setup.py
-----------------------------------
Registers (or removes) a Windows Task Scheduler job that runs
onedrive_sync.py on a repeating interval.

Usage:
  python schedule_setup.py --install --interval 30    # every 30 minutes
  python schedule_setup.py --install --interval 60    # every hour
  python schedule_setup.py --remove                   # unregister task
  python schedule_setup.py --status                   # check if registered

Requirements:
  - Must be run as Administrator (or with appropriate Task Scheduler rights)
  - Python must be in PATH, or set PYTHON_EXE env var to the full path

# SCALE-TODO: When switching auth to client_credentials, the scheduled
# task no longer needs an interactive user session. At that point you can
# change the task's "Run whether user is logged on or not" setting and
# store credentials in the Windows Credential Manager instead of a
# token cache file. See SCALE-TODO in onedrive_sync.py for full details.
"""

import os
import sys
import subprocess
import argparse
from pathlib import Path

TASK_NAME   = "HarrisPepe_OneDriveSync"
SCRIPT_PATH = Path(__file__).parent.resolve() / "onedrive_sync.py"

def _python_exe() -> str:
    return os.environ.get("PYTHON_EXE") or sys.executable

def _schtasks(*args) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["schtasks"] + list(args),
        capture_output=True,
        text=True,
    )

def install(interval_minutes: int):
    python = _python_exe()
    cmd = f'"{python}" "{SCRIPT_PATH}" --schedule {interval_minutes}'

    print(f"Registering task: {TASK_NAME}")
    print(f"  Command:  {cmd}")
    print(f"  Interval: every {interval_minutes} minute(s)")

    # Create a task that runs at startup then repeats every N minutes
    result = _schtasks(
        "/Create", "/F",
        "/TN", TASK_NAME,
        "/TR", cmd,
        "/SC", "ONSTART",
        "/RI", str(interval_minutes),
        "/DU", "9999:59",          # run indefinitely
        "/IT",                      # run only when user is logged on
        "/RL", "HIGHEST",
    )

    if result.returncode == 0:
        print(f"\n  ✓ Task registered successfully.")
        print(f"    Start it now with:  schtasks /Run /TN {TASK_NAME}")
        print(f"    Or just run manually: python onedrive_sync.py --schedule {interval_minutes}")
        print()
        print("  NOTE: Token cache is at secrets/token_cache.json")
        print("  Run bootstrap_onedrive.py once interactively to populate the cache")
        print("  before the scheduled task starts, or the task will fail on first run.")
        print()
        print("  SCALE-TODO: Token expires after ~90 days. See onedrive_sync.py header.")
    else:
        print(f"\n  ✗ Task registration failed:")
        print(f"    {result.stderr.strip()}")
        print("  Try running this script as Administrator.")

def remove():
    result = _schtasks("/Delete", "/TN", TASK_NAME, "/F")
    if result.returncode == 0:
        print(f"  ✓ Task '{TASK_NAME}' removed.")
    else:
        print(f"  ✗ Remove failed (task may not exist): {result.stderr.strip()}")

def status():
    result = _schtasks("/Query", "/TN", TASK_NAME, "/FO", "LIST")
    if result.returncode == 0:
        print(result.stdout)
    else:
        print(f"  Task '{TASK_NAME}' not found or not accessible.")

def main():
    parser = argparse.ArgumentParser(description="Manage OneDrive sync scheduled task")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--install", action="store_true", help="Register the scheduled task")
    group.add_argument("--remove",  action="store_true", help="Remove the scheduled task")
    group.add_argument("--status",  action="store_true", help="Check task status")
    parser.add_argument("--interval", type=int, default=30,
                        help="Sync interval in minutes (default: 30)")
    args = parser.parse_args()

    if args.install:
        install(args.interval)
    elif args.remove:
        remove()
    elif args.status:
        status()

if __name__ == "__main__":
    main()
