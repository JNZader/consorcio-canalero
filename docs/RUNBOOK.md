# Runbook — Consorcio Canalero 10 de Mayo

> Operations playbook for the Hetzner deploy. Read this before paging
> anyone at 3 AM. Update it after every incident — the next outage
> probably has the same root cause as the last one.

## TL;DR — common commands

```bash
# SSH to the server
ssh -i ~/.ssh/hetzner_ghagga -p 2222 javier@157.180.29.238

# Where the stack lives
cd /home/javier/stacks/consorcio

# Current service health
docker compose ps
curl -sf https://cc10demayo-api.javierzader.com/live    # 200 ⇒ process alive
curl -sf https://cc10demayo-api.javierzader.com/ready   # 200 ⇒ ready for traffic
curl -sf https://cc10demayo-api.javierzader.com/health  # legacy combined (always 200)

# Tail logs
docker compose logs -f backend
docker compose logs --tail 200 backend | jq -c 'select(.level=="error")'

# Restart a service safely
docker compose restart backend

# Full redeploy from main (build local)
git pull origin main && docker compose up -d --build backend worker geo-worker
```

---

## 1. First-time setup of the optional integrations

The repo wires Sentry, BetterStack and UptimeRobot opt-in. Default
configuration disables all three. To turn them on:

### 1.1 Sentry (error tracking)

1. Signup at <https://sentry.io>. Free tier: 5 000 errors/month.
2. Create **two projects** in the same organisation:
   - Platform: **FastAPI** → name it `consorcio-backend`.
   - Platform: **React** → name it `consorcio-frontend`.
3. In each project go to *Settings → Client Keys (DSN)* and copy the DSN.
4. **Backend**: edit `/home/javier/stacks/consorcio/.env` and set:
   ```env
   SENTRY_DSN=https://<key>@<org>.ingest.us.sentry.io/<project_id>
   SENTRY_TRACES_SAMPLE_RATE=0.0   # bump to 0.1 if you want perf traces
   ```
   Then `docker compose up -d backend worker celery-worker`.
5. **Frontend**: Cloudflare Pages → project → *Settings → Environment
   variables*. Add:
   ```
   VITE_SENTRY_DSN=https://<key>@<org>.ingest.us.sentry.io/<project_id>
   VITE_SENTRY_TRACES_SAMPLE_RATE=0
   VITE_SENTRY_ENVIRONMENT=production
   ```
   Trigger a new deploy (e.g. retry the latest one).
6. Smoke-test: in `gee-backend/app` add `raise RuntimeError("sentry test")`
   to a temporary endpoint, hit it, confirm the issue appears in Sentry,
   roll back. On the frontend: `throw new Error("sentry test")` from the
   browser console under a Sentry-wrapped route.

### 1.2 BetterStack / Logtail (centralised logs)

1. Signup at <https://betterstack.com> → *Telemetry → Logs* (`logs.betterstack.com`).
   Free tier: 1 GB/month.
2. Create **two sources** under *Sources*:
   - Platform: **FastAPI** → name `consorcio-backend`.
   - Platform: **JavaScript / Browser** → name `consorcio-frontend`.
3. From each source page copy the **Source token**.
4. **Backend** `.env`:
   ```env
   BETTERSTACK_TOKEN=<token from FastAPI source>
   # BETTERSTACK_HOST=https://eu1.logs.betterstack.com   # only if EU region
   ```
   `docker compose up -d backend worker celery-worker`.
5. **Frontend** Cloudflare Pages env vars:
   ```
   VITE_LOGTAIL_TOKEN=<token from JS/Browser source>
   # VITE_LOGTAIL_ENDPOINT=https://eu1.logs.betterstack.com   # only if EU
   ```
6. Smoke-test backend: tail `docker compose logs backend` and confirm
   the same line shows up in BetterStack's "Live tail" within ~5 s.

### 1.3 UptimeRobot (HTTP uptime monitor + alert)

1. Signup at <https://uptimerobot.com>. Free tier: 50 monitors / 5-min check.
2. *Add new monitor*:
   - Type: **HTTP(s)**
   - Friendly name: `Consorcio API health`
   - URL: `https://cc10demayo-api.javierzader.com/live`
   - Monitoring interval: 5 min (free-tier minimum)
3. *Alert contacts*: add the email(s) that should receive an "is down" notice.
4. Repeat with URL `https://consorcio-canalero.pages.dev/` for the frontend.
5. (Optional) Add `https://cc10demayo-api.javierzader.com/ready` as a
   third monitor — it returns 503 when DB / Redis are down even if the
   process is alive, so you'll notice dependency outages even before
   the process dies.

> **Why `/live` and not `/health`?**  The legacy `/health` endpoint
> always returns HTTP 200, with degradation only in the JSON body.
> UptimeRobot would never alert on it. `/live` is the new liveness
> probe (200 = process responsive); `/ready` is true readiness (503
> when DB or Redis are down).

