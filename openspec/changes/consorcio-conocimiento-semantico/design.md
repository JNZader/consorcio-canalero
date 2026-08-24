# Design: Conocimiento Semántico V1 — Cited Legal Q&A for the Comisión Directiva

## Technical Approach

V1 adds three layers **above** the V0 retrieval core, plus one piece of infrastructure V0 never needed
because it never served a query. The core is **nearly** untouched, and the exceptions are named rather than
glossed: `recuperar` accepts a precomputed query vector (G1), `verificar_embedder` starts comparing the HF
revision as well as the model id (G0), and `documento_row_from_frontmatter` derives `clasificacion` instead of
hardcoding it (G2a). Everything else in the retrieval path is exactly V0's.

```
question ─► [embed ONCE via sidecar] ─► qvec ──────────────────┐
                     │ sidecar down → no_disponible            │ (same vector,
                     ▼                                         │  never re-embedded)
             [G1 router: rules → BGE-M3 centroid]──► redirect (no retrieval, no generation)
                     │ legal | mixto(legal part)                │
                     ▼                                          ▼
             service.recuperar (qvec passed in) ──► refusals: EmbeddingsNoCargadas /
                     │                                  EmbedderMismatch / VectorSupportUnavailable
                     │                                  (service.py:269-288, 291-334) → 503, never prose
                     ▼
             AbstentionPolicy (D5, unchanged) ──► abstención explícita
                     │ above threshold
                     ▼
             [G2a per-unit privacy exclusion] ─► payload ⊆ retrieved set
                     │ payload empty → abstención (never a whole-request refusal)
                     ▼
             [G2b generación] → [G3 verificación mecánica contra el PAYLOAD]
                     │
                     └─► serve | regenerate ×1 | abstain | generacion_fallida
```

The unstated blocker: **the server image cannot embed a query today**. `requirements-rag.txt:1-9` states torch
"jamás para la imagen del servidor", the V0 JD amendment (archive design D8, RJDA-101) asserts by test that
`torch`/`transformers`/`FlagEmbedding` appear in none of `requirements.txt`, `requirements.lock`,
`requirements-dev.lock`, and the vector leg needs `embedder.encode([pregunta])` (`service.py:342`). No
generation decision matters until that is solved.

## Architecture Decisions

### G0 — Query embedding at serving time: a sidecar, not the app image

| Option | Tradeoff | Verdict |
|---|---|---|
| **BGE-M3 sidecar container** (`conocimiento-embed`), single process, model loaded once, `POST /embed` | New service to run on the box; ~2.2 GB RSS resident; one internal hop | **CHOSEN** |
| torch in the server image | Breaks the D8 guard test by design, ~2 GB image growth, and `app/server.py` runs 2 uvicorn workers → 2 model copies | Rejected |
| Hosted embedding API for the query | `openspec/specs/knowledge-hybrid-retrieval/spec.md:121` bans it as the production embedding path, and the ratified amendment keeps it banned — it permits hosted GENERATION only, "embeddings and question routing remain LOCAL" (retrieval delta:131-133); a non-BGE-M3 vector is refused by `verificar_embedder` (`service.py:281-288`) anyway | Rejected |

House precedent exists: `geo-worker` is exactly this shape (`docker-compose.yml:300-304`, consumed via
`settings.geo_worker_tile_url`, `config.py:88`). New setting `conocimiento_embed_url`.

**Rule (mechanical, not conventional):** the sidecar reports the loaded model's `modelo` **and** its HF
`revision_hf` as two separate fields, and the backend adapter carries **both** verbatim into the `Embedder`
seam — `Embedder.model_id` and `Embedder.revision`, which the Protocol already declares
(`embedding.py:265-266`). Hardcoding `"BAAI/bge-m3"` in the adapter would defeat `verificar_embedder`
(`service.py:259-288`), which exists because a model mismatch has no symptom at the query surface — the
reasoning is written out in the `EmbedderMismatch` docstring at `service.py:203-218`. *(Anchor corrected,
bounded correction 2026-08-23: round 1 cited `:203-218` for the function itself; that range is the exception
class, and the function is at `:259-288`.)*

**Revision comparison is normalized to the RESOLVED commit hash on both sides, and this is not optional.**
*(Bounded correction, 2026-08-23.)* `BGEM3Embedder.__init__` ends with
`self.revision = revision or getattr(self._model.config, "_commit_hash", None)` (`embedding.py:372`), so what
the seam reports depends on how the model was constructed: with `revision=None` it reports the **resolved
40-hex commit hash** transformers recorded on the config; with `revision="<tag-or-branch>"` it reports the
**symbolic string it was handed**. The offline O.3 batch and the serving sidecar are constructed by different
operators at different times, so the realistic case is a manifest stamped with a hash and a sidecar started
from `EMBED_REVISION_HF=<tag>`. Under a raw tuple comparison those differ, `EmbedderMismatch` fires on two
processes running the *same weights*, and the surface serves a permanent `503` that no amount of re-loading
fixes — the failure mode is indistinguishable at the query surface from the real mismatch the guard exists
for, which is the worst possible shape for a guard.

The canonicalization rule, applied before the tuple comparison, on **both** operands:

1. the compared value is always the **resolved commit hash**: lowercased, 40 hex characters;
2. a symbolic ref (tag, branch, `main`) is **resolved to its hash at load time** and never compared as a
   string. Concretely, `embedding.py:373` inverts its precedence — the config's `_commit_hash` wins over the
   symbolic argument, and the argument survives only as the *requested* pin recorded next to it — and the
   sidecar reports the resolved value in `revision_hf`, so the env var is an input, never the report;
3. a value that is not a 40-hex hash after resolution is **unknown provenance**, and the guard refuses with
   `EmbedderMismatch` naming it verbatim. It never falls back to string-comparing tags, because two different
   commits can both be tagged `main` and a tag comparison would pass them;
4. `NULL == NULL` keeps its one deliberate exemption for `DeterministicEmbedder` (`embedding.py:304`),
   unchanged — a synthetic embedder resolves to no hash by construction.

This is the same discipline as the corpus pin: `verify_corpus_pin` (`service.py:96-119`) compares a resolved
`git rev-parse HEAD` against the declared SHA, not a branch name against a branch name.

**The identity guard is extended, because today it closes only half the door.** `verificar_embedder`
(`service.py:259-288`) compares `procedencia.modelo != embedder.model_id` and stops there — but
`ProcedenciaEmbeddings` already carries `revision_hf` (`repository.py:599-604`, selected by
`LEER_PROCEDENCIA_SQL` at `:611-618`) and `VectorsManifest` already stamps it (`embedding.py:201-214`). Two
BGE-M3 revisions report the same `model_id` and produce different vectors; the symptom is again a confident,
meaningless ranking. V1 therefore adds a second, explicit comparison in the same function: `procedencia.revision_hf`
vs `embedder.revision`, raising `EmbedderMismatch` with both operands named. Written as one tuple check
(`(procedencia.modelo, procedencia.revision_hf) != (embedder.model_id, embedder.revision)`) so a future field
cannot be added to one side only.

*Compatibility of stored `procedencia`:* rows loaded before the sidecar exists may hold `revision_hf IS NULL`.
A NULL recorded revision is **not** treated as "matches anything" — that would restore the hole. It is treated
as *unknown provenance*: the query is refused with `EmbedderMismatch` naming the NULL, and the fix is a
re-load of a manifest that carries the revision. The one deliberate exemption is `DeterministicEmbedder`, whose
`revision` is `None` by construction (`embedding.py:304`) and whose artifacts stamp `revision_hf: null` — NULL
on both sides is a match, NULL on one side is not. This is also what handles **version skew across re-ingest**:
a re-embed under a different HF revision fails the guard at the first query instead of ranking quietly.

Query latency on the box is **unmeasured** (proposal risk row; `scripts/rag_query_latency.py` exists for it).
The vector leg itself is measured at ~11 ms (archive design D4 `EXPLAIN`). Measurement is a task, not an
assumption. **Two measurement tasks, both before enablement, both on the box, not on the workstation:**

1. CPU query-embedding latency (`scripts/rag_query_latency.py`) — feeds the end-to-end budget in G3.
2. Sidecar **RAM and cold-start** feasibility. The model is ~2.2 GB on disk and the process resident set is
   estimated ~2.2 GB; the CX33 is 2 shared vCPU and its memory is already carrying Postgres, Redis, the two
   uvicorn workers, geo-worker and Martin. "It fits" is an assumption until `docker stats` says so under a
   real query, and the measurement includes time-to-first-embed from a cold container.

**Cold start is a state, not a wait.** The sidecar exposes `GET /health` (process alive) and `GET /ready`
(model loaded and one warm-up embed completed). Until `/ready` is true the surface returns `no_disponible`
with cause `embedder_no_listo` — it never blocks the request thread waiting for a 30–60 s model load, and it
never routes or abstains on the strength of an embedder that has not loaded.

**The sidecar image gets its own pinned lock, not `requirements-rag.txt`.** That file is a range spec
(`torch>=2.0.0`, `transformers>=4.40.0`, `FlagEmbedding>=1.2.0`) and it also pulls `sentence-transformers`,
which exists there only for the E5 baseline (`requirements-rag.txt:23-33`) and has no business in a serving
container. A serving image whose torch version floats is a serving image whose vectors can change on rebuild —
which is precisely what the provenance guard exists to catch, and catching it in production is the expensive
place. So: `docker/embed/requirements-embed.lock`, fully pinned with hashes in the house
`--require-hashes` style, `torch` CPU wheel only, no `sentence-transformers`.

### G1 — Router: rule-first, then a local centroid over the query vector we already compute

| Option | Tradeoff | Verdict |
|---|---|---|
| **Rules → BGE-M3 centroid (local, zero extra model)** | Needs the owner-ratified labeled set; centroids must be LOOCV-scored or they are fitted on the scoring sample | **CHOSEN** |
| Hosted-LLM classifier | Sends **CD-authored question text** to an external provider on every query — collides with `spec.md:119-121` and adds cost/latency before we even know the question is legal | Rejected |
| Rules only | Cannot separate `mixto`, and confidence is not measurable, so "bias toward redirect under doubt" (routing spec:72-81) has no signal to threshold | Rejected |

Stage 1 is a deterministic lexicon over operational/geospatial markers (deuda/cuota/saldo, trámite,
expediente, denuncia, "¿dónde…?", canal N°, coordinates, a padrón-shaped person name). Stage 2 embeds the
question through the same sidecar and scores cosine against per-class centroids built from the labeled set;
the **margin** between the best and second-best class is the confidence. Below the calibrated margin →
redirect. `mixto` produces **one** response carrying both an answer block and a redirect block
(routing spec:53-63), never two responses.

**One question, one embedding.** Stage 2 and the retrieval vector leg need the *same* vector of the *same*
text under the *same* model. Embedding twice costs a second sidecar hop on the critical path and, worse,
creates a state where the router classified one vector and retrieval searched another. So the query vector is
computed **once**, at the top of the request, and threaded down. `service.recuperar` is therefore **not**
unchanged (an earlier draft of this design claimed it was): it gains one optional keyword-only parameter,

```python
def recuperar(..., embedder: Embedder | None = None, qvec: Sequence[float] | None = None, ...)
```

with the rule that `qvec` does not bypass a single guard — `require_vector_support` and `verificar_embedder`
still run, and `embedder` is still required when `modo` uses the vector leg, because the identity that
`verificar_embedder` compares lives on the embedder, not on the vector. The only behaviour change is at
`service.py:340-343`: `(qvec,) = embedder.encode([pregunta])` becomes "use the caller's vector if it supplied
one, otherwise embed". Passing `qvec` computed by a *different* embedder than the one handed in is a caller
bug the guard cannot see; the single call site in the V1 router builds both from the same adapter instance.

**`mixto` has its own signature and is exempt from the doubt-redirect.** A `mixto` question is geometrically
*supposed* to sit between two centroids — its margin is small by construction, so a bare
`margin < umbral → redirect` rule turns every correctly-recognized mixed question into a redirect and the
`mixto` class becomes unreachable in practice. The dedicated rule: if the top-2 classes are exactly
`{legal, operational}` (or `{legal, geoespacial}`) **and** their two scores lie within the margin band **and**
both clear an absolute cosine floor, the outcome is `mixto` — one response with both blocks. Doubt that is
*not* of this shape (a low absolute score, or a top-2 that does not include `legal`) still redirects, per
routing spec:72-81. Both the band and the floor are calibrated on the labeled set by the same LOOCV
discipline, never hand-set.

Threshold calibration reuses D5's discipline verbatim: LOOCV over the labeled set, shipped threshold from
the full set, both published, same-sample figures labeled `upper bound`.

**Numeric bar, proposed for owner ratification** (the routing spec mandates a confusion matrix but sets no
number, which is a gate with no bar):

| Figure | Proposed bar | Why this one |
|---|---|---|
| `operational → legal` cell | **≤ 0.05** | This is the cell that fabricates an answer about a real person's debt. It is the only asymmetric bar. |
| overall accuracy | **≥ 0.85** | On a labeled set of **n ≥ 40** with a **floor of 10 items per class**, so the four-class matrix has cells rather than anecdotes. |
| `legal → operational` | not barred | Its failure mode is an unnecessary redirect: annoying, not dangerous. Barring it would trade a safe error for an unsafe one. |

Below the bar the router does not ship — and the fallback is *not* "ship it anyway with a higher margin",
it is stage-1-rules-only with everything ambiguous redirected, which is measurably worse at `mixto` and
honestly so.

**Runtime observability: the record stores the question VERBATIM.** Routing spec:85 and its scenario at
:94-98 require that the record show "the question, the class assigned and the confidence" — a hash satisfies
none of that, because reconstructing a question from its hash is the thing hashes exist to prevent. The record
is `(pregunta, clase, margen, umbral_vigente, ts)` and it lives in **the box's own Postgres**. That is not a
privacy regression and does not touch the Privacy Boundary: the boundary governs what leaves the deployment,
and an internal table is not an external service. Constraints, stated so they are enforced rather than
assumed: the record never leaves the deployment, never enters an eval payload or a generation payload, is
readable only through an admin surface behind `require_admin`, and is retained on a bounded window
(proposed 90 days) rather than forever. The confusion matrix names the `operational → legal` cell explicitly.

