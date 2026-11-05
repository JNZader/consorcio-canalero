"""Calendar dates in the consorcio's timezone (Córdoba, ART, no DST)."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

ART = ZoneInfo("America/Argentina/Buenos_Aires")


def hoy_argentina(now: datetime | None = None) -> date:
    """Today in America/Argentina/Buenos_Aires.

    Containers run UTC. Between 21:00 and 24:00 ART, ``date.today()`` on the
    server is already the next calendar day.
    """
    moment = now if now is not None else datetime.now(ART)
    return moment.astimezone(ART).date()
