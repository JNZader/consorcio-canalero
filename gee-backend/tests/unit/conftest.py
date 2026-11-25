"""Minimal environment defaults for hermetic unit tests."""

import os

os.environ.setdefault("UPLOADS_ROOT", "/tmp/consorcio-unit-uploads")
# app.main also makedirs(documentos_root) at import; default /app/documentos
# is not writable on the GitHub runner (same trap as uploads_root).
os.environ.setdefault("DOCUMENTOS_ROOT", "/tmp/consorcio-unit-documentos")
