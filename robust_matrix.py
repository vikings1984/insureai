#!/usr/bin/env python3
from __future__ import annotations


def annotate_matrix(matrix: dict, scenario_rows: list[dict]) -> dict:
    availability = {str(r.get('scenario')): r.get('execution_readiness', 'ready') for r in scenario_rows}
    out = dict(matrix)
    results = []
    for result in matrix.get('results', []):
        names = [str(x) for x in result.get('scenarios', [])]
        ready = [n for n in names if availability.get(n, 'ready') == 'ready']
        robust = [dict(a, robust=len(ready) >= 2, eligible_scenarios=len(ready)) for a in result.get('robust_actions', [])]
        nr = dict(result)
        nr['evidence_ready_scenarios'] = ready
        nr['robust_actions'] = robust
        nr['robustness_note'] = '只有至少两个证据可用的独立情景，才允许标记为跨情景稳健。'
        results.append(nr)
    out['results'] = results
    return out
