#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P0-2 Run model: one identity linking every artifact in a single pipeline run.

A Run is created once at the start of a pipeline execution. Every released
artifact, the release manifest, and the release provenance record must carry
the same ``run_id`` so that any production state can be traced back to the
exact build that produced it (Replay / auditability, see plan §十 / §二十一 P0-2).

The model is intentionally small and dependency-light: it only depends on
``contract`` for the schema-version single source of truth, so it can be
imported from any producer or from the CI without pulling in the intelligence
engine.
"""
from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from contract import SCHEMA_VERSIONS

ROOT = Path(__file__).resolve().parent
RUN_FILENAME = "run.json"

# Current intelligence engine version. Surfaced in every artifact so a released
# bundle can be correlated with the engine that produced it.
ENGINE_VERSION = "4.2"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_run_id() -> str:
    return "run_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]


@dataclass
class Run:
    run_id: str
    build_sha: str = "unknown"
    engine_version: str = ENGINE_VERSION
    schema_version: str = SCHEMA_VERSIONS["release_provenance_schema"]
    started_at: str = ""
    ended_at: str | None = None
    status: str = "running"  # running | passed | failed
    failed_stage: str | None = None

    def __post_init__(self) -> None:
        if not self.started_at:
            self.started_at = _now()

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "build_sha": self.build_sha,
            "engine_version": self.engine_version,
            "schema_version": self.schema_version,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "status": self.status,
            "failed_stage": self.failed_stage,
        }

    def save(self, root: Path) -> Path:
        path = root / RUN_FILENAME
        path.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return path

    @classmethod
    def load(cls, root: Path) -> "Run | None":
        path = root / RUN_FILENAME
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            run_id=data.get("run_id", new_run_id()),
            build_sha=data.get("build_sha", "unknown"),
            engine_version=data.get("engine_version", ENGINE_VERSION),
            schema_version=data.get("schema_version", SCHEMA_VERSIONS["release_provenance_schema"]),
            started_at=data.get("started_at", ""),
            ended_at=data.get("ended_at"),
            status=data.get("status", "running"),
            failed_stage=data.get("failed_stage"),
        )


def create_run(*, build_sha: str | None = None, root: Path = ROOT) -> Run:
    run = Run(run_id=new_run_id(), build_sha=build_sha or os.environ.get("GITHUB_SHA", "unknown"))
    run.save(root)
    return run


def stamp_provenance(obj: dict, run: Run) -> dict:
    """Add an additive provenance block to an artifact.

    This never touches existing keys consumers rely on; it only attaches a new
    ``_provenance`` object so the artifact is traceable to the run that built it.
    """
    obj["_provenance"] = {
        "run_id": run.run_id,
        "build_sha": run.build_sha,
        "engine_version": run.engine_version,
        "schema_version": run.schema_version,
        "generated_at": _now(),
    }
    return obj


if __name__ == "__main__":
    run = create_run()
    print(json.dumps(run.to_dict(), ensure_ascii=False, indent=2))
