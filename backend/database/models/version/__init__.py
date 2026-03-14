from datetime import datetime, timezone, timedelta
from database.base import db

CST = timezone(timedelta(hours=8))
def now_cst(): return datetime.now(CST).replace(tzinfo=None)


class AppVersion(db.Model):
    __tablename__ = 'app_version'

    id           = db.Column(db.Integer,     primary_key=True, autoincrement=True)
    version      = db.Column(db.String(20),  nullable=False)
    description  = db.Column(db.Text)
    download_url = db.Column(db.String(500))
    created_at   = db.Column(db.DateTime,    default=now_cst)