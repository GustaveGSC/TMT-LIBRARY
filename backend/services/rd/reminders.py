"""研发变更提醒业务规则。"""

from database.repository.rd.reminders import rd_reminder_repository


class RdReminderService:
    @staticmethod
    def _content(payload: dict) -> str:
        content = (payload.get('content') or '').strip()
        if not content:
            raise ValueError('提醒内容不能为空')
        return content

    @staticmethod
    def _optional_text(payload: dict, key: str) -> str | None:
        return (payload.get(key) or '').strip() or None

    @staticmethod
    def list_active() -> list[dict]:
        return [item.to_dict() for item in rd_reminder_repository.list_active()]

    @staticmethod
    def list_all() -> list[dict]:
        return [item.to_dict() for item in rd_reminder_repository.list_all()]

    def create(self, payload: dict) -> dict:
        reminder = rd_reminder_repository.create(
            self._content(payload),
            self._optional_text(payload, 'notes'),
            self._optional_text(payload, 'created_by'),
        )
        return reminder.to_dict()

    def update(self, reminder_id: int, payload: dict) -> dict | None:
        reminder = rd_reminder_repository.get(reminder_id)
        if not reminder:
            return None
        reminder = rd_reminder_repository.update(
            reminder,
            self._content(payload),
            self._optional_text(payload, 'notes'),
        )
        return reminder.to_dict()

    @staticmethod
    def set_active(reminder_id: int, is_active: bool) -> dict | None:
        reminder = rd_reminder_repository.get(reminder_id)
        if not reminder:
            return None
        return rd_reminder_repository.set_active(reminder, is_active).to_dict()


rd_reminder_service = RdReminderService()
