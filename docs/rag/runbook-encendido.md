# Runbook — turning the semantic knowledge surface on (G9)

**Change:** `consorcio-conocimiento-semantico` · **Tasks:** 10.1–10.6 ·
**Written:** 2026-08-24 · **Design:** `openspec/changes/consorcio-conocimiento-semantico/design.md`, section G9.

This is the ordered procedure for enabling `conocimiento_qa_enabled` on the
Hetzner box. Every step names the command that performs it, the command that
verifies it, the state it fails into and how to get back. **A step with no
recovery is a step that will be improvised at 2 a.m.**, so there are none.

Two properties of this document are deliberate and worth stating before the first
command:

* **It promises no numbers.** The measurement steps say how to produce figures,
  never what the figures will be. Every harness this runbook calls refuses to
  emit a verdict without a real run behind it — that refusal is the feature, and
  a runbook that quoted expected values would be teaching the operator to read
  past it.
* **The box's compose file lives outside this repository.** Single environment,
  Hetzner, one compose file maintained on the box. Section 0 carries the two
  service blocks to paste into it **verbatim**; this repository's
  `docker-compose.yml` is the development shape and is never deployed there.

## The ceremony is joint with `flujo-caminos`

Owner decision, 2026-08-24: **one trip to the box, not two.** The
`flujo-caminos` rollout (`openspec/changes/flujo-caminos/tasks.md`, task **O.1**)
and this runbook run in the same maintenance window. O.1 owns its own ordered
sequence — migrate → ETL dry-run → id/count comparison against the live GEE
`red_vial` asset → real ETL → crossing task → unchanged-surface verification →
frontend — and nothing here reorders it.

The interleaving rule is simple, because the two arcs share exactly one
resource: **the database and its single `alembic upgrade head`.**

1. Run **step 1** of this runbook (verified backup) first. It covers both arcs;
   two separate backups of the same box in one window is ceremony.
2. Run **steps 2–5** here (sidecar deploy, health-verify, stop the app, image
   swap). O.1 has no stake in them and they are the ones that can send everyone
   home early.
3. Run `alembic upgrade head` **once** (step 6). It carries both arcs' revisions.
   Both arcs verify their own objects afterwards; neither runs its own upgrade.
4. Run **O.1's ETL sequence**, then **steps 6b–11** here. The ordering between
   them is free after the shared migration, but the corpus re-ingest and the road
   ETL both write for minutes and running them serially keeps the failure
   attribution honest.
5. **Flag flips last, on both sides**, after each arc's own verification passed.

---

## Section 0 — the external compose blocks (task 10.2)

Paste both services into the box's compose file. They are recorded here because
that file is not in this repository, and a block nobody wrote down is a block
that gets retyped from memory at the worst moment.

### 0.1 `conocimiento-embed` — the BGE-M3 query-embedding sidecar

```yaml
  conocimiento-embed:
    build:
      context: .
      dockerfile: docker/embed/Dockerfile
    container_name: consorcio-conocimiento-embed
    restart: unless-stopped
    expose:
      - "8002"
    environment:
      # An INPUT pin, symbolic or hash. What the service REPORTS is always the
      # resolved 40-hex commit, which is what the identity guard compares.
      - EMBED_MODEL_ID=${EMBED_MODEL_ID:-BAAI/bge-m3}
      - EMBED_REVISION_HF=${EMBED_REVISION_HF:-}
      - EMBED_DEVICE=cpu
    volumes:
      # The model is pulled once into this cache, not baked into the image.
      - conocimiento-embed-cache:/cache/huggingface
    networks:
      - consorcio-network
    healthcheck:
      # `/health` and NOT `/ready`: the model takes 30–60 s to load and a
      # readiness-based healthcheck would restart-loop the container through its
      # own cold start forever. Readiness is the surface's question, answered per
      # request as `embedder_no_listo`.
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8002/health', timeout=5).close()"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 15s
```

plus, on the **backend** service:

```yaml
    environment:
      - CONOCIMIENTO_EMBED_URL=http://conocimiento-embed:8002
```

and, in the file's top-level `volumes:` block:

```yaml
  conocimiento-embed-cache:
    name: consorcio-conocimiento-embed-cache
```

**Three deliberate differences from the block drafted in `design.md:933-955`,
recorded here rather than silently applied.** U3 shipped the sidecar and the
repository's `docker-compose.yml` is the authority on its shape:

| Design draft | What U3 shipped, and why |
|---|---|
| `ports: - "127.0.0.1:8002:8002"` | `expose: "8002"`. The surface reaches it over the compose network through `CONOCIMIENTO_EMBED_URL`; publishing it to the host loopback adds a reachable port and buys nothing. The reboot probe in step 3 therefore runs `docker compose exec`, not a host `curl`. |
| `hf-cache:/root/.cache/huggingface` | `conocimiento-embed-cache:/cache/huggingface` — the named volume the image's `HF_HOME` actually points at. |
| `healthcheck` on `/ready` with `start_period: 180s` | `/health` via the image's own Python. `/ready` in a healthcheck restart-loops the container through its own cold start; `curl` is not in the image. |

`profiles: ["conocimiento"]` from the repository file is deliberately **not**
carried over. It exists to keep a bare `docker compose up -d` on a developer
machine from pulling 2.2 GB of weights; on the box this service is supposed to
start with everything else, and a profile there would mean a reboot brings the
box back with the answerer silently absent.

### 0.2 `conocimiento-worker` — the mailbox's postman

