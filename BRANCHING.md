# Branching & Repository Hygiene

InsureAI uses a deliberately small branch model. The repository contains a long history of experimental `feature/*` branches; those branches are historical workspaces, not part of the supported runtime architecture.

## Supported branches

| Branch | Role | Rule |
|---|---|---|
| `insureai` | **canonical / production branch** | All production code, data pipeline changes and release automation land here. GitHub Pages and scheduled collection use this branch. |
| `cloudflare/workers-autoconfig` | deployment-specific integration | Keep only while Cloudflare deployment automation is actively maintained. Do not use it as a second application source of truth. |

## Feature branches

New work should use short-lived branches named:

```text
feature/<single-purpose-change>
fix/<single-purpose-bug>
chore/<maintenance-task>
```

A feature branch should:

1. have one coherent purpose;
2. branch from `insureai`;
3. merge back to `insureai` through a PR when practical;
4. be deleted after merge or abandonment;
5. never become a second production branch.

Do **not** create versioned variants such as `feature/foo-v2`, `feature/foo-final3`, or `feature/foo-clean` for iterative fixes. Amend the same feature branch or open a new short-lived branch with a precise purpose.

## Historical branch cleanup

The repository currently has many old `feature/*` branches from the incremental development of the intelligence pipeline. They should be treated as cleanup candidates, not as dependencies.

Before deleting a historical branch, verify:

- no open PR uses it as a head branch;
- it is merged into `insureai`, or its changes are intentionally abandoned;
- no scheduled workflow references it;
- no deployment configuration references it;
- no documentation instructs users to check it out.

After verification, delete the branch from GitHub. Never force-reset `insureai` merely to make branch history look cleaner.

## Source-of-truth rule

There is exactly one application source of truth:

```text
insureai
```

Generated artifacts (`data.json`, quality reports, audit/provenance manifests, SEO output, etc.) may be committed by automation, but their generators remain the source of truth. A generated JSON file must not become an independent hand-maintained branch of business logic.

## Release rule

A release is considered coherent only when the same `insureai` revision passes:

1. data contract validation;
2. unit tests;
3. quality gates;
4. audit ledger validation;
5. release manifest validation;
6. release provenance validation.

Deployment verification is a separate state from analytical quality. `quality=passed` must never be interpreted as `deployment=verified`.

## Repository hygiene checklist

Before starting another optimization cycle:

```bash
git fetch --prune --all
git branch -vv
git status --short
python3 -m unittest discover -s tests -v
```

The working tree should be clean before release commits, and local credentials, caches, editor files and machine-specific configuration must remain ignored.
