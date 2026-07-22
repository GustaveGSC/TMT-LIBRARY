"""站点 key-value 配置持久化。"""

from database.base import db
from database.models.account import SiteConfig


class SiteConfigRepository:
    @staticmethod
    def get_value(key: str) -> str | None:
        row = db.session.get(SiteConfig, key)
        return row.value if row else None

    @staticmethod
    def set_value(key: str, value: str) -> None:
        row = db.session.get(SiteConfig, key)
        if row:
            row.value = value
        else:
            db.session.add(SiteConfig(key=key, value=value))
        db.session.commit()


site_config_repository = SiteConfigRepository()
