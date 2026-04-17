#!/usr/bin/env bash
# Phase 3 Bootstrap — Cleanup
# Removes Python caches, test artifacts, and generated install files before committing.

set -euo pipefail

echo "Phase 3 Bootstrap — Cleanup"
echo "Removing Python caches and test artifacts..."

# Python caches
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
find . -type f -name "*.pyc" -delete 2>/dev/null || true
find . -type f -name "*.pyo" -delete 2>/dev/null || true

# Generated install artifacts (usually gitignored)
for dir in config secrets state logs .venv; do
    if [ -d "$dir" ]; then
        echo "Removing $dir/ ..."
        rm -rf "$dir"
    fi
done

echo "✓ Cleanup complete"
echo ""
echo "The repository is now clean for packaging/commit."
echo "Run 'git status' to verify."
