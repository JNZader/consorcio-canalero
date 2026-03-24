"""Denuncias domain — citizen reports about canal infrastructure."""

from app.domains.denuncias.models import Denuncia, DenunciaHistorial, EstadoDenuncia
from app.domains.denuncias.router import router
from app.domains.denuncias.service import DenunciaService

__all__ = [
    "Denuncia",
    "DenunciaHistorial",
    "DenunciaService",
    "EstadoDenuncia",
    "router",
]
