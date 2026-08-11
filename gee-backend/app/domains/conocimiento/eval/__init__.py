"""Offline evaluation for the conocimiento retrieval layer (design.md D6).

**Import rule, and it is a design rule rather than a preference (D4).** Nothing
in this package may import `repository` directly. Retrieval enters through
`service.recuperar`, which is where the three refusals that keep a measurement
honest live: `EmbeddingsNoCargadas` (this snapshot was never embedded),
`EmbedderMismatch` (the query embedder is not the one that wrote the column) and
the capability check underneath them. `repository.vector_search` raises only the
last of the three — it receives a query vector, not an embedder, so it cannot
know which model produced the column it is searching. A harness that called it
directly would happily rank a real BGE-M3 corpus with the deterministic smoke
embedder and publish 50 confident, fully attributed, entirely fabricated hits as
a measurement.

`test_rag_eval_harness.py::TestServiceLayerBoundary` asserts this over the
package's real import graph, so the rule cannot decay into a comment.
"""
