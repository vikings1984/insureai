#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verify that an optimization persists in historical module-health evidence."""
from __future__ import annotations

from typing import Any


def _module_rates(history: dict[str, Any], module: str) -> list[float]:
    snapshots = history.get("snapshots", []) if isinstance(history, dict) else []
    rates: list[float] = []
    for snapshot in snapshots if isinstance(snapshots, list) else []:
        if not isinstance(snapshot, dict):
            continue
        rows = snapshot.get("modules", {})
        if not isinstance(rows, dict):
            continue
        row = rows.get(module)
        if isinstance(row, dict) and row.get("error_rate") is not None:
            try:
                rates.append(float(row["error_rate"]))
            except (TypeError, ValueError):
                continue
    return rates


def verify_fix(
    module: str,
    history: dict[str, Any] | None = None,
    *,
    min_snapshots: int = 3,
    improvement_threshold: float = 0.05,
) -> dict[str, Any]:
    """Return evidence that a fix persisted across multiple snapshots.

    A fix is considered verified only when there are enough observations, the
    latest two observations remain non-worsening, and the average recovery rate
    improves the pre-fix baseline by at least ``improvement_threshold``.
    """
    history = history or {}
    rates = _module_rates(history, module)
    if len(rates) < min_snapshots:
        return {
            "status": "unavailable",
            "module": module,
            "observations": len(rates),
            "required_observations": min_snapshots,
            "reason": "insufficient_history",
        }

    baseline = rates[0]
    recovery = rates[-2:]
    improvement = round(baseline - (sum(recovery) / len(recovery)), 4)
    persisted = recovery[1] <= recovery[0] + 0.02
    verified = improvement >= improvement_threshold and persisted
    regressed = recovery[1] - recovery[0] >= improvement_threshold

    if regressed:
        status = "regressed"
    elif verified:
        status = "verified"
    else:
        status = "recovering"

    return {
        "status": status,
        "module": module,
        "observations": len(rates),
        "required_observations": min_snapshots,
        "baseline_error_rate": round(baseline, 4),
        "recovery_error_rates": recovery,
        "improvement": improvement,
        "improvement_threshold": improvement_threshold,
        "persisted": persisted,
    }
