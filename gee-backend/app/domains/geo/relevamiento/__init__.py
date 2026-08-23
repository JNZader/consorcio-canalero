"""Fase B — the field survey of a road segment, and the DEM's guess about it.

Standard domain layout (``CLAUDE.md``): ``models`` / ``schemas`` / ``repository``
/ ``service`` / ``router``. Two rules shape every module here:

* **Append-only.** There is no UPDATE and no DELETE path anywhere in this
  package. A correction is a new row; the previous one stays retrievable.
* **The candidate is never the value.** The DEM guess lives in its own table and
  is labelled a candidate on every surface that shows it.
"""
