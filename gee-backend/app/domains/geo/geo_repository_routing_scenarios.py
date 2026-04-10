from __future__ import annotations

from datetime import datetime, timezone
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.geo.geo_repository_support import paginated_results
from app.domains.geo.routing_models import (
    GeoRoutingScenario,
    GeoRoutingScenarioApprovalEvent,
)


def _scenario_select():
    return select(GeoRoutingScenario)


class GeoRepositoryRoutingScenariosMixin:
    def _next_routing_scenario_version(
        self,
        db: Session,
        previous_version_id: uuid.UUID | None,
    ) -> int:
        if previous_version_id is None:
            return 1

        previous = self.get_routing_scenario(db, previous_version_id)
        if previous is None:
            return 1
        return int(previous.version) + 1

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
        previous_version_id: uuid.UUID | None = None,
        is_favorite: bool = False,
    ) -> GeoRoutingScenario:
        scenario = GeoRoutingScenario(
            name=name,
            profile=profile,
            version=self._next_routing_scenario_version(db, previous_version_id),
            previous_version_id=previous_version_id,
            request_payload=request_payload,
            result_payload=result_payload,
            notes=notes,
            is_favorite=is_favorite,
            created_by_id=created_by_id,
        )
        db.add(scenario)
        db.flush()
        return scenario

    def get_routing_scenario(
        self, db: Session, scenario_id: uuid.UUID
    ) -> GeoRoutingScenario | None:
        return db.execute(
            _scenario_select().where(GeoRoutingScenario.id == scenario_id)
        ).scalar_one_or_none()

    def list_routing_scenario_approval_events(
        self,
        db: Session,
        scenario_id: uuid.UUID,
    ) -> list[GeoRoutingScenarioApprovalEvent]:
        return list(
            db.execute(
                select(GeoRoutingScenarioApprovalEvent)
                .where(GeoRoutingScenarioApprovalEvent.scenario_id == scenario_id)
                .order_by(GeoRoutingScenarioApprovalEvent.acted_at.desc())
            ).scalars()
        )

    def _record_routing_approval_event(
        self,
        db: Session,
        *,
        scenario_id: uuid.UUID,
        action: str,
        note: str | None = None,
        acted_by_id: uuid.UUID | None = None,
    ) -> GeoRoutingScenarioApprovalEvent:
        event = GeoRoutingScenarioApprovalEvent(
            scenario_id=scenario_id,
            action=action,
            note=note,
            acted_by_id=acted_by_id,
            acted_at=datetime.now(timezone.utc),
        )
        db.add(event)
        db.flush()
        return event

    def approve_routing_scenario(
        self,
        db: Session,
        scenario_id: uuid.UUID,
        *,
        approved_by_id: uuid.UUID | None = None,
        note: str | None = None,
    ) -> GeoRoutingScenario | None:
        scenario = self.get_routing_scenario(db, scenario_id)
        if scenario is None:
            return None

        scenario.is_approved = True
        scenario.approved_at = datetime.now(timezone.utc)
        scenario.approved_by_id = approved_by_id
        scenario.approval_note = note
        self._record_routing_approval_event(
            db,
            scenario_id=scenario.id,
            action="approved",
            note=note,
            acted_by_id=approved_by_id,
        )
        db.flush()
        return scenario

    def unapprove_routing_scenario(
        self,
        db: Session,
        scenario_id: uuid.UUID,
        *,
        approved_by_id: uuid.UUID | None = None,
        note: str | None = None,
    ) -> GeoRoutingScenario | None:
        scenario = self.get_routing_scenario(db, scenario_id)
        if scenario is None:
            return None

        scenario.is_approved = False
        scenario.approved_at = None
        scenario.approved_by_id = None
        scenario.approval_note = note
        self._record_routing_approval_event(
            db,
            scenario_id=scenario.id,
            action="unapproved",
            note=note,
            acted_by_id=approved_by_id,
        )
        db.flush()
        return scenario

    def set_routing_scenario_favorite(
        self,
        db: Session,
        scenario_id: uuid.UUID,
        *,
        is_favorite: bool,
    ) -> GeoRoutingScenario | None:
        scenario = self.get_routing_scenario(db, scenario_id)
        if scenario is None:
            return None
        scenario.is_favorite = is_favorite
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
            _scenario_select(),
            page=page,
            limit=limit,
            order_by=(
                GeoRoutingScenario.is_favorite.desc(),
                GeoRoutingScenario.created_at.desc(),
            ),
        )
