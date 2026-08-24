# Provider terms verification — the pre-enablement gate (task 6.7)

The generation surface is pinned to **`deepseek-v4-flash` through the opencode-go
pool, routed by mcp-llm-bridge** (amendment A2, owner decision 0.4). The ratified
privacy amendment permits public law text plus the CD member's question to leave
the box. It does **not** permit either of them to become training data.

So the pin is not complete until two things are verified against reality, and
until they are, **the feature flag does not turn on**. This is fail-closed: not a
warning, not a log line, not a TODO. `verificar_terminos` refuses.

## What code does and what code cannot do

| | Owner | Code |
|---|---|---|
| Read the pool's model list and confirm the exact id | ✅ | ❌ |
| Read the provider's published terms | ✅ | ❌ |
| Refuse to enable when nobody did the above | ❌ | ✅ |

`app/domains/conocimiento/proveedores.py` holds the mechanism:
`cargar_terminos` reads the record and `verificar_terminos` refuses unless it
verifiably covers **this** `(conocimiento_modelo, conocimiento_pool)` pair. The
record lives at `app/domains/conocimiento/proveedor_terminos.yaml`, next to the
pin and checked in, so a later silent terms change is a diff rather than a
discovery.

A machine cannot do the verification part. It can only refuse to pretend it was
done, which is what it does today: the shipped record is `verificado: false`.

> **Where the gate is called from — read this before enabling anything.** As of
> 2026-08-24 `verificar_terminos` is called by tests and by **nothing on the
> serving path**. U6 built the mechanism; the consumer is the first ANDed fact of
> the feature-flag dependency and lands with **task 7.2**, as
>
> ```python
> verificar_terminos(
>     cargar_terminos(),
>     modelo=settings.conocimiento_modelo,
>     pool=settings.conocimiento_pool,
> )   # ⇒ 503 base_de_conocimiento_no_lista, cause `terminos_no_verificados`
> ```
>
> Until that lands, this gate guards nothing: flipping `conocimiento_qa_enabled`
> to `true` today would serve questions with the record still unverified, and the
> only thing enforcing A2's "if those terms cannot be verified, the flag is not
> enabled" would be somebody remembering. **Do not enable the flag before 7.2.**

## Procedure

### 1. The exact model id, as the pool actually exposes it

A pin that does not name a real route is worthless — the failure arrives as a
provider error on the first real question, long after everyone believed the pin
was settled.

Bring the bridge gateway up and ask it, rather than trusting a blog post or this
document:

```
cd ~/programacion/mcp-llm-bridge && LLM_GATEWAY_PORT=3456 pnpm serve
curl -s http://127.0.0.1:3456/v1/models
```

Record the id **verbatim** as it appears there. If it differs from
`conocimiento_modelo`, the fix is the env var — never a code edit
(`proveedores.py` writes no model name anywhere).

### 2. The published terms

Find the provider's published terms for **API traffic** (not the consumer chat
product — they routinely differ, and the consumer one is usually the permissive-
to-the-vendor one). Two criteria, both hard:

- **No training on input.** A provider that trains on inputs is ineligible
  regardless of price or latency. There is no compensating control: once the
  question is in a training corpus, no configuration takes it out.
- **A bounded retention window**, in days. "They keep it for a while" is not a
  retention term. `0` is a legitimate value and means the provider publishes that
  it retains nothing.

  **Upper bound: 1095 days** (`proveedores.RETENCION_MAX_DIAS`, three years).
  Beyond it the record refuses. A very large number is not a bounded window with
  a big value in it; it is indefinite retention written in days, and the
  questions a CD member asks about their own consorcio are not archive material
  for the provider. If a provider's published term is genuinely longer and the
  pin is still wanted, that is a decision to take and to raise the constant
  with — not a value to slip past a type check.

Note that the pool is an intermediary: verify the terms of the operator that
actually receives the traffic. The same model id behind a different pool is a
different operator, different terms and different retention — which is why the
record pins the pool too and the gate checks it.

### 3. Record it, with evidence

Fill `proveedor_terminos.yaml` and flip `verificado: true` **in the same commit**:

```yaml
modelo_id: <verbatim from /v1/models>
pool: opencode-cli
verificado: true
verificado_el: "YYYY-MM-DD"
verificado_por: <name>
fuente_url: <URL of the terms you actually read>
sha256_terminos: <sha256 of that text as read>
no_entrenamiento: true
retencion_dias: <integer>
```

All four evidence fields are required and their absence refuses. A record nobody
can audit is a claim, not a verification.

Get the digest from the text you read, not from a summary of it:

```
curl -s <fuente_url> | sha256sum
```

### 4. Flip the test that guards the gate

`test_el_registro_que_esta_hoy_en_el_repo_no_habilita_el_flag` in
`tests/new/conocimiento/test_costos.py` asserts that today's record refuses. That
test is **meant to be edited**, once, by whoever performs this procedure: turning
it into its positive form is the visible diff in which the verification is
claimed, with the owner's name in the record beside it.

Nothing else in the suite changes. If flipping the record makes any other test
pass that was failing, something was depending on the gate being closed and that
is a finding, not a nuisance.

## Re-verification

The record is a snapshot of published terms, and published terms change. Re-run
this procedure when any of these happen, and treat a change in the digest as a
change in the terms until proven otherwise:

- the model pin changes (`conocimiento_modelo`);
- the pool changes (`conocimiento_pool`) — different operator, different terms;
- `sha256_terminos` no longer matches the live document.
