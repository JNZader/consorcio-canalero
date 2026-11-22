"""Central SQLAlchemy model registry for Alembic metadata discovery.

Importing this module registers every declarative ``Base`` subclass in
``gee-backend/app`` on ``Base.metadata`` so ``alembic --autogenerate`` and
``Base.metadata.create_all()`` share the complete schema without importing
Alembic runtime objects.
"""

from app.auth import email_codes as _auth_email_codes  # noqa: F401
from app.auth import models as _auth_models  # noqa: F401
from app.domains.capas import models as _capas_models  # noqa: F401
from app.domains.conocimiento import models as _conocimiento_models  # noqa: F401
from app.domains.denuncias import models as _denuncias_models  # noqa: F401
from app.domains.finanzas import models as _finanzas_models  # noqa: F401
from app.domains.geo import models as _geo_models  # noqa: F401
from app.domains.geo.informe_area import models as _informe_area_models  # noqa: F401
from app.domains.geo.intelligence import models as _geo_intelligence_models  # noqa: F401
from app.domains.geo.puntos_interes import models as _puntos_interes_models  # noqa: F401
from app.domains.geo.rainfall import models as _rainfall_models  # noqa: F401
from app.domains.geo.relevamiento import models as _relevamiento_models  # noqa: F401
from app.domains.monitoring import models as _monitoring_models  # noqa: F401
from app.domains.padron import models as _padron_models  # noqa: F401
from app.domains.reuniones import models as _reuniones_models  # noqa: F401
from app.domains.settings import models as _settings_models  # noqa: F401
from app.domains.tramites import models as _tramites_models  # noqa: F401
from app.shared import audit_log as _shared_audit_log  # noqa: F401
from app.shared import celery_outbox as _shared_celery_outbox  # noqa: F401
