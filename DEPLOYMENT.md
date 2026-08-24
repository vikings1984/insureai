# InsureAI deployment configuration

InsureAI uses two intentionally separate URLs:

- `PUBLIC_SITE_URL`: canonical content/SEO URL used by Daily Collect and prerendering. It may remain the GitHub Pages URL.
- `DEPLOYMENT_URL`: the URL of the actual production deployment that Deployment Verification probes.

## Enabling Cloudflare Workers deployment

Workers static-asset deployment ships in `.github/workflows/deploy-cloudflare.yml`. It is gated on repository secrets and stays skipped (not failed) until they are configured.

1. **Create API credentials.** In the Cloudflare dashboard, create an API token using the **Edit Cloudflare Workers** template and note your account ID.
2. **Add repository secrets.** In Settings → Secrets and variables → Actions, add:
   - `CLOUDFLARE_API_TOKEN` — your API token
   - `CLOUDFLARE_ACCOUNT_ID` — your account ID
3. **Deploy.** The next push to `insureai` (or a manual `workflow_dispatch` run) uploads the static assets. `wrangler deploy` creates the `insureai` Worker and assigns a `*.workers.dev` domain.
4. **Point `DEPLOYMENT_URL` at production.** Set it to the assigned domain (for example `https://insureai.<your-subdomain>.workers.dev`). Deployment Verification then probes it every 6 hours.

The `.assetsignore` file keeps Python sources, docs, and internal audit/release artifacts out of Cloudflare, while `data.json`, `research.json`, `index.html`, `css/`, and `js/` are uploaded — the same front-end content GitHub Pages serves.

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
