"""Conocimiento domain — RAG corpus schema, ingestion, and retrieval.

No `router.py`: V0 ships no HTTP surface (design.md D8). Every entry point
is a script in `gee-backend/scripts/`, delegating to `service.py` once it
exists (Slice 3).
"""

from app.domains.conocimiento.models import RagCorpus, RagDocumento, RagUnidad

__all__ = ["RagCorpus", "RagDocumento", "RagUnidad"]
