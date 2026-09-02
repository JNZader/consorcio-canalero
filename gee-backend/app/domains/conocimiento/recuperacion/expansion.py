"""Query rewrite that runs BEFORE BM25 and the cross-encoder, never after.

The serving question "¿La APRHI nos puede intervenir? ¿Por cuánto tiempo?"
(gold `9750#42`) names APRHI. Ley 9750 never does — Art. 42 names the
Autoridad de Aplicación, Art. 2 names the Subsecretaría de Recursos Hídricos
or its successor. On snapshot `12043582bf8016288a7e8084e85a4b713a97af2f`
that gap measured:

* BM25 rank 13 (inside B50, outside K=10) with query lexemes
  `aprhi,cuant,interven,pued,tiemp` overlapping the gold TF only on
  `interven=2.0`;
* CE rank 27 on the same pool, because `bge-reranker-v2-m3` prefers the
  9867 APRHI-organic units that literally contain the acronym;
* appending "Autoridad de Aplicación" (keeping APRHI) moved BM25 13→4 and
  CE 27→0. Replacing APRHI, or adding plazo/término/seis meses, also CE
  rank 0.

This module is that append. It is NOT a synonym table, NOT a blend of BM25
into the CE score (ratified unblended, `design.md:1136-1138`), and NOT a
rewrite of the user-facing question: `_recuperar_bm25_ce` expands a copy
for retrieval; `ResultadoRecuperacion.pregunta` and the generator keep the
original. The fused ablation arms (`fts`/`vector`/`hybrid`) do not call it,
so their published numbers stay comparable.

Rewriting the 2010 unit to say APRHI is out of scope: that would be
adulterating the text.
"""

from __future__ import annotations

import re

_MARCADOR_APRHI = re.compile(r"\baprhi\b", re.IGNORECASE)
_YA_EXPANDIDA = re.compile(
    r"autoridad\s+de\s+aplicaci[oó]n",
    re.IGNORECASE,
)
_EXPANSION_APRHI = "Autoridad de Aplicación"


def expandir_consulta_recuperacion(pregunta: str) -> str:
    """Return the retrieval query. Identity when the acronym is absent.

    Idempotent: a question that already names the Autoridad de Aplicación
    is returned unchanged, so a second pass cannot stack the phrase.
    """
    if not _MARCADOR_APRHI.search(pregunta):
        return pregunta
    if _YA_EXPANDIDA.search(pregunta):
        return pregunta
    return f"{pregunta.rstrip()} {_EXPANSION_APRHI}"
