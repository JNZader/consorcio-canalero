# Fly.io backend manual deploy (free-tier conservative)

This setup deploys only `gee-backend` on Fly.io with a single shared VM, auto stop/start, and no GitHub app integration.

## Context

- Backend runtime: `gee-backend/Dockerfile` exposes `8000` and serves health at `/health`.
- Existing CI/CD in `.github/workflows/deploy.yml` targets Koyeb; Fly is intentionally manual-only.

## 1) Create app (one time)

```bash
flyctl auth login
flyctl apps create <FLY_APP_NAME>
```

Then set your app name in `fly.toml` (`app = "<FLY_APP_NAME>"`).

## 2) Set backend secrets (placeholders)

```bash
flyctl secrets set \
  SUPABASE_URL="<SUPABASE_URL>" \
  SUPABASE_PUBLISHABLE_KEY="<SUPABASE_PUBLISHABLE_KEY>" \
  SUPABASE_SECRET_KEY="<SUPABASE_SECRET_KEY>" \
  SUPABASE_JWT_SECRET="<SUPABASE_JWT_SECRET>" \
  REDIS_URL="<REDIS_URL>" \
  GEE_PROJECT_ID="<GEE_PROJECT_ID>" \
  GEE_SERVICE_ACCOUNT_KEY="<GEE_SERVICE_ACCOUNT_KEY_JSON_OR_BASE64>"
```

Optional legacy keys if needed by your environment:

```bash
flyctl secrets set \
  SUPABASE_KEY="<SUPABASE_KEY_LEGACY>" \
  SUPABASE_SERVICE_ROLE_KEY="<SUPABASE_SERVICE_ROLE_KEY_LEGACY>"
```

## 3) Manual deploy

From repo root:

```bash
flyctl deploy --config fly.toml
```

## 4) Verify app status and logs

```bash
flyctl status
flyctl logs
curl -fsS https://<FLY_APP_NAME>.fly.dev/health
```

## 5) Check machine scaling/auto-stop state

```bash
flyctl machine list
flyctl machine status <MACHINE_ID>
```

Expected conservative behavior:

- `auto_stop_machines = "stop"`
- `auto_start_machines = true`
- `min_machines_running = 0`
- single shared VM (`shared`, 1 CPU, 256 MB)
