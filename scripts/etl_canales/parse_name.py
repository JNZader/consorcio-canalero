"""Strict-then-fallback parser for the KMZ ``<name>`` metadata string.

Why we do not use ExtendedData
------------------------------
The KMZs authored in Google Earth Pro embed ALL per-canal metadata inside the
``<name>`` string — there is NO ``<ExtendedData>`` block.  The author uses the
middle-dot ``·`` (U+00B7) as a field separator and packs 0-4 of the following
fields, in roughly canonical order:

    [CODIGO] · [DESCRIPCION] · [LONGITUD m] · [PRIORIDAD] [★]

Every field is optional.  Descriptions can themselves contain human noise
(``sin intervención``, ``sujeto a presupuesto``, ``readecuación``) that LOOKS
like a priority but is not.  Priority chunks can also carry trailing ROI notes
after the ``★`` character (``MEDIA-ALTA ★ alto ROI``).

Strategy (single pass on top of chunked splits):

1. Split the name on ``·``.  Each chunk is trimmed.
2. Detect and STRIP the ``★`` star anywhere in the string up front; the
   ``featured`` flag is global.  Anything after the star on the same chunk is
   considered trailing noise and ignored.
3. Walk chunks left-to-right:
   - If chunk 0 exactly matches the codigo shape (``[A-Z]{1,3}\\d{1,2}[A-Z]?``)
     treat it as the codigo; otherwise leave codigo = None.
   - If a chunk (anywhere but position 0, or including 0 when no codigo was
     captured) matches the longitud shape (``\\d[\\d.,]*\\s*m``), capture it.
   - If a chunk matches a canonical priority keyword exactly (after Unicode
     cleanup), capture it.
   - Otherwise append the chunk to the descripcion parts list, preserving
     author order and separating chunks with the original ``·`` so the UI can
     show the original phrasing intact.
4. If NO descripcion chunks survive, fall back to the raw pre-star name.

Spanish numeric notation: ``1.355`` means 1355 (thousands separator), NOT
1.355 decimal.  Every ``\\d[\\d.,]*\\s*m`` match is parsed by stripping ``.``
and treating ``,`` as a decimal.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Canonical priority values the rest of the codebase consumes.  Every entry
# on the LHS is already lower-cased.  Alternative spellings (space vs hyphen,
# accent variations) map to the same canonical RHS.
PRIORIDAD_CANONICAL: dict[str, str] = {
    "alta": "Alta",
    "media-alta": "Media-Alta",
    "media_alta": "Media-Alta",
    "media alta": "Media-Alta",
    "mediaalta": "Media-Alta",
    "media": "Media",
    "opcional": "Opcional",
    "largo plazo": "Largo plazo",
    "largo-plazo": "Largo plazo",
    "largo_plazo": "Largo plazo",
    "largoplazo": "Largo plazo",
}

# The ``·`` character is U+00B7 (middle dot).
SEP: str = "\u00b7"
STAR: str = "\u2605"

# Codigo detector: 1-3 uppercase letters + 1-2 digits + optional uppercase tail.
# Matches N4, E21, S2, S2B.  Bare multi-word strings like "S2 complemento
# opcional (P12)" do NOT match because the whole chunk must be the codigo.
_CODIGO_RE = re.compile(r"^[A-Z]{1,3}\d{1,2}[A-Z]?$")

# Longitud detector: ``\\d[\\d.,]*\\s*m`` at chunk start.  Captures the
# numeric part; a permissive trailing tail is tolerated so chunks like
# ``"468 m"`` and ``"5.916 m"`` both classify (the trailing tail, if any, is
# absorbed into descripcion at the call site).
_LONG_RE = re.compile(r"^(\d[\d.]*)(?:,(\d+))?\s*m\b")

# Parenthesized real-code detector: names like
# ``"S2 complemento opcional (P12) · 5.916 m · sujeto a presupuesto"`` carry
# the TRUE codigo inside the parentheses (``P12``).  The leading ``S2`` is a
# family/group marker the author uses, NOT the canal identifier.  Matches
# ``(P12)``, ``(P14a)``, ``(P14b)``, ``(N3)`` — P-series (propuestas) and
# N-series (norte) for safety.  The parens may carry trailing words the
# author uses to disambiguate sibling alternatives (``(P14a norte)``,
# ``(P14b sur)``); only the leading codigo token is captured, the rest
# stays in the descripcion via the normal chunk walk.  Case-sensitive on
# purpose: ``(p12)`` would be typo drift we want to surface, not silently
# consume.
_PARENTHESIZED_CODE_RE = re.compile(r"\(([PN]\d+[a-z]?)\b")


@dataclass(frozen=True)
class ParsedName:
    """Structured decoding of a KMZ Placemark ``<name>``.

    ``descripcion`` is never ``None`` — when there is literally nothing else
    to say about a canal, the full raw name is used so UI always has a
    readable label.  The 3 metadata slots (``codigo``, ``longitud_declarada_m``,
    ``prioridad``) are ``None`` when absent so callers can discriminate
    presence via identity check, not falsy-string heuristics.
    """

    codigo: str | None
    descripcion: str
    longitud_declarada_m: float | None
    prioridad: str | None
    featured: bool


def _normalize_priority_token(chunk: str) -> str | None:
    """Return canonical priority for a chunk, or ``None`` when unrecognised.

    The chunk must be a priority keyword AND NOTHING ELSE — a chunk like
    ``"readecuación"`` is NOT a priority even though it's a lowercase word.
    """
    if not chunk:
        return None
    # Normalise unicode so "LARGO PLAZO " and "largo  plazo" both reach the
    # same key.  Collapse whitespace runs to single spaces.
    normalized = unicodedata.normalize("NFKC", chunk).strip().lower()
    normalized = re.sub(r"\s+", " ", normalized)
    return PRIORIDAD_CANONICAL.get(normalized)


def _parse_longitud_token(chunk: str) -> tuple[float | None, str]:
    """Parse ``"1.355 m"`` or ``"1.355 m algo"`` → (1355.0, "algo").

    Returns ``(None, chunk)`` when the chunk does not start with a longitud
    token.  Spanish thousands separator ``.`` is stripped; Spanish decimal
    comma ``,`` becomes a Python decimal point.
    """
    match = _LONG_RE.match(chunk)
    if match is None:
        return None, chunk
    integer_part = match.group(1).replace(".", "")
    decimal_part = match.group(2)
    if decimal_part is not None:
        value = float(f"{integer_part}.{decimal_part}")
    else:
        value = float(integer_part)
    tail = chunk[match.end():].strip()
    return value, tail


def parse_name(raw: str) -> ParsedName:
    """Decode a KMZ Placemark ``<name>`` into a structured ``ParsedName``.

    Always returns a ``ParsedName`` — never raises for bad input.
    """
    if raw is None:
        return ParsedName(None, "", None, None, False)
    working = raw.strip()
    if working == "":
        return ParsedName(None, "", None, None, False)

    # --- Detect + strip the ★ star.  Anything after the star on the last
    # chunk is considered ROI noise and discarded.  The featured flag is
    # global to the whole string.
    featured = STAR in working
    if featured:
        working = working.split(STAR, 1)[0].rstrip()

    # --- Parenthesized code override.  When the author packed the real
    # codigo inside parentheses (e.g. ``"S2 complemento opcional (P12) ·
    # 5.916 m · sujeto a presupuesto"``), that wins unconditionally over any
    # strict/fallback position-based recovery below.  This matches the
    # authoring convention used across the propuestas layer: ``S2`` is the
    # group family, ``(P12)`` is the canal itself.  We capture the match
    # here and apply it AFTER the normal parse so the rest of the pipeline
    # (longitud, prioridad, descripcion, featured) keeps producing the same
    # structured fields — only the codigo slot is overridden.
    paren_match = _PARENTHESIZED_CODE_RE.search(working)
    paren_code: str | None = paren_match.group(1) if paren_match else None

    # --- Split on · and trim every chunk.
    chunks = [c.strip() for c in working.split(SEP)]
    chunks = [c for c in chunks if c]

    codigo: str | None = None
    longitud: float | None = None
    prioridad: str | None = None
    descripcion_parts: list[str] = []

    recovered_via_fallback = False

    for idx, chunk in enumerate(chunks):
        # 1. Codigo — ONLY at chunk 0.  Mid-chunks that happen to match the
        # codigo shape are rare and usually intentional descripcion tokens.
        if idx == 0 and codigo is None and _CODIGO_RE.match(chunk):
            codigo = chunk
            continue

        # 2. Longitud — anywhere.  If the chunk begins with the longitud
        # pattern, capture the value; preserve any trailing prose in the
        # descripcion so we don't lose author intent.
        if longitud is None:
            maybe_value, tail = _parse_longitud_token(chunk)
            if maybe_value is not None:
                longitud = maybe_value
                if tail:
                    # If the tail itself is a priority, promote it; otherwise
                    # keep as descripcion noise.
                    tail_priority = _normalize_priority_token(tail)
                    if prioridad is None and tail_priority is not None:
                        prioridad = tail_priority
                    else:
                        descripcion_parts.append(tail)
                continue

        # 3. Priority keyword — anywhere.  Accept only canonical values to
        # avoid swallowing descriptors like "readecuación" or "sin
        # intervención" (which are valid descripcion material).
        if prioridad is None:
            candidate = _normalize_priority_token(chunk)
            if candidate is not None:
                prioridad = candidate
                # Fallback used only when strict position-0 codigo-slot
                # ordering failed to extract something (i.e., chunks out of
                # canonical order).  The log helps the user spot drift.
                if idx == 0 and codigo is None:
                    recovered_via_fallback = True
                continue

        # 4. Fall-through → descripcion.
        descripcion_parts.append(chunk)

    descripcion = f" {SEP} ".join(descripcion_parts) if descripcion_parts else ""
    # Fallback: if EVERY chunk classified as codigo/longitud/priority, use
    # the pre-star raw string as descripcion so UI shows something readable.
    if not descripcion:
        descripcion = working.strip()

    # Detect recovery-via-fallback: if we have ANY structured field but the
    # chunks were not in canonical order (codigo not at idx 0 despite being
    # extracted later, priority at idx 0, etc.).  Emit a WARN so authoring
    # drift is visible in CI logs.
    if (
        not recovered_via_fallback
        and codigo is None
        and chunks
        and any(_CODIGO_RE.match(c) for c in chunks[1:])
    ):
        # A codigo-shaped chunk exists but NOT at position 0 — recover it.
        for pos, chunk in enumerate(chunks):
            if pos == 0:
                continue
            if _CODIGO_RE.match(chunk):
                codigo = chunk
                # Remove that chunk from descripcion if it was absorbed there.
                descripcion = descripcion.replace(f"{SEP} {chunk}", "").replace(
                    f"{chunk} {SEP}", ""
                ).replace(chunk, "").strip()
                descripcion = re.sub(rf"^\s*{re.escape(SEP)}\s*", "", descripcion)
                descripcion = re.sub(rf"\s*{re.escape(SEP)}\s*$", "", descripcion)
                recovered_via_fallback = True
                break

    if recovered_via_fallback:
        logger.warning(
            "parse_name: fallback order recovery on %r — codigo=%r longitud=%r prioridad=%r",
            raw,
            codigo,
            longitud,
            prioridad,
        )

    # Parenthesized P/N-series code wins over any prefix-based codigo.  This
    # is the documented authoring convention for propuestas where the leading
    # token ("S2") is a family marker, not the canal code.
    final_codigo = paren_code if paren_code else codigo

    # Keyword inference fallback — ONLY runs when the strict/fallback parse
    # failed to extract an explicit priority token.  Real KMZ names like
    # "S2 complemento opcional (P12) · 5.916 m · sujeto a presupuesto" carry
    # lowercase semantic cues ("opcional", "sujeto a presupuesto", "largo
    # plazo") instead of the canonical uppercase tag the rest of the dataset
    # uses.  Without this step those features end up with prioridad=None and
    # the MapLibre ``["in", ["get", "prioridad"], ["literal", activeEtapas]]``
    # filter silently hides them — the P12 invisibility bug.  Explicit
    # uppercase tags always take precedence because the strict parse ran
    # first; this is a fallback, not an override.
    final_prioridad = prioridad
    if final_prioridad is None:
        lower = raw.lower()
        if "opcional" in lower or "sujeto a presupuesto" in lower:
            final_prioridad = "Opcional"
        elif "largo plazo" in lower:
            final_prioridad = "Largo plazo"

    return ParsedName(
        codigo=final_codigo,
        descripcion=descripcion,
        longitud_declarada_m=longitud,
        prioridad=final_prioridad,
        featured=featured,
    )
