"""CDATA parser for the Escuelas Rurales KMZ.

The KMZ stores ALL per-school metadata inside an HTML-ish CDATA blob authored
in Google Earth Pro.  We parse ONLY the 3 operational labels that REQ-ESC-2
allows through — all remaining labels (CUE, Departamento, Sector, Directivo,
Teléfono, Email) are IGNORED at parse time so they can NEVER leak into the
public static asset.

Input shape (real KMZ, verified):

    <b>Escuela Joaquín Víctor González</b><br/>
    <b>CUE:</b> 140173000<br/>
    <b>Localidad:</b> Monte Leña<br/>
    <b>Departamento:</b> Unión<br/>
    <b>Ámbito:</b> Rural Aglomerado<br/>
    <b>Nivel:</b> Inicial · Primario<br/>
    <b>Sector:</b> Estatal<br/>
    <b>Directivo:</b> Barbero, Norma Magdalena<br/>
    <b>Teléfono:</b> (03537) 15654790<br/><b>Email:</b> torner20@hotmail.com<br/>

Rules of engagement:

- The field SEPARATOR is ``<br/>`` (or ``<br>``) — NEVER the middle-dot ``·``
  that appears inside the ``Nivel`` value.
- The label ``Ámbito`` has a diacritic on the ``Á``.  We match it and the
  plain-ASCII variant ``Ambito`` so the parser doesn't silently drop the
  field if the authoring tool ever writes the NFD variant.
- Unicode accents are preserved in VALUES (e.g. ``Monte Leña`` stays intact).
- Whitelist approach: the regex captures ONLY the 3 approved label names.
  Any future CDATA field (e.g. ``Matrícula``) is invisible to us by design.
"""

from __future__ import annotations

import re

# Whitelist regex — one pattern captures all 3 approved labels in one pass.
# Rationale:
#   * ``<b>\s*(Label)\s*:\s*</b>`` → bold label tag with optional whitespace.
#   * ``\s*([^<]+?)\s*`` → value is everything up to the next ``<``, lazy so
#     we stop before ``<br/>`` or the next ``<b>``.
#   * ``<br/?>`` → tolerate ``<br>`` and ``<br/>`` (both appear in real KMZs).
#   * ``re.IGNORECASE`` → future-proof against ``LOCALIDAD`` vs ``Localidad``.
#   * ``re.UNICODE`` is default in Python 3; kept explicit for documentation.
#   * ``[ÁA]mbito`` accepts both the accented and ASCII-folded spellings.
LABEL_PATTERN: re.Pattern[str] = re.compile(
    r"<b>\s*(Localidad|[ÁA]mbito|Nivel)\s*:\s*</b>\s*([^<]+?)\s*<br\s*/?>",
    re.IGNORECASE | re.UNICODE,
)

# Mapping from the raw label (lowercased, accent-folded) to the output key.
# Keeps the contract crisp: the returned dict has EXACTLY these 3 keys when
# all fields are present.
_LABEL_TO_KEY: dict[str, str] = {
    "localidad": "localidad",
    "ambito": "ambito",
    "ámbito": "ambito",
    "nivel": "nivel",
}


def parse_description(cdata: str) -> dict[str, str]:
    """Extract the 3 operational labels from a KMZ CDATA description.

    Args:
        cdata: The raw CDATA HTML-ish blob as it appears inside
            ``<Placemark><description><![CDATA[ ... ]]></description>``.

    Returns:
        A dict with at most 3 keys — ``localidad``, ``ambito``, ``nivel``.
        A label that is missing from the CDATA is OMITTED from the result
        rather than present-with-empty-value; the caller decides whether
        that constitutes a data-quality failure.

    Notes:
        * PII labels (``Directivo``, ``Teléfono``, ``Email``) and burocratic
          codes (``CUE``, ``Departamento``, ``Sector``) are IGNORED at parse
          time — they cannot leak into the returned dict.
        * When a label appears more than once in the same CDATA (future
          robustness), the FIRST occurrence wins so the output stays
          deterministic in document order.
        * The parser is pure: no I/O, no global state.
    """
    if not cdata:
        return {}

    out: dict[str, str] = {}
    for match in LABEL_PATTERN.finditer(cdata):
        raw_label, value = match.group(1), match.group(2)
        key = _LABEL_TO_KEY.get(raw_label.lower())
        if key is None:
            continue  # defensive — regex only captures known labels
        # First occurrence wins — keep the output deterministic.
        if key not in out:
            out[key] = value.strip()
    return out
