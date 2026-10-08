# Deployment

The app is one Docker container with no database. It must run as a **single instance**, because batch jobs live in memory (DECISIONS.md D13).

## Settings

| Variable | Required | Notes |
|---|---|---|
| `LV_ANTHROPIC_API_KEY` | yes, unless `LV_PROVIDER=fixture` | Store it as a platform secret. Set a monthly spend limit in the Anthropic console too. |
| `LV_ACCESS_CODE` | recommended for a public URL | Visitors enter it once; a cookie remembers it for a week. `/healthz` stays open. |
| `LV_PROVIDER` | no | `fixture` runs the keyless demo (sample labels only, with a banner saying so). |
| `LV_MODEL`, `LV_EFFORT` | no | Default `claude-haiku-5-5`, `low`. |

The container listens on `$PORT` (default 8000) and serves `GET /healthz` for health checks.

## Option A: Render (quickest)

1. In Render, choose **New → Blueprint** and select this repository. `render.yaml` defines the service.
2. Enter `LV_ANTHROPIC_API_KEY` (and optionally `LV_ACCESS_CODE`) when prompted.
3. Deploy. The URL is shown on the service page.

Use a paid instance type: the free plan sleeps when idle, and a 30–60 s cold start on the first request would undercut the 5-second requirement.

## Option B: Azure Container Apps (TTB's platform)

```bash
az group create -n label-verifier -l eastus
az containerapp up -n label-verifier -g label-verifier --source . --ingress external --target-port 8000 \
  --env-vars LV_MODEL=claude-haiku-5-5 LV_EFFORT=low
az containerapp secret set -n label-verifier -g label-verifier \
  --secrets anthropic-key=<key> access-code=<code>
az containerapp update -n label-verifier -g label-verifier --min-replicas 1 --max-replicas 1 \
  --set-env-vars LV_ANTHROPIC_API_KEY=secretref:anthropic-key LV_ACCESS_CODE=secretref:access-code
```

`--min-replicas 1` avoids cold starts; `--max-replicas 1` keeps batch jobs on one instance.

Inside TTB's network, outbound calls to `api.anthropic.com` may be blocked (Marcus's interview). The in-tenant route is to call Claude through **Microsoft Foundry** in TTB's Azure tenant. That needs a small `FoundryExtractor` behind the existing `LabelExtractor` interface (TECHNICAL_DESIGN.md §15); the rest of the app is unchanged.

## Option C: anywhere Docker runs

```bash
docker build -t label-verifier .
docker run -p 8000:8000 -e LV_ANTHROPIC_API_KEY -e LV_ACCESS_CODE label-verifier
```