Amendment A3 made the product an asynchronous mailbox: `POST /preguntas`
enqueues, and a worker with a GPU processes items in batches. **Without this
process the queue has no consumer**: items sit `pendiente` forever and the only
symptom is `GET /api/v2/conocimiento/estado` reporting them ageing.

**Where the postman itself comes from, stated explicitly and not left to a table
cell.** The two artifacts this section commands — the entrypoint
`gee-backend/scripts/rag_worker.py` and the knob `CONOCIMIENTO_WORKER_POLL_S`
(`conocimiento_worker_poll_s` in `app/config.py`) — **ship with the U7 postman
commit**, `feat(conocimiento): U7 — asynchronous mailbox: queue, worker, HTTP
surface and its postman (#226)`, which is already on `main`. The branch this
runbook was written on was cut before that commit landed, so **in this
pre-replant tree neither file nor knob exists**: `app/domains/conocimiento/
trabajador.py` is here, its command-line entrypoint is not. Nothing in this
section is therefore runnable from this branch alone, and that is a property of
the branch, not of the procedure — replanting onto `main` is what makes the
systemd unit below name a script that exists, at which point this paragraph is
trivially true rather than a caveat. **Verify it rather than assume it**, on the
tree that will actually be deployed:

```
ls gee-backend/scripts/rag_worker.py
rg -n 'conocimiento_worker_poll_s' gee-backend/app/config.py
```

**Where it runs, stated before the block, because getting this wrong wastes a
maintenance window.** The worker reranks with `bge-reranker-v2-m3` on **CUDA**.
The Hetzner box is a CX33: 2 shared vCPU, **no GPU**. A3 resolved the GPU host as
*the owner's workstation, when it is available*, and the queue is precisely what
absorbs that intermittence. So the worker's compose block belongs to the compose
file **on the GPU host**, reaching the box's Postgres over the same
`DATABASE_URL` the backend uses — not to the box's own file, unless and until the
box grows a GPU.

**One prerequisite this repository does not yet satisfy, named rather than
papered over.** `requirements-rag.txt` — the CUDA stack — is deliberately outside
every image built here (design D8, and `tests/test_ci_workflow_contracts.py`
holds it there). **No Dockerfile in this repository builds it**:
`gee-backend/Dockerfile.worker` is the Celery/GDAL geo worker and is a different
process entirely. `venv-rag` is a host virtualenv. Two consequences:

* **Runnable today — a supervised host process.** This is the form to use until
  the image exists:

