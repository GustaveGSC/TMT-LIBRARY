from database.base import db
from database.models.version import AppVersion


class VersionRepository:

    @staticmethod
    def get_latest() -> AppVersion | None:
        return AppVersion.query.order_by(AppVersion.id.desc()).first()

    @staticmethod
    def create(version: str, description: str, download_url: str) -> AppVersion:
        v = AppVersion(version=version, description=description, download_url=download_url)
        db.session.add(v)
        db.session.commit()
        return v