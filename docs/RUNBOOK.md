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
git pull origin main && docker compose up -d --build backend worker celery-beat geo-worker
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

### 1.4 Offsite backups (Phase 2 / F2-A + F2-B)

Two scripts in `scripts/` plus two compose services run the daily
encrypted backups. **Pick one storage backend** (Backblaze B2 *or*
Hetzner Storage Box) — the same `.env` drives both backup runners.

#### 1.4.a Option A — Backblaze B2 (recommended for offsite separation)

1. Signup at <https://www.backblaze.com/sign-up/cloud-storage>. Free
   tier: 10 GB storage + 1 GB egress/day. Past that ~€5/TB/month.
2. *Create a Bucket* → name it `consorcio-backups`, **Files in Bucket
   are: Private**, **Default Lifecycle Settings**: "Keep prior versions
   for X days" → 30. Use the EU region if available.
3. *App Keys → Add a New Application Key* → name "consorcio-backup",
   bucket = your bucket, capabilities = `listBuckets`, `listFiles`,
   `readFiles`, `writeFiles`, `deleteFiles`. Copy the **keyID** and
   the **applicationKey** (the long one) — Backblaze shows the secret
   exactly once.
4. Edit `/home/javier/stacks/consorcio/.env`:
   ```env
   # pg_dump backup (F2-A)
   BACKUP_BACKEND=b2
   B2_BUCKET=consorcio-backups
   B2_KEY_ID=<keyID from step 3>
   B2_APPLICATION_KEY=<applicationKey from step 3>
   BACKUP_ENCRYPTION_PASSPHRASE=<openssl rand -base64 48>
   BACKUP_RETENTION_DAYS=30

   # restic volume backup (F2-B)
   RESTIC_REPOSITORY=b2:consorcio-backups:/restic/consorcio
   RESTIC_PASSWORD=<openssl rand -base64 48>
   B2_ACCOUNT_ID=<same keyID as B2_KEY_ID>
   B2_ACCOUNT_KEY=<same as B2_APPLICATION_KEY>
   ```
5. **Store both passphrases off-server** (password manager). Lose them
   and the backups are unrecoverable.

#### 1.4.b Option B — Hetzner Storage Box (cheapest if VPS is Hetzner)

1. Hetzner Cloud Console → *Storage Boxes* → add a 100 GB box (~€3.20
   /month, same datacenter as the VPS for fastest writes).
2. *Settings* of the new box → **enable SSH support** + create a
   sub-account dedicated to the consorcio (`u123456-sub1`) with its
   own password.
3. (Recommended) Generate an SSH key on the server (`ssh-keygen -t
   ed25519 -f ~/.ssh/hetzner_sb`), then add the public key in the
   Storage Box UI.
4. Edit `.env`:
   ```env
   # pg_dump backup
   BACKUP_BACKEND=hetzner-sb
   HETZNER_SB_HOST=u123456.your-storagebox.de
   HETZNER_SB_USER=u123456-sub1
   HETZNER_SB_SSH_KEY=/home/javier/.ssh/hetzner_sb   # or HETZNER_SB_PASS=...
   BACKUP_ENCRYPTION_PASSPHRASE=<openssl rand -base64 48>
   BACKUP_RETENTION_DAYS=30

   # restic volume backup
   RESTIC_REPOSITORY=sftp:u123456-sub1@u123456.your-storagebox.de:/restic/consorcio
   RESTIC_PASSWORD=<openssl rand -base64 48>
   ```
5. **Important**: Storage Box has no automatic lifecycle. The
   ``backup_postgres.sh`` script's ``BACKUP_RETENTION_DAYS`` setting
   only affects the B2 path; for SB you either set a manual cleanup
   cron (``find``-style delete via SFTP) or accept unbounded growth.
   Volume backups via ``restic forget --prune`` ARE managed
   automatically because restic stores its own lifecycle metadata.

#### 1.4.c Trigger a one-off backup (verifies the credentials are right)