---

## 2. Daily ops

### 2.1 Deploy from `main`

The Hetzner stack currently builds locally on `git pull` (no image
pull). The simpler flow:

```bash
ssh -i ~/.ssh/hetzner_ghagga -p 2222 javier@157.180.29.238
cd /home/javier/stacks/consorcio
git pull origin main
docker compose up -d --build backend worker geo-worker
```

This rebuilds the affected containers in place and rolling-restarts
them; healthchecks gate the rollover.

#### Optional path: pull pre-built images from GHCR

The GitHub Actions workflow `.github/workflows/deploy.yml` publishes
images to `ghcr.io/jnzader/consorcio-canalero/{backend,geo-worker}`
on every push to `main` with two tags: the short SHA and `:latest`.
The summary on every workflow run prints the SHA + the `.env` line
to paste. To migrate the server to this mode:

1. Replace `/home/javier/stacks/consorcio/docker-compose.yml` with a
   copy of `docker-compose.prod.yml` from the repo.
2. In `.env`, set `BACKEND_IMAGE` and `GEO_WORKER_IMAGE` to the SHA-pinned
   refs (see `.env.prod.example` for the format).
3. To deploy a new build: edit those two lines, then
   `docker compose pull backend geo-worker && docker compose up -d backend geo-worker worker`.
4. To roll back: same flow, just point at the previous SHA from
   <https://github.com/JNZader/consorcio-canalero/pkgs/container/consorcio-canalero%2Fbackend>.

### 2.2 Rotate JWT secret

Every user logged in right now has a session signed with the current
`JWT_SECRET`. Rotating invalidates all sessions — schedule outside
peak hours.

```bash
NEW=$(openssl rand -hex 32)
ssh -i ~/.ssh/hetzner_ghagga -p 2222 javier@157.180.29.238 \
  "cd /home/javier/stacks/consorcio && \
   cp .env .env.bak-\$(date +%Y%m%d-%H%M%S) && \
   sed -i 's|^JWT_SECRET=.*|JWT_SECRET=${NEW}|' .env && \
   docker compose up -d backend worker celery-worker"
```

### 2.3 Apply a new Alembic migration

The compose files now include a `migrate` service that runs
`alembic upgrade head` before `backend` / `celery-worker` start. After
a `git pull` that includes a new revision, the normal
`docker compose up -d --build` flow runs it automatically.

If you need to run it manually (e.g. baseline an existing DB):

```bash
docker compose run --rm migrate
```

### 2.4 Inspect denuncia uploads

Photos live in the `consorcio-denuncia-uploads` named volume. To list:

```bash
docker run --rm -v consorcio-denuncia-uploads:/data alpine ls -lh /data
```

To back up:

```bash
docker run --rm -v consorcio-denuncia-uploads:/data -v "$PWD:/out" \
  alpine tar czf /out/denuncia-uploads-$(date +%Y%m%d).tgz -C /data .
```

---

## 3. Incident playbooks

Each section: **detection → triage → mitigation → root cause**.

### 3.1 Backend container OOM

**Detection**
- UptimeRobot reports `/live` 5xx or timeouts.
- `docker compose ps` shows `backend` `unhealthy` or restarting.
- `docker compose events --since 10m` shows `oom-kill` events.

**Triage**
```bash
docker stats --no-stream consorcio-backend
# Memory column at 100 % of the 512M limit ⇒ OOM
docker compose logs --tail 200 backend | grep -i -E 'killed|memory|oom'
```

**Mitigation**
- Short-term: `docker compose restart backend` to clear any leak.
- If it OOMs immediately again, raise `mem_limit` in
  `docker-compose.yml` (currently 512M) and `up -d backend`.

**Root cause hunting**
- Inspect any new endpoints introduced in the last deploy that load
  large GeoJSON / raster into memory.
- Check rate-limit middleware isn't disabled (`RATE_LIMIT_DISABLED`
  must be false in prod — the boot-time check enforces this).
- If sustained, enable `py-spy` profiling: temporarily add
  `command: ["py-spy", "top", "--pid", "1"]` in a sidecar container.

### 3.2 Database down / unreachable

**Detection**
- `/ready` returns 503 (`database.status != healthy`).
- `docker compose logs backend | grep -i 'connection\|psycopg\|asyncpg'`.
- Sentry: spike of `OperationalError: could not connect to server`.

**Triage**
```bash
docker compose ps postgres
docker compose logs --tail 100 postgres | tail -50
```

**Mitigation**
- If postgres exited: `docker compose up -d postgres` and watch logs.
- If healthy but backend can't reach it: check `DATABASE_URL` host;
  in the multi-stack shared-postgres setup the host is `shared-postgres`
  (Docker network alias).
