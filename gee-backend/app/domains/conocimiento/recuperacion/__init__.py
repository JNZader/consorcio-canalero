"""The B50 retrieval path: real BM25 candidate generation + cross-encoder ranking.

This package exists because the measured campaign
(`docs/rag/candidate-recall-campaign-2026-08-23.md`, 5 passes / 116
configurations, plus `docs/rag/reranker-experiment-2026-08-23.md`) closed the
retrieval question the V0 design had left open, and closed it AGAINST the shape
V0 built:

* candidate generation is **real BM25 with IDF**, not `ts_rank_cd` — measured
  0.759 vs 0.655 hit@5, a 0.104 gap that is three gold questions wide;
* the **vector leg is out of candidate generation** — the exhaustive ceiling
  (cross-encoder over all 1398 norma units, pool recall 1.0 by construction)
  scores 0.724, BELOW B50's 0.759, so candidate recall is not the bottleneck and
  the bounded pool doubles as a precision filter;
* ranking is `bge-reranker-v2-m3` over those 50 candidates and **nothing lexical
  ever enters its score** (RRF −0.035/−0.069; CE×lexical −0.104/−0.207, monotone
  in the blend weight).

The legacy `fts` / `vector` / `hybrid` modes in `service.recuperar` are NOT
deleted: they are the published ablation this path is measured against, and an
ablation whose baseline arm no longer runs is a claim, not a comparison.
"""

from __future__ import annotations

from app.domains.conocimiento.recuperacion.bm25 import (
    BM25_B,
    BM25_K1,
    PROFUNDIDAD_CANDIDATOS,
    IndiceBM25,
    IndiceVacio,
    construir_indice,
    lexemas_de_consulta,
    limpiar_cache_indices,
    obtener_indice,
)
from app.domains.conocimiento.recuperacion.expansion import expandir_consulta_recuperacion
from app.domains.conocimiento.recuperacion.reranker import (
    MAX_LENGTH,
    MODELO_RERANKER,
    REVISION_RERANKER,
    BGEReranker,
    Candidato,
    Reranker,
    RerankerDeterministico,
    RerankerNoDisponible,
    ordenar_por_ce,
)

__all__ = [
    "BGEReranker",
    "BM25_B",
    "BM25_K1",
    "Candidato",
    "IndiceBM25",
    "IndiceVacio",
    "MAX_LENGTH",
    "MODELO_RERANKER",
    "PROFUNDIDAD_CANDIDATOS",
    "REVISION_RERANKER",
    "Reranker",
    "RerankerDeterministico",
    "RerankerNoDisponible",
    "construir_indice",
    "expandir_consulta_recuperacion",
    "lexemas_de_consulta",
    "limpiar_cache_indices",
    "obtener_indice",
    "ordenar_por_ce",
]