```bash
ssh -i ~/.ssh/hetzner_ghagga -p 2222 javier@157.180.29.238
cd /home/javier/stacks/consorcio
docker compose --profile backup run --rm backup-postgres
docker compose --profile backup run --rm backup-volumes
```

The two services live behind the `backup` compose profile so they
don't auto-start with `docker compose up`. First run will build the
image (~1 min); subsequent runs are seconds.

#### 1.4.d Schedule the daily backup via host crontab

```cron
# m h dom mon dow  command
15 03 * * *  cd /home/javier/stacks/consorcio && /usr/bin/docker compose --profile backup run --rm backup-postgres >>/var/log/consorcio-backup-postgres.log 2>&1
45 03 * * *  cd /home/javier/stacks/consorcio && /usr/bin/docker compose --profile backup run --rm backup-volumes  >>/var/log/consorcio-backup-volumes.log  2>&1
```

The 30-min gap keeps the two jobs from saturating the upload bandwidth
at the same time. Both logs rotate via logrotate in
`/etc/logrotate.d/consorcio` (template in `docs/templates/`).

### 1.5 Email / SMTP (Phase 2 / F2-J)

Currently the password-reset and the (incoming) email verification
flow write the token to the structured logger. Wire any SMTP provider
to send actual mails. Brevo (300/day free, no card) is the easiest
LATAM choice; Resend (100/day) is fine if your domain is set up with
SPF/DKIM/DMARC.

1. Provider signup (Brevo example):
   - <https://www.brevo.com/free-shop-account/> → free plan.
   - *SMTP & API* → enable the SMTP relay → copy the **SMTP key**.
2. Edit `.env`:
   ```env
   SMTP_HOST=smtp-relay.brevo.com
   SMTP_PORT=587
   SMTP_USERNAME=<your brevo login email>
   SMTP_PASSWORD=<SMTP key from step 1>
   SMTP_FROM=no-reply@<your domain>
   SMTP_FROM_NAME=Consorcio Canalero 10 de Mayo
   ```
3. `docker compose up -d backend worker`. The backend reads these vars
   on boot; password reset + email verification flows start delivering.
4. **Operator-side hardening**: most SMTP providers (Brevo included)
   log message bodies for 30+ days for support purposes. Password-reset
   and email-verification tokens are valid one-shot credentials. If
   your threat model includes the provider's support team, configure
   their account to disable body logging OR migrate to the provider's
   API (Brevo, Resend, SES all have a transactional API alongside
   SMTP) which doesn't leave the token in a stored body.

### 1.7 Registro del banco de datos en AAIP (Phase 4 / F4-L)

Trámite **obligatorio** bajo la Ley 25.326 si tratamos datos
personales (que sí hacemos: padrón, denuncias, fotos). Es gratuito
y se hace una sola vez; las modificaciones posteriores también son
gratuitas. La AAIP audita más a empresas grandes que a consorcios,
pero no inscribir el banco es multa formal y dificulta cualquier
reclamo del consorcio ante otras entidades que sí cumplen.

**Pasos**:

1. Ingresar a <https://www.argentina.gob.ar/aaip/datospersonales/inscribite>
   con clave fiscal AFIP de la persona jurídica del consorcio (o de
   la persona física responsable).
2. Completar el formulario "RNBD" (Registro Nacional de Bases de
   Datos). Datos clave a tener a mano:
   - Razón social / denominación del consorcio
   - CUIT del consorcio (o del responsable persona física)
   - Domicilio físico + electrónico (``contacto@consorcio10demayo.gob.ar``)
   - Responsable de la base: nombre completo del titular
     administrativo + email
   - Categorías de datos (marcar todas las que apliquen):
     identificación (nombre, DNI), patrimoniales (parcela, hectáreas),
     contacto (teléfono, email), académicos (no aplica), laborales
     (no aplica)
   - Finalidad declarada: "Gestión administrativa del padrón de
     consorcistas, recepción de denuncias ciudadanas, planificación
     operativa territorial."
   - Cesiones: solo a autoridades públicas competentes con
     requerimiento legal escrito (marcar el casillero correspondiente).
