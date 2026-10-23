# Review ledger: conocimiento-ingesta-sin-orden

Judgment Day, round 1. Two blind judges. No refuter. No fix round: the only shared finding is WARNING, status `info`.

Target: uncommitted working tree on `feat/conocimiento-ingesta-sin-orden` (base `c8f2dfef`).

| id | lens | location | severity | status | evidence |
|----|------|----------|----------|--------|----------|
| JD-001 | judgment-day | `gee-backend/scripts/rag_ingest.py:306-320` | WARNING | info | The new gate catches `BarraInvalida` and `BarraSinOrdenRechazada` only. A missing file, a YAML parse error, a non-numeric figure, or a non-mapping document raises out of `cargar_barra` (`FileNotFoundError` / `yaml.YAMLError` / `ValueError` / `AttributeError`). The process exits 1 with a traceback and does not print `INGESTION ABORTED`. Nothing is written, because the crash is before `create_engine`. Judge A calls the gap pre-existing: `--exigir-barra` already catches the same two types. Judge B calls the copy introduced. Both agree on the behavior. Tests cover an unknown `estado`, which does raise `BarraInvalida`. Not fixed. |

Confirmed severe: none.
Suspect: none.
Contradictions: none on whether the defect exists. Disposition (pre-existing vs introduced) differs; the behavior stands as `info`.

terminal_state: approved
scoped_rejudgment: not_run
skill_resolution: paths-injected
