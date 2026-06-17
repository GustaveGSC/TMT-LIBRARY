from database.base import db
from utils import now_cst

# ── 资料类型 ───────────────────────────────────────────────────────────────
class ProductResourceType(db.Model):
    __tablename__ = 'product_resource_type'

    id         = db.Column(db.Integer,     primary_key=True, autoincrement=True)
    name       = db.Column(db.String(100), nullable=False, unique=True)
    sort_order = db.Column(db.Integer,     nullable=False, default=0)
    created_at = db.Column(db.DateTime,   nullable=False, default=now_cst)

    def to_dict(self) -> dict:
        return {
            'id':         self.id,
            'name':       self.name,
            'sort_order': self.sort_order,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None,
        }


# ── 成品-资料关联中间表（含 sort_order）──────────────────────────────────
finished_resource = db.Table(
    'product_finished_resource',
    db.Column('finished_id',  db.Integer, db.ForeignKey('product_finished.id',  ondelete='CASCADE'), primary_key=True),
    db.Column('resource_id',  db.Integer, db.ForeignKey('product_resource.id',  ondelete='CASCADE'), primary_key=True),
    db.Column('sort_order',   db.Integer, nullable=False, default=0),
)

# ── 资料-标签关联中间表 ───────────────────────────────────────────────────
resource_tag = db.Table(
    'product_resource_tag',
    db.Column('resource_id', db.Integer, db.ForeignKey('product_resource.id', ondelete='CASCADE'), primary_key=True),
    db.Column('tag_id',      db.Integer, db.ForeignKey('product_tag.id',      ondelete='CASCADE'), primary_key=True),
)

# ── 资料-型号关联中间表 ───────────────────────────────────────────────────
resource_model = db.Table(
    'product_resource_model',
    db.Column('resource_id', db.Integer, db.ForeignKey('product_resource.id', ondelete='CASCADE'), primary_key=True),
    db.Column('model_id',    db.Integer, db.ForeignKey('product_model.id',    ondelete='CASCADE'), primary_key=True),
)


# ── 资料条目 ───────────────────────────────────────────────────────────────
class ProductResource(db.Model):
    __tablename__ = 'product_resource'

    id                = db.Column(db.Integer,      primary_key=True, autoincrement=True)
    title             = db.Column(db.String(200),  nullable=False)
    type_id           = db.Column(db.Integer,      db.ForeignKey('product_resource_type.id', ondelete='RESTRICT'), nullable=True)
    url               = db.Column(db.String(1000), nullable=False)
    storage_key       = db.Column(db.String(500),  nullable=True)      # OSS key，source='oss' 时有值
    source            = db.Column(db.String(20),   nullable=False, default='external')   # 'oss' | 'external'
    file_type         = db.Column(db.String(20),   nullable=False, default='link')       # 'pdf'|'image'|'video'|'link'|'other'
    original_filename = db.Column(db.String(300),  nullable=True)
    description       = db.Column(db.Text,         nullable=True)
    created_at        = db.Column(db.DateTime,     nullable=False, default=now_cst)
    updated_at        = db.Column(db.DateTime,     nullable=False, default=now_cst, onupdate=now_cst)

    resource_type = db.relationship('ProductResourceType', backref='resources', lazy='joined')
    tags          = db.relationship('ProductTag',  secondary='product_resource_tag',   lazy='joined')
    models        = db.relationship('ProductModel', secondary='product_resource_model', lazy='joined')

    def to_dict(self, linked_count: int = None, sort_order: int = None, link_type: str = None) -> dict:
        d = {
            'id':                self.id,
            'title':             self.title,
            'type_id':           self.type_id,
            'type_name':         self.resource_type.name if self.resource_type else None,
            'url':               self.url,
            'source':            self.source,
            'file_type':         self.file_type,
            'original_filename': self.original_filename,
            'description':       self.description,
            'tags':              [{'id': t.id, 'name': t.name} for t in self.tags],
            'model_ids':         [m.id for m in self.models],
            'created_at':        self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None,
            'updated_at':        self.updated_at.strftime('%Y-%m-%d %H:%M:%S') if self.updated_at else None,
        }
        if linked_count is not None:
            d['linked_count'] = linked_count
        if sort_order is not None:
            d['sort_order'] = sort_order
        if link_type is not None:
            d['link_type'] = link_type
        return d
