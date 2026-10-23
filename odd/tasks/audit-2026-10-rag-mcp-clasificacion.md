# audit-2026-10-rag-mcp-clasificacion

Minimal hardening for audit finding RAG-1 (WARNING, 2026-10): the norms kernel
served private-classified units unlabeled on its main path, and the MCP mirror
advertised itself as plain "read-only access" with no private-content warning.
Scope = labeling + warnings only.

## In

- [x] `UnidadNorma` (and thus `UnidadNormaOrdenada`) carries a REQUIRED
  `clasificacion` field, populated end-to-end from the document classification:
  `repository.HYDRATE_SQL` now selects `d.clasificacion`, so every
  `CitaRecuperada` hit is labeled at hydration and `normas.buscar` picks the
  label up through the existing `model_validate` wrap (no kernel code change
  needed). Route, CLI and MCP get it via the shared kernel ("One Code Path").
- [x] `CitaRecuperada` carries the same required `clasificacion` (single source
  of truth for the label; all real paths hydrate from the DB where the column is
  NOT NULL). Manual test constructions updated (6 files).
- [x] `UnidadLeida.clasificacion` moved UP to `UnidadNorma` (leer was already
  labeled; behavior unchanged, guard test added that the field stays required).
- [x] Generation boundary untouched: `assert_unidades_publicas` still re-reads
  the classification from the database (DB-authoritative, never trusts the
  hit's copy) and the provider prompt renders named fields only — the new label
  cannot leak into a provider payload. The stale repository comment claiming
  HYDRATE_SQL must never expose `clasificacion` was rewritten.
- [x] MCP mirror (`scripts/rag_normas_mcp.py`): server instructions and tool
  descriptions factored into module constants (`INSTRUCCIONES`,
  `DESCRIPCION_BUSCAR/LEER/CHEQUEAR`) and now warn that results may include
  `privado`-classified units, that each unit carries `clasificacion`, and that
  piping output into a third-party/cloud LLM sends that content to an external
  provider — operator's responsibility. `chequear` (verdict only, no corpus
  text) states the label without the disclosure warning. `description=` kwarg
  verified against the pinned wheel (mcp==2.3.0,
  sha256 dd0c44c0…; `Tool.from_function` resolves `description or fn.__doc__`).
- [x] Kernel spec (`knowledge-norms-kernel`) NOT edited: it does not enumerate
  buscar's response fields (leer's clause already named clasificacion). Surface
  spec (`knowledge-norms-surface`) "Norms Response Schema" DOES enumerate unit
  fields, so the additive `clasificacion` was added there, with the
  labeled-not-filtered statement.
- [x] Tests: kernel labeling (red-checked — fails with AttributeError on
  unfixed code), ranked-shape labeling, `leer` requirement guard, SDK-free
  static assertions on the MCP warning constants. Full MCP suite (26 tests)
  also run WITH the SDK via a throwaway /tmp install: route == CLI == MCP
  equivalence still holds with the new field.

## Out

- Filtering `privado` units BY SURFACE (e.g. MCP or route serving public-only
  while admin CLI keeps full access): owner decision, explicitly left open.
  This packet only labels; it does not filter. The admin HTTP route and the CLI
  legitimately read privado today.
- Restricting MCP authentication beyond possession of DATABASE_URL.
- Abstention/retuning, order policy, anything else in the kernel spec.