**Sidecar unavailability is never a routing decision.** If stage 2 cannot embed — sidecar unreachable, not
`/ready`, timing out, or returning a malformed vector — the request ends in `no_disponible` with the cause
named. It does **not** fall back to stage-1 rules and answer, and it does **not** redirect: a redirect is a
*classification claim* ("this is operational, go to /finanzas"), and claiming it because a container is down
is a fabricated classification. See G4 for where liveness is checked first.

### G2 — Generation provider: hosted API, under the RATIFIED privacy amendment

The box is CPU-only, 2 shared vCPU (explore.md:105; archive design D3 "the CX33 is CPU-only"). A 7–8B local
model there produces a 400-token answer in **minutes** (estimate, not measured — no serving hardware exists
to measure on); a 1–3B model that would fit the latency budget is the wrong tool for a `0.00`
invented-citation bar. The owner's RTX 5060 Ti is a workstation used for the offline batch (O.3), not a
serving host with uptime.

So the only viable provider is a **hosted API** (the repo has no LLM client today — verified: no
`anthropic`/`openai` import anywhere in `gee-backend/app/`). Honest numbers:

| | Hosted API (Claude-class) | Local on the box |
|---|---|---|
| Latency / query | **estimate** 3–8 s for ~8 k input + ~500 output tokens | **estimate** 2–7 min; unusable |
| Cost / query | **estimate** ≈ USD 0.03–0.05 at published list prices — re-derive at implementation, do not trust this line | ~0 marginal, plus the app's own latency degrading under load |
| Verdict | **CHOSEN, gated** | Rejected |

**The gate is not optional, and it was the biggest finding of this design. It is now RATIFIED, not
pending.** The owner ratified the Privacy Boundary amendment on **2026-08-23**; it is written into
`specs/knowledge-hybrid-retrieval/spec.md:129-173` of this change, with its five scenarios. What follows is
the mechanical shape V1 must build to satisfy it — not a request for permission.

The amendment's semantics, restated exactly because a paraphrase here is how a gate drifts:

- classification is **derived from corpus frontmatter, never hardcoded**;
- every retrieved unit in the generation payload must **individually** verify, at request time
  (`assert_unidades_publicas`), that its `clasificacion` is in the **shippable set** — *(bounded correction,
  2026-08-23: the shippable set is `{publico, institucional}`, per the owner's sealed product decision of the
  same date; round 1 read it as `{publico}` alone. See G2a for the three-class derivation and for why
  `institucional` — the consorcio's own normative instruments — is shippable while every fuente secundaria is
  not.)*;
- a non-shippable unit in the retrieval set is **EXCLUDED from the payload** — it is not a whole-request
  refusal, and it is not grounds for widening the retrieval;
- if exclusion leaves the context **empty**, the system **abstains** with the honest no-answer state rather
  than calling the provider;
- the question text travels to the generation provider **only** — never to an embedding, routing or judge
  service.

This is deliberately *not* `assert_public_domain`'s semantics. That function (`eval/privacy.py:65-93`) refuses
the WHOLE snapshot if a single document is non-public, and its docstring explains why that is right for a
*baseline*: a baseline computed over a filtered corpus is compared against a corpus it was not computed over.
A served answer has no such symmetry requirement — it is grounded in whatever units it actually cites — so
per-unit exclusion is correct here and snapshot-refusal is not. Both live side by side, they do not replace
each other, and `test_rag_privacy.py` keeps asserting the snapshot semantics for the eval baseline.

*(Bounded correction, 2026-08-23 — the two gates do not share a set, and that is deliberate.)*
`assert_public_domain` keeps comparing against `publico` **only** (`eval/privacy.py:40-46`, `:65-93`): the
optional API-embedding comparison baseline is bounded by the retrieval spec to "the current public-domain
(SAIJ/BO-sourced) corpus text", and an `institucional` document is not that — it is a consorcio instrument the
owner cleared for the *answer* path, not for a corpus-wide comparison against a third-party embedding service.
So a snapshot containing the `institucional` document keeps failing `assert_public_domain`, the API baseline
stays unreachable in practice, and that is the correct outcome rather than a bug to fix. The serving gate
`assert_unidades_publicas` is the one that admits `{publico, institucional}`, per unit, per request. Two
questions, two sets, one place each.

#### G2a — `clasificacion` derived at INGEST time, from provenance already in the frontmatter

*(REDESIGNED — bounded correction, 2026-08-23, under the owner's sealed product decision of the same date:
what may travel to the hosted provider is **published public law** (gazette/registry-sourced) **and the
consorcio's own normative instruments**. Technical reports and every other fuente secundaria stay private.
Round 1 shipped a single binary `publico`/`privado` rule whose only promotion path was a gazette host; it
classified the consorcio's own constitutive act as `privado` and made gold items C-1 and C-8 — both of which
cite `10demayo#res…` units — unanswerable by construction. That is fixed here, and the fix is a widening of
the shippable set, so it is stated with its full consequence list rather than as a knob turn.)*

`repository.py:164-166` hard-codes `"clasificacion": "privado"` for every ingested document with a comment
saying nothing promotes one. V1 replaces that hardcode with a **deterministic three-class rule over
frontmatter keys that already exist**, evaluated inside `documento_row_from_frontmatter` (a pure function — no
DB, no network, and therefore fully unit-testable). The three classes are evaluated **in this order**, and the
order is load-bearing:

```
privado        ⇔  es_secundaria is True                      # evaluated FIRST — see below
institucional  ⇔  es_secundaria is False
                  AND tipo ∈ TIPOS_INSTITUCIONALES           # the consorcio's own normative instruments
publico        ⇔  es_secundaria is False
                  AND at least one `fuente_url` entry's host # published by an official gazette/registry
                      matches FUENTES_PUBLICAS
privado        ⇔  everything else                            # default-deny survives, unchanged
```

**`es_secundaria` is not a frontmatter key — it is derived from `tipo`** by `es_secundaria_for`
(`repository.py:87-103`) against the two checked-in vocabularies `TIPOS_SECUNDARIOS` (`:44-52`) and
`TIPOS_DERECHO_APLICABLE` (`:54-66`), and an unknown `tipo` raises rather than defaulting. So the whole
classification rests on vocabularies that already exist and already refuse to guess; it invents no new
frontmatter contract and requires no corpus edit.

**Why the secundaria test runs first.** It makes the host allowlist unreachable for a fuente secundaria, which
is what closes the `fuente_url` key-naming gap: `informe-f3-fragmento.md` has **no `fuente_url` key at all**,
and carries eleven official-looking hosts (`legislaturacba.gob.ar`, `www.cba.gov.ar`, `argentina.gob.ar`,
`faolex.fao.org`, three press outlets…) under a *different* key, `fuentes_externas_verificadas`
(`informe-f3-fragmento.md:19-30`). **Only `fuente_url` is consulted; no other key is.** That is safe here
precisely because of the ordering: `informe-operativo` ∈ `TIPOS_SECUNDARIOS`, so the document is `privado`
before any host is looked at, and would remain `privado` even if someone later renamed the key. Consulting
`fuentes_externas_verificadas` would be actively wrong anyway — its entries are the sources an analyst
*consulted while writing a report*, including press, and a press URL is not a publication of the document.
The rule therefore reads exactly one key, and the reason it can afford to is stated rather than assumed.

**`TIPOS_INSTITUCIONALES` is an explicit subset of `TIPOS_DERECHO_APLICABLE`, pinned, not intersected with a
jurisdiction.** The owner decision names *estatuto, resoluciones del Consejo Directivo, registro
administrativo*. Verified against the 11 checked-in fixtures — `corpus_expectations.yaml` records no `jurisdiccion` key, so the other 24 documents are unverifiable in-repo, consistent with the derivability note below *(scoped verification, 2026-08-23)*: **no fixture `jurisdiccion` value identifies the consorcio.** Every value
is a territorial one — `Córdoba`, `Córdoba, Argentina`, and for `consorcio-10-de-mayo` the string
`"Córdoba, Argentina — Departamento Unión (≈83% del ámbito) y Departamento Marcos Juárez (≈17%)"`. So an
a `jurisdiccion = consorcio` intersection is **not derivable** and is not used; the set is written out:

```
TIPOS_INSTITUCIONALES = {"registro-administrativo"}      # today, the whole set
```

`registro-administrativo` is the only `tipo` in the existing vocabulary that carries the consorcio's own
constitutive instruments; it is the `tipo` of `consorcio-10-de-mayo-registro-aprhi`, the document that holds
Res. SRHyC 189/2014 (the act that creates the consorcio) and Res. Gral. APRHI 005/2026 (its current
authorities). `estatuto` and a consorcio-resolution `tipo` **do not exist in this corpus** — neither appears
in `TIPOS_DERECHO_APLICABLE` nor in any of the 35 documents — so they are not pre-added. When such a `tipo` is
introduced it must be added to `TIPOS_DERECHO_APLICABLE` *and* to `TIPOS_INSTITUCIONALES` in the same reviewed
diff, which is exactly the explicit-registration discipline `es_secundaria_for` already enforces.

**`resolucion-administrativa` is deliberately NOT institucional.** That `tipo` covers provincial-authority
acts — DIPAS 395/2004, DPH 11821/1985, APRHI 3/2026 and 004/2026 — which are neither the consorcio's own
instruments nor, in several cases, gazette-published. Blanket-promoting the `tipo` would ship a Drive-scanned
provincial resolution to the provider on the strength of a category name. Those documents reach `publico` only
through the host rule, on their own evidence, or stay `privado`.

**Host matching semantics, pinned to one rule.** An allowlist entry `E` matches a URL host `H` iff
`H == E` **or** `H.endswith("." + E)` — a **label-boundary suffix match** on the lowercased, port-stripped,
IDNA-decoded host. Nothing else. This admits `www.saij.gob.ar` under the entry `saij.gob.ar` and
`gld.legislaturacba.gob.ar` under `legislaturacba.gob.ar`, and rejects `saij.gob.ar.evil.example` (which does
not end in `.saij.gob.ar`) and `notsaij.gob.ar` (no label boundary). It is **not** a registrable-suffix /
public-suffix computation: no PSL dependency, no DNS, and each entry is written as the exact host beneath
which subdomains are admitted, so widening the allowlist is always a visible diff.

`FUENTES_PUBLICAS` is a checked-in, explicit host allowlist: `saij.gob.ar`, `boletinoficial.cba.gov.ar`,
`web2.cba.gov.ar`, `www.cba.gov.ar`, `legislaturacba.gob.ar`, `aprhi.gob.ar`, `infoleg.gob.ar`. Two entries
changed in this correction and both changes are the pinned rule applied honestly: `www.aprhi.gob.ar` becomes
`aprhi.gob.ar`, because the fixture host actually present is `www.aprhi.gob.ar`
(`normas-srh-2013-fragmento.md:10-11`) and the bare entry admits it under the suffix half of the rule while
the `www.`-prefixed entry would only have admitted `*.www.aprhi.gob.ar`; and `www.cba.gov.ar` stays
**narrow on purpose** — a bare `cba.gov.ar` entry would admit every provincial subdomain, including ones
nobody has looked at, so the wide entry is refused even though it would be shorter.

Nothing is inferred from prose: `verificacion` and `estado_vigencia` are free text in this corpus
(`ley-8548-fragmento.md` carries a full paragraph in `estado_vigencia`), and a regex over legal prose is
exactly the silent misclassification `repository.py:9-13` refuses to build.

What the rule yields on the checked-in fixtures, verified line by line against their actual frontmatter under
the pinned suffix rule, with the **matched host** named because a classification whose evidence is not
recorded cannot be audited:

