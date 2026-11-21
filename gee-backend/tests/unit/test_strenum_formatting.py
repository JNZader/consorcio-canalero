"""Regression guard: string enums use StrEnum so f-strings emit values in Python 3.15+."""

from __future__ import annotations

from enum import StrEnum

import pytest

from app.auth.models import UserRole
from app.domains.capas.models import FuenteCapa, TipoCapa
from app.domains.denuncias.models import EstadoDenuncia
from app.domains.denuncias.notify import notification_task_id
from app.domains.geo.models import (
    EstadoGeoJob,
    FormatoGeoLayer,
    FuenteGeoLayer,
    TipoAnalisisGee,
    TipoGeoJob,
    TipoGeoLayer,
)
from app.domains.monitoring.models import EstadoSugerencia, TipoAnalisis
from app.domains.padron.models import EstadoConsorcista
from app.domains.reuniones.models import EstadoReunion, TipoReunion
from app.domains.settings.models import CategoriaSettings
from app.domains.tramites.models import EstadoTramite, PrioridadTramite, TipoTramite
from app.shared.celery_outbox import CeleryTaskKey

STR_ENUM_CLASSES: tuple[type[StrEnum], ...] = (
    CeleryTaskKey,
    UserRole,
    TipoCapa,
    FuenteCapa,
    TipoReunion,
    EstadoReunion,
    EstadoConsorcista,
    TipoTramite,
    EstadoTramite,
    PrioridadTramite,
    CategoriaSettings,
    EstadoDenuncia,
    EstadoSugerencia,
    TipoAnalisis,
    TipoGeoLayer,
    FuenteGeoLayer,
    FormatoGeoLayer,
    EstadoGeoJob,
    TipoGeoJob,
    TipoAnalisisGee,
)


@pytest.mark.parametrize("enum_cls", STR_ENUM_CLASSES, ids=lambda cls: cls.__name__)
def test_enum_inherits_from_strenum_and_formats_value(enum_cls: type[StrEnum]) -> None:
    assert issubclass(enum_cls, StrEnum)
    for member in enum_cls:
        assert f"{member}" == member.value
        assert str(member) == member.value


def test_denuncia_notification_id_matches_enum_and_plain_string() -> None:
    import uuid

    denuncia_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
    assert notification_task_id(denuncia_id, EstadoDenuncia.RESUELTO, "Ok") == notification_task_id(
        denuncia_id, "resuelto", "Ok"
    )
