"""研发个人笔记业务规则。"""

from database.repository.rd.notes import rd_note_repository


class RdNoteService:
    @staticmethod
    def _clean_content(payload: dict) -> str:
        content = (payload.get('content') or '').strip()
        if not content:
            raise ValueError('笔记内容不能为空')
        return content

    def list_notes(self, username: str) -> list[dict]:
        return [note.to_dict() for note in rd_note_repository.list_for_user(username)]

    def create_note(self, username: str, payload: dict) -> dict:
        content = self._clean_content(payload)
        return rd_note_repository.create(username, content).to_dict()

    def update_note(self, note_id: int, username: str, payload: dict) -> dict | None:
        note = rd_note_repository.get_for_user(note_id, username)
        if not note:
            return None
        content = self._clean_content(payload)
        return rd_note_repository.update(note, content).to_dict()

    @staticmethod
    def delete_note(note_id: int, username: str) -> bool:
        note = rd_note_repository.get_for_user(note_id, username)
        if not note:
            return False
        rd_note_repository.delete(note)
        return True


rd_note_service = RdNoteService()
