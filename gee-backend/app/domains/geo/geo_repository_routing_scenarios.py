from __future__ import annotations

from datetime import datetime, timezone
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.geo.geo_repository_support import paginated_results
from app.domains.geo.routing_models import GeoRoutingScenario


class GeoRepositoryRoutingScenariosMixin:
    def create_routing_scenario(
        self,
        db: Session,
        *,
        name: str,
        profile: str,
        request_payload: dict,
        result_payload: dict,
        notes: str | None = None,
        created_by_id: uuid.UUID | None = None,
    ) -> GeoRoutingScenario:
        scenario = GeoRoutingScenario(
            name=name,
            profile=profile,
            request_payload=request_payload,
            result_payload=result_payload,
            notes=notes,
            created_by_id=created_by_id,
        )
        db.add(scenario)
        db.flush()
        return scenario

    def get_routing_scenario(
        self, db: Session, scenario_id: uuid.UUID
    ) -> GeoRoutingScenario | None:
        return db.execute(
            select(GeoRoutingScenario).where(GeoRoutingScenario.id == scenario_id)
        ).scalar_one_or_none()

    def approve_routing_scenario(
        self,
        db: Session,
        scenario_id: uuid.UUID,
        *,
        approved_by_id: uuid.UUID | None = None,
    ) -> GeoRoutingScenario | None:
        scenario = self.get_routing_scenario(db, scenario_id)
        if scenario is None:
            return None

        scenario.is_approved = True
        scenario.approved_at = datetime.now(timezone.utc)
        scenario.approved_by_id = approved_by_id
        db.flush()
        return scenario

    def list_routing_scenarios(
        self,
        db: Session,
        *,
        page: int = 1,
        limit: int = 20,
    ) -> tuple[list[GeoRoutingScenario], int]:
        return paginated_results(
            db,
            select(GeoRoutingScenario),
            page=page,
            limit=limit,
            order_by=GeoRoutingScenario.created_at.desc(),
        )
