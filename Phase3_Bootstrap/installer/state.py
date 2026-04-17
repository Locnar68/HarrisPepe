"""
Bootstrap state machine.

Each step in the installer is idempotent. The state file records which ones
have completed so a failed run can be resumed with ``--resume`` and skip the
already-done work.

State file shape (JSON)::

    {
      "version": "3.0.0-rc1",
      "started_at": "2026-04-17T12:00:00Z",
      "completed_steps": ["prereqs", "interview", "gcp_auth"],
      "last_completed_step": "gcp_auth",
      "last_updated": "2026-04-17T12:07:12Z"
    }

Config is saved separately under ``config/config.yaml`` — not embedded here.
"""

from __future__ import annotations

import enum
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


class Step(str, enum.Enum):
    PREREQS          = "prereqs"
    INTERVIEW        = "interview"
    GCP_AUTH         = "gcp_auth"
    PROJECT          = "project"
    BILLING          = "billing"
    APIS             = "apis"
    SERVICE_ACCOUNT  = "service_account"
    GCS              = "gcs"
    SECRETS          = "secrets"
    DATA_STORE       = "data_store"
    ENGINE           = "engine"
    CONNECTORS       = "connectors"
    REPORT           = "report"


@dataclass
class BootstrapState:
    path: Path
    completed_steps: list[str] = field(default_factory=list)
    started_at: Optional[str] = None
    last_updated: Optional[str] = None
    config: Any = None  # set externally; not persisted here

    # ------------------------------------------------------------------
    # I/O
    # ------------------------------------------------------------------
    def load(self) -> None:
        if not self.path.exists():
            self.started_at = _now()
            return
        data = json.loads(self.path.read_text(encoding="utf-8"))
        self.completed_steps = list(data.get("completed_steps", []))
        self.started_at = data.get("started_at") or _now()
        self.last_updated = data.get("last_updated")

    def save(self) -> None:
        self.last_updated = _now()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": "3.0.0-rc1",
            "started_at": self.started_at or _now(),
            "completed_steps": self.completed_steps,
            "last_completed_step": self.last_completed_step,
            "last_updated": self.last_updated,
        }
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def reset(self, keep_config: bool = False) -> None:
        """Wipe previous state. Called on non-resume runs.

        If ``keep_config`` is True we preserve the INTERVIEW marker so a
        pre-supplied ``--config`` file does not force re-asking the questions.
        """
        preserved = []
        if keep_config and Step.INTERVIEW.value in self.completed_steps:
            preserved.append(Step.INTERVIEW.value)
        self.completed_steps = preserved
        self.started_at = _now()
        self.save()

    # ------------------------------------------------------------------
    # Checkpoint API
    # ------------------------------------------------------------------
    def is_done(self, step: Step) -> bool:
        return step.value in self.completed_steps

    def mark_done(self, step: Step) -> None:
        if step.value not in self.completed_steps:
            self.completed_steps.append(step.value)
        self.save()

    @property
    def last_completed_step(self) -> Optional[str]:
        return self.completed_steps[-1] if self.completed_steps else None


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
