"""研发物料门禁持久化。"""

from database.base import db
from database.models.rd import MaterialGate


class MaterialGateRepository:
    @staticmethod
    def list_active() -> list[MaterialGate]:
        return (
            MaterialGate.query.filter_by(is_active=True)
            .order_by(MaterialGate.code.asc(), MaterialGate.id.desc())
            .all()
        )

    @staticmethod
    def list_all() -> list[MaterialGate]:
        return MaterialGate.query.order_by(MaterialGate.created_at.desc()).all()

    @staticmethod
    def get(gate_id: int) -> MaterialGate | None:
        return db.session.get(MaterialGate, gate_id)

    @staticmethod
    def get_active_by_code(code: str, *, exclude_id: int | None = None) -> MaterialGate | None:
        query = MaterialGate.query.filter_by(code=code, is_active=True)
        if exclude_id is not None:
            query = query.filter(MaterialGate.id != exclude_id)
        return query.first()

    @staticmethod
    def find_active_by_codes(codes: list[str]) -> list[MaterialGate]:
        if not codes:
            return []
        return (
            MaterialGate.query
            .filter(MaterialGate.is_active.is_(True), MaterialGate.code.in_(codes))
            .order_by(MaterialGate.code.asc(), MaterialGate.id.desc())
            .all()
        )

    @staticmethod
    def create(code: str, name: str, level: str, reason: str, created_by: str | None) -> MaterialGate:
        gate = MaterialGate(code=code, name=name, level=level, reason=reason, created_by=created_by)
        db.session.add(gate)
        db.session.commit()
        return gate

    @staticmethod
    def update(gate: MaterialGate, code: str, name: str, level: str, reason: str) -> MaterialGate:
        gate.code = code
        gate.name = name
        gate.level = level
        gate.reason = reason
        db.session.commit()
        return gate

    @staticmethod
    def set_active(gate: MaterialGate, is_active: bool) -> MaterialGate:
        gate.is_active = is_active
        db.session.commit()
        return gate

    @staticmethod
    def delete(gate: MaterialGate) -> None:
        db.session.delete(gate)
        db.session.commit()


material_gate_repository = MaterialGateRepository()
