from database.base import db
from database.models.version import AppVersion


class VersionRepository:

    @staticmethod
    def get_latest() -> AppVersion | None:
        return AppVersion.query.order_by(AppVersion.id.desc()).first()

    @staticmethod
    def create(version: str, description: str,
               download_url: str = None, mac_download_url: str = None) -> AppVersion:
        v = AppVersion(
            version          = version,
            description      = description,
            download_url     = download_url or None,
            mac_download_url = mac_download_url or None,
        )
        db.session.add(v)
        db.session.commit()
        return v