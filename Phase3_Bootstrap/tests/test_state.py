"""Unit tests for installer.state — checkpoint/resume state machine."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from installer.state import BootstrapState, Step


def test_empty_state(tmp_path: Path):
    s = BootstrapState(tmp_path / "state.json")
    assert s.completed_steps == []
    assert not s.is_done(Step.PREREQS)
    assert s.last_completed_step is None


def test_mark_and_persist(tmp_path: Path):
    path = tmp_path / "state.json"
    s = BootstrapState(path)
    s.mark_done(Step.PREREQS)
    s.mark_done(Step.INTERVIEW)

    assert path.exists()
    data = json.loads(path.read_text())
    assert data["completed_steps"] == ["prereqs", "interview"]
    assert data["last_completed_step"] == "interview"


def test_load_round_trip(tmp_path: Path):
    path = tmp_path / "state.json"
    s1 = BootstrapState(path)
    s1.mark_done(Step.PREREQS)
    s1.mark_done(Step.GCP_AUTH)

    s2 = BootstrapState(path)
    s2.load()
    assert s2.is_done(Step.PREREQS)
    assert s2.is_done(Step.GCP_AUTH)
    assert not s2.is_done(Step.PROJECT)
    assert s2.last_completed_step == "gcp_auth"


def test_mark_done_idempotent(tmp_path: Path):
    s = BootstrapState(tmp_path / "state.json")
    s.mark_done(Step.PREREQS)
    s.mark_done(Step.PREREQS)
    s.mark_done(Step.PREREQS)
    assert s.completed_steps == ["prereqs"]


def test_reset_wipes_all(tmp_path: Path):
    s = BootstrapState(tmp_path / "state.json")
    s.mark_done(Step.PREREQS)
    s.mark_done(Step.INTERVIEW)
    s.reset(keep_config=False)
    assert s.completed_steps == []


def test_reset_keeps_interview_when_keep_config(tmp_path: Path):
    s = BootstrapState(tmp_path / "state.json")
    s.mark_done(Step.PREREQS)
    s.mark_done(Step.INTERVIEW)
    s.reset(keep_config=True)
    assert s.completed_steps == ["interview"]
    assert not s.is_done(Step.PREREQS)


@pytest.mark.parametrize("step", list(Step))
def test_every_step_roundtrips(tmp_path: Path, step: Step):
    s = BootstrapState(tmp_path / "state.json")
    s.mark_done(step)
    s2 = BootstrapState(tmp_path / "state.json")
    s2.load()
    assert s2.is_done(step)