- If the volume is corrupt: `docker compose down postgres`, restore
  from the last `pg_dump` (see 4.1), `docker compose up -d postgres`.

**Root cause**
- Disk full? `df -h` on the host.
- Connection-limit exhaustion? `SELECT count(*) FROM pg_stat_activity;`
  in `psql`. Default `max_connections=100`; raise temporarily and
  schedule PgBouncer (roadmap F4).

### 3.3 GEE rate limit / auth failure

**Detection**
- `/ready` shows `gee.status = degraded` (non-critical, won't 503).
- Sentry: `EEException: rate limit` or `Permission denied`.

**Triage**
- Visit <https://console.cloud.google.com/iam-admin/quotas?project=cc10demayo>
  and check the daily compute quota.
- Confirm the service-account JSON in `GEE_SERVICE_ACCOUNT_KEY` is
  current (rotate annually in GCP IAM).

**Mitigation**
- Rate limit: throttle the cron / Celery beat tasks that hit GEE.
- Auth: regenerate the service account key in GCP, update the env
  var, `docker compose up -d backend geo-worker`.

### 3.4 Deploy broken — fail-fast rejected the boot

The `_enforce_production_secrets()` check refuses to start when
production config is unsafe. See `gee-backend/app/config.py:_enforce_production_secrets`.

**Detection**
- `docker compose ps backend` shows `Exited (1)`.
- `docker compose logs --tail 30 backend` ends with:
  ```
  RuntimeError: Refusing to start with insecure configuration:
    - JWT_SECRET is too short (X bytes); must be at least 64 bytes...
    - CORS_ORIGINS contains a localhost/dev origin in production...
    - REDIS_PASSWORD is set to the placeholder 'changeme'...
  ```

**Mitigation** — fix the env var(s) listed:
- `JWT_SECRET`: `openssl rand -hex 32` ⇒ 64-char value.
- `CORS_ORIGINS`: explicit comma-separated list of `https://…`
  origins; no `*`, no localhost.
- `REDIS_PASSWORD`: anything that isn't `changeme` or empty.
- `RATE_LIMIT_DISABLED`: must not be truthy in prod.

Then `docker compose up -d backend`.

### 3.5 Deploy broken — Alembic migration failed

**Detection**
- `docker compose ps migrate` shows `Exited (1)`.
- `backend` never starts (depends_on the migrate completion).

**Triage**
```bash
docker compose logs migrate | tail -50
```

Common causes:
- New revision references a column that doesn't exist on the prod DB
  → manual schema diverged from the model; reconcile by hand.
- Migration ran on a DB the auth user doesn't own → check `DATABASE_URL`
  user has `ALTER` privileges on the schema.

**Mitigation**
- Fix the revision (locally, push, redeploy).
- Roll back one revision: `docker compose run --rm migrate alembic downgrade -1`.

### 3.6 Restore from backup

> **Pre-req**: backups must already exist. Phase 1 doesn't wire
> automated backups — roadmap F2 covers `pg_dump` to Backblaze B2 +
> `restic` for uploads. Until then this section is theoretical.

Once backups are in place:

```bash
# 1. Stop dependants
docker compose stop backend worker celery-worker

# 2. Drop and recreate the DB
docker compose exec postgres psql -U consorcio -c "DROP DATABASE consorcio_canalero;"
docker compose exec postgres psql -U consorcio -c "CREATE DATABASE consorcio_canalero;"

# 3. Restore from the latest dump
docker compose exec -T postgres pg_restore -U consorcio -d consorcio_canalero < backup.dump

# 4. Restart
docker compose up -d backend worker celery-worker
```

---

## 4. Periodic drills

- **Monthly**: practice 3.6 against a `consorcio_canalero_drill`
  database. Time the procedure end-to-end; the target RTO is 4 h.
- **Weekly**: read this file. Update any step that's stale.
- **Quarterly**: rotate `JWT_SECRET`, `REDIS_PASSWORD`, GCP service
  account key, GHCR token, Cloudflare API token.

---

## 5. Where things live

| Component | Location |
|-----------|----------|
| Repo | <https://github.com/JNZader/consorcio-canalero> |
| Frontend | Cloudflare Pages — project `consorcio-canalero` |
| Backend, geo-worker, martin | Hetzner CX33 — `/home/javier/stacks/consorcio` |
| Postgres + Redis | Same VPS, shared across stacks |
| Container registry | `ghcr.io/jnzader/consorcio-canalero` |
| CI/CD | GitHub Actions — `.github/workflows/{frontend,backend,deploy,gh-pages}.yml` |
| Tile server | `https://cc10demayo-tiles.javierzader.com` (Martin) |
| API | `https://cc10demayo-api.javierzader.com` |
| Sentry | <https://sentry.io> (when configured) |
| BetterStack | <https://logs.betterstack.com> (when configured) |
| UptimeRobot | <https://uptimerobot.com> (when configured) |
