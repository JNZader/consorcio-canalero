"""Informe de área — background report infrastructure (PR 2, T1).

S2/S3 of ``odd/tasks/informe-area-pr2.md``: a private-per-user background
report over a multi-subcuenca selection, with cache (S4), caps (S5), Celery
execution via the transactional outbox, and 90-day retention (S11).

T1 ships the machinery — model, cache, router, task, retention — and NO PDF
rendering: ``mapas.py`` is a stub and the download route answers a typed
"not yet" error until T2 lands the builder.
"""
