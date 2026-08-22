# InsureAI deployment configuration

InsureAI uses two intentionally separate URLs:

- `PUBLIC_SITE_URL`: canonical content/SEO URL used by Daily Collect and prerendering. It may remain the GitHub Pages URL.
- `DEPLOYMENT_URL`: the URL of the actual production deployment that Deployment Verification probes.

## GitHub Actions variable

Set `DEPLOYMENT_URL` as a repository Actions variable (not a secret) to the production URL exposed by Cloudflare Workers. Do not point it at a preview deployment.

Example:

```text
DEPLOYMENT_URL=https://<production-worker-domain>
```

When `DEPLOYMENT_URL` is missing, Deployment Verification reports `deployment_configuration_missing` rather than treating the canonical site as the production target. This is deliberate: a missing configuration is configuration debt, not evidence of an outage.

## Verification semantics

The deployment verifier requires HTTP 200, a non-empty response, and the expected InsureAI marker. The result is recorded separately from Decision, Trust, and Urgency; deployment health is advisory-only.

## Operational rule

Changing the canonical URL must not silently change the production deployment target, and changing the deployment target must not silently change SEO/canonical URLs. Keep the two variables separate.
