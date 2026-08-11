"""Privacy boundary for the optional hosted-embedding baseline (design.md D3).

O.5 resolved to a LOCAL baseline (`intfloat/multilingual-e5-large`), so V0 makes
no external call at all and this module guards a door nobody currently opens.
That is the point: `clasificacion` defaults to `privado` for every ingested
document and nothing in V0 promotes one, so the gate makes the API leg
unreachable BY CONSTRUCTION rather than by everyone remembering.

Two independent guarantees, because a single one is always one edit from being
bypassed:

1. `assert_public_domain` refuses unless ZERO documents in the snapshot are
   non-public — default-deny, and deliberately not a filter. Silently dropping
   the private documents would produce a baseline computed over a different
   corpus than the one being compared against, which is a second, quieter lie on
   top of the privacy one.
2. `payload_para_servicio_externo` selects `clasificacion = 'publico'` in SQL, so
   the query itself cannot carry a private text even if a future caller forgets
   the assert.

Raw SQL rather than the ORM for the same reason the retrieval legs use it: this
module must be readable as "what leaves the machine", and a query you can read
end to end is what makes that reviewable.
"""

from __future__ import annotations

from typing import Sequence

from sqlalchemy import text
from sqlalchemy.orm import Session

#: The only value that may leave the machine. Anything else — including a value
#: a future migration adds — is non-public by exclusion, which is the correct
#: direction for a default-deny gate.
CLASIFICACION_PUBLICA = "publico"

_CONTAR_SNAPSHOT_SQL = text("SELECT count(*) FROM rag_documento WHERE corpus_sha = :corpus_sha")

_NO_PUBLICOS_SQL = text(
    """
    SELECT documento_id, clasificacion
    FROM rag_documento
    WHERE corpus_sha = :corpus_sha AND clasificacion <> :publico
    ORDER BY documento_id
    """
)

_PAYLOAD_SQL = text(
    """
    SELECT u.citation_key, u.texto
    FROM rag_unidad u
    JOIN rag_documento d
      ON d.corpus_sha = u.corpus_sha AND d.documento_id = u.documento_id
    WHERE u.corpus_sha = :corpus_sha AND d.clasificacion = :publico
    ORDER BY u.citation_key ASC
    """
)


class CorpusNoPublico(RuntimeError):
    """This snapshot holds non-public documents, so nothing may leave the box."""


def assert_public_domain(db: Session, corpus_sha: str) -> None:
    """Raise unless every document of the snapshot is `clasificacion = 'publico'`.

    An unknown snapshot raises too. "Zero private documents" is trivially true of
    a snapshot that does not exist, and a default-deny gate that passes on a typo
    is not a gate.
    """
    total = db.execute(_CONTAR_SNAPSHOT_SQL, {"corpus_sha": corpus_sha}).scalar_one()
    if not total:
        raise CorpusNoPublico(
            f"snapshot {corpus_sha} has no documents in rag_documento. Refusing "
            "rather than reading an unknown snapshot as public: an empty result "
            "is what a mistyped SHA looks like."
        )

    ofensores = db.execute(
        _NO_PUBLICOS_SQL, {"corpus_sha": corpus_sha, "publico": CLASIFICACION_PUBLICA}
    ).all()
    if ofensores:
        muestra = ", ".join(f"{fila[0]} ({fila[1]})" for fila in ofensores[:10])
        extra = f" (+{len(ofensores) - 10} more)" if len(ofensores) > 10 else ""
        raise CorpusNoPublico(
            f"{len(ofensores)} of {total} documents in snapshot {corpus_sha} are "
            f"not `{CLASIFICACION_PUBLICA}`: {muestra}{extra}. The hosted-embedding "
            "baseline is refused for the WHOLE snapshot rather than run over the "
            "public subset, because a baseline computed over a different corpus "
            "than the one it is compared against is a second problem, not a "
            "workaround for the first."
        )


def payload_para_servicio_externo(
    db: Session,
    corpus_sha: str,
    _saltear_gate_solo_para_test: bool = False,
) -> Sequence[tuple[str, str]]:
    """The `(citation_key, texto)` pairs that MAY be sent to an external service.

    Ordered by citation key so a baseline run is reproducible.

    The escape hatch is named to be unusable by accident and exists for exactly
    one test: proving that the SQL alone excludes private text, independently of
    the assert above. Two guarantees are only two if you can fail one and observe
    the other hold.
    """
    if not _saltear_gate_solo_para_test:
        assert_public_domain(db, corpus_sha)
    filas = db.execute(
        _PAYLOAD_SQL, {"corpus_sha": corpus_sha, "publico": CLASIFICACION_PUBLICA}
    ).all()
    return [(fila[0], fila[1]) for fila in filas]
