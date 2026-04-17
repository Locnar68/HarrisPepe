#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Clean up generated files, caches, and test artifacts before committing.

.DESCRIPTION
    Removes:
    - __pycache__ directories
    - .pytest_cache
    - .mypy_cache
    - .ruff_cache
    - *.pyc, *.pyo files
    - Generated state/logs/config/secrets (gitignored, but cleanup for fresh packaging)

.EXAMPLE
    .\cleanup.ps1
#>

Write-Host "Phase 3 Bootstrap — Cleanup" -ForegroundColor Cyan
Write-Host "Removing Python caches and test artifacts..." -ForegroundColor Gray

# Python caches
Get-ChildItem -Path . -Recurse -Directory -Filter "__pycache__" -Force | Remove-Item -Recurse -Force
Get-ChildItem -Path . -Recurse -Directory -Filter ".pytest_cache" -Force | Remove-Item -Recurse -Force
Get-ChildItem -Path . -Recurse -Directory -Filter ".mypy_cache" -Force | Remove-Item -Recurse -Force
Get-ChildItem -Path . -Recurse -Directory -Filter ".ruff_cache" -Force | Remove-Item -Recurse -Force
Get-ChildItem -Path . -Recurse -File -Filter "*.pyc" | Remove-Item -Force
Get-ChildItem -Path . -Recurse -File -Filter "*.pyo" | Remove-Item -Force

# Generated install artifacts (if present — usually gitignored)
if (Test-Path "config") {
    Write-Host "Removing config/ ..." -ForegroundColor Gray
    Remove-Item -Path "config" -Recurse -Force -ErrorAction SilentlyContinue
}
if (Test-Path "secrets") {
    Write-Host "Removing secrets/ ..." -ForegroundColor Gray
    Remove-Item -Path "secrets" -Recurse -Force -ErrorAction SilentlyContinue
}
if (Test-Path "state") {
    Write-Host "Removing state/ ..." -ForegroundColor Gray
    Remove-Item -Path "state" -Recurse -Force -ErrorAction SilentlyContinue
}
if (Test-Path "logs") {
    Write-Host "Removing logs/ ..." -ForegroundColor Gray
    Remove-Item -Path "logs" -Recurse -Force -ErrorAction SilentlyContinue
}

# Virtual environment (if present)
if (Test-Path ".venv") {
    Write-Host "Removing .venv/ ..." -ForegroundColor Gray
    Remove-Item -Path ".venv" -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Host "✓ Cleanup complete" -ForegroundColor Green
Write-Host ""
Write-Host "The repository is now clean for packaging/commit." -ForegroundColor Gray
Write-Host "Run 'git status' to verify." -ForegroundColor Gray