3. Subir la política de privacidad publicada en ``/privacidad`` como
   adjunto (PDF generado desde el navegador con "Imprimir → Guardar
   como PDF" alcanza).
4. Esperar el número de inscripción (normalmente 5-15 días hábiles).
   Anotarlo en la sección "Banco de Datos N.º …" al pie de la
   política de privacidad.
5. Cuando llegue el N.º, editar
   ``consorcio-web/src/components/PrivacyPolicyPage.tsx`` (última
   línea, ``inscripto ante el Registro Nacional de Bases de Datos —
   AAIP``) y reemplazar el placeholder por el número real, después
   ``git push``.

**Renovación / actualización**: solo cuando cambien la finalidad, el
responsable o las categorías de datos. Anual no es obligatorio.

### 1.8 PgBouncer transaction-pool (Phase 4 / F4-F)

PgBouncer sits between the Python app containers (``backend`` +
``worker`` + ``celery-beat``) and PostgreSQL, multiplexing N
client-side connections onto a much smaller number of postgres
backends. **Net effect on prod (Hetzner CX33)**: SQLAlchemy's
20+20 pool per process collapsed to a single shared backend
connection through PgBouncer, freeing ~40 postgres slots that
used to sit idle on lock.

**Activation requires BOTH halves** — code-side AND ops-side. Either
one alone makes the situation worse, not better.

#### Code-side (already in repo)

In ``gee-backend/app/db/session.py`` and ``app/config.py``:

  - ``settings.use_pgbouncer`` (env var ``USE_PGBOUNCER``,
    default ``false``).
  - When ``true``: ``poolclass=NullPool`` on both engines AND
    ``prepared_statement_name_func`` on the asyncpg engine.
    Neither alone is enough — SA's asyncpg dialect ALWAYS calls
    ``connection.prepare()``, so without the UUID-tagged name
    PgBouncer-multiplexed backends throw
    ``DuplicatePreparedStatementError`` under load.

The flag is opt-in so installs without PgBouncer don't pay the
``statement_cache_size=0`` deopt.

#### Ops-side checklist

1. ``pgbouncer`` service in ``docker-compose.prod.yml`` (already
   added). Image: ``edoburu/pgbouncer:v1.23.1-p3``. Pool mode
   ``transaction``, ``MAX_CLIENT_CONN=200``, ``DEFAULT_POOL_SIZE=25``,
   ``SERVER_RESET_QUERY=DISCARD ALL`` (mandatory per SA docs).

2. ``.env`` on the server needs:

   ```
   POSTGRES_PASSWORD=<real pg password — read pg_shadow, NOT POSTGRES_PASSWORD env on the postgres container which only applies at initdb>
   DATABASE_URL=postgresql://<user>:<pass>@pgbouncer:5432/<db>   ← host = pgbouncer, NOT postgres
   USE_PGBOUNCER=true
   ```

3. ``docker compose up -d pgbouncer`` first; wait for healthy.
   Then ``docker compose up -d backend worker``. Order matters
   because backend's ``depends_on`` lists pgbouncer.

4. Verify multiplexing actually happened:

   ```bash
   docker exec consorcio-postgres psql -U <user> -d <db> -c "SELECT client_addr, count(*) FROM pg_stat_activity WHERE datname='<db>' GROUP BY 1 ORDER BY 2 DESC;"
   ```

   You should see ONE client_addr (the pgbouncer container IP) with
   a small count (default 1 connection, grows under burst).
   Pre-PgBouncer this list had ~40+ rows.

#### Gotchas

- The ``migrate`` one-shot container talks to postgres DIRECTLY
  (not via pgbouncer). This is now config-enforced: the
  ``migrate`` service in ``docker-compose.prod.yml`` defines its
  own ``environment.DATABASE_URL`` that overrides ``.env`` to
  point at ``postgres:5432``. Alembic DDL relies on session-level
  state that transaction-pool mode discards between batches.
- If you ever see ``DuplicatePreparedStatementError`` or
  ``InvalidSqlStatementNameError`` in backend logs after enabling
  the flag, the most likely cause is the code-side half being
  out of date (older image deployed against newer PgBouncer
  service). Roll the backend image forward.

#### Verify deployed config matches the repo

A 3vr review of the F4-F ops commit (253e727) flagged that the
server may run a legacy compose file (no PgBouncer service in
git history) while the new pgbouncer service in this repo is the
documented source-of-truth. To check the live values match what
this RUNBOOK describes:

```bash
ssh production
docker exec consorcio-pgbouncer env | grep -E '(POOL_MODE|MAX_CLIENT_CONN|DEFAULT_POOL_SIZE|SERVER_RESET_QUERY|AUTH_TYPE)'
```

Expected output (all four must match):

```
POOL_MODE=transaction
MAX_CLIENT_CONN=200
DEFAULT_POOL_SIZE=25
SERVER_RESET_QUERY=DISCARD ALL
AUTH_TYPE=scram-sha-256
```

If anything diverges, either the server config was hand-edited
post-deploy OR the repo has drifted from what is actually
running. Reconcile before the next deploy.

#### Rollback (PgBouncer making things worse)

If the gate misbehaves under real load (saturation, sustained
``server_login_timeout`` errors, mass ``DuplicatePreparedStatementError``):

1. SSH to the server and edit ``/home/javier/stacks/consorcio/.env``:

   ```
   DATABASE_URL=postgresql://<user>:<pass>@postgres:5432/<db>   ← host = postgres
   USE_PGBOUNCER=false
   ```

2. Restart the app containers (NOT pgbouncer — leave it running, it
   is idempotent harm = none when nothing routes through it):

   ```bash
   docker compose up -d backend worker celery-beat
   ```

3. Verify the rollback landed. ``pg_stat_activity`` should now show
   one row per backend process (3-4 client_addr values) instead of
   the single multiplexed PgBouncer row:

   ```bash
   docker exec consorcio-postgres psql -U <user> -d <db> -c "SELECT client_addr, count(*) FROM pg_stat_activity WHERE datname='<db>' GROUP BY 1 ORDER BY 2 DESC;"
   ```

4. Optional, only if you want to fully tear down: ``docker compose
   stop pgbouncer && docker compose rm -f pgbouncer``. Not
   required for the rollback to take effect — step 1 already
   stopped any traffic from reaching it.

The whole rollback is reversible: re-enable the same way (set
``USE_PGBOUNCER=true`` + flip DATABASE_URL back to ``pgbouncer:5432``,
restart app containers) once whatever caused the failure is
understood.

### 1.6 Things that look weird but are by design

See **[docs/KNOWN_LIMITATIONS.md](./KNOWN_LIMITATIONS.md)** for the full
list with rationale + expected-fix milestones. Quick reference:

- Boot logs duplicated (2 uvicorn workers).
- PWA icons are a green "CC" placeholder; replace under
  ``consorcio-web/public/icons/``.
- Celery DB pool intentionally smaller than backend (5+5 vs 20+20).
- ``celery-beat`` is a singleton — do NOT ``--scale celery-beat=2``.
- ``logout-all`` has a ≤15 min residual access-token window.
- SMTP message bodies log to provider; switch to API mode to avoid.
- Refresh-token replay-detection timing has a microsecond-grade
  side-channel residual (theoretical, sub-threat-model).
- Mantine CSS imports stay monolithic until v9 lands.
- React Compiler opted-out on `LocationSection.tsx` + `TerrainViewer3D.tsx`.

---

## 2. Daily ops

### 2.1 Pre-push preflight (CI replacement while Actions is paused)

> ⚠️ **CI is paused** — the GitHub Actions workflows `Backend`,
> `Build and Publish Images`, and `Frontend` are `disabled_manually`
> at the org level because the Actions billing quota was exceeded.
> Until quota resets / a paid plan kicks in, the Phase 4 gates
> (ruff + mypy + auth-gate tests + 60% coverage + 30% mutation)
> are NOT enforced server-side. **Run the local preflight before
> every push.**

`gee-backend/scripts/preflight.sh` reproduces the same gates that
the disabled CI workflows used to enforce. Run it from the
`gee-backend/` directory before `git push`:

```bash
cd gee-backend
bash scripts/preflight.sh             # ALL gates (~10min, the default)
bash scripts/preflight.sh --fast      # skip mutation gate (~30s)
```

The mutation gate is part of the DEFAULT run — keeping it behind a
flag would let it rust silently. Use `--fast` only during inner-loop
edits; the unflagged invocation is the one that gates ``git push``.
Exit code is 0 iff every enforced gate passes. The script prints a
clear ✘/✔ per step and a closing summary listing any failures.

What it covers (each step mirrors what the GH Actions workflow ran):

1. **ruff check** — uses `gee-backend/ruff.toml` (rule set
   `E4 + E7 + E9 + F` mirroring ruff's default; F841 silenced in
   `tests/` for smoke-test patterns).
2. **mypy strict scope** — `app/auth`, `app/domains/padron`,
   `app/domains/denuncias`. Other modules opt out via `mypy.ini`.
3. **auth-gate regression tests** —
   `tests/new/test_auth_gates.py`. Catches a missing `Depends(...)`
   on a PII endpoint.
4. **Backend coverage ≥ 60%** —
   `pytest tests/new/ --cov-config=.coveragerc --cov-fail-under=60`.
5. **Mutation kill-rate ≥ 0.30** —
   `scripts/cosmic_gate.py` against denuncias.service,
   monitoring.service, tramites.schemas.

If `ruff check` fails after a fresh dependency upgrade or a new
file lands, fix the underlying issue rather than widening the
`ignore` list — the gate is small on purpose.

### 2.2 Deploy from `main`

The Hetzner stack currently builds locally on `git pull` (no image
pull). The simpler flow:

```bash
ssh -i ~/.ssh/hetzner_ghagga -p 2222 javier@157.180.29.238
cd /home/javier/stacks/consorcio
git pull origin main
docker compose up -d --build backend worker celery-beat geo-worker
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

### 2.3 Rotate JWT secret

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

### 2.4 ``/auth/jwt/logout-all`` and the residual access-token window

The endpoint revokes EVERY refresh token for the calling user, but
JWT access tokens issued in the previous 15 minutes remain valid
until natural expiry (the JWT is stateless by design — we don't
maintain a server-side revocation list for access tokens). Practical
implication: an attacker with a STOLEN access token has at most
~15 min after the user clicks "logout from all devices" to do
damage. If you need stricter zero-trust revocation, roadmap F3 covers
adding a per-user ``revocation_epoch`` column that the JWT strategy
checks on every request — at the cost of one DB read per call.

### 2.5 Apply a new Alembic migration

The compose files now include a `migrate` service that runs
`alembic upgrade head` before `backend` / `celery-worker` start. After
a `git pull` that includes a new revision, the normal
`docker compose up -d --build` flow runs it automatically.

If you need to run it manually (e.g. baseline an existing DB):

```bash
docker compose --profile migrate run --rm migrate
```

> ⚠️ **NEVER** run `docker compose run --rm backend alembic ...`
> while `USE_PGBOUNCER=true` is in `.env`. The backend container
> inherits `DATABASE_URL=postgresql://...@pgbouncer:5432/...`
> from the stack env, and alembic DDL emits multi-statement
> transactions that PgBouncer transaction-pool mode discards
> between commits — migrations land HALF-applied and the
> session blows up on the next `CREATE INDEX`. The dedicated
> `migrate` service in `docker-compose.yml` overrides
> `DATABASE_URL` inline to talk to postgres directly AND forces
> `USE_PGBOUNCER=false` for the duration of the migration, so
> the command above is the only safe way to run alembic on the
> live server.

Other safe alembic operations through the same service:

```bash
docker compose --profile migrate run --rm migrate alembic current
docker compose --profile migrate run --rm migrate alembic history
docker compose --profile migrate run --rm migrate alembic downgrade -1
```

### 2.6 Inspect denuncia uploads

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
> Pre-req: section 1.4 (offsite backups) must be configured. The
> commands below assume Backblaze B2; for Hetzner SB just swap the
> download step.

**Postgres dump restore** (F2-A):

```bash
# 1. Download the most recent dump from B2 (or sftp from Storage Box)
docker compose --profile backup run --rm --entrypoint sh backup-postgres -c '
  B2_ACCOUNT_INFO=/tmp/.b2 b2 account authorize "$B2_KEY_ID" "$B2_APPLICATION_KEY" &&
  B2_ACCOUNT_INFO=/tmp/.b2 b2 ls "$B2_BUCKET" postgres/ | tail -1 |
  awk "{print \$NF}" |
  xargs -I {} B2_ACCOUNT_INFO=/tmp/.b2 b2 file download "$B2_BUCKET" {} /tmp/latest.sql.zst.enc &&
  cat /tmp/latest.sql.zst.enc
' > latest.sql.zst.enc

# 2. Decrypt + decompress
openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 \
  -pass "env:BACKUP_ENCRYPTION_PASSPHRASE" \
  -in latest.sql.zst.enc | zstd -d -o latest.sql

# 3. Stop dependants so they don't write during restore
docker compose stop backend worker celery-worker

# 4. Wipe + restore (psql, since the dump uses CLEAN/IF-EXISTS)
docker compose exec -T postgres psql -U "$DB_USER" -d consorcio_canalero < latest.sql

# 5. Restart
docker compose up -d backend worker celery-worker
```

**File-backed volumes restore** (F2-B, restic):

```bash
# List snapshots
docker compose --profile backup run --rm --entrypoint restic backup-volumes snapshots

# Restore the most recent into a scratch path on the host
docker compose --profile backup run --rm \
  --entrypoint restic \
  -v "$PWD/restore:/restore" \
  backup-volumes \
  restore latest --target /restore

# Move into the live volumes (stops the consumers first)
docker compose stop backend geo-worker
docker run --rm -v consorcio-denuncia-uploads:/dest -v "$PWD/restore/app/uploads:/src:ro" \
  alpine sh -c 'cp -av /src/. /dest/'
docker run --rm -v consorcio-geo-data:/dest -v "$PWD/restore/data/geo:/src:ro" \
  alpine sh -c 'cp -av /src/. /dest/'
docker compose up -d backend geo-worker
```

---

## 4. Periodic drills

- **Daily (automated)**: section 1.4.d cron triggers
  `backup-postgres` at 03:15 UTC and `backup-volumes` at 03:45 UTC.
  Confirm both runs every Monday — check `/var/log/consorcio-backup-*.log`
  for "backup OK" within the past 24 h.
- **Monthly (manual drill)**: practice section 3.6 against a
  `consorcio_canalero_drill` database (not the live one!). Steps:
  1. `docker compose exec postgres psql -U $DB_USER -c "CREATE DATABASE consorcio_canalero_drill;"`
  2. Pull the latest dump from B2/SB into a scratch dir.
  3. Run the restore commands from section 3.6 against `_drill`.
  4. `\dt` to confirm tables, count a few rows (`SELECT COUNT(*) FROM denuncias;`).
  5. `DROP DATABASE consorcio_canalero_drill` when done.
  Time the end-to-end procedure; the target RTO is 4 h. Note the
  timing in this file under "Last drill" so you can spot regressions.
- **Quarterly**: rotate `JWT_SECRET`, `REDIS_PASSWORD`, GCP service
  account key, GHCR token, Cloudflare API token,
  `BACKUP_ENCRYPTION_PASSPHRASE`, and `RESTIC_PASSWORD`. When you
  rotate the restic password you MUST keep the old one accessible
  until every snapshot encrypted with it has aged out.
- **Annually**: rebuild the `Dockerfile.backup` image to pick up the
  latest base + ``b2``/``restic`` security patches:
  `docker compose --profile backup build --no-cache`.

**Last drill**: not yet executed. Update this line after the first
real run.

---

### 4.1 Server-vs-repo compose drift (F5-A2)

The Hetzner stack runs a CUSTOM ``docker-compose.yml`` that diverged
from the in-repo ``docker-compose.yml`` (dev local) and from
``docker-compose.prod.yml`` (the canonical prod template). All three
files coexist; only the server's is load-bearing for live traffic.

**What's different on the server (vs ``docker-compose.prod.yml``):**

- Builds from local ``./gee-backend`` source (``build:`` directive)
  instead of pulling from GHCR (``image: ghcr.io/...``). Reason:
  GH Actions ``Build and Publish Images`` workflow is currently
  ``disabled_manually`` — quota exceeded. With no published image,
  there's nothing to pull, so the server falls back to a local
  ``docker compose build``.
- Postgres + Redis are EMBEDDED on the same compose, not external.
  ``docker-compose.prod.yml`` treats them as external services on
  a shared Docker network. The server inherited the embedded
  topology from an earlier phase and was never migrated.
- Caddy / proxy is NOT in the compose — runs as a system service
  outside Docker.

**What we have in sync (F4-F + F4.X-1 + F4.X-2 fix-forwards):**

- Backend service ``environment`` block forwards ``USE_PGBOUNCER``.
- Worker service ``environment`` block forwards ``USE_PGBOUNCER``.
- PgBouncer service is up with ``POOL_MODE=transaction``,
  ``MAX_CLIENT_CONN=200``, ``SERVER_RESET_QUERY=DISCARD ALL``,
  ``AUTH_TYPE=scram-sha-256``.
- Dedicated ``migrate`` service with ``DATABASE_URL`` override to
  postgres directly + ``USE_PGBOUNCER=false`` so alembic doesn't
  blow up on multi-statement DDL.

**What's required before the server can adopt ``docker-compose.prod.yml``:**

1. GH Actions billing quota resets (or the user upgrades to a paid
   plan). Until then ``Build and Publish Images`` cannot produce
   the ``ghcr.io/jnzader/consorcio-canalero/{backend,geo-worker}``
   images that ``docker-compose.prod.yml`` references.
2. Run § 2.7 (cutover) once images are published — replace the
   server's ``docker-compose.yml`` with a copy of
   ``docker-compose.prod.yml`` from the repo, set
   ``BACKEND_IMAGE`` + ``GEO_WORKER_IMAGE`` in ``.env`` to the
   SHA-pinned tags, ``docker compose pull && docker compose up -d``.

**Why we haven't backported the embedded topology into the prod
file instead:**

External postgres + redis is the correct prod pattern (shared
across stacks, separate upgrade cadence, separate backup
schedules). The server is the one in the wrong shape, not the
prod compose. The migration goes one way: server → prod.yml,
when the CI side is ready.

**Drift watch — what to check periodically:**

Run on the server:

```bash
docker exec consorcio-pgbouncer env | grep -E '(POOL_MODE|MAX_CLIENT_CONN|DEFAULT_POOL_SIZE|SERVER_RESET_QUERY)'
docker exec consorcio-backend env | grep -E '(USE_PGBOUNCER|DATABASE_URL)'
docker exec consorcio-worker env | grep -E '(USE_PGBOUNCER|DATABASE_URL)'
```

Compare against the equivalent values in
``docker-compose.prod.yml``. Divergence usually means somebody
hand-edited the server's compose without updating the repo —
reconcile before the next deploy.

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
| Backblaze B2 | <https://secure.backblaze.com> (when F2-A on B2) |
| Hetzner Storage Box | <https://console.hetzner.cloud/projects> (when F2-A on SB) |
| SMTP provider | Brevo / Resend / etc. (when F2-J configured) |

### 5.1 External accounts checklist

Tick each as you create the account and stash credentials in the
password manager. Empty rows = the integration is wireable but not
yet activated.

| Integration | Account created? | Where token / key lives | RUNBOOK section |
|-------------|------------------|--------------------------|-----------------|
| Sentry (errors) | ☐ | `.env` SENTRY_DSN + Cloudflare Pages VITE_SENTRY_DSN | 1.1 |
| BetterStack (logs) | ☐ | `.env` BETTERSTACK_TOKEN + Cloudflare Pages VITE_LOGTAIL_TOKEN | 1.2 |
| UptimeRobot (uptime) | ☐ | Monitor created in UptimeRobot UI (no app token) | 1.3 |
| Backblaze B2 (backups) | ☐ | `.env` B2_KEY_ID / B2_APPLICATION_KEY / B2_BUCKET | 1.4.a |
| Hetzner Storage Box (backups) | ☐ | `.env` HETZNER_SB_HOST / USER / SSH_KEY | 1.4.b |
| SMTP (email verify, reset) | ☐ | `.env` SMTP_HOST / USERNAME / PASSWORD | 1.5 |
| Backup encryption passphrase | ☐ | `.env` BACKUP_ENCRYPTION_PASSPHRASE (LOSE = backups unrecoverable) | 1.4 |
| Restic passphrase | ☐ | `.env` RESTIC_PASSWORD (LOSE = backups unrecoverable) | 1.4 |

#### 2.2.a B3-P backend deployment preparation (fail-closed)

Do **not** use this package to deploy yet. It is a deterministic controller-side
plan and read-only preflight; `execute` deliberately refuses after its three
admission gates until the canary/cutover state machine receives its own review.
It never accesses Biogas and never runs migrations, workers, geo-worker, Compose
`down`, Docker cleanup, or Caddy/firewall changes.

```bash
python3 scripts/deploy_b3p.py                       # default: prints only, no subprocess
python3 scripts/deploy_b3p.py preflight             # read-only SSH gates, one command each
python3 scripts/deploy_b3p.py plan --target-sha <40-lowercase-hex-sha>
```

Pinned defaults are Hetzner `javier@157.180.29.238:2222`, key
`~/.ssh/hetzner_ghagga`, stack `/home/javier/stacks/consorcio`, repository
`JNZader/consorcio-canalero`, backend-only target, and B3-P SHA
`1bb3985beb6817e2d7093203d515e8de2235a889`. A different **exact** SHA can be
planned/preflighted with `--target-sha`; official GitHub REST must report that
same SHA with `verification.verified=true` and `reason=valid` before execution.

The preflight fails closed on its first non-zero read-only SSH gate and redacts
credential-shaped output. It includes fresh branch/HEAD/status/staged/untracked/
unfinished-operation, Compose/custom-prod/no-reload, exact normalized backend
mounts, fetch/ancestry/collision/no-compose-or-Alembic, resources/port/live-image,
and Consorcio+Biogas read-only baselines. Runtime volume names normalize exactly
from `consorcio-backend-cache`, `consorcio-geo-data`, and
`consorcio-denuncia-uploads`; extras, anonymous volumes, binds (including code,
root, or Docker socket) fail. A future executable state machine must retain an
immutable `OLD_ID` rollback tag, backup the Compose file, build backend only,
canary on `127.0.0.1:18080`, require a local credentialed tunnel smoke (health,
ready, anonymous 401, authenticated real-basin membership 200), bound/redact
observations, and automatically restore the old image ID after failed cutover.
