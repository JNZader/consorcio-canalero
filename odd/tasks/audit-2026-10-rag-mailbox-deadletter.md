# audit-2026-10-rag-mailbox-deadletter

Bounded per-item crash counter for the RAG QA mailbox, fixing audit finding
RAG-5 (WARNING, 2026-10, still open): an unnamed exception on the OLDEST queued
item crash-looped the worker forever. `rag_worker.bucle`'s deliberate
`except BaseException: rollback; raise` ("bugs are loud") plus
`buzon.reclamar_pendiente`'s equally deliberate no-intermediate-state claim plus
systemd `Restart=always RestartSec=10` meant: crash → rollback → restart →
reclaim the SAME oldest item → crash, every ~10 s, zero queue progress, the only
signal `worker_demorado` on `GET /estado`, manual SQL the only unwedge. The
crash-does-not-stick property was correct; the failure was blast radius. Scope =
capping that blast radius without softening the crash.

## In

- [x] Storage: one INTEGER column, `rag_consulta.caidas_worker` (NOT NULL,
  server default 0, CHECK `>= 0`), via new Alembic revision
  **`conocimiento_008`** (`app/db/migrations/versions/conocimiento_008_caidas_worker.py`).
  A column and not a sidecar because the crash rolls back the item's whole
  transaction — only a write from OUTSIDE that transaction survives, and the
  row is the only place whose lifetime matches the item's. `conocimiento_007`
  was NOT the tip to chain onto: `lluvia_ext_001` had already chained there and
  the tree's verified single head is `0033_one_way_profile`, so 008 revises
  that (same cross-domain chaining discipline 005 documented; forking the tree
  is the outage 005's docstring records). `alembic heads` now reports
  `conocimiento_008 (head)`, single head.
- [x] `buzon.registrar_caida(db, item_id, *, causa, max_caidas=MAX_CAIDAS_WORKER)`:
  locks the row `FOR UPDATE SKIP LOCKED` (a dying process must not wait behind
  a live worker); no-ops if the item is gone, terminal (another worker finished
  it), or currently locked; otherwise increments, and at
  `buzon.MAX_CAIDAS_WORKER` (**3**) terminalizes to `generacion_fallida` through
  the normal `persistir_resultado` — no seventh state, the 007 coupling CHECKs
  untouched. The `motivo` follows generacion.py's convention and is honest:
  `caidas_worker: 3 caídas del worker al procesar este ítem (límite 3); última
  causa KeyError: 'bug'` (counts the attempts, names the last cause).
- [x] The counter increments ONLY on worker crash paths. `trabajador.procesar_uno`
  gained an `al_reclamar` callback (fired right after the claim, before anything
  can raise — in memory, the only place that survives the rollback);
  `rag_worker.bucle` gained `al_caer` (called in the `BaseException` handler
  after rollback+close, before the re-raise); `rag_worker.ContadorDeCaidas`
  binds the two: it commits the count from a separate session, logs every crash
  at ERROR with item id + count + cause, and logs the terminalization at
  CRITICAL naming the item and stating the bug is still live. Clean generation
  failures — including state-machine `generacion_fallida` — never touch the
  counter. `main()` wires the accountant into the real loop.
- [x] "Bugs are loud" preserved verbatim: every crash still propagates (each
  cycle of the wedge test asserts the `KeyError` re-raised), the traceback still
  hits journald, the process still exits non-zero, systemd still restarts. An
  accountant failure is logged CRITICAL and never masks the original exception.
- [x] Claim interaction: none needed and that is the point — a dead-lettered
  item is `generacion_fallida`, so `reclamar_pendiente`'s existing
  `estado = 'pendiente'` filter + `creada_en ASC` ordering skip it and take the
  next oldest non-terminal item. Pinned by test.
- [x] Tests (RED→GREEN): the wedge scenario was first reproduced on unfixed
  code (RED verbatim: `AssertionError: RED RAG-5: tras 3 caídas el ítem
  venenoso sigue 'pendiente' — el worker reclama el mismo ítem para siempre y la
  cola no avanza`), then locked down as
  `test_rag_worker.py::TestElItemVenenosoNoWedgeaLaCola` (real Postgres, real
  `bucle`, committed rows: 3 crash/restart cycles terminalize the poison item
  with the honest motivo, every cycle still raises, the next claim processes
  the following item, queue drains, CRITICAL log names the item). Plus: clean
  `generacion_fallida` and clean `respuesta` leave `caidas_worker` at 0;
  fresh items are born at 0; terminal/missing/locked items are not counted;
  the `al_reclamar` seam fires exactly on claim and never on an empty queue;
  migration 008 shape (column, default 0, CHECK, downgrade drops column+check
  and nothing else) on a throwaway database.
- [x] Runbook (`docs/rag/runbook-encendido.md`): step 6's revision enumeration
  updated — the ceremony's `alembic upgrade head` from the box's
  `conocimiento_004` now ends at `conocimiento_008`. Note: the task brief
  expected "6 → 7 revisions", but the runbook's "six" was already stale —
  `lluvia_ext_001`…`006`, the `0024`…`0033` canal/caminos chain and two `zz_*`
  migrations chained above `conocimiento_007` after the runbook was written.
  The real walk is now 25 revisions; step 6 says so, groups the non-RAG rows
  into one table row (same rule rows 1–3 set for `flujo-caminos`), points at
  `alembic history -r conocimiento_004:head` as the authoritative list, and the
  `alembic heads` expectations (step 6 and §4.3 fact 4) now say
  `conocimiento_008`. §0.2's worker section documents the dead-letter
  behaviour.

## Out

- Fixing the stale `truncado_dos_veces` wording the audit also flagged in
  `generacion.py` — separate finding, deliberately not touched here.
- Any retry/backoff policy for crashed items, any re-queue tooling, any
  operator-facing surface for `caidas_worker` beyond the item's own
  `respuesta.motivo` (the frontend renders `generacion_fallida` items
  unchanged).
- Making `MAX_CAIDAS_WORKER` a configuration knob — it is a constant because
  its value is a claim about how many crashes are signal; a knob would let an
  operator tune the signal away under load instead of fixing the bug the
  crashes name.
- Re-enumerating every migration in the runbook's step 6 table individually
  (the non-RAG arcs get one grouped row; `alembic history` remains the census).
