"""Tramites domain — administrative procedure tracking."""

from app.domains.tramites.models import Tramite, TramiteSeguimiento, EstadoTramite
from app.domains.tramites.router import router
from app.domains.tramites.service import TramiteService

__all__ = [
    "Tramite",
    "TramiteSeguimiento",
    "TramiteService",
    "EstadoTramite",
    "router",
]