```ini
# /etc/systemd/system/consorcio-conocimiento-worker.service   (on the GPU host)
[Unit]
Description=Consorcio conocimiento mailbox worker
After=network-online.target

[Service]
WorkingDirectory=/srv/consorcio-canalero/gee-backend
EnvironmentFile=/srv/consorcio-canalero/gee-backend/.env
ExecStart=/srv/consorcio-canalero/gee-backend/venv-rag/bin/python scripts/rag_worker.py
Restart=always
RestartSec=10
KillSignal=SIGTERM

[Install]
WantedBy=multi-user.target
```

  ⚠ **`EnvironmentFile=` is systemd's parser, not compose's `env_file:`** — it
  applies its own shell-style quoting rules (surrounding quotes are stripped, a
  trailing `\` continues the line onto the next), so the same `.env` that the
  backend container reads can reach the worker with *different* values; a quoted
  secret and anything sharing a line with a `#` are the usual two. Read back what
  the process actually got, never what the file looks like:
  `tr '\0' '\n' < /proc/$(systemctl show -p MainPID --value consorcio-conocimiento-worker)/environ`.

  `SIGTERM` is the correct stop signal and needs no drain: `reclamar_pendiente`
  never commits an intermediate state, so an abandoned transaction leaves the
  item exactly `pendiente`, which is the state it never left.

* **The compose form, recorded as the target shape** (task 10.2). Its `build:`
  stanza names a Dockerfile that **does not exist yet** — building
  `requirements-rag.txt` into an image is the missing prerequisite, and this
  block is not runnable until it does:

```yaml
  conocimiento-worker:
    build:
      context: .
      dockerfile: docker/rag-worker/Dockerfile   # ⚠ NOT PRESENT IN THIS REPO YET
    container_name: consorcio-conocimiento-worker
    restart: unless-stopped
    command: ["python", "scripts/rag_worker.py"]
    env_file:
      # The SAME .env as the backend: same DATABASE_URL, same provider pin, same
      # credential, same knobs. Two files drift, and the drift is invisible
      # because both processes keep running.
      - .env
    networks:
      - consorcio-network
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
```

**Knobs and their defaults** (`gee-backend/app/config.py`, and the worker's own):

| Env var | Default | What it does |
|---|---|---|
| `CONOCIMIENTO_QA_ENABLED` | `false` | The kill switch. **Leave it false until step 11.** |
| `CONOCIMIENTO_EMBED_URL` | `http://conocimiento-embed:8002` | Where the sidecar lives. |
| `CONOCIMIENTO_EMBED_TIMEOUT_S` | `10.0` | Per-call timeout to the sidecar. |
| `CONOCIMIENTO_PROVEEDOR_URL` | `http://127.0.0.1:3456` | mcp-llm-bridge gateway. |
| `CONOCIMIENTO_MODELO` | `opencode-go/deepseek-v4-flash` | The pinned model. Changing it invalidates the terms record (step 7a) **and** every graded answer. |
| `CONOCIMIENTO_POOL` | `opencode-cli` | The pool the pin routes through. |
| `CONOCIMIENTO_PROVEEDOR_API_KEY` | *(empty)* | Fact 2 of the enablement AND. Empty ⇒ the surface stays off. |
| `CONOCIMIENTO_PROVIDER_TIMEOUT_S` | `20.0` | One provider call. |
| `CONOCIMIENTO_ITEM_DEADLINE_S` | `60.0` | Worker budget for ONE queued item. Not a request deadline — nobody is on a socket (A3). |
| `CONOCIMIENTO_WORKER_POLL_S` | `5.0` | Sleep when the queue is empty. Ships with the postman commit. |
| `CONOCIMIENTO_WORKER_STALE_AFTER_S` | `900.0` | Past this age the surface says the worker has not picked the item up instead of showing an indefinite spinner. `0` disables the message. |
| `CONOCIMIENTO_QUOTA_DIARIA_USUARIO` | `0` | **Unset. Blocked on the A2 cost re-derivation** — set before step 11. |
| `CONOCIMIENTO_SPEND_CEILING_USD` | `0.0` | Same. |
| `CONOCIMIENTO_SPEND_WINDOW_H` | `24` | Ceiling window. |
| `CONOCIMIENTO_RATE_LIMIT_REQUESTS` / `_WINDOW` | `10` / `60` | The surface's own limiter, keyed on user id. |
| `CONOCIMIENTO_MAX_BODY_BYTES` | `16384` | Bounds the bytes; `buzon.PREGUNTA_MAX_CHARS` bounds the text. |
| `CONOCIMIENTO_READY_TTL_S` | `5.0` | Cached `/ready` probe TTL for the flag gate. |

**Why `venv-rag` and not the app venv.** The worker reranks with
`bge-reranker-v2-m3` on CUDA, which needs `requirements-rag.txt` — the CUDA stack
deliberately kept out of the app image (design D8). Under the default
interpreter `scripts/rag_worker.py` exits **2** naming `requirements-rag.txt`
rather than dying on an ImportError traceback. There is no `--reranker-device
cpu`: CPU reranking at depth 50 is ~99 s/query, which is an outage that answers.

**Foreground form**, for the first supervised run of a window — the one where
somebody wants to watch the refusals scroll past before handing the process to
systemd:

```
venv-rag/bin/python scripts/rag_worker.py --database-url "$DATABASE_URL"
```

Its other flags: `--corpus-sha` pins the worker to a revision across an ingestion
(it otherwise answers from the ACTIVE snapshot), `--intervalo-s` overrides the
empty-queue sleep, and `--max-items N` stops after N items — a supervised one-shot
drain, never a substitute for the loop.

**Deployment refusals do not fail items.** An unverified terms record, an
unbuildable provider or a missing/synthetic reranker are identical for every item
in the queue, so failing an item on them would tell a CD member their question
could not be answered about a box that never tried. The loop logs the cause and
keeps polling: items stay `pendiente`, `GET /estado` shows them ageing, and
fixing the record or the credential resumes processing with nothing lost. An
unnamed exception propagates instead — a loop that swallows bugs is a worker that
reports itself alive while processing nothing.

Exit codes: `0` clean stop on SIGTERM/SIGINT · `1` refused to start (unverified
terms, unbuildable provider, no CUDA reranker) · `2` usage, including "this
interpreter has no torch".

---

## Section 1 — the ordered sequence

### Step 1 — verified restore of the backup

A file that exists is not a backup. Restore the dump into a throwaway container
and assert row counts plus `PostGIS`/`pgRouting` extension presence.

```
pg_dump -Fc "$DATABASE_URL" > /var/backups/consorcio-pre-vector-$(date +%F).dump
docker run -d --name restore-probe -e POSTGRES_PASSWORD=probe pgrouting/pgrouting:16-3.4-3.6.1
docker exec -i restore-probe pg_restore -U postgres -d postgres --no-owner < /var/backups/consorcio-pre-vector-$(date +%F).dump
docker exec restore-probe psql -U postgres -c "SELECT extname FROM pg_extension WHERE extname IN ('postgis','pgrouting');"
docker exec restore-probe psql -U postgres -c "SELECT count(*) FROM rag_documento;"
docker rm -f restore-probe
```

* **Failure state:** the swap does not proceed.
* **Recovery:** fix the dump. Nothing on the live box has changed yet.

### Step 2 — deploy the sidecar

Add §0.1 to the external compose file, then:

```
docker compose up -d conocimiento-embed
docker compose ps conocimiento-embed
docker compose exec conocimiento-embed python -c \
  "import urllib.request;print(urllib.request.urlopen('http://localhost:8002/ready',timeout=5).read().decode())"
```

* **Failure state:** the image build fails, or the model never loads — OOM, or no
  disk for the 2.2 GB of weights.
* **Recovery:** remove the block and `docker compose up -d` without it. Nothing
  else has moved and the flag is still off. **This is where the §2.1 RAM
  measurement pays for itself.**

### Step 3 — health-verify the sidecar

Not "is it up": **is it the pinned pair, and does it actually produce vectors.**
Three probes, in the design's order — `/health`, `/ready`, and **one real embed
of a known string**. All three run through `docker compose exec`, because the
service is `expose`d and not host-published (§0.1).

```
docker compose exec conocimiento-embed python -c \
  "import json,urllib.request;print(json.load(urllib.request.urlopen('http://localhost:8002/health',timeout=5)))"
docker compose exec conocimiento-embed python -c \
  "import json,urllib.request;print(json.load(urllib.request.urlopen('http://localhost:8002/ready',timeout=5)))"
docker compose exec conocimiento-embed python -c \
  "import json,urllib.request; p=urllib.request.Request('http://localhost:8002/embed', data=json.dumps({'textos':['consorcio canalero']}).encode('utf-8'), headers={'Content-Type':'application/json'}); d=json.load(urllib.request.urlopen(p,timeout=60)); v=d['vectores'][0]; print(d['modelo'], d['revision_hf'], d['dims'], len(v), v[:3])"
```

`/health` answers `{"vivo": true}` the moment the process is up and says nothing
about the model. `/ready` answers `{"listo": true, ...}` only after the weights
loaded **and** the warm-up embed completed; until then both it and `/embed` are
`503` with `causa: embedder_no_listo`.

Assert, on **`/ready` and on the `/embed` response alike**, that `modelo` is
`BAAI/bge-m3` and `revision_hf` is the pinned **resolved 40-hex commit** — the
sidecar reports the resolved hash, never the symbolic tag it was asked for
(`revision_solicitada` is reported separately and is not the identity). Then
assert the vector itself: `len(v)` equals the reported `dims`, and the numbers
are floats, not an empty list.

**The embed is not ceremony.** `/ready` is a statement about load state; it is
`/embed` that exercises the encoder the corpus vectors were produced with, and
the identity travels back **with the batch** precisely so the caller compares
what produced *these* numbers rather than what a separate `/ready` call reported
at some other moment. "The model says it loaded" and "the model returns a
vector" are different facts, and only the second one is what the surface needs.

* **Failure state:** a different revision is reported by *either* endpoint, the
  embed 503s, or the vector length disagrees with `dims` ⇒ **STOP**.
* **Recovery:** fix `EMBED_REVISION_HF` and restart. Proceeding here means every
  later step is calibrated against the wrong vector space.

### Step 4 — announce the maintenance window and stop the app

```
docker compose stop backend
```

No failure state of its own. This is where the `flujo-caminos` window opens too.

### Step 5 — swap the Postgres image

Change the `postgres` service's image to `consorcio-postgres:16-vector`, built
from `docker/postgres/Dockerfile`.

```
docker build -f docker/postgres/Dockerfile -t consorcio-postgres:16-vector docker/postgres
docker compose up -d postgres
docker inspect --format '{{.Config.Image}}' "$(docker compose ps -q postgres)"
```

* **Failure state:** the container will not start on the existing volume.
* **Recovery:** revert the image tag **before any migration runs**. Nothing
  vector-shaped exists yet, so this revert is safe.

### Step 6 — `alembic upgrade head`

The box is on **`conocimiento_004`**. Head is **`conocimiento_007`**, and the
path between them is **six revisions, not three**: `conocimiento_005`'s
`down_revision` is `0023_add_relevamiento_tramo`, so the `flujo-caminos`
revisions sit *inside* this arc's own upgrade path. That is not an accident of
enumeration — it is the structural reason the ceremony is joint and the upgrade
runs exactly once.

| # | Revision | What it creates |
|---|---|---|
| 1 | `0021_add_red_vial` | `red_vial` — `flujo-caminos` |
| 2 | `0022_add_cruce_camino` | `cruce_camino` — `flujo-caminos` |
| 3 | `0023_add_relevamiento_tramo` | `relevamiento_tramo` **and** `tramo_clasificacion_candidata` — `flujo-caminos` |
| 4 | `conocimiento_005` | widens the `clasificacion` CHECK to admit `institucional`; adds the nullable `clasificacion_evidencia` column |
| 5 | `conocimiento_006` | `decision_ruta` |
| 6 | `conocimiento_007` | `buzon_consultas` |

**Four road tables appearing during this step — `red_vial`, `cruce_camino`,
`relevamiento_tramo`, `tramo_clasificacion_candidata` — is EXPECTED and is not
this arc running more than it was asked to.** They are `flujo-caminos` O.1's
objects, carried by the single shared upgrade the interleaving rule at the top
of this file (point 3) already committed to. An operator who sees them and stops
the migration halfway is creating the one failure state this step calls
dangerous.

Print the plan before running it, so the six are seen before they are applied:

```
docker compose run --rm backend alembic history -r conocimiento_004:head
docker compose run --rm backend alembic upgrade head
docker compose run --rm backend alembic heads   # expect: conocimiento_007 (head)
```

**`conocimiento_005` MUST precede step 7.** Re-ingesting before it means the
first `institucional` document dies on an `IntegrityError` against the old CHECK
and the whole transaction rolls back.

If `conocimiento_002`'s vector branch was already recorded as applied on the
vector-less image, run `app/domains/conocimiento/ddl.py`'s `UPGRADE_STATEMENTS`
directly — the non-destructive path measured in archive design D7, table row B.

* **Failure state:** **a half-applied migration. This is the dangerous cell.**
* **Recovery:** do **not** re-run blindly. Inspect `alembic_version` against the
  objects actually present:

```
docker compose exec postgres psql -U consorcio -d consorcio -c "SELECT version_num FROM alembic_version;"
docker compose exec postgres psql -U consorcio -d consorcio -c "SELECT 1 FROM pg_extension WHERE extname='vector';"
docker compose exec postgres psql -U consorcio -d consorcio -c "\d+ rag_documento"
docker compose exec postgres psql -U consorcio -d consorcio -c \
  "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid='rag_documento'::regclass AND contype='c';"
```

If the version row moved but the objects are missing, the recovery is the sealed
rollback of section 3, from step 1's verified backup — **never a hand-patched
schema**.

### Step 6b — the pinned corpus checkout must be on the box

The corpus is **private and is not vendored in this repository**, so "the box has
it" is a step, not an assumption.

```
git -C /srv/consorcio-corpus-legal rev-parse HEAD    # must equal the pinned corpus_sha
git -C /srv/consorcio-corpus-legal status --porcelain # must be empty
```

The pinned SHA is `12043582bf8016288a7e8084e85a4b713a97af2f` (`Makefile`,
`RAG_CORPUS_SHA`; also the `corpus_sha` header of
`app/domains/conocimiento/eval/expected_clasificacion.yaml`).

* **Failure state:** `CorpusPinMismatch`, with three distinct causes the
  exception names individually — **not a git checkout**, **HEAD ≠ declared SHA**,
  **dirty working tree**.
* **Recovery:** clone, or `git checkout <sha>`, and clean the tree. Nothing has
  been written: this check runs before the transaction opens.

### Step 7 — re-run the ingest for reclassification

```
venv/bin/python scripts/rag_ingest.py \
    --corpus-path /srv/consorcio-corpus-legal \
    --corpus-sha 12043582bf8016288a7e8084e85a4b713a97af2f \
    --database-url "$DATABASE_URL"
```

* **Failure state:** `CorpusPinMismatch`, `JurisdiccionFaltante`, an unknown
  `tipo`, a gate failure, or an `IntegrityError` if step 6's `conocimiento_005`
  did not run.
* **Recovery:** **transaction rollback, not "aborts before writing".** The whole
  ingest runs inside ONE transaction. Some aborts (the pin check, an unknown
  `tipo` on the first document) land before any write; others land after rows
  were written *in the open transaction*. Either way the committed state is
  untouched — but the guarantee is *rollback*, and the difference matters to
  anyone watching disk or reading uncommitted state from another session. Fix the
  frontmatter rule or the allowlist and re-run.

### Step 7a — the provider terms verification (task 6.7) — **THE OWNER'S SIGNATURE**

**This is a manual step and it has no automated substitute.** A machine cannot
read published terms; it can only refuse to pretend they were read. The
procedure is `docs/rag/proveedor-terminos.md`.

Performed 2026-08-31 against the live `opencode-go/deepseek-v4-flash` pin
(record in `proveedor_terminos.yaml`, `verificado: true`, owner's name on it).
`CONOCIMIENTO_QA_ENABLED` stays false until step 11. Re-run the same procedure
when any re-verification trigger in that document fires (pin/pool change,
digest mismatch, DeepSeek ZDR monthly expiry). The owner:

1. confirms the exact model id **as the opencode-go pool exposes it**;
2. reads the provider's published no-training-on-input and retention terms;
3. fills `app/domains/conocimiento/proveedor_terminos.yaml` with
   `verificado: true` **together with all four evidence fields**
   (`verificado_el`, `verificado_por`, `fuente_url`, `sha256_terminos`) and the
   two substantive fields (`no_entrenamiento`, `retencion_dias` within
   `RETENCION_MAX_DIAS`), in **one commit, with the owner's name on it**, which
   also keeps `test_el_registro_QUE_ESTA_HOY_EN_EL_REPO_cubre_el_pin` (and the
   matching costs test) asserting coverage.

Verify what the box will see:

```
curl -fsS -H "Authorization: Bearer $ADMIN_TOKEN" \
  https://<box>/api/v2/conocimiento/estado | python -m json.tool
```

`terminos_verificados` must be `true`. It is the **first** ANDed fact of
`enforce_conocimiento_qa_enabled`; the other two are `credencial_presente` and
`embedder_listo`.

* **Failure state:** the record cannot be verified.
* **Recovery:** **the flag is not enabled.** Fail-closed, not a warning. This is
  a real terminal state of this runbook, not a retry.

### Step 8 — verify the reclassification against the checked-in artifact

```
venv/bin/python scripts/rag_verificar_clasificacion.py \
    --corpus-sha 12043582bf8016288a7e8084e85a4b713a97af2f \
    --database-url "$DATABASE_URL"
echo "exit=$?"
```

All **35** rows, **class and evidence**, diffed row by row against
`app/domains/conocimiento/eval/expected_clasificacion.yaml`.

Exit `0` every row matches · `1` at least one row diverges · `2` the comparison
was refused (the artifact is pinned to another `corpus_sha`, or the
classification rule in the tree moved since the artifact was generated).

**Never a `count(*)`.** A count passes on any permutation that preserves it, and
two documents swapping classes — one private promoted, one public demoted — is
exactly the silent privacy failure this step exists to catch.

* **Failure state:** **any** row differing in class or in evidence.
* **Recovery:** **STOP with the flag still off.** A wrong classification here is
  the privacy boundary failing silently, which is the one failure this whole
  design is arranged around.

### Step 9 — load the corpus vectors

```
venv/bin/python scripts/rag_load_vectors.py \
    --vectors artifacts/rag/vectors-12043582.copy \
    --database-url "$DATABASE_URL"
```

The artifact and its sidecar (model id, HF revision, dims, sha256,
`over_ceiling` keys) come from the GPU batch on the owner's workstation
(`scripts/rag_embed_batch.py`); this step is the **load**, and it is the step
with the gates.

* **Failure state:** a manifest or identity refusal — `sintetico` vectors, an
  `over_ceiling` mismatch, a model that is not the snapshot's.
* **Recovery:** the loader refuses **before writing**. Re-run the batch; the
  database keeps its previous state.

**Read section 2 before deciding whether to run this step at all.**

### Step 10 — smoke

```
docker compose exec postgres psql -U consorcio -d consorcio -c "SELECT 1 FROM pg_extension WHERE extname='vector';"
docker compose exec postgres psql -U consorcio -d consorcio -c "SELECT extname FROM pg_extension WHERE extname IN ('postgis','pgrouting');"
# Martin is not host-published (it is reached at `martin:3000` over the compose
# network), so the catalog is probed from a container that is on that network.
docker compose exec backend python -c \
  "import urllib.request;print(urllib.request.urlopen('http://martin:3000/catalog',timeout=5).status)"
```

and **one real retrieval**, which under the ratified serving path is
`modo="bm25_ce"` — see section 2.

* **Failure state:** any smoke fails.
* **Recovery:** the sealed rollback of section 3. **Do not flip the flag to
  "test it in prod".**

### Step 11 — flip the flag

Only after every step above, and only when all of section 4's preconditions are
green.

```
# in the box's .env
CONOCIMIENTO_QA_ENABLED=true
```
```
docker compose up -d backend
# and, on the GPU host, the worker (§0.2):
systemctl --now enable consorcio-conocimiento-worker
curl -fsS -H "Authorization: Bearer $ADMIN_TOKEN" https://<box>/api/v2/conocimiento/estado | python -m json.tool
```

`GET /estado` is the acceptance read, and the queue block is what makes it
load-bearing rather than decorative: `profundidad_cola`,
`mas_antiguo_pendiente`, `ultima_corrida_worker` and `worker_demorado` together
separate "the worker is between batches" from "the worker has been down since
yesterday". Depth alone says neither.

* **Failure state:** the surface misbehaves.
* **Recovery:** flag off. The surface is inert, there is no DB change and no
  rollback is needed.

---

## Section 2 — what the vectors are for, post-B50 (task 10.3)

Step 9 still loads vectors and step 10 still smokes the `vector` extension, and
**this is deliberate even though the ratified serving path does not read a vector
column.** The B50 decision (task 2.7) put `bm25_ce` — BM25 at depth 50 followed
by the `bge-reranker-v2-m3` cross-encoder — on the serving path. The stored
corpus vectors therefore have **no serving consumer**.

What they still have:

* the `vector` extension, the column and the HNSW index are what the `vector` and
  `hybrid` **ablation arms** in `scripts/rag_eval.py` measure against, and those
  arms are how any future move off B50 gets evidence instead of a hunch;
* the schema and the loader's identity gates are already built and tested, and
  ripping them out to re-add them later is strictly more risk than leaving them;
* the embedder identity guard `(modelo, revision_hf)` is what makes the
  abstention threshold artifact re-derivable — it is pinned to the embedder pair.

So the honest statement, written here so nobody later reads step 9 as evidence
that serving is vector-backed: **the serving smoke of step 10 is a `bm25_ce`
retrieval, and the vectors loaded in step 9 are eval and future-option
infrastructure.** Step 9 can be deferred without blocking enablement; steps 8,
7a and section 4 cannot.

---

## Section 3 — the reboot re-derivation probe matrix

If the box reboots between any two steps, the recovery is **not** "continue where
the notes stopped". It is **re-derive the state**. `restart: unless-stopped`
brings the sidecar, the worker and Postgres back, so every step must be
answerable by a probe rather than by memory.

| Step to re-derive | Probe | What it reads |
|---|---|---|
| 2 — sidecar deployed | `docker compose ps conocimiento-embed` | the container exists and is `running`/`healthy` |
| 3 — sidecar health-verified | `docker compose exec conocimiento-embed python -c "import json,urllib.request;print(json.load(urllib.request.urlopen('http://localhost:8002/ready',timeout=5)))"` | not just "up": a container that came back on a *different* image reports a different `(modelo, revision_hf)` pair, and `/ready` alone would say yes |
| 5 — image swapped | `docker inspect --format '{{.Config.Image}}' "$(docker compose ps -q postgres)"` | the running image tag is `consorcio-postgres:16-vector`. **This is the one memory gets wrong after a reboot** — a compose file edited but not applied looks identical to one applied |
| 6 — migrations applied | `SELECT version_num FROM alembic_version` **and** `SELECT 1 FROM pg_extension WHERE extname='vector'` **and** `\d+ rag_documento` **and** the widened CHECK in `pg_constraint` | version row **and** objects, never the version row alone |
| 7/8 — reclassification done | `scripts/rag_verificar_clasificacion.py --corpus-sha <pinned>` | all 35 rows, class + evidence. Not a count |
| 9 — vectors loaded | `SELECT embedding_modelo, embedding_revision_hf, embedding_sintetico FROM rag_corpus WHERE corpus_sha = '<pinned>';` | identity, not merely non-NULL |
| 11 — flag | the env var, and `GET /api/v2/conocimiento/estado` | the flag is env-backed and defaults to `False`, so a reboot **cannot** bring the surface up half-configured — the one property that makes this recoverable at all |

Two of these probes are **not** database reads, and that is the point: rounds 1
of the design listed four probes, all of them database reads, and therefore had
no probe at all for the two steps whose failure mode is a container that came
back wrong.

### Every correction this runbook makes to the design's G9 section, in one list

The design is the sealed plan; this document is the plan meeting the tree that
was actually built. Where the two disagree, **the tree wins and the disagreement
is written down here** rather than applied silently — a runbook that quietly
diverges from its design leaves the next reader with two documents and no way to
tell which one was checked.

| # | The design says | This runbook says, and the tree's evidence |
|---|---|---|
| 1 | `ports: - "127.0.0.1:8002:8002"` on the sidecar (`design.md:933-955`) | `expose: - "8002"` — `docker-compose.yml:368-369`. The surface reaches it over the compose network; a host port buys nothing |
| 2 | `hf-cache:/root/.cache/huggingface` | `conocimiento-embed-cache:/cache/huggingface` — `docker-compose.yml:379`, the image's real `HF_HOME` |
| 3 | `healthcheck` on `/ready` via `curl`, `start_period: 180s` | `/health` through the image's own Python — `docker-compose.yml:382-391`. `/ready` restart-loops the container through its own cold start, and `curl` is not in the image |
| 4 | Reboot probe for step 3: `curl -fsS http://127.0.0.1:8002/ready` from the host | `docker compose exec conocimiento-embed python -c ...` — the direct consequence of **1** and **3**: no host port to curl, and no curl to do it with |
| 5 | Step 6 "now also carries **`conocimiento_005`**" — three revisions from `conocimiento_004` | **six** revisions. `conocimiento_005`'s `down_revision` is `0023_add_relevamiento_tramo`, so `0021`/`0022`/`0023` are on this arc's upgrade path. Enumerated in full at step 6 |
| 6 | Probe for step 9: `SELECT embedding_modelo, embedding_revision_hf, sintetico FROM rag_corpus` (`design.md:988`) | the column is **`embedding_sintetico`** — `models.py:150`. `sintetico` is the spelling of the *artifact manifest* field (`rag_load_vectors.py:444`) and of `ProcedenciaEmbeddings.sintetico` (`repository.py:911`), never of the column; run as written the probe fails with `column "sintetico" does not exist`, which is a probe that cannot answer the question it exists for |

Corrections **5** and **6** are the two that would have fired during a window
rather than before one: 5 as an operator halting a correct migration because
four unexpected road tables appeared, 6 as a reboot probe erroring out at the
exact moment somebody needs to know whether the vectors survived.

### Sealed rollback order

**flag off → `alembic downgrade conocimiento_001` → revert the image.**

The middle step is expensive and V0 measured it: `003`'s downgrade DELETEs rows
and `004`'s drops the provenance columns, so it requires a **full re-ingest and a
vector re-load** (archive design D7, "DESTRUCTIVE FALLBACK"). That cost is
precisely why the surface comes off first — flag-off makes the system inert
without touching the database.

**Never revert the image with vector objects live.**

---

## Section 4 — measurement, and the exact preconditions for step 11

### 4.1 Box measurements (task 10.4) — **on the box, not the workstation**

Both precede step 2's go/no-go and neither has been taken yet. **This runbook
records how to produce them; it quotes no figures.**

**CPU query-embedding latency.** The question is narrow: can a 2-shared-vCPU box
turn a question into a query vector fast enough to serve?

```
venv-rag/bin/python scripts/rag_query_latency.py \
    --gold-set app/domains/conocimiento/eval/gold_set.yaml \
    --device cpu --threads 2 \
    --json artifacts/rag/latencia-box.json
```

`--threads` is explicit because `torch.set_num_threads` dominates this
measurement and leaving it implicit makes two runs on the same machine disagree.
The JSON is what `scripts/rag_eval.py --latencia` renders into the report; without
it the report states that the latency criterion was **not evaluated** rather than
inventing one.

**Sidecar RAM and cold start.** The model is ~2.2 GB on disk and the resident set
is estimated at ~2.2 GB. The box is already carrying Postgres, Redis, two uvicorn
workers, geo-worker and Martin. **"It fits" is an assumption until `docker stats`
says so**, and the measurement includes time-to-first-embed from a cold
container:

```
docker compose down conocimiento-embed && docker volume rm consorcio-conocimiento-embed-cache
docker compose up -d conocimiento-embed
docker stats --no-stream consorcio-conocimiento-embed
# then time the first successful /ready
```

Note that clearing the cache volume measures the *worst* cold start — the
download included. Time the second one too: with the volume warm, that is the
cold start a reboot actually pays.

### 4.2 The eval runs (U9 harnesses)

These harnesses **refuse without real runs behind them**, and this runbook does
not work around that refusal. What it does is name how the runs are produced.

**Retrieval, with the `bm25_ce` arm published beside the recorded FTS-only
baselines:**

```
venv-rag/bin/python scripts/rag_eval.py \
    --corpus-sha 12043582bf8016288a7e8084e85a4b713a97af2f \
    --database-url "$DATABASE_URL" \
    --modo fts --modo bm25_ce \
    --reranker bge --reranker-device cuda \
    --latencia artifacts/rag/latencia-box.json
```

`--reranker deterministic` exists for smoke runs **only**: in `bm25_ce` the order
is the cross-encoder's alone, so a stand-in replaces the ranking entirely — the
report it writes carries no verdict and its filename says `SINTETICO`.

**Answer-level grading.** `app/domains/conocimiento/eval/answer_set.yaml` ships as
a shell, `estado: BORRADOR`, deliberately carrying **no answers**. The answers are
produced by running the ratified questions through the **real serving path on the
GPU worker** — real BM25, real `bge-reranker-v2-m3`, the pinned provider — and
then the owner grades every claim. `eval/answers.py` loads, checks and scores what
comes back; **it never writes it.** Once the set is graded and its `estado`
starts with `RATIFICADO`:

```
venv-rag/bin/python scripts/rag_eval.py \
    --corpus-sha 12043582bf8016288a7e8084e85a4b713a97af2f \
    --database-url "$DATABASE_URL" \
    --modo bm25_ce --reranker bge \
    --answer-set app/domains/conocimiento/eval/answer_set.yaml \
    --provider-model-pin deepseek-v4-flash
```

The three pins `(prompt_version, provider_model_pin, corpus_sha)` are compared at
the CLI edge, before the database is opened. On divergence the harness refuses,
names both operands, and says the fix is a **re-grade — never a re-scoring**.

**SLM bench (the ladder's first rung).** Two graded arms over the SAME answers,
same prompt, same payloads, same graders. Both arms are REAL runs from the GPU
worker; the command compares them and **issues no verdict** — moving the provider
pin is the owner's call.

```
venv-rag/bin/python scripts/rag_eval.py \
    --corpus-sha 12043582bf8016288a7e8084e85a4b713a97af2f \
    --database-url "$DATABASE_URL" \
    --modo bm25_ce --reranker bge \
    --slm-bench app/domains/conocimiento/eval/slm_bench.yaml
```

Reports are written to `docs/rag/` (`--destino`).

### 4.3 The enablement gate — exactly what must be green before step 11

The flag is an **AND, not a switch**. Three of these facts are enforced in code
by `enforce_conocimiento_qa_enabled` and reported by
`GET /api/v2/conocimiento/estado`; the rest are the runbook's own and nothing
enforces them but this list.

**Enforced in code (all three must be true, in this order):**

| # | Fact | Field on `GET /estado` | If false |
|---|---|---|---|
| 1 | The provider **terms record** verifiably covers this `(modelo, pool)` pair | `terminos_verificados` | the surface refuses; `causa_no_listo` names it |
| 2 | The provider **credential** is present | `credencial_presente` | same |
| 3 | The sidecar's `/ready` is true | `embedder_listo` | `no_disponible` with cause `embedder_no_listo` |

**Not enforced in code — the operator's list:**

| # | Fact | Evidence |
|---|---|---|
| 4 | Migrations at head and objects present | step 6's probes; `alembic heads` = `conocimiento_007` |
| 5 | Step 8 exits **0** — all 35 rows match in class and evidence | `scripts/rag_verificar_clasificacion.py` |
| 6 | Retrieval bars cleared on the ratified arm, published beside the recorded FTS-only baselines `0.138` / `0.091` / `0.040` | the `rag_eval.py` report |
| 7 | The answer set is `RATIFICADO` and scored — invented-citation `0.00`, uncited-claim `0.00`, contradicted-claim `0.00` | the answer-level block of the report |
| 8 | **Abstention policy (open question 0.1) decided by the owner** | until then U9's abstention row is `not-evaluable` **and the surface is not enabled** |
| 9 | `CONOCIMIENTO_QUOTA_DIARIA_USUARIO` and `CONOCIMIENTO_SPEND_CEILING_USD` set to real values | both ship as `0`, blocked on the A2 cost re-derivation |
| 10 | The **worker is running** — §0.2 deployed, not started by hand | `GET /estado`: `ultima_corrida_worker` recent, `worker_demorado` false |
| 11 | Box measurements taken (§4.1) | `artifacts/rag/latencia-box.json` and the `docker stats` record |
| 12 | The **abstention-threshold artifact belongs to the snapshot about to be served** | the header of `app/domains/conocimiento/eval/umbral_abstencion.yaml` against `rag_corpus`'s provenance row — the pre-flight below |

**Fact 12 is a pre-flight precisely so it is not a post-mortem.**
`service.verificar_umbral_abstencion` reads that artifact **per retrieval**, and
a `derivado` threshold whose `corpus_sha`, `embedding_modelo` or
`embedding_revision_hf` does not match the active snapshot raises
`UmbralAbstencionNoCorresponde` — a `CorpusNoServible`, which the worker turns
into `no_disponible` and the synchronous surface into `503
base_de_conocimiento_no_lista`. Discovering that *after* step 11 means every
question a CD member asks comes back refused with nothing else having changed.
Read both operands before flipping the flag:

```
docker compose exec backend python -c \
  "from app.domains.conocimiento.eval.umbral_abstencion import cargar_umbral as c; u=c(); print(u.estado, u.corpus_sha, u.embedding_modelo, u.embedding_revision_hf, u.umbral)"
docker compose exec postgres psql -U consorcio -d consorcio -c \
  "SELECT embedding_modelo, embedding_revision_hf, embedding_sintetico FROM rag_corpus WHERE corpus_sha = '12043582bf8016288a7e8084e85a4b713a97af2f';"
```

**What passes:** `estado: no_derivado` — the shipped state today, while owner
decision 0.1 is open — passes **silently and by design**: there is no number, so
nothing can be served against the wrong one. **What must match:** if the
artifact ever reads `derivado`, all three of its pins must equal the row above,
and `cargar_umbral` additionally refuses a `derivado` artifact whose header is
incomplete, because `None == None` against a snapshot with absent provenance is
a vacuous pass. This pre-flight *confirms* which of the two states the box is in;
it does not assume the shipped one.

**Fact 8 is a stop, not a caveat.** The owner explicitly deferred the abstention
policy: reranker confidence is a measurably worse signal than cosine, and the two
options — relaxing recall to ≥ 0.90, or building a different signal — are a
decision no task may make on the owner's behalf.

---

## Section 5 — what this runbook does not do

* It does not set the router's numeric bar. That is fixed only **after** measuring
  on the ratified labeled set (amendment A4); a bar set before measuring is a bar
  set to whatever the system already does.
* It does not re-chunk the 10 oversized units (follow-up F1), grow the gold set
  (F2), or replace the `require_admin` approximation with a real Comisión
  Directiva role (F3). All three are explicitly outside the apply gate.
* It does not quote a single measured figure, for the reason at the top of this
  file.
