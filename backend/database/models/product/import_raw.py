from datetime import datetime, timezone, timedelta
from database.base import db

CST = timezone(timedelta(hours=8))
def now_cst(): return datetime.now(CST).replace(tzinfo=None)


class ImportProductRaw(db.Model):
    __tablename__ = 'import_product_raw'

    id          = db.Column(db.Integer,     primary_key=True, autoincrement=True)
    code        = db.Column(db.String(255), nullable=False, unique=True)
    name        = db.Column(db.String(255), nullable=False)
    group_code  = db.Column(db.String(255), nullable=False)
    group_name  = db.Column(db.String(255), nullable=False)
    imported_at = db.Column(db.DateTime,    nullable=False)

    def to_dict(self) -> dict:
        return {
            'id':          self.id,
            'code':        self.code,
            'name':        self.name,
            'group_code':  self.group_code,
            'group_name':  self.group_name,
            'imported_at': self.imported_at.strftime('%Y-%m-%d %H:%M:%S') if self.imported_at else None,
        }
