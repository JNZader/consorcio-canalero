"""Deterministic slug generator for canal feature IDs.

Slugs back the per-canal layer-id convention in the frontend store
(``canal_relevado_<slug>`` / ``canal_propuesto_<slug>``) so they MUST be:

- lowercase,
- ASCII-only (accents stripped via NFKD decomposition),
- ``[a-z0-9]+`` runs joined by ``-``, with NO leading/trailing dash,
- pure functions — no global state, no I/O.

When the base slug collides with one already in use (common case: seven
"Canal existente (sin intervención)" relevados spread across folders),
``slugify_with_suffix(base, folder, idx)`` appends the slugified folder name
plus a numeric index to disambiguate.  The caller owns the collision counter;
the helper is stateless.
"""

from __future__ import annotations

import re
import unicodedata

_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def slugify(text: str) -> str:
    """Return a URL-safe, lowercase, accent-free slug.

    Empty or whitespace-only input returns an empty string so callers can
    compose ``f"{slug}-{folder}-{idx}"`` without NPE-style surprises.
    """
    if text is None:
        return ""
    # NFKD splits accented characters into base + combining mark; we drop
    # every combining mark so "á" → "a", "ñ" → "n", "ü" → "u".
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    lowered = stripped.lower()
    # Replace any run of non-[a-z0-9] with a single dash, then trim edges.
    collapsed = _NON_ALNUM_RE.sub("-", lowered)
    return collapsed.strip("-")


def slugify_with_suffix(base: str, folder: str, idx: int) -> str:
    """Append a ``-{folder-slug}-{idx}`` suffix to an already-computed base.

    The folder label is slugified too (so "Canal Monte Leña" → "canal-monte-lena").
    When the folder is empty, we still emit the idx to guarantee uniqueness.
    """
    folder_slug = slugify(folder) if folder else ""
    if folder_slug:
        return f"{base}-{folder_slug}-{idx}"
    return f"{base}-{idx}"
