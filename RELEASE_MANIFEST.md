# Release Manifest

`release_manifest.json` records the boundary between **quality validation** and **production deployment**.

A release can be `quality_status=passed` while `deployment_status=pending` and `deployment_verified=false`. This is intentional: CI proves the repository is internally consistent; it does not prove that an external hosting provider has deployed and served the exact commit.

For the current application channel, the manifest declares `cloudflare_workers` for production deployment; `SITE_URL` remains the canonical/SEO URL. The two URLs are intentionally separate (see `DEPLOYMENT.md`).
