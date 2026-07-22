"""研发变更提醒持久化。"""

from database.base import db
from database.models.rd import EcrReminder


class RdReminderRepository:
    @staticmethod
    def list_active() -> list[EcrReminder]:
        return (
            EcrReminder.query
            .filter_by(is_active=True)
            .order_by(EcrReminder.created_at.desc())
            .all()
        )

    @staticmethod
    def list_all() -> list[EcrReminder]:
        return EcrReminder.query.order_by(EcrReminder.created_at.desc()).all()

    @staticmethod
    def get(reminder_id: int) -> EcrReminder | None:
        return db.session.get(EcrReminder, reminder_id)

    @staticmethod
    def create(content: str, notes: str | None, created_by: str | None) -> EcrReminder:
        reminder = EcrReminder(
            content=content,
            notes=notes,
            created_by=created_by,
        )
        db.session.add(reminder)
        db.session.commit()
        return reminder

    @staticmethod
    def update(reminder: EcrReminder, content: str, notes: str | None) -> EcrReminder:
        reminder.content = content
        reminder.notes = notes
        db.session.commit()
        return reminder

    @staticmethod
    def set_active(reminder: EcrReminder, is_active: bool) -> EcrReminder:
        reminder.is_active = is_active
        db.session.commit()
        return reminder


rd_reminder_repository = RdReminderRepository()