| Fixture | `tipo` (→ `es_secundaria`) | Evidence consulted | Matched host / justification | Derived |
|---|---|---|---|---|
| `ley-9750` | `ley-provincial` (False) | `fuente_url` | `www.saij.gob.ar` ⊂ `saij.gob.ar`; also `boletinoficial.cba.gov.ar` | `publico` |
| `ley-10679` | `ley-provincial` (False) | `fuente_url` | `www.saij.gob.ar` ⊂ `saij.gob.ar`; also `boletinoficial.cba.gov.ar` | `publico` |
| `ley-8548` | `ley-provincial` (False) | `fuente_url` | `www.saij.gob.ar` ⊂ `saij.gob.ar`; also `web2.cba.gov.ar` | `publico` |
| `ley-8803` | `ley` → `ley-provincial` (False) | `fuente_url` | `www.saij.gob.ar` ⊂ `saij.gob.ar`; also `web2.cba.gov.ar` | `publico` |
| `decreto-318-2007` | `decreto` (False) | `fuente_url` | `www.saij.gob.ar` ⊂ `saij.gob.ar` — **both** entries are SAIJ; it carries **no** BO or `web2.cba.gov.ar` URL (round 1's table row claimed one; corrected) | `publico` |
| `ley-5589` | `ley-provincial` (False) | `fuente_url` | `www.cba.gov.ar` (exact entry match); also `web2.cba.gov.ar`, `boletinoficial.cba.gov.ar` | `publico` |
| `resolucion-4-2026` | `resolucion-ministerial` (False) | `fuente_url` | `web2.cba.gov.ar` (exact); also `boletinoficial.cba.gov.ar` | `publico` |
| `normas-srh-2013` | `norma-tecnica` (False) | `fuente_url` | `www.cba.gov.ar` (exact); also `www.aprhi.gob.ar` ⊂ `aprhi.gob.ar` | `publico` |
| `consorcio-10-de-mayo` | `registro-administrativo` (False) | `tipo` | `tipo ∈ TIPOS_INSTITUCIONALES` — the consorcio's own constitutive act; hosts are ArcGIS + Drive and match nothing | **`institucional`** |
| `resolucion-aprhi-004-2026` | `resolucion-administrativa` (False) | `fuente_url` | no match (`drive.google.com`, `services1.arcgis.com`, `hub.arcgis.com`); `tipo ∉ TIPOS_INSTITUCIONALES` | `privado` |
| `informe-f3` | `informe-operativo` (**True**) | — | secundaria; short-circuits before any host is read | `privado` |

Across the full 35-document corpus the class floors are known without reading the private repository, because
`corpus_expectations.yaml` carries every document's `tipo` and `es_secundaria`: **6 documents are
`es_secundaria: true`** (`auditoria-obras-zona-10-de-mayo`, `caso-testigo-tres-colonias-canal-santa-cecilia`,
`informe-f3-sujeto-expropiante`, `informe-zona-de-camino-cordoba`, `jurisprudencia-potrerillo-larreta-2017`,
`obra-tres-colonias-canal-santa-cecilia.kmz`) and are `privado` by the first clause; **1 document is
`registro-administrativo`** (`consorcio-10-de-mayo-registro-aprhi`) and is `institucional` by `tipo` alone;
the remaining **28** are decided by the host rule and cannot be settled from this repository, because
`corpus_expectations.yaml` records no `fuente_url`. That is precisely why the expected-classification artifact
below is generated against the pinned checkout rather than asserted here.

**A future `actas` layer is `privado` with no new code**, on the same first clause the reports land on, as
soon as its `tipo` is registered in `TIPOS_SECUNDARIOS` — and if it is registered as derecho aplicable
instead, it is `privado` anyway unless someone explicitly adds its `tipo` to `TIPOS_INSTITUCIONALES`, which is
a reviewed diff. Neither path promotes it silently.

**The expected-classification artifact, so this is falsifiable now.** `eval/expected_clasificacion.yaml` is
checked in and lists all **35** documents with, for each, its `documento_id`, `tipo`, derived `es_secundaria`,
expected `clasificacion`, and the **evidence string** — the matched host for `publico`, the literal
`tipo:registro-administrativo ∈ TIPOS_INSTITUCIONALES` for `institucional`, and either
`es_secundaria` or `sin host en FUENTES_PUBLICAS` for `privado`. It carries the pinned
`corpus_sha: 12043582bf8016288a7e8084e85a4b713a97af2f` in its header and is refused on divergence by the same
comparison discipline as `verificar_corpus_sha` (`harness.py:254-269`). It is **generated** by a script run
against the private corpus checkout at that SHA — the `publico` rows cannot be derived from this repository
alone — and then committed, so from that moment on it is a fixed expectation that CI and the runbook diff
against. Runbook step 8 diffs the reclassified `rag_documento` rows against it row by row instead of comparing
a single count, and the unit suite diffs the 11 checked-in fixtures against their rows in it, so a rule
regression fails in CI without a database.

**Change control.** Any edit to `FUENTES_PUBLICAS`, to `TIPOS_INSTITUCIONALES`, or to
`expected_clasificacion.yaml` requires explicit owner sign-off recorded in the PR that makes it. These three
artifacts *are* the privacy boundary in executable form; a quiet one-line addition to any of them ships a
document to a third party, which is not a refactor.

**Auditability at the row level.** `rag_documento` gains a nullable `clasificacion_evidencia` column holding
that same evidence string, written by ingest alongside `clasificacion`. Without it, "why is this document
public?" is answerable only by re-running the rule against a corpus checkout that the box may not have; with
it, the answer is a `SELECT`. It is evidence, never an input: nothing reads it back to decide anything.

**This changes zero bytes in the corpus repository.** The rule reads frontmatter that is already there, so
`corpus_sha` does not move, the gold set's `corpus_sha` pin (`harness.py:254-269`) stays valid, and no
frozen-SHA collision is created. What *does* change is the 35 rows already in `rag_documento`, whose
`clasificacion` was written as `privado` by the old hardcode. Reclassifying them is **not** a data migration
and not a hand-written `UPDATE`: it is **a re-run of ingest**, because `UPSERT_DOCUMENTO_SQL`
(`repository.py:186-207`) is `ON CONFLICT (corpus_sha, documento_id) DO UPDATE` and already sets
`clasificacion = EXCLUDED.clasificacion` at `:202`. Same SHA in, same rows updated in place, new
classification. It is a named, ordered step of the G9 runbook, not an implicit consequence of deploying.

**A schema migration is a hard prerequisite of that re-ingest, not an optional tidy-up.** `rag_documento`
carries `CHECK (clasificacion IN ('publico', 'privado'))` — `models.py:156-157`, created by
`conocimiento_001_rag_corpus_schema.py:85-86`. Writing `institucional` against that constraint is an
`IntegrityError`, and because ingest runs in **one transaction** (`scripts/rag_ingest.py:170`, `:219-232`) it
would roll the whole re-ingest back. So a new migration `conocimiento_005` widens the CHECK to
`('publico', 'institucional', 'privado')` and adds the nullable `clasificacion_evidencia` column, and it runs
in the runbook's `alembic upgrade head` step **before** the re-ingest step. Its downgrade must first demote
any `institucional` row to `privado` — the safe direction — or the narrowed CHECK cannot be re-created.

**Gold items C-1 and C-8 become servable, with one residual named rather than assumed.** Both cite units of
`consorcio-10-de-mayo-registro-aprhi` (`gold_set.yaml:169`, `:246-249`), which is now `institucional` and
therefore admitted to the payload. C-8 also cites `res-dipas-395-2004#art1` and `#art3`, from
`resolucion-dipas-395-2004-linea-ribera-provisoria` (`tipo: resolucion-administrativa`), whose `fuente_url`
hosts are **not verifiable from this repository** — it is one of the 24 documents with no checked-in fixture.
If that document carries no `FUENTES_PUBLICAS` host it stays `privado`, its two keys are excluded from the
payload, and C-8 becomes a partial-context item rather than a fully-grounded one. This is settled the moment
`expected_clasificacion.yaml` is generated at the pinned SHA, and it is an **input to owner ratification of
the allowlist** (Open Questions), not a thing to discover during the runbook.

#### G2b — per-request enforcement, and what "excluded" means downstream

`assert_unidades_publicas(db, corpus_sha, claves) -> frozenset[str]` returns the **shippable subset** of the
requested keys — `clasificacion IN ('publico', 'institucional')` *(bounded correction, 2026-08-23; the name is
kept because it is the name the ratified amendment uses)* — by the same raw-SQL join shape `eval/privacy.py:49-58`
already uses, so "what leaves the machine" is readable end to end. The admitted set is a module-level constant
shared with the ingest rule, so "shippable" has exactly one definition in the codebase. Then:

1. the generation **payload** is the retrieved list filtered to that subset — in retrieved order, nothing
   re-ranked and nothing back-filled to restore `k`;
2. if the payload is empty, the answer is **abstención**, and the request never reaches the provider;
3. **every downstream check binds to the payload, not to the retrieved set** (see G3). An excluded unit's
   citation key is an *invented* key, not a permitted one;
   *(Bounded correction, 2026-08-23 — abstention calibration.* An exclusion-driven abstention is **downstream**
   of `AbstentionPolicy`: the policy already cleared its threshold on the retrieved set, and the exclusion then
   emptied the context. So the end-to-end abstention pair the generation spec bars on — recall `1.00`,
   precision ≥ `0.80` — is **not** the retrieval-level pair; it must be measured POST-exclusion, on the served
   surface. G7 carries that as its own metric row. It also means a **reclassification triggers a
   re-MEASUREMENT** of the end-to-end abstention figures even though `corpus_sha` has not moved: the corpus is
   byte-identical, the payloads are not.)*;
4. the exclusion is recorded in the request's internal trace (which keys were dropped and why), so a CD member
   asking "why did it abstain" gets an answer that is not a shrug.

Implementation shape: a `Generador` Protocol in `generacion.py` with `AnthropicGenerador` and a
`GeneradorDeterministico` (fixture-driven) for tests. **No test ever makes a network call.**

#### G2c — cost controls, because a hosted call is a spend surface

At an estimated ≈ USD 0.03–0.05 per query, an unbounded admin surface is an unbounded bill, and the rate
limiter alone does not bound it (a limiter caps *rate*, not *total*). Three controls, all env-configured, all
**fail-CLOSED** — when a ceiling is hit the surface returns `no_disponible` with the cause named, and never
degrades to an uncited or a cheaper-model answer:

| Control | Setting | Keyed on |
|---|---|---|
| Per-user daily quota | `conocimiento_quota_diaria_usuario` | **authenticated user id** |
| Global spend ceiling (rolling window) | `conocimiento_spend_ceiling_usd`, `conocimiento_spend_window_h` | deployment |
| In-flight semaphore | `conocimiento_max_concurrency` | per process, the `ficha_max_concurrency` precedent (`config.py:252`) |

**"Daily" is defined, because an undefined window is an unimplementable quota** *(bounded correction,
2026-08-23)*. The per-user quota uses a **calendar day in `America/Argentina/Cordoba`**, not a rolling 24 h
window. Chosen over rolling for two reasons, both about the user rather than the implementation: a CD member
who exhausts the quota can be told "se renueva a la medianoche", which a rolling window cannot state without
naming the timestamp of their first call; and the Redis key becomes `quota:conocimiento:{user_id}:{YYYY-MM-DD}`
with a TTL to the next local midnight, so the counter is a single integer rather than a timestamp set. The
cost of the choice is stated: a burst is possible across a midnight boundary, up to two quotas in a few
minutes. That is bounded, visible in the spend ceiling, and cheaper than the alternative's opacity. The
**global spend ceiling keeps its rolling window** (`conocimiento_spend_window_h`) — it exists to bound a
runaway, and a runaway does not respect midnight.

**The limiter and the quota key on the authenticated user id, not the client IP.** `router_ficha.py:130-131`
keys on `request.client.host`, which is correct for a public unauthenticated surface and wrong here: this
route is behind `require_admin`, the deployment sits behind a proxy, and every admin arriving through it
collapses into one bucket — so one CD member exhausts the quota of all of them, and the audit trail says
"the proxy did it". The identity is available (the route is authenticated) so it is used. Trusting a
forwarded-for header instead would be worse than the IP: it is caller-controlled.

Semaphore note, same honesty as `router_ficha.py:104-128`: the semaphore is per PROCESS and `app/server.py`
runs 2 uvicorn workers, so the box-wide in-flight bound is `2 × conocimiento_max_concurrency`. The spend
ceiling, which is in Redis, is the one that is actually box-wide.

**Provider data-retention terms are a pin criterion, not a footnote.** The provider/model pin (Open Questions)
is selected against published terms that state no-training-on-input and a bounded retention window for API
traffic; a provider that trains on inputs is not eligible regardless of price or latency, because the ratified
amendment permits public law text plus the question to leave the box — not to become training data. The pinned
terms are recorded next to the model pin so a silent terms change is a diff, not a discovery.

#### G2d — caching: none server-side in V1, and that is a decision

No server-side answer cache. Every question is answered fresh. The reason is the per-request privacy
contract: a cache keyed on the question would serve an answer built from a payload whose classification was
verified *at some earlier request*, so a document reclassified to `privado` would keep leaking through the
cache — and a cache that re-verifies classification on every hit has already done the expensive part of the
work. The cost of not caching is bounded by G2c's quota, which is the control that belongs to the problem.

Client side: TanStack Query with a **finite** `staleTime` (proposed 5 minutes) and **no** persistence to
`localStorage`/`IndexedDB`. An answer sitting in a persisted cache is a legal opinion outliving the session
that asked for it.

Reclassification note, stated rather than silently ignored: **answers already served are historical
documents.** If a document is later reclassified `privado`, past answers that cited it are not retroactively
unsayable — they were served under the classification in force. V1 has no answer store to purge; if a future
version adds one, this note becomes a requirement rather than a note.

### G3 — Citation enforcement: mechanical, post-hoc, budget = exactly one regeneration

Order: generate → parse citation keys → **key membership against the POST-EXCLUSION PAYLOAD** (`set`
comparison, not model self-report) → **uncited-claim** check (every sentence classified as a substantive claim
must carry ≥1 key) → **vigencia/secundaria marker check** → serve, or reject.

**The membership set is the payload, never the retrieved set.** This is the one place where a plausible
shortcut breaks the ratified privacy amendment. The payload is a strict subset of the retrieved set when G2b
excluded anything; validating against the retrieved set would accept a key belonging to an excluded, non-public
unit — a key the model can only have produced by hallucination, since that unit's text was never in the
prompt, and one whose citation card would then render a private document's provenance to the reader. So: an
excluded unit's key is an **invented-citation violation**, full stop. The same binding governs rendering — the
`CitaRecuperada` list handed to the response schema is filtered to payload keys before serialization, so the
UI cannot render a card for a unit the generator never saw (G6).

**Budget: 1 regeneration, then abstain (2 generations maximum).** Rationale: the context is *fixed* across
attempts — the payload does not change — so a second failure is evidence about the model, not about
retrieval, and a third attempt buys nothing while doubling cost and pushing latency past ~16 s. The retry
prompt carries the explicit violation list (which keys were invented, which sentences were uncited), which is
the one thing that materially changes the second attempt. Abstention is the same explicit state the
`AbstentionPolicy` produces, so the caller has one abstention contract, not two.

**Which failures consume the attempt, and which do not.** Conflating "the model wrote something it must not
serve" with "the HTTP call did not complete" spends the correction budget on a network blip and, worse, makes
a provider outage indistinguishable from a model that cannot ground its claims:

| Failure | Consumes the regeneration attempt? | Terminal state if it recurs |
|---|---|---|
| Invented citation key (incl. an excluded unit's key) | **YES** | `abstencion` after the retry |
| Uncited substantive claim | **YES** | `abstencion` after the retry |
| Missing vigencia/secundaria marker | **YES** | `abstencion` after the retry |
| Response truncated by `max_tokens` | **YES** *(reclassified, bounded correction 2026-08-23)* | `generacion_fallida` |
| Provider timeout / connection error / 5xx | no | `generacion_fallida` |
| Provider 429 / quota / auth error | no | `no_disponible` (a configuration or ceiling fact, not a generation fact) |

Transport failures get a small bounded transport budget instead — **2 attempts with one short backoff, inside
the request's own latency budget**, never a background retry and never a queue. Exhausting it lands in
`generacion_fallida`.

**Truncation is not a transport failure, and round 1 filed it as one.** *(Bounded correction, 2026-08-23.)*
`GeneracionTransporte`'s docstring listed truncation next to timeouts and 5xx, but the two are opposite facts:
a truncated response means **the HTTP call completed successfully** and the model emitted a `max_tokens` stop
reason. Retrying it as transport means re-issuing the identical request against the identical fixed payload
and the identical `max_tokens`, which is deterministic-in-expectation: it burns a full generation's cost and
latency to get the same truncation. Worse, it hides a real signal — truncation says the answer did not fit,
which is a prompt/budget fact the operator needs.

**Decision: truncation consumes the single regeneration attempt, on the CORRECTION path, with a changed
input.** The retry is not a replay: it carries the same violation-list mechanism the other enforcement
failures use, with the violation being `truncado`, and it changes exactly one of the two things that can make
the second attempt fit — `max_tokens` is raised to its configured ceiling for the retry, and if it was already
at the ceiling the payload is trimmed to its highest-ranked units instead. A second truncation is terminal as
`generacion_fallida` (not `abstencion`: grounded context existed and the provider did answer; what failed is
certification, not the corpus).

Why the correction path rather than "straight to `generacion_fallida`": straight-to-terminal is simpler and
was the tempting choice, but it converts the single most likely benign failure — a verbose answer over a
generous corpus — into a dead end that a one-token-larger budget would have fixed, and it does so without ever
telling the operator that the ceiling is the binding constraint. The cost of the chosen path is honest and
bounded: it is the *same* one-retry budget, not an extra one, so the worst case is still two generations.
`GeneracionTransporte`'s docstring loses the word "truncation" accordingly.

**A fifth state, because "we could not generate" is not "there is no applicable norm".** The four-state union
forced a real generation failure to be reported as an abstention, which tells the CD member "the corpus has no
answer for you" when the truth is "the corpus had grounded context and the provider did not answer". That is
a false statement about the law, produced by a state machine that had nowhere else to put the case. So V1 adds
`generacion_fallida`: *grounded context existed and generation could not be certified*. It is distinguishable
by the caller from `abstencion` (no applicable norm), from `redireccion`, from `no_disponible` (a dependency
is not ready) and from `respuesta`. It carries the cause and, deliberately, **no prose and no partial draft** —
the last rejected draft is never surfaced (generation spec:68-73).

**Uncited-claim detection is a specified rule, not a judgment call.** "Substantive claim" is defined
mechanically and the rule is a checked-in artifact with its own tests, so it can be audited and so a change to
it is a diff:

1. **Segment** the answer into sentences with a deterministic segmenter over Spanish text, with an explicit
   abbreviation/ordinal exception list (`art.`, `inc.`, `N°`, `Res.`, `Dec.`, `Ley N° 9.750`) so a legal
   citation's own periods do not split a sentence.
2. **Exclude** a sentence from the substantive class if it matches the checked-in exclusion list: the
   abstention sentence, the fixed disclaimer/framing boilerplate (including the vigencia and secundaria
   framings below), a pure heading, a pure enumeration lead-in, and a sentence with no verb clause.
3. **Everything else is a substantive claim** and must carry ≥1 key. The default direction is deliberate:
   an unrecognized sentence shape is treated as a claim, so the failure mode of the rule is a rejected answer,
   not a served uncited one.

The exclusion list is a fixture, not a regex buried in a function, and the answer prompt is written to produce
exactly those boilerplate forms — so the rule and the prompt are one artifact reviewed together.

**Vigencia and secundaria: a mechanical pre-serve check, not a prompt hope.** The generation spec's
requirement (generation spec:111-132) is enforced in code before serving, not delegated to the model: if **any** cited
unit has `estado_vigencia != vigente` or `es_secundaria is True`, the response MUST carry the corresponding
marker fields for that citation (`estado_vigencia` verbatim, the `es_secundaria` flag) **and** the answer must
contain the corresponding framing sentence from the fixed boilerplate set. Missing markers ⇒ rejection ⇒ retry
⇒ abstention. Backend-enforced, so a UI change cannot silently drop the label. Honest limit, stated rather
than papered over: this check proves the marker is *present*, not that the surrounding prose does not
misrepresent the unit anyway ("la ley 8548 establece…" next to a `DEROGADA` badge). That residue is exactly
what owner grading in G7 measures — mechanically checkable is the floor, not the ceiling.

**End-to-end latency budget, restated as an HONEST sum with enforced deadlines** *(bounded correction,
2026-08-23: round 1 wrote "~16 s + 2× embed" by counting two generations and silently ignoring that each one
carries its own transport budget of 2 attempts, so the real call ceiling is **4**, not 2; and it named no
timeout anywhere, which makes a "budget" a wish. Every term is an estimate until the G0 measurements land.)*

Three timeouts, all env-configured, all enforced in code:

> **TWO timeouts, not three, and neither bounds an HTTP request** *(bounded correction, 2026-08-24)*. The table
> and the worst-case sum immediately below are round-1 text that amendment A3 superseded (`:1292-1294`) and
> that this section still asserted in the present tense. As IMPLEMENTED in U6:
>
> - `conocimiento_provider_timeout_s` (20 s) survives verbatim, but bounds one **worker** attempt;
> - `conocimiento_request_deadline_s` is **renamed** `conocimiento_item_deadline_s` (60 s) and bounds the
>   processing of one **queued item** on a MONOTONIC clock, since it measures elapsed processing and nobody is
>   waiting on a socket. The effective attempt timeout is the SMALLER of the two, or the item budget would be
>   decorative: an attempt would run past it and the overrun would only be noticed afterwards. Expiry raises
>   `PresupuestoAgotado` and `generar_respuesta` ends the item in `generacion_fallida`;
> - `conocimiento_semaforo_timeout_s` and the in-flight semaphore are **DROPPED**, not merely unused —
>   `test_no_queda_semaforo_ni_su_timeout_en_el_dominio` asserts the knobs are absent from `Settings`. A knob
>   that survives its own decision is a knob someone will set, expecting an effect that no longer exists.
>
> Everything in the sum below is therefore the WORKER's arithmetic. "Observed worst case = 60 s exactly,
> aborted to `generacion_fallida`" is still true and is now a bounded item, not an aborted request: no CD
> member is watching a spinner while it runs.

| Knob | Proposed value | What it bounds |
|---|---|---|
| `conocimiento_provider_timeout_s` | **20 s** | ONE provider HTTP attempt. Exceeded ⇒ `GeneracionTransporte`, which the transport budget may retry |
| `conocimiento_request_deadline_s` | **60 s** | the WHOLE request, measured from the first line of the handler. A hard wall-clock deadline: when it expires the request aborts to `generacion_fallida` immediately, mid-attempt, whatever stage it is in |
| `conocimiento_semaforo_timeout_s` | **5 s** | waiting for the in-flight slot. Exceeded ⇒ `no_disponible` (the box is saturated — a load fact, not a generation fact), never a queued request and never an unbounded wait |

The semaphore timeout is short on purpose: a caller who waits 5 s for a slot and *then* starts a 20 s
generation has already spent a third of the deadline on queueing. Precedent for a transaction-scoped bound
rather than a hope is `ficha_statement_timeout_ms` (`config.py:264`).

The worst case, counted properly:

```
semaphore acquire       ≤ 5 s   (hard; else no_disponible before any spend)
embed (sidecar, CPU)    ~?      ← MEASURED TASK, still the only unbounded term
retrieve (fts+vector)   ~11 ms  (archive design D4, EXPLAIN)
generate #1  attempt 1  ≤ 20 s  ┐ transport budget 2
             backoff    ~1 s    │
             attempt 2  ≤ 20 s  ┘
enforcement             <50 ms  (set ops + segmentation, no I/O)
generate #2  attempt 1  ≤ 20 s  ┐ transport budget 2
             backoff    ~1 s    │
             attempt 2  ≤ 20 s  ┘
                        ────────
arithmetic worst case   ≥ 87 s + 2× embed   ← EXCEEDS the 60 s deadline
observed worst case     = 60 s exactly, aborted to `generacion_fallida`
```

**The arithmetic worst case does not fit the deadline, and that is the design, not an oversight.** Sizing the
deadline to cover four 20 s attempts would mean 90 s+ of a CD member staring at a spinner for an answer that
by then is certainly failing anyway. So the deadline is the binding constraint and the sum is not: the request
aborts at 60 s to `generacion_fallida`, which is exactly the honest state for "grounded context existed and no
certified answer was produced". The budgets are re-justified against that, not against each other:

- the **typical** path is one embed + one generation (~3–8 s estimated) and is nowhere near the wall;
- the **plausible bad** path is one transport retry plus one regeneration — roughly 3 attempts — which fits
  inside 60 s at the estimated 3–8 s per call and only approaches the wall if the provider is degraded, which
  is precisely when aborting is right;
- the 20 s per-attempt timeout is ~2.5× the top of the 3–8 s estimate, so it fires on a hung call rather than
  on a merely slow one. It is re-derived once the provider is pinned, against that provider's published p99.

If the measured embed term pushes p95 past the CD's tolerance, the answer is fewer retrieved units or a
smaller `max_tokens` — never a second concurrent provider call, which multiplies cost and does not shorten the
tail, and never a larger deadline, which only lengthens the failure.

**Cost ceiling, re-derived for the 4-call worst case** *(bounded correction, 2026-08-23)*. G2c's ≈ USD
0.03–0.05 is a **per-generation** estimate, and round 1's ceiling arithmetic implicitly assumed one. A single
request can issue up to **4** provider calls, all billed — a transport retry is charged even when the response
never arrives intact. So the worst-case cost of one request is ≈ **USD 0.12–0.20**, 4× the headline figure,
and `conocimiento_spend_ceiling_usd` must be sized against that number rather than against the per-query one.
The spend accounting increments **per attempt**, not per request, or the ceiling under-counts exactly in the
degraded conditions it exists to bound. The deadline caps this too: a request killed at 60 s cannot have
issued more attempts than fit in 60 s.

> **How the ceiling is actually CHECKED, and what "the deadline" is now** *(bounded correction, 2026-08-24)*.
> Three amendments to the paragraph above, as implemented in U6:
>
> 1. **The ceiling refuses when this attempt WOULD cross it, not when it has ALREADY been crossed.** The
>    paragraph above is written in terms of a ceiling being exceeded and then noticed, and task 6.4 restated it
>    as "ceiling exceeded ⇒ `no_disponible`". Checking "already over" always overshoots by exactly one attempt,
>    and it lets a ceiling smaller than one attempt's cost authorise an unbounded first call — a USD 0.05
>    ceiling quietly permitting a USD 0.10 spend, once, every time the window rolls. `MedidorDeGasto` charges
>    BEFORE the attempt is issued and refuses on the projection, so with the ceiling reached **no request
>    leaves at all**.
> 2. **The USD 0.12–0.20 figure is STALE BY CONSTRUCTION** (amendment A2, `:1260-1263`): it was derived from
>    Claude-class list pricing and the pin is `deepseek-v4-flash`. The per-attempt accounting RULE is unchanged
>    and still correct; the number must be re-derived before `conocimiento_spend_ceiling_usd` is set, and until
>    it is, unset REFUSES (`TechoNoConfigurado`). The 4-call worst case is likewise an upper bound on CALLS,
>    which is the part that survives re-pricing.
> 3. **"a request killed at 60 s" is an ITEM killed at 60 s** (amendment A3). The bound is the worker's
>    per-item budget; there is no HTTP request to kill.

Enforcement never bypasses the layer below: retrieval refusals propagate as `503 base_de_conocimiento_no_lista`
and abstention as `abstencion`; neither is ever converted into prose (generation spec:75-109).

### G4 — Feature flag: env-backed `Settings`, default `False`, never a DB row

`conocimiento_qa_enabled: bool = False` in `app/config.py`, plus `enforce_conocimiento_qa_enabled` as the
**first** router dependency returning 503 — the exact `ficha_enabled` pattern (`config.py:124`,
`router_ficha.py:135-151, 322-326`). A missing env var is `False` by pydantic default, satisfying "the
deployment's default state, with no flag explicitly set, is off" (retrieval delta:35).

Rejected: `system_settings` (`domains/settings/models.py:22-37`). It is admin-writable at runtime, so the
kill switch for an admin-only answerer would live *inside* the surface it gates; and a seeded row makes
"no configuration present" unrepresentable.

The flag is an **AND** with ~~two~~ **three** more facts *(the third added 2026-08-24, see below)*, checked in
the same first dependency, because a surface that is "on" and fails on every request is not on:

1. **credential presence** — no provider key configured ⇒ 503, not a 500 from the first hosted call;
2. **sidecar liveness** — `conocimiento_embed_url` unset, or the sidecar's `/ready` not true, ⇒ 503
   `base_de_conocimiento_no_lista` with cause `embedder_no_listo`. Checked with a cached readiness probe (short
   TTL, non-blocking) so the gate costs nothing per request but still flips within seconds of the container
   dying. This is the first-dependency half of G1's rule: unavailability is answered as unavailability at the
   door, and any later-stage unavailability lands in the same state — never a redirect, never an abstention.
3. **the provider TERMS GATE** *(added as a bounded correction, 2026-08-24)* — `verificar_terminos` over the
   checked-in record, against `(conocimiento_modelo, conocimiento_pool)`, ⇒ 503
   `base_de_conocimiento_no_lista` cause `terminos_no_verificados`. A2 already ruled that "if those terms
   cannot be verified, the flag is not enabled" (`:1272-1274`), and U6 built the entire mechanism — the
   record, the six refusals, the test asserting the shipped record refuses — with **no caller on the serving
   path**. A fail-closed gate nobody calls is enforced by somebody remembering, which is the failure mode the
   whole G4 "an AND, not a flag" structure exists to remove. It is evaluated per request against the loaded
   record, so flipping the record is a deploy and never a code change — the same reason the pin lives in
   config.

### G5 — HTTP surface

`gee-backend/app/domains/conocimiento/router.py`, mounted at `/api/v2/conocimiento`.
`POST /preguntas` with dependency order `enforce_qa_enabled → require_admin → enforce_body_limit →
enforce_qa_rate_limit → enforce_qa_quota → acquire in-flight slot`. Own limiter instance on its own Redis
namespace (`ratelimit:conocimiento:`), per the `get_ficha_rate_limiter` precedent (`router_ficha.py:102-128`)
— a shared limiter would let a legal question throttle the operator geo routes. `require_admin` via the house
lazy-import shim (`settings/router.py:34-37`). Limiter and quota key on the **authenticated user id**, not on
`request.client.host` — see G2c for why the ficha's `_client_ip` keying (`router_ficha.py:130-131`) is the
wrong precedent behind an authenticated route and a proxy. The quota runs *after* `require_admin` precisely
so a user id exists to key on.

**Response contract: a five-state discriminated union for the LEGAL leg, plus one ORTHOGONAL partial-redirect
block.** *(Restructured — bounded correction, 2026-08-23. Round 1 put `redireccion` inside the same `estado`
union as `respuesta` and `abstencion` and then asserted the states "never overlap". Those two claims are
jointly unsatisfiable for `mixto`: the routing spec requires ONE response carrying **both** an answer block
and a redirect block (routing spec:53-63), and explicitly requires the redirect to survive when the legal part
abstains (routing spec:65-70). A single mutually-exclusive tag cannot represent `abstencion` and `redireccion`
at once, so `mixto` was unrepresentable — the class the whole G1 `mixto` signature exists to reach.)*

```
estado: respuesta | abstencion | redireccion | generacion_fallida | no_disponible   # the LEGAL leg
redireccion_parcial: Redireccion | null                                            # ORTHOGONAL, optional
```

- `estado` keeps **five** values and they remain mutually exclusive: exactly one is true of the legal leg, and
  the caller never has to infer abstention from an empty answer string nor read a provider outage as "no
  applicable norm" (G3).
- `redireccion_parcial` is **not** a sixth state and is not part of the union. It is present, on **any**
  `estado`, iff the router classified the question `mixto`, and it names the surface for the non-legal part.
  It is absent otherwise.
- `estado = redireccion` remains the **pure** redirect: a wholly `operational`/`geoespacial` question, or a
  doubt-redirect. It carries no answer, no citation and no `redireccion_parcial` (the redirect *is* the
  response; a partial redirect alongside a total one would be the same fact twice).

Every `mixto` combination is now representable, including the two the spec names and the two round 1 could not
have produced at all:

| `estado` | `redireccion_parcial` | Case |
|---|---|---|
| `respuesta` | present | legal part answered with citations, operational part redirected (routing spec:57-63) |
| `abstencion` | present | legal part below threshold, **redirect still stands** (routing spec:65-70) |
| `generacion_fallida` | present | grounded context existed, generation could not be certified; the redirect is a routing fact and is unaffected by a provider failure |
| `no_disponible` | present or absent | a dependency is down. If routing completed before the failure the redirect is still true and is carried; if the failure was the *embedder*, no classification happened, so there is nothing honest to carry and the field is absent |
| `redireccion` | absent | pure non-legal question |
| `respuesta` / `abstencion` / `generacion_fallida` | absent | pure legal question |

The "never overlapping" property is therefore restated precisely: **the five `estado` values never overlap
with each other**; the partial-redirect block is orthogonal to all of them and overlaps none, because it
answers a different question ("was part of this non-legal?") than `estado` does ("what happened to the legal
part?"). One response, both blocks — which is what routing spec:55 asks for.

Diagnostic `GET /api/v2/conocimiento/estado` (admin) returns `service.procedencia_embeddings` (`service.py:225`):
model, `sintetico`, `embeddings_loaded_at`. Serving additionally refuses outright when `sintetico` is true.

### G6 — `consorcio-web` page

Child route `/admin/conocimiento` under `adminLayoutRoute` (`src/routeTree.gen.tsx:590-595` — hand-written
despite the `.gen` name; siblings at :645-666), so `adminGuard` applies; plus `ProtectedRoute
allowedRoles={['admin']}` for the in-page state. Server-side `require_admin` is the boundary; the hidden page
is not (retrieval delta:37-41).

Client: `src/lib/api/conocimiento.ts` + `src/hooks/useConocimientoQA.ts` (TanStack Query), mirroring
`lib/api/ficha.ts` + `useFichaTerritorial.ts`. Panel `components/admin/ConocimientoPanel.tsx`, Mantine.
Cache policy per G2d: finite `staleTime`, no persistence.

**The card list is the payload, not the retrieved set.** The backend serializes only the `CitaRecuperada`
rows whose key survived G2b's exclusion, so the panel physically cannot render a card for an excluded unit.
The filter is server-side and is the same set G3 validates against — one set, one place, so "what the model
saw", "what may be cited" and "what the reader sees" cannot drift apart.

Citation UX, driven by the fields `CitaRecuperada` already carries (`schemas.py:107-121`): each citation
renders as a card with the `citation_key` as its anchor (in-answer keys link to the card — there is no public
corpus URL; the corpus repo is private), a vigencia badge from `estado_vigencia`, a `fuente secundaria — no es
derecho aplicable` chip when `es_secundaria`, the **verbatim** `relevancia_consorcio` as a warning banner when
present, the verbatim `texto` in a preformatted block, and `fuente_url` as an external link when present. No
paraphrase anywhere in the citation block.

### G7 — Eval extension: mechanical metrics automated, faithfulness graded by the owner

| Metric | How scored | Why |
|---|---|---|
| invented-citation rate | set membership vs the **POST-EXCLUSION generation payload** — **string/set match, deterministic** *(universe corrected, bounded correction 2026-08-23)* | needs no judgment; a judge here would add noise to a `0.00` bar |
| uncited-claim rate | sentence→key mapping, deterministic | same |
| **citation faithfulness** | **owner-graded** on a ratified answer set of **n ≥ 30 ANSWERS**, stored as a checked-in labeled artifact | "does this unit support this claim?" is irreducibly semantic |
| router accuracy | confusion matrix, deterministic | — |
| **end-to-end abstention recall / precision** | deterministic, measured **POST-exclusion** on the served surface | *(added, bounded correction 2026-08-23)* — see below |

**The invented-citation universe is the payload, not the retrieved page.** *(Bounded correction,
2026-08-23.)* Round 1's row said "retrieved page", which is the universe the **enforcement** code explicitly
does **not** use: G3 binds membership to the post-exclusion payload, and the generation spec's clarified
requirement now says the same. An eval that scores against the retrieved page measures a different function
than the one that runs in production, and it errs in the dangerous direction — a key belonging to a
retrieved-but-excluded unit would score as *correct* in the eval and be *rejected* in production, so the
metric would read `0.00` for a system that abstains. The eval universe is the payload, computed by the same
`assert_unidades_publicas` call the request path uses. Same set, same function, one definition.

**End-to-end abstention is a separate measurement from retrieval abstention.** The generation spec bars
serving unless "end-to-end abstention recall stays `1.00` with precision ≥ `0.80` on held-out decisions", and
those decisions are **not** `AbstentionPolicy`'s. The policy decides on the retrieved set; the privacy
exclusion then runs and can empty the payload, producing an abstention the policy never chose (G2b). So the
end-to-end pair is measured on the **served** outcome, post-exclusion, and reported as its own row next to —
never merged into — the retrieval-level LOOCV pair. Two consequences, both stated because both are easy to
skip:

- an exclusion-driven abstention is a **true** abstention for recall purposes (no answer was served) but
  counts against **precision** if the corpus did hold an applicable norm in an excluded unit. That is the
  honest accounting: the reader is entitled to see how much of the abstention rate the privacy gate is
  producing;
- **a reclassification re-triggers this measurement even though `corpus_sha` has not moved.** The corpus is
  byte-identical; the payloads are not. The end-to-end block therefore pins
  `(corpus_sha, expected_clasificacion_sha256)` and refuses on divergence of *either*, by the same string
  comparison as `verificar_corpus_sha` (`harness.py:254-269`). Pinning `corpus_sha` alone would let a
  widened allowlist reuse figures measured under a narrower one.

**LLM-judge rejected for V1**, with the tradeoff stated: it would scale, but it (a) opens a second external
inference path against the same privacy requirement, (b) correlates its errors with the generator when it
shares a model family, and (c) breaks V0's explicit "no LLM-as-judge" property (archive design D6), which is
what makes the harness deterministic. Revisit when the answer set outgrows manual grading.

**`n ≥ 30` counts ANSWERS, not claims, and the claim count is reported alongside.** An answer carries several
claims, so "n = 30" read as claims would be six or seven answers wearing a bigger number — the same
sample-inflation the V0 harness refuses elsewhere. The report publishes `n_respuestas`, `n_afirmaciones`, and
the **per-answer claim count distribution**, so a reader can see whether the faithfulness rate rests on thirty
independent answers or on one verbose one.

**Single-grader label noise is measured, not assumed away.** There is exactly one grader (the owner), so
inter-rater agreement is undefined; what *is* obtainable is **intra-rater** agreement. A **10% sample of the
graded claims — with a hard floor of 15 claims, whichever is larger — is re-graded in a second pass**, blind
to the first pass's labels and at least a day later, and the agreement figure is published with the
faithfulness rate. A faithfulness number of 0.97 next to an intra-rater agreement of 0.80 is a different fact
from the same number next to 0.98, and the reader is entitled to know which one they are holding.

*(Floor added, bounded correction 2026-08-23.)* The floor is the point: at n = 30 answers with, say, 3 claims
each, a bare 10% is **9 claims**, and an agreement figure computed on 9 items moves by 0.11 per disagreement.
Publishing that as "intra-rater agreement" would be the same sample-inflation this section refuses two
paragraphs above, wearing the opposite sign. 15 is the floor, not a target; if 10% exceeds it, 10% wins. If
the graded set is smaller than 15 claims in total the figure is reported as **not-evaluable**, never as a
number — the same not-evaluable discipline the retrieval spec uses below n = 20.

**Grades are pinned to what produced them, and a mismatch refuses rather than scores.** A faithfulness label
is a judgment about a specific answer produced by a specific prompt, a specific model and a specific corpus;
re-using it after any of the three moves is scoring the old system's output as if it were the new one's. So
the graded artifact carries `(prompt_version, provider_model_pin, corpus_sha)` and the harness refuses on
divergence, following the exact precedent of `verificar_corpus_sha` (`harness.py:254-269`) and the private
gold-set pin check at `:242-249` — a pure string comparison at the CLI edge, before the database is opened.
The refusal message names both operands and says the fix is a re-grade, never a re-scoring.

**Proposed thresholds for owner ratification** (the spec leaves faithfulness mandatory-but-unset):
`invented-citation = 0.00` and `uncited-claim = 0.00` (hard, already spec'd); **claims contradicted by their
cited unit = 0.00** (hard); **fully-supported claim rate ≥ 0.95** (ratifiable — partial support at n≈30 with
one grader has real label noise, and a 1.00 bar there converts one disagreement into a stop).

**Where the serving abstention threshold comes from.** It is not a hand-tuned constant in code and not a
number typed into an env file from memory. It is a config value **seeded from the eval artifact** —
`eval/umbral_abstencion.yaml`, written by the LOOCV run and carrying its own
`(corpus_sha, embedding_modelo, embedding_revision_hf, n, metodologia)` header. The serving path reads it and
**re-derivation is triggered** by any change to `corpus_sha` or to the embedder identity (model **or** HF
revision — the pair G0 now compares). On mismatch the surface refuses with `base_de_conocimiento_no_lista`
rather than serving against a threshold calibrated for a different corpus or a different vector space; same
refusal discipline as `verificar_corpus_sha`, for the same reason.

Serving gate ordering, per the delta (retrieval delta:82): the hybrid arm on **real** BGE-M3 vectors clears
hit@5 ≥ 0.85 / MRR ≥ 0.70 / citation-precision 1.00, published side by side with the recorded FTS-only
baselines `0.138` / `0.091` / `0.040`, **before** the answer-level set is scored. No margin is invented here:
the bars are the owner's ratified V0 bars, unchanged.

### G8 — O.3 dependency: what it produces and how absence is detected honestly

O.3 produces `vectors-{sha8}.copy` + its sidecar (model id, HF revision, dims, sha256, `over_ceiling` keys),
loaded by `scripts/rag_load_vectors.py` into a staging table and stamped onto `rag_corpus` in the same
transaction (archive design D3). **Absence** detection already exists and needs no new code:
`verificar_embedder` raises `EmbeddingsNoCargadas` when `embedding_modelo IS NULL` (`service.py:273-280`).
**Identity** detection is the one thing V1 strengthens: the `EmbedderMismatch` branch at `:281-288` compares
only `modelo`, and G0 extends it to the `(modelo, revision_hf)` pair — the sidecar record already carries the
revision, so the artifact side needs nothing. V1's other obligation is to **not catch-and-degrade**: map both
refusals to `503 base_de_conocimiento_no_lista`, distinct from abstention and from `generacion_fallida`, and
let the message through.

### G9 — pgvector image swap: runbook, sealed order, verified backup

Precondition — **verified** backup: restore the dump into a throwaway container and assert row counts plus
`PostGIS`/`pgRouting` extension presence. A file that exists is not a backup (retrieval delta:47-51).

**Forward, in order. Every step names its failure state and its recovery; a step with no recovery is a step
that will be improvised at 2 a.m.** Note the deployment shape: this box runs a compose file that lives
**outside this repository** (single environment, Hetzner), so the sidecar step is not "docker compose up" —
it is an edit to that external file, and the runbook carries the exact block to paste:

```yaml
  conocimiento-embed:
    build:
      context: ./gee-backend
      dockerfile: docker/embed/Dockerfile
    container_name: consorcio-conocimiento-embed
    restart: unless-stopped
    ports:
      - "127.0.0.1:8002:8002"        # loopback only, exactly like geo-worker
    environment:
      - EMBED_MODEL_ID=BAAI/bge-m3
      - EMBED_REVISION_HF=${EMBED_REVISION_HF}   # pinned, reported back verbatim
    volumes:
      - hf-cache:/root/.cache/huggingface        # named volume; no re-download per restart
    healthcheck:
      test: ["CMD", "curl", "-fsS", "http://127.0.0.1:8002/ready"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 180s                          # cold model load; see the G0 measurement
    networks:
      - consorcio-network
```

with `CONOCIMIENTO_EMBED_URL=http://conocimiento-embed:8002` added to the backend service's environment.

| # | Step | Failure state | Recovery |
|---|---|---|---|
| 1 | Verified restore of the backup into a throwaway container | swap does not proceed | fix the dump; nothing on the live box has changed yet |
| 2 | **Deploy the sidecar**: add the block above to the external compose file, `docker compose up -d conocimiento-embed`, wait for `/ready` | image build fails, or the model never loads (OOM / no disk for 2.2 GB) | remove the block, `docker compose up -d` without it. Nothing else has moved; the flag is still off. **This is where the G0 RAM measurement pays for itself** |
| 3 | **Health-verify the sidecar**: `/health`, `/ready`, one embed of a known string, and assert the reported `modelo` + `revision_hf` are the pinned pair | wrong revision reported ⇒ STOP | fix `EMBED_REVISION_HF` and restart. Proceeding here means every later step is calibrated against the wrong vector space |
| 4 | Maintenance window announced; stop the app | — | — |
| 5 | Swap image to `consorcio-postgres:16-vector` | container will not start on the volume | revert the image tag **before** any migration runs; nothing vector-shaped exists yet, so this revert is safe |
| 6 | `alembic upgrade head` — this now also carries **`conocimiento_005`**: widen `CHECK (clasificacion IN (...))` to admit `institucional` and add the nullable `clasificacion_evidencia` column (G2a). It MUST precede step 7 or the re-ingest dies on an `IntegrityError` and rolls back. (002's vector branch now takes the real path; if it was already recorded as applied on the vector-less image, run `ddl.UPGRADE_STATEMENTS` directly — the non-destructive path measured in archive design D7, table row B) | **half-applied migration**: this is the dangerous cell | do **not** re-run blindly. Inspect `alembic_version` against the objects actually present (`pg_extension`, the column, the index). If the version row moved but objects are missing, the recovery is the sealed rollback of the next section, from the verified backup of step 1 — never a hand-patched schema |
| 6b | **Prerequisite for step 7**: a checkout of the **private corpus repository at the pinned `corpus_sha`**, clean, present on the box. `scripts/rag_ingest.py` takes `--corpus-path` (`:51-52`) and `verify_corpus_pin` (`service.py:96-119`) refuses anything else | `CorpusPinMismatch` — three distinct causes, each named by the exception: **not a git checkout** (`service.py:104-105`), **HEAD ≠ declared SHA** (`:107-112`), **dirty working tree** (`:113-118`) | clone or `git checkout <sha>` and `git status --porcelain` until clean. Nothing has been written; this check runs before the transaction opens. The corpus is private and is NOT vendored in this repository, so "the box has it" is a step, not an assumption |
| 7 | **Re-run ingest for reclassification** (`scripts/rag_ingest.py --corpus-path <checkout> --corpus-sha <pinned>`) | ingest aborts: `CorpusPinMismatch`, `JurisdiccionFaltante`, unknown `tipo` (`repository.py:87-103`), gate failure, or an `IntegrityError` if step 6's `conocimiento_005` CHECK widening did not run | **Transaction rollback, not "aborts before writing".** *(Claim corrected, bounded correction 2026-08-23.)* The whole ingest runs inside ONE transaction — `scripts/rag_ingest.py:170` states it and `:219-232` implements it as `with Session(engine) as session, session.begin()`, with an explicit `session.rollback()` on a failed verification. Some aborts (the pin check, an unknown `tipo` on the first document) do land before any write; others land after rows have been written **in the open transaction**. Either way the committed state is untouched, but the guarantee is *rollback*, not *no write attempted* — and the difference matters if anyone reads uncommitted state from another session or wonders why the disk moved. Fix the frontmatter rule or the allowlist and re-run |
| 8 | **Verify the reclassification against the checked-in artifact**: diff every row of `SELECT documento_id, clasificacion, clasificacion_evidencia FROM rag_documento WHERE corpus_sha = <pinned> ORDER BY documento_id` against `eval/expected_clasificacion.yaml` — all 35 rows, class **and** evidence string | **any** row differs in class or in evidence | STOP with the flag still off. *(Corrected, bounded correction 2026-08-23: round 1 compared a single `count(*) FILTER (WHERE clasificacion='publico')`, which passes on any permutation that preserves the count — two documents swapping classes is exactly the silent privacy failure this step exists to catch, and a count cannot see it.)* A wrong classification here is the privacy boundary failing silently, which is the one failure this whole design is arranged around |
| 9 | `rag_load_vectors.py` | manifest/identity refusal (`sintetico`, `over_ceiling` mismatch) | the loader refuses before writing; re-run the batch. The DB keeps the previous state |
| 10 | Smoke: `SELECT 1 FROM pg_extension WHERE extname='vector'`, PostGIS, pgRouting, Martin tiles, and one real `recuperar` through the sidecar | any smoke fails | sealed rollback below. **Do not flip the flag to "test it in prod"** |
| 11 | **Only then** flip `conocimiento_qa_enabled` | the surface misbehaves | flag off — inert, no DB change, no rollback needed |

**Reboot mid-window.** If the box reboots between any two steps, the recovery is not "continue where the
notes stopped": it is re-derive the state. `restart: unless-stopped` brings the sidecar and Postgres back, so
every step must be answerable by a probe rather than by memory. *(Matrix completed, bounded correction
2026-08-23: round 1 listed four probes, all of them database reads, and therefore had **no probe at all** for
the two steps that are not database changes — the image swap and the sidecar deploy. "Which step completed"
was unanswerable for exactly the steps whose failure mode is a container that came back wrong.)*

| Step to re-derive | Probe | Reads |
|---|---|---|
| 2 — sidecar deployed | `docker compose ps conocimiento-embed` | container exists and is `running`/`healthy` (the healthcheck is in the compose block above) |
| 3 — sidecar health-verified | `curl -fsS http://127.0.0.1:8002/ready` **and** assert the reported `modelo` + resolved `revision_hf` are the pinned pair | not just "up": a container that came back on a *different* image reports a different pair, and `/ready` alone would say yes |
| 5 — image swapped | `docker inspect --format '{{.Config.Image}}' $(docker compose ps -q postgres)`, which prints the running container's image tag | the running image tag is `consorcio-postgres:16-vector`. **This is the one that memory gets wrong after a reboot**, because a compose file edited but not applied looks identical to one applied |
| 6 — migrations applied | `SELECT version_num FROM alembic_version` + `SELECT 1 FROM pg_extension WHERE extname='vector'` + the presence of the vector column/index + the widened `clasificacion` CHECK in `pg_constraint` | version row **and** objects, never the version row alone (see step 6's half-applied cell) |
| 7/8 — reclassification done | the full step-8 diff against `eval/expected_clasificacion.yaml` | all 35 rows, class + evidence. Not a count |
| 9 — vectors loaded | `SELECT embedding_modelo, embedding_revision_hf, sintetico FROM rag_corpus WHERE corpus_sha = <pinned>` | identity, not merely non-NULL |
| 11 — flag | the env var | flag is env-backed and defaults to `False` (G4), so a reboot **cannot** bring the surface up half-configured — the one property that makes this recoverable at all |

Rollback, sealed order: **flag off → `alembic downgrade conocimiento_001` → revert image**. Cost of the middle
step, stated because V0 measured it: 003's downgrade DELETEs rows and 004's drops the provenance columns, so
it requires a full re-ingest **and** a vector re-load (archive design D7, "DESTRUCTIVE FALLBACK"). That cost is
precisely why the surface comes off first — flag-off makes the system inert without touching the database.
Never revert the image with vector objects live.

## File Changes

| File | Action | Description |
|---|---|---|
| `gee-backend/app/domains/conocimiento/router.py` | Create | `/api/v2/conocimiento`, flag + `require_admin` + own limiter |
| `.../conocimiento/routing.py` | Create | Rules + centroid classifier, LOOCV threshold, decision record |
| `.../conocimiento/generacion.py` | Create | `Generador` Protocol, prompt assembly, citation enforcement, 1-retry budget |
| `.../conocimiento/proveedores.py` | Create | `AnthropicGenerador`, `GeneradorDeterministico`, sidecar `Embedder` adapter |
| `.../conocimiento/schemas.py` | Modify | `PreguntaRequest`, **five**-state `estado` union for the legal leg (adds `generacion_fallida`) **plus the orthogonal optional `redireccion_parcial` block** (G5, bounded correction 2026-08-23), `Redireccion`, `RespuestaCitada` |
| `.../conocimiento/repository.py` | Modify | `clasificacion` derived by the **three-class** rule (`es_secundaria` → `TIPOS_INSTITUCIONALES` → `FUENTES_PUBLICAS`) in `documento_row_from_frontmatter` — **replaces** the hardcode at `:164-166`; adds `clasificacion_evidencia`; `UPSERT_DOCUMENTO_SQL` already updates both in place (`:195-206`), so re-ingest reclassifies |
| `.../conocimiento/models.py` + `app/db/migrations/versions/conocimiento_005_*.py` | Modify / Create | **Widen `CHECK (clasificacion IN ('publico','privado'))`** (`models.py:156-157`, created at `conocimiento_001_rag_corpus_schema.py:85-86`) to admit `institucional`, and add the nullable `clasificacion_evidencia` column. Hard prerequisite of the runbook's re-ingest step; its downgrade demotes `institucional` → `privado` before re-narrowing |
| `.../conocimiento/service.py` | Modify | (a) `recuperar` gains the optional precomputed `qvec` (the `embedder.encode` at `:342` becomes "use the caller's vector if given"); (b) `verificar_embedder` (`:259-288`) compares the `(modelo, revision_hf)` **pair** against `(embedder.model_id, embedder.revision)`, on **resolved commit hashes** (G0 canonicalization); (c) `assert_unidades_publicas` per-request shippable-subset filter admitting `{publico, institucional}` |
| `.../conocimiento/embedding.py` | Modify | Sidecar-backed `Embedder` implementation carrying `model_id` **and** `revision` verbatim from the sidecar's report; **`:372` inverts its precedence so the resolved `_commit_hash` wins over a symbolic pin** (G0); no torch import in the app image |
| `.../conocimiento/eval/expected_clasificacion.yaml` | Create | The checked-in expected classification of all **35** documents (class + evidence string), pinned to `corpus_sha`, generated against the private checkout at that SHA. Diffed by the unit suite (11 fixtures) and by runbook step 8 (all 35). **Owner sign-off required in the PR for any edit**, as for `FUENTES_PUBLICAS` and `TIPOS_INSTITUCIONALES` |
| `.../conocimiento/eval/{answers.py,answer_set.yaml,router_set.yaml,umbral_abstencion.yaml,report.py}` | Create/Modify | Answer + router metrics blocks; invented-citation scored against the **post-exclusion payload**; the **end-to-end (post-exclusion) abstention pair** as its own row, pinned to `(corpus_sha, expected_clasificacion_sha256)`; graded artifacts pinned to `(prompt_version, provider_model_pin, corpus_sha)`; the abstention threshold artifact the serving config is seeded from |
| `gee-backend/app/api/v2/__init__.py` | Modify | Mount the router |
| `gee-backend/app/config.py` | Modify | `conocimiento_qa_enabled=False`, `conocimiento_embed_url`, provider key + pinned model, limiter knobs, `conocimiento_quota_diaria_usuario`, `conocimiento_spend_ceiling_usd`, `conocimiento_max_concurrency`, and the three timeouts of G3: `conocimiento_provider_timeout_s`, `conocimiento_request_deadline_s`, `conocimiento_semaforo_timeout_s` |
| `gee-backend/tests/new/conocimiento/test_rag_no_router.py` | Delete | Replaced in the SAME work unit (below) |
| `gee-backend/tests/new/conocimiento/test_rag_ingest_frontmatter.py` | Modify | `test_clasificacion_defaults_to_privado` (`:113-116`) is **replaced** by the source-derived three-class rule, asserted against `expected_clasificacion.yaml` for all 11 checked-in fixtures: `ley-9750`/`ley-10679`/`ley-8548`/`ley-8803`/`decreto-318-2007`/`ley-5589`/`resolucion-4-2026`/`normas-srh-2013` ⇒ `publico` with the matched host recorded; `consorcio-10-de-mayo` ⇒ **`institucional`** (`tipo`); `resolucion-aprhi-004-2026` ⇒ `privado` (Drive/ArcGIS only, `tipo ∉ TIPOS_INSTITUCIONALES`); `informe-f3` ⇒ `privado` (secundaria — asserted to short-circuit **before** host matching, and specifically that `fuentes_externas_verificadas` is never read). Plus label-boundary host tests: `saij.gob.ar.evil.example` and `notsaij.gob.ar` are NOT matched by `saij.gob.ar`, `www.saij.gob.ar` is |
| `gee-backend/tests/new/conocimiento/test_rag_privacy.py` | Modify | `test_the_real_ingestion_path_is_refused_because_everything_is_privado` (`:85-92`) **keeps passing** — it seeds its own rows `{"ley-9750": "privado", "ley-5589": "privado"}` and never calls the ingestion path *(claim corrected, bounded correction 2026-08-23: round 1 said the test "no longer holds", which is false; what stops holding is its **docstring**, which asserts that `documento_row_from_frontmatter` writes `privado` "for every document, with no code path that promotes one")*. Real contract: rewrite that docstring to state what the test now proves — that `assert_public_domain` refuses an all-`privado` snapshot — and add its missing sibling, that a snapshot containing an **`institucional`** document also refuses, since the eval baseline's set stays `publico`-only. `assert_public_domain` keeps its **whole-snapshot refusal** semantics; `assert_unidades_publicas` gets its own tests for the **per-request exclusion** semantics (non-shippable unit dropped, `institucional` unit ADMITTED, payload non-empty ⇒ generation proceeds on the subset, payload empty ⇒ abstención). The two coexist and neither replaces the other |
| `gee-backend/tests/new/conocimiento/test_qa_surface.py` etc. | Create | Gated-surface, routing, enforcement suites |
| `docker/embed/{Dockerfile,requirements-embed.lock,app.py}` | Create | `conocimiento-embed` sidecar. **NOT** built from `requirements-rag.txt` (unpinned ranges + `sentence-transformers`, `requirements-rag.txt:23-33`): its own fully pinned lock, CPU torch, `/embed` + `/health` + `/ready` |
| external `docker-compose.yml` (lives **outside this repo**, see G9) | Runbook step | `conocimiento-embed` service block + `CONOCIMIENTO_EMBED_URL` on the backend |
| `consorcio-web/src/{routeTree.gen.tsx,lib/api/conocimiento.ts,hooks/useConocimientoQA.ts,components/admin/ConocimientoPanel.tsx}` | Modify/Create | CD page; five-state union; finite `staleTime`, no persistence |
| `openspec/changes/.../specs/knowledge-hybrid-retrieval/spec.md` (Privacy Boundary) | Amended — **RATIFIED 2026-08-23**, widened by the sealed product decision the same day | Not a pending prerequisite: the amendment is written, with its five scenarios. The per-unit condition now reads `clasificacion ∈ {publico, institucional}`; the API-embedding-baseline scenario is untouched and stays `publico`-only |
| `openspec/changes/.../specs/knowledge-answer-generation/spec.md` | Amend | Names `generacion_fallida` in the state union (fix round 1, 2026-08-23); the membership universe is the post-exclusion payload; **"Context is exactly the retrieved page"** is completed to *the retrieved page filtered by the classification gate*, and **"Secundaria citation is labeled"** is scoped, both with dated notes (bounded correction, 2026-08-23) |

## Interfaces

*(Documentary reconciliation, 2026-08-24. This block was written in round 1 and was never revised when the
truncation correction was ratified at `:555-576` and when amendment A3 added `pendiente`. It therefore
contradicted, in the same document, two decisions the prose had already made. Nothing about the ratified
decisions changes here and nothing is rewritten out of history: the superseded signatures are recorded in the
notes below each entry.)*

```python
@dataclass(frozen=True)
class SalidaProveedor:
    """What ONE provider call returned. The `max_tokens` stop reason is a field
    because `:555-576` requires truncation to be distinguished from a transport
    failure and routed down the correction path; a bare `-> str` would force
    that distinction to be re-derived by sniffing the prose, which is the
    model-self-report shortcut G3 forbids everywhere else."""
    texto: str
    truncado: bool = False


class Generador(Protocol):
    model_id: str
    sintetico: bool                     # a stand-in; refused by the serving and
                                        # eval-publish gates, as for the reranker
    def generar(self, prompt: str, *, max_tokens: int) -> SalidaProveedor: ...

# SUPERSEDED (round 1): `def generar(self, prompt: str, *, max_tokens: int) -> str: ...`
# Superseded by the ratified truncation correction at :555-576 (2026-08-23), which
# this block had not yet absorbed. Recorded 2026-08-24.


class GeneracionTransporte(RuntimeError):
    """Timeout / connection / 5xx — the call did NOT complete. Does NOT consume
    the regeneration attempt; retried inside a small transport budget and, if it
    persists, terminal as `generacion_fallida` — never as `abstencion`.

    Truncation is NOT here (bounded correction, 2026-08-23): a `max_tokens` stop
    reason means the call COMPLETED. It is an enforcement violation, consumes
    the single regeneration attempt, and its retry raises `max_tokens` or trims
    the payload rather than replaying the identical request. See G3."""


CLASIFICACIONES_ENVIABLES: frozenset[str] = frozenset({"publico", "institucional"})
#: The shippable set, defined ONCE and shared by the ingest rule and the
#: per-request gate. `assert_public_domain`'s eval baseline deliberately does
#: NOT use it — that gate stays `publico`-only (G2).


@dataclass(frozen=True)
class PayloadGeneracion:
    """The POST-EXCLUSION context. Every downstream check binds to THIS."""
    claves: frozenset[str]              # subset of the retrieved set
    unidades: tuple[CitaRecuperada, ...]
    claves_excluidas: frozenset[str]    # not in CLASIFICACIONES_ENVIABLES,
                                        # dropped before any external call
    @property
    def vacio(self) -> bool: ...        # empty ⇒ abstención, never a provider call


@dataclass(frozen=True)
class RespuestaConocimiento:
    """One response. `estado` is the LEGAL leg and is mutually exclusive across
    its SIX values; `redireccion_parcial` is ORTHOGONAL to it and is present on
    ANY state when the router classified `mixto` (G5, bounded correction
    2026-08-23). `estado='redireccion'` is the PURE redirect and never carries a
    partial one.

    The invariants run in both directions: the five non-answer states carry no
    prose and no citations, and `respuesta` carries BOTH, non-empty. An
    answer-shaped item with neither is the one shape the panel must never
    render, so it is unconstructible rather than merely undocumented."""
    estado: Literal["pendiente", "respuesta", "abstencion", "redireccion",
                    "generacion_fallida", "no_disponible"]
    redireccion_parcial: Redireccion | None = None

# SUPERSEDED (round 1): the same union without `pendiente`, described as five values.
# Superseded by amendment A3, which this block had not yet absorbed. Recorded 2026-08-24.


@dataclass(frozen=True)
class VerificacionCitas:
    claves_citadas: frozenset[str]
    claves_inventadas: frozenset[str]   # cited but NOT in the payload (an excluded
                                        # unit's key counts as invented)
    afirmaciones_sin_cita: tuple[str, ...]
    marcadores_faltantes: tuple[str, ...]   # cited non-vigente / secundaria unit
                                            # served without its marker fields
    truncado: bool = False              # `max_tokens` stop reason (:555-576)
    sin_contenido: bool = False         # blank draft. Every other check passes
                                        # VACUOUSLY on empty text, so without
                                        # this an empty response certifies
    @property
    def acepta(self) -> bool: ...       # all five clear

# SUPERSEDED (round 1): the same dataclass without `truncado`/`sin_contenido`, with
# `acepta` documented as "all three empty". Recorded 2026-08-24.


def assert_unidades_publicas(
    db: Session, corpus_sha: str, claves: Sequence[str]
) -> frozenset[str]: ...                # returns the SHIPPABLE SUBSET
                                        # (clasificacion IN CLASIFICACIONES_ENVIABLES);
                                        # never raises on a non-shippable unit —
                                        # exclusion, not refusal
```

## Testing Strategy

| Layer | What | How |
|---|---|---|
| Unit (no DB, CI) | rule lexicon; `mixto` top-2 signature; centroid margin + LOOCV; **three-class `clasificacion` derivation** (secundaria short-circuits before host matching; `TIPOS_INSTITUCIONALES` by `tipo`; label-boundary host suffix vs substring; the 11 fixtures diffed against `expected_clasificacion.yaml`); **revision canonicalization** (a symbolic pin and its resolved hash compare EQUAL, two hashes compare unequal, a non-resolvable ref refuses); citation parsing; **key-membership against the PAYLOAD** (an excluded unit's key is invented; an `institucional` unit's key is NOT); sentence segmentation + boilerplate exclusion list; vigencia/secundaria marker check; retry-budget exhaustion → abstención; **truncation consumes the regeneration attempt and its retry changes `max_tokens`/payload rather than replaying**; transport failure → `generacion_fallida` **and not** abstención | pytest, `GeneradorDeterministico` fixtures. **Mutation targets** (per `openspec/config.yaml`): `routing.py`, `generacion.py`, `eval/answers.py` |
| Contract (no DB) | the **five `estado` values** never overlap **with each other**; `redireccion_parcial` is representable on `respuesta`, `abstencion`, `generacion_fallida` and `no_disponible`, and is absent on `estado='redireccion'`; `generacion_fallida` carries no prose; refusals map to 503 and never to prose | pytest + Pydantic |
| Integration (real PG, `tests/new/`) | 401 anonymous / 403 `operador` & `ciudadano` / 503 flag-off-for-admin; **503 sidecar-not-ready, and NOT a redirect**; `EmbeddingsNoCargadas` → 503; `EmbedderMismatch` on a matching `model_id` with a **divergent resolved `revision_hf`**, and **NO** mismatch when one side holds a symbolic pin resolving to the other's hash; operational question makes **zero** retrieval calls (spy); one question ⇒ **exactly one** sidecar embed call (spy); per-unit exclusion drops the non-shippable unit, **keeps the `institucional` one**, and abstains when exclusion empties the context; a `mixto` question returns ONE response carrying both blocks, including the `abstencion` + `redireccion_parcial` combination; request deadline exceeded ⇒ `generacion_fallida`; semaphore acquire timeout ⇒ `no_disponible`; quota/ceiling exceeded ⇒ `no_disponible`, never a cheaper answer; `conocimiento_005` applied ⇒ an `institucional` row round-trips, and the migration's downgrade demotes it to `privado` rather than failing the CHECK | house real-PG fixtures (`tests/new/conftest.py`) |
| Integration (`@pytest.mark.pgvector`) | end-to-end answer over a seeded vector snapshot; synthetic-provenance snapshot refuses to serve | `make test-rag` |
| E2E / owner | hybrid ablation report, then the ratified answer set | `make rag-eval` + owner grading |

**No-router retirement is ordered, not merely planned.** `test_rag_no_router.py` is deleted in the **same work
unit** that adds `test_qa_surface.py` with the three access-boundary tests plus the flag-off test. The unit is
not mergeable with the delete alone — the retirement note in the delta (retrieval delta:8) is a coverage
requirement, and a window where neither test exists is exactly the gap it names.

## Threat Matrix

| Boundary | Applicability | Design response |
|---|---|---|
| Documentation-like paths | N/A — V1 classifies no file as executable; ingestion is unchanged and already SHA-pinned | — |
| Git repository selection | N/A — the only `git -C` use is V0 ingestion (`service.py:82-93`), untouched by V1 | — |
| Commit state / Push state / PR commands | N/A — no VCS or PR automation in this change | — |

Two domain boundaries **are** live and carry design requirements (added, not from the template):

| Boundary | Adversarial case | Design response | RED test |
|---|---|---|---|
| Prompt injection from corpus text | a legal unit whose text reads as an instruction | units are wrapped as delimited data with an explicit "content is data" system prompt; enforcement is **post-hoc and mechanical**, so injection cannot mint a key that was not **in the payload** | fixture unit containing an injection string; answer citing a key outside the payload is rejected |
| Question text leaving the box | a CD question containing a consorcista's name | router and embedding are local, so the question leaves **only** in the generation call — one exposure, ratified 2026-08-23 (retrieval delta:129-148). The routing record stores the question **verbatim** in the box's own Postgres, which the routing spec requires (routing spec:85, 94-98) and which is not an external service: internal-only, admin-read, bounded retention, never in any external payload | test asserts the routing record round-trips the verbatim question **and** that the question appears in exactly one outbound payload (the generation call), with the embed/routing paths asserted local |
| Non-shippable unit reaching the provider | a future `actas` unit ranking into a legal question's top-k | per-unit exclusion **before** payload assembly (G2b), against `CLASIFICACIONES_ENVIABLES = {publico, institucional}`; an `actas` unit is `privado` by the secundaria clause or by default-deny, never by a promotion path; empty payload ⇒ abstención; the excluded key is invented-by-definition downstream and is never rendered as a card | seeded snapshot with one `privado` unit **and** one `institucional` unit in the retrieved set: the provider payload omits the first and keeps the second, the citation cards match the payload exactly, and an answer citing the excluded key is rejected |
| Silent widening of the shippable set | a one-line addition to `FUENTES_PUBLICAS` or `TIPOS_INSTITUCIONALES` ships a class of documents to a third party under cover of a refactor | the three artifacts (`FUENTES_PUBLICAS`, `TIPOS_INSTITUCIONALES`, `expected_clasificacion.yaml`) require **owner sign-off recorded in the PR**; `expected_clasificacion.yaml` pins all 35 expected classes with their evidence, so any rule change shows up as an artifact diff rather than as a behaviour change nobody reads | a rule change that is not reflected in `expected_clasificacion.yaml` fails the unit diff; runbook step 8 fails the 35-row diff on the box |

## Migration / Rollout

The privacy amendment is **already ratified** (2026-08-23) and is therefore not a gate on this sequence; what
remains gated is the measurement.

O.3 + 4.14 → publish the hybrid arm against the FTS baseline → owner ratifies the retrieval thresholds, the
answer set, the router set and the router numeric bar → ship the code with the flag off → the G9 runbook,
whose first substantive step is **deploying and health-verifying the sidecar** and whose seventh is
**re-running ingest so the 35 rows are reclassified** → smoke → flip the flag. Rollback per G9's sealed order.

## Open Questions

- [x] ~~Privacy amendment wording and owner ratification~~ — **RATIFIED 2026-08-23**, written into
  `specs/knowledge-hybrid-retrieval/spec.md:129-173` with per-unit exclusion semantics. No longer a blocker.
- [x] ~~Which classes may travel to the hosted provider~~ — **SEALED 2026-08-23**: published public law
  (gazette/registry-sourced) **and** the consorcio's own normative instruments (`institucional`). Technical
  reports and every other fuente secundaria stay private. Written into G2a as the three-class rule.
- [ ] Owner ratification of the **`FUENTES_PUBLICAS` host allowlist** and of **`TIPOS_INSTITUCIONALES`**
  (G2a). The rule is deterministic; which hosts count as official publication, and which `tipo` values are the
  consorcio's own instruments, are judgments the owner makes once and the code then obeys. Ratify against the
  **generated `expected_clasificacion.yaml`**, not against the allowlist in the abstract — the artifact is
  where "these 35 documents land in these 35 classes" becomes reviewable. It also settles the one open
  residual: whether `resolucion-dipas-395-2004-linea-ribera-provisoria` carries a `FUENTES_PUBLICAS` host, and
  therefore whether gold item C-8 is fully or only partially grounded.
- [ ] Concrete values for the three G3 timeouts (`conocimiento_provider_timeout_s` 20 s,
  `conocimiento_request_deadline_s` 60 s, `conocimiento_semaforo_timeout_s` 5 s are proposals) — the first
  is re-derived against the pinned provider's published p99, the second against the CD's tolerance.
- [ ] Owner ratification of the **router numeric bar** (G1): `operational → legal` ≤ 0.05, overall accuracy
  ≥ 0.85, labeled set n ≥ 40 with a 10-per-class floor.
- [ ] Provider/model pin, the re-derived per-query cost from current published pricing, **and the provider's
  published data-retention / no-training terms** recorded next to the pin (G2c).
- [ ] Concrete values for `conocimiento_quota_diaria_usuario` and `conocimiento_spend_ceiling_usd`.
- [ ] CPU query-embedding latency on the box (`scripts/rag_query_latency.py`), which sets the end-to-end budget.
- [ ] Sidecar RAM + cold-start measurement on the box (G0), before the runbook's step 2 is attempted.
- [ ] Size of the answer set (n ≥ 30 **answers** proposed) and the retention window for the routing record
  (90 days proposed).

---

## Amendment (2026-08-23, owner-ratified): retrieval architecture and bars re-ratified from measurement

The empirical campaign (`docs/rag/candidate-recall-campaign-2026-08-23.md`, 5 passes / 116 configurations,
plus `docs/rag/reranker-experiment-2026-08-23.md`) closed the retrieval question this design had left gated.
The owner ratified the following, superseding the earlier bar values and the vector-primary retrieval shape
wherever this document assumes them:

**Retrieval architecture (config `B50`)**
- Candidate generation: **real BM25** (with IDF — Postgres `ts_rank_cd` is NOT acceptable: measured 0.655 vs
  0.759) over norma-only units, top-50. Implemented as an in-process postings-list index built from the
  lexemes already stored in `tsv` (measured: 0.14 s build, ~2 MB, ~0.5 ms/query).
- The vector leg is **dropped from candidate generation**. Measured basis: the exhaustive ceiling
  (cross-encoder over all 1398 norma units, pool recall 1.0 by construction) scores 0.724 — BELOW B50's
  0.759 — so candidate recall is solved and the bounded pool doubles as a precision filter.
- Ranking: `bge-reranker-v2-m3` over the 50 candidates, fp16 on GPU. Honest latency budget 0.75–1.0 s/query
  (mean over the full gold set; the earlier 0.581 s figure was a single-question timing). GPU or hosted
  endpoint remains a hard serving requirement (measured CPU: 98.9 s/query on an i7-12700K).
- The `es_secundaria` exclusion stays load-bearing (without it the cross-encoder collapses
  norma-vs-secundaria to 0.483). Lexical signals must NEVER blend into the cross-encoder score
  (RRF −0.035/−0.069; CE×lexical fusion −0.104/−0.207, monotone in blend weight); lexical lives in
  candidate generation only. A per-document cap is REJECTED (it lifts hit@5 to 0.793 but collapses
  vigencia-correctness to 0.333).

**Re-ratified bars (owner decision, 2026-08-23)**
- hit@5 ≥ 0.72 · hit@10 ≥ 0.80 · MRR ≥ 0.55 · citation-precision ≥ 0.33 (=1.00 is unreachable by
  construction on this gold set) · norma-vs-secundaria = 1.00 · vigencia-correctness = 1.00 (both now
  measured clear at B50; they must not regress).
- Abstention bars remain an OPEN owner decision ("decidir después"): the reranker-confidence signal is
  measurably worse than cosine (LOOCV precision 0.489 at recall 1.000); options on the table are relaxing
  recall to ≥0.90 or a different signal (none-of-the-above candidate / entailment check). Tasks must carry
  this as a named open question, not silently pick one.

**Honesty rider**: the gold set is 29 answerable questions and 116 configurations were tried against it;
one question is worth 0.034 hit@5. The B50 family reads as ≈0.72–0.76. Growing the gold set is the next
measurement step; re-chunking the 10 oversized units (max 58,619 chars; the reranker truncates at 1024
tokens) is the principled lever for the remaining knife-edge miss and may be scheduled as follow-up work,
not as an apply gate.

---

## Amendment (2026-08-23, owner-ratified): Phase-0 decisions — async queue model, provider pin, allowlist

The owner ratified the Phase-0 block on 2026-08-23. This appendix records the decisions verbatim in their
effect on the design and names, with anchors, every body section they supersede. Where this appendix and the
body disagree, this appendix wins. **Decision 0.1 (abstention policy) remains explicitly OPEN by owner
decision ("decidir después") and nothing here touches it.**

### A1 — Decision 0.2: `FUENTES_PUBLICAS` gains two hosts, and an INDEX URL stops establishing publication

**Supersedes** the allowlist literal in G2a (`design.md:335-342`), the fixture evidence table
(`design.md:352-364`), the corpus-wide floor paragraph (`design.md:366-374`), the C-8 residual
(`design.md:422-430`) and the corresponding Open Question (`design.md:1096-1102`).

Two hosts are added to `FUENTES_PUBLICAS`:

| Added entry | Why the owner ratified it |
|---|---|
| `boletinoficial.gob.ar` | The **national** Boletín Oficial. An official gazette is an official gazette; the allowlist previously carried only the provincial gazette (`boletinoficial.cba.gov.ar`), which classified nationally-gazetted norms as `privado`. |
| `justiciacordoba.gob.ar` | The judiciary of Córdoba — the official site of the provincial state. |

The full ratified list is therefore: `saij.gob.ar`, `boletinoficial.cba.gov.ar`, `boletinoficial.gob.ar`,
`web2.cba.gov.ar`, `www.cba.gov.ar`, `legislaturacba.gob.ar`, `aprhi.gob.ar`, `infoleg.gob.ar`,
`justiciacordoba.gob.ar`. The label-boundary suffix semantics of `design.md:327-333` are **unchanged** and
still govern how an entry matches a host.

**New rule — an INDEX/landing URL does not establish publication.** A `fuente_url` entry that points at a page
which *lists* documents (e.g. `https://www.aprhi.gob.ar/normativas/`) is **not** evidence that the document was
published there. Only a URL that resolves to a **concrete document** participates in the allowlist match. The
host allowlist is thus a necessary but no longer sufficient condition: the entry must be both an allowlisted
host **and** a concrete-document URL.

**The exclusion mechanism is an implementation decision belonging to U1, not an owner decision.** Either a
named checked-in list (`INDICE_NO_PUBLICACION`) of exact index URLs, or a documented heuristic, is acceptable;
whichever U1 picks must be a checked-in artifact with tests, and it falls under the same change-control rule as
`FUENTES_PUBLICAS` itself (`design.md:394-397`) — a quiet edit to it promotes or demotes a document.

**Effect on the corpus at the pinned SHA**, computed in
`gee-backend/artifacts/rag/expected_clasificacion-draft-r2-2026-08-23.yaml` (which supersedes the r1 draft):
**26 `publico` / 1 `institucional` / 8 `privado`** across 35 documents, up from 24/1/10.

- `resolucion-dnv-1898-2025-aranceles-permisos`: `privado` → **`publico`**, via the national gazette entry.
- `resolucion-dipas-395-2004-linea-ribera-provisoria`: `privado` → **`publico`**, via
  `justiciacordoba.gob.ar`. **This closes the C-8 residual named at `design.md:422-430` and in task 1.12 in the
  favourable direction: gold item C-8 is FULLY grounded, not partially.**
- `resolucion-dph-11821-1985-visacion-planos-linea-ribera` stays `publico`, but on **different evidence**: the
  index rule removes its APRHI match and `justiciacordoba.gob.ar` replaces it. Without the new host it would
  have flipped to `privado`.
- `decreto-3780-c-65-obras-cursos-naturales-artificiales` stays `publico` on its `www.cba.gov.ar` PDF after the
  index rule removes its APRHI match — see the judgment note carried in the r2 artifact.
- No document moves toward `privado`.

**Named consequence for the owner:** after the index rule, the `aprhi.gob.ar` entry promotes **zero** documents
at this SHA — every APRHI URL in the corpus is an index or a section landing. The entry stays because the owner
ratified it, but it is inert today.

### A2 — Decision 0.4: the generation provider is pinned to `deepseek-v4-flash` via the opencode-go pool

**Supersedes** G2's provider table and its Claude-class framing (`design.md:204-224`), the
`AnthropicGenerador` naming in G2b (`design.md:455-456`) and in the Interfaces block, and the provider Open
Question (`design.md:1108-1109`).

- Model pin: **`deepseek-v4-flash`**, reached through the **opencode-go pool**, routed by **mcp-llm-bridge**.
- The pin lives in **configuration, not code**: changing the model must be a config edit, never a code edit.
  The `Generador` Protocol shape of G2b is unchanged; only the concrete adapter and its name change.
- The cost figures throughout G2c and G3 (`design.md:218`, `:458-470`, `:666-673`) were derived from
  Claude-class list pricing and are **stale by construction**. They must be re-derived against this pin before
  `conocimiento_spend_ceiling_usd` is set; the per-attempt accounting rule (`design.md:671-672`) is unchanged
  and still correct.

**New blocking verification task in U6, before the flag is ever enabled** (added to `tasks.md` as 6.7):

1. verify the **exact model id** as the opencode-go pool exposes it — the pin is worthless if it does not name
   a real route;
2. verify the provider's published **no-training-on-input and retention terms**, and record them next to the
   pin, per the existing rule at `design.md:493-497`.

**If those terms cannot be verified, the flag is not enabled.** This is a fail-closed gate, not a warning: the
ratified privacy amendment permits public law text plus the question to leave the box, and does not permit
either to become training data.

### A3 — Decision 0.5: the product is an ASYNCHRONOUS MAILBOX, not a synchronous answerer

This is the largest supersession in this appendix. The owner's product decision:

> Questions are **queued**. A worker with a GPU — the owner's workstation, when it is available — processes
> them **in batches**. The answer becomes visible when it has been processed; until then the question shows an
> honest **"pendiente"** state.

This resolves the reranker-serving decision that `tasks.md` 0.5 posed (GPU host / hosted endpoint /
flag-off): the GPU host is the owner's workstation, and its intermittent availability is absorbed by the queue
rather than by the request.

**What it supersedes, by anchor:**

| Body section | Anchor | Disposition under the queue model |
|---|---|---|
| End-to-end latency budget: the 60 s deadline, the ≥ 87 s arithmetic worst case, the "aborted at 60 s" observed case | `design.md:614-664` | **No longer a serving gate.** These become the **worker's processing budget** for one queued item. A worker that exceeds it fails that item to `generacion_fallida`; no CD member is waiting on a socket while it runs. |
| The three timeout knobs, `conocimiento_provider_timeout_s` / `conocimiento_request_deadline_s` / `conocimiento_semaforo_timeout_s` | `design.md:619-629` | The first two survive as **worker-side** knobs. `conocimiento_request_deadline_s` is renamed in effect to a per-item worker deadline — it no longer bounds an HTTP request. |
| In-flight semaphore and its 5 s acquire timeout ⇒ `no_disponible` | `design.md:466-470`, `:489-491`, `:625` | **Replaced by the queue.** Saturation is now expressed as queue depth and a longer wait, not as a refusal at the door. The per-process/2-worker honesty note is moot: the worker's own concurrency is the bound. |
| `503 reranker_no_disponible` when GPU/hosted reranking is absent | `design.md:1132-1134`, task 7.3 | **Replaced by the queue state.** A GPU that is not currently available is the normal case, not an outage: items stay `pendiente`. Only a *permanently* misconfigured worker is an operational fault, and it surfaces on the diagnostic endpoint, not as a per-question 503. |
| G5 HTTP surface: `POST /preguntas` returning the answer, five-state union in the response body | `design.md:699-752` | **Restructured into submit → id → status.** See below. |
| G6 page: a panel that asks and renders an answer | `design.md:754-775` | **Becomes a mailbox (bandeja):** question, state, answer when present. See below. |

**The new HTTP shape (U7).** `POST /api/v2/conocimiento/preguntas` **enqueues** and returns an identifier plus
the initial state; it never carries an answer. A second surface returns the state of one item, and a listing
surface returns the requester's items. The dependency order of `design.md:702-703` is otherwise unchanged
(`enforce_qa_enabled → require_admin → enforce_body_limit → enforce_qa_rate_limit → enforce_qa_quota`), minus
the in-flight slot.

**The five-state union survives, and gains one state.** The states of `design.md:711-749` are *item* states
now, not response states: `respuesta`, `abstencion`, `redireccion`, `generacion_fallida`, `no_disponible` —
plus **`pendiente`** (queued, not yet processed) as the initial state of every item. The orthogonal
`redireccion_parcial` block is unchanged and still orthogonal. A pure `redireccion` may be answered
**synchronously at submit time** when routing is available, because routing needs no GPU — but that is an
optimisation, not a contract, and the honest default is to enqueue.

**Cost and privacy invariants are unchanged by the queue.** The per-request privacy gate
(`assert_unidades_publicas`, G2b), the payload-bound citation enforcement (G3), the one-regeneration budget,
the per-user quota and the global spend ceiling all move to the worker and keep their semantics exactly. In
particular, the classification is verified **at processing time**, which is strictly the same discipline G2d's
no-cache decision (`design.md:499-514`) was protecting.

**One new honesty obligation the synchronous design never had:** a queued item must not sit `pendiente`
forever with no explanation. The item state carries a timestamp and, when the worker has not run for longer
than a configured window, the surface says so rather than showing an indefinite spinner. "Pendiente" is only
honest while it is true.

### A4 — Decision 0.3: the router labeled set is drafted, then ratified; the bar is fixed AFTER measuring

**Supersedes** the numeric-bar Open Question (`design.md:1106-1107`) in its ordering, not in its content.

The orchestrator drafts **~40–50 labeled questions** and the owner ratifies that set. The router's numeric bar
is **fixed only after measuring on the ratified set** — the proposed figures at `design.md:175-186`
(`operational → legal` ≤ 0.05, overall ≥ 0.85) remain *proposals* and must not be written into code or into
`eval/` before that measurement. Setting a bar before measuring is how a gate gets set to whatever the system
already does.

### A5 — Decision 0.6: ratified as proposed

The answer set is **n ≥ 30 answers** and the routing-record retention window is **90 days** — the figures
already proposed at `design.md:1113-1114`, `design.md:196` and `design.md:783`, now ratified rather than
proposed. No design change; the Open Question closes.

### A6 — What remains open

- **0.1 abstention policy** — explicitly deferred by the owner. The amendment at `design.md:1145-1148` stands
  unchanged: reranker confidence is a measurably worse signal than cosine, the options are relaxing recall to
  ≥ 0.90 or building a different signal, and **no task may pick a side**. U9's abstention row stays
  `not-evaluable` and the surface is not enabled.
- Concrete values for `conocimiento_quota_diaria_usuario` and `conocimiento_spend_ceiling_usd`, now blocked on
  the A2 cost re-derivation against `deepseek-v4-flash`.
- The two box measurements (`design.md:1111-1112`) survive the queue model with a smaller blast radius: they
  now size the worker, not a user-facing deadline.
