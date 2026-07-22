"""研发个人笔记持久化。"""

from database.base import db
from database.models.rd import EcrNote


class RdNoteRepository:
    @staticmethod
    def list_for_user(username: str) -> list[EcrNote]:
        return (
            EcrNote.query
            .filter_by(username=username)
            .order_by(EcrNote.created_at.desc())
            .all()
        )

    @staticmethod
    def get_for_user(note_id: int, username: str) -> EcrNote | None:
        return EcrNote.query.filter_by(id=note_id, username=username).first()

    @staticmethod
    def create(username: str, content: str) -> EcrNote:
        note = EcrNote(username=username, content=content)
        db.session.add(note)
        db.session.commit()
        return note

    @staticmethod
    def update(note: EcrNote, content: str) -> EcrNote:
        note.content = content
        db.session.commit()
        return note

    @staticmethod
    def delete(note: EcrNote) -> None:
        db.session.delete(note)
        db.session.commit()


rd_note_repository = RdNoteRepository()
