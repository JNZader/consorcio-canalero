#!/usr/bin/env python3
"""Runbook step 8: diff every reclassified row against the checked-in artifact.

    python scripts/rag_verificar_clasificacion.py \\
        --corpus-sha 12043582bf8016288a7e8084e85a4b713a97af2f

Step 8 of the G9 runbook (`design.md:969`) is where the privacy boundary is
verified against reality rather than assumed: after the re-ingest, every row of
`rag_documento` at the pinned snapshot must match
`app/domains/conocimiento/eval/expected_clasificacion.yaml` in **class and
evidence**, all 35 of them.

**Why this is a row-by-row diff and never a count.** Round 1 of the design wrote
this step as a single `count(*) FILTER (WHERE clasificacion='publico')`, and the
bounded correction of 2026-08-23 removed it: that query passes on any permutation
that preserves the count. One private document promoted and one public document
demoted is exactly the silent privacy failure this step exists to catch, and the
count is identical on both sides of it. The evidence string is compared for the
same reason one step further in: a document that lands on the right class through
the wrong reason is a rule regression that will move a DIFFERENT document at the
next revision.

**What refuses instead of scoring.** Two preconditions make the comparison
meaningful, and neither is a divergence to report:

* the artifact must be pinned to the snapshot being checked — a `fuente_url` list
  is corpus content, so an expectation written against one revision says nothing
  about another (`expectations.verificar_corpus_sha_clasificacion`);
* the classification rule in the tree must be the one the artifact was generated
  under. If `regla_clasificacion_sha256()` moved, the artifact records what
  another rule derived, and diffing against it reports the rule change as 35
  document-level findings or, worse, as none at all.

Both exit **2**: the check itself is invalid, and "0 divergences" from an invalid
comparison is the most expensive output this script could produce.

Exit codes: 0 every row matches · 1 at least one row diverges (STOP, flag stays
off) · 2 the comparison was refused, or usage.
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.domains.conocimiento import repository  # noqa: E402
from app.domains.conocimiento.expectations import (  # noqa: E402
    ClasificacionShaMismatch,
    ExpectedClasificaciones,
    load_expected_clasificacion,
    verificar_corpus_sha_clasificacion,
)

#: Divergence kinds. Named constants rather than free strings because the
#: operator reads them in the runbook and the tests assert on them.
CLASE_DIFIERE = "clase"
EVIDENCIA_DIFIERE = "evidencia"
FALTA_EN_SNAPSHOT = "falta-en-snapshot"
FALTA_EN_ARTEFACTO = "falta-en-artefacto"


class ComparacionInvalida(RuntimeError):
    """The comparison could not be made — not the same as "nothing differs"."""


@dataclass(frozen=True)
class Divergencia:
    documento_id: str
    clase: str
    esperado: tuple[str, str] | None
    observado: tuple[str, str] | None


LEER_SNAPSHOT_SQL = text(
    """
    SELECT documento_id, clasificacion, clasificacion_evidencia
    FROM rag_documento
    WHERE corpus_sha = :corpus_sha
    ORDER BY documento_id
    """
)


def leer_snapshot(db: Session, corpus_sha: str) -> dict[str, tuple[str, str]]:
    """Every document of one snapshot, as `{id: (clase, evidencia)}`.

    A NULL `clasificacion_evidencia` reads as the empty string rather than
    `None`: the column is nullable since `conocimiento_005`, so a row written
    before the three-class rule is representable, and it must surface as a
    divergence the operator reads — never as a `TypeError` inside the diff.
    """
    filas = db.execute(LEER_SNAPSHOT_SQL, {"corpus_sha": corpus_sha}).all()
    return {fila[0]: (fila[1], fila[2] or "") for fila in filas}


def exigir_comparable(
    esperado: ExpectedClasificaciones,
    *,
    corpus_sha: str,
    regla_sha256: str,
) -> None:
    """Refuse an artifact that describes another revision or another rule."""
    try:
        verificar_corpus_sha_clasificacion(esperado, corpus_sha)
    except ClasificacionShaMismatch as exc:
        raise ComparacionInvalida(str(exc)) from exc

    if esperado.regla_sha256 != regla_sha256:
        raise ComparacionInvalida(
            f"expected_clasificacion.yaml was generated under regla_sha256 "
            f"{esperado.regla_sha256} but the rule in this tree hashes to "
            f"{regla_sha256}. The artifact records what a DIFFERENT rule derived; "
            "diffing the snapshot against it reports the rule change as document "
            "findings instead of as what it is. Regenerate the artifact with "
            "scripts/rag_expected_clasificacion.py — a change-controlled act that "
            "needs the owner's sign-off in the PR that makes it."
        )


def comparar(
    esperado: ExpectedClasificaciones,
    observado: dict[str, tuple[str, str]],
) -> tuple[Divergencia, ...]:
    """Row-by-row diff, ordered by `documento_id`.

    Ordered because a diff that reorders between runs cannot be reviewed twice,
    and step 8 is a step somebody re-runs after fixing the first finding.
    """
    divergencias: list[Divergencia] = []
    for doc_id in sorted(set(esperado.documentos) | set(observado)):
        item = esperado.documentos.get(doc_id)
        fila = observado.get(doc_id)
        if item is None:
            divergencias.append(Divergencia(doc_id, FALTA_EN_ARTEFACTO, None, fila))
            continue
        par_esperado = (item.clasificacion, item.evidencia)
        if fila is None:
            divergencias.append(Divergencia(doc_id, FALTA_EN_SNAPSHOT, par_esperado, None))
            continue
        if fila[0] != par_esperado[0]:
            divergencias.append(Divergencia(doc_id, CLASE_DIFIERE, par_esperado, fila))
        elif fila[1] != par_esperado[1]:
            divergencias.append(Divergencia(doc_id, EVIDENCIA_DIFIERE, par_esperado, fila))
    return tuple(divergencias)


def _par(valor: tuple[str, str] | None) -> str:
    return "—" if valor is None else f"{valor[0]} / {valor[1]}"


def render(
    corpus_sha: str,
    observado: dict[str, tuple[str, str]],
    divergencias: tuple[Divergencia, ...],
) -> list[str]:
    """The operator-facing report. A step nobody can read is a step nobody runs."""
    conteos = {clase: 0 for clase in ("publico", "institucional", "privado")}
    for clase, _ in observado.values():
        conteos[clase] = conteos.get(clase, 0) + 1
    resumen = ", ".join(f"{clase}={total}" for clase, total in sorted(conteos.items()))

    lineas = [
        f"runbook step 8 — corpus_sha {corpus_sha}",
        f"rows in snapshot: {len(observado)} ({resumen})",
    ]
    if not divergencias:
        lineas.append("OK — every row matches expected_clasificacion.yaml in class and evidence.")
        return lineas

    lineas.append(f"DIVERGENCIAS: {len(divergencias)}")
    lineas.append(f"{'documento_id':<52} {'motivo':<18} esperado -> observado")
    for d in divergencias:
        lineas.append(
            f"{d.documento_id:<52} {d.clase:<18} {_par(d.esperado)} -> {_par(d.observado)}"
        )
    lineas.append(
        "STOP. The flag stays off. A wrong classification here is the privacy "
        "boundary failing silently, which is the one failure this design is "
        "arranged around."
    )
    return lineas


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--corpus-sha",
        required=True,
        help="the snapshot to check; must be the revision the artifact is pinned to",
    )
    parser.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL"),
        help="defaults to $DATABASE_URL",
    )
    parser.add_argument(
        "--expected",
        type=Path,
        default=None,
        help="defaults to the checked-in eval/expected_clasificacion.yaml",
    )
    return parser


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - CLI wiring
    args = build_parser().parse_args(argv)
    if not args.database_url:
        print("error: --database-url or $DATABASE_URL is required", file=sys.stderr)
        return 2

    esperado = load_expected_clasificacion(args.expected)
    try:
        exigir_comparable(
            esperado,
            corpus_sha=args.corpus_sha,
            regla_sha256=repository.regla_clasificacion_sha256(),
        )
    except ComparacionInvalida as refusal:
        print(f"COMPARISON REFUSED\n{refusal}", file=sys.stderr)
        return 2

    engine = create_engine(args.database_url)
    with Session(engine) as session:
        observado = leer_snapshot(session, args.corpus_sha)

    divergencias = comparar(esperado, observado)
    print("\n".join(render(args.corpus_sha, observado, divergencias)))
    return 1 if divergencias else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
