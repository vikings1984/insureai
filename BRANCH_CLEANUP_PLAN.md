# Branch Cleanup Plan

Last audited: 2026-08-22
Canonical branch: `insureai`

## Protected branches

- `insureai` — production/application source of truth.
- `cloudflare/workers-autoconfig` — deployment-specific branch; retain until deployment migration is formally retired.

## Confirmed cleanup candidates

The following branches are fully behind `insureai` with `ahead_by=0` in the current comparison and therefore contain no commits that are missing from the canonical branch. They are safe deletion candidates **provided no external deployment/workflow reference exists**:

- `feature/eval-final2`
- `feature/eval-final3`
- `feature/eval-final4`
- `feature/eval-final5`
- `feature/eval-run-5`
- `feature/evaluation-system-2`

These branches are historical snapshots rather than active development lines.

## Do not delete yet

The following branches contain commits not present on `insureai` and therefore require content-level review before deletion:

- `feature/eval-run-6` — 6 commits ahead; adds evaluation workflow, `evaluation.py`, tests, and documentation.
- `feature/audit-lineage-v2` — 4 commits ahead; adds `audit_ledger.py` and tests plus workflow changes.
- `feature/change-impact-v2` — 5 commits ahead; adds `change_impact.py`, tests, and changes workflow/review behavior.

An `ahead_by > 0` result is treated as **review**, never as a deletion candidate.

## Deletion gate

Before deleting any candidate branch, verify:

1. No open PR uses the branch.
2. No GitHub Actions workflow references the branch explicitly.
3. No deployment configuration references the branch.
4. No documentation identifies it as an active maintenance branch.
5. Its commits are either fully contained in `insureai` or explicitly archived elsewhere.

## Naming cleanup

Avoid creating new branches with iterative suffixes such as `-v2`, `-final2`, `-run-6`, or `-clean`. Use one short-lived branch per change:

- `feature/<single-purpose-change>`
- `fix/<single-purpose-bug>`
- `chore/<maintenance-task>`

## Operating rule

Do not force-reset or repoint historical branches merely to make the branch list look clean. Delete only after the deletion gate passes. The canonical branch must never be rewritten for cleanup purposes.
