from database.base import db
from sqlalchemy.dialects import mysql
from utils import now_cst


def _join_key_string(length):
    """JOIN 键在 MySQL 对齐 ERP 历史表；其他数据库保留普通 String。"""
    return db.String(length).with_variant(
        mysql.VARCHAR(length, collation='utf8mb4_0900_ai_ci'), 'mysql'
    )


class ErpGroupCategory(db.Model):
    """ERP 分组的默认大类配置。

    大类固定为五种且允许多标签，故使用布尔列而非额外的多对多关联表。
    未创建记录即代表该 ERP 分组尚未分类，不预灌种子数据。
    """
    __tablename__ = 'erp_group_category'
    id          = db.Column(db.Integer, primary_key=True, autoincrement=True)
    group_code  = db.Column(_join_key_string(64), nullable=False, unique=True)
    is_finished = db.Column(db.Boolean, nullable=False, default=False)
    is_packaged = db.Column(db.Boolean, nullable=False, default=False)
    is_semi     = db.Column(db.Boolean, nullable=False, default=False)
    is_material = db.Column(db.Boolean, nullable=False, default=False)
    is_useless  = db.Column(db.Boolean, nullable=False, default=False)
    remark      = db.Column(db.String(255), nullable=True)
    updated_by  = db.Column(db.String(100), nullable=True)
    created_at  = db.Column(db.DateTime, nullable=False, default=now_cst)
    updated_at  = db.Column(db.DateTime, nullable=False, default=now_cst, onupdate=now_cst)

    def to_dict(self):
        categories = [
            key for key in ('finished', 'packaged', 'semi', 'material', 'useless')
            if getattr(self, f'is_{key}')
        ]
        return {'group_code': self.group_code, 'categories': categories,
                'remark': self.remark, 'updated_by': self.updated_by}


class ProductMaterial(db.Model):
    """按需创建的物料人工属性。

    ERP 权威字段 name/group_code/group_name 只保留在 import_product_raw，避免重导
    时产生两份真相；绝大多数物料无需维护，本表因此不预灌空行。
    """
    __tablename__ = 'product_material'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    code = db.Column(_join_key_string(255), nullable=False, unique=True)
    short_name = db.Column(db.String(255), nullable=True)
    category = db.Column(db.String(100), nullable=True)
    spec = db.Column(db.String(512), nullable=True)
    # cover_image/cover_image_original/img_updated_at：2026-09-27 起停用，图片改存 material_image（支持多张）
    cover_image = db.Column(db.String(500), nullable=True)
    cover_image_original = db.Column(db.String(500), nullable=True)
    img_updated_at = db.Column(db.Integer, nullable=True)
    remark = db.Column(db.Text, nullable=True)
    # 单独指定的物料类型（逗号分隔，取值同 CATEGORY_TYPES），优先级最高：
    # 单独指定 > 编码前缀规则 > 分组默认类型。NULL 表示不单独指定，按规则判定。
    type_override = db.Column(db.String(100), nullable=True)
    # NULL 跟随 ERP/关键词默认；True/False 分别为人工强制停用/启用。
    is_disabled = db.Column(db.Boolean, nullable=True, default=None, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=now_cst)
    updated_at = db.Column(db.DateTime, nullable=False, default=now_cst, onupdate=now_cst)

    def to_dict(self):
        return {
            'code': self.code, 'short_name': self.short_name, 'category': self.category,
            'spec': self.spec, 'remark': self.remark,
            'type_override': [t for t in (self.type_override or '').split(',') if t],
        }


class MaterialImage(db.Model):
    """物料图片，一个物料可有多张，按 sort_order 升序展示，第一张即封面。

    2026-09-27 起取代 product_material.cover_image/cover_image_original/img_updated_at
    （那三列保留在库里但不再读写，历史数据已由迁移 20260927_02 搬进本表）。
    """
    __tablename__ = 'material_image'
    id         = db.Column(db.Integer, primary_key=True, autoincrement=True)
    code       = db.Column(_join_key_string(255), nullable=False, index=True)
    url        = db.Column(db.String(500), nullable=False)
    orig_url   = db.Column(db.String(500), nullable=True)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    created_by = db.Column(db.String(100), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=now_cst)
    updated_at = db.Column(db.DateTime, nullable=False, default=now_cst, onupdate=now_cst)

    def to_dict(self):
        return {
            'id': self.id, 'url': self.url, 'orig_url': self.orig_url,
            'sort_order': self.sort_order,
        }


class MaterialDisableKeyword(db.Model):
    """物料名称停用判定关键词；规则由界面维护，不在业务代码中写死。"""
    __tablename__ = 'material_disable_keyword'
    id          = db.Column(db.Integer, primary_key=True, autoincrement=True)
    keyword     = db.Column(db.String(64), nullable=False, unique=True)
    is_disabled = db.Column(db.Boolean, nullable=False, default=False)
    remark      = db.Column(db.String(255), nullable=True)
    created_at  = db.Column(db.DateTime, nullable=False, default=now_cst)

    def to_dict(self):
        return {
            'id': self.id, 'keyword': self.keyword,
            'is_disabled': bool(self.is_disabled), 'remark': self.remark,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S')
            if self.created_at else None,
        }


class MaterialBom(db.Model):
    """研发 BOM 的单层记录：一个父件（研发编码+版本）及其直接子件。

    研发 BOM Excel 是多层展开的树，导入时拆成「每个有下级的节点一份单层 BOM」存储，
    查看时再逐层展开。这样同一个半成品被多个产品引用时只存一份，改一次处处生效。
    研发版本比 ERP 细（成品/产成品 ERP 只到 -A，研发是 -A01/-A02），所以按研发
    编码+版本存，erp_code 是导入时匹配到的 ERP 物料编码（匹配不到为空）。
    """
    __tablename__ = 'material_bom'
    __table_args__ = (db.UniqueConstraint('code', 'version', name='uq_material_bom_code_version'),)
    id          = db.Column(db.Integer, primary_key=True, autoincrement=True)
    code        = db.Column(db.String(64), nullable=False)             # 研发编码（不含版本）
    version     = db.Column(db.String(16), nullable=False, default='')  # 研发版本，如 A01
    erp_code    = db.Column(_join_key_string(255), nullable=True, index=True)
    name        = db.Column(db.String(255), nullable=True)
    spec        = db.Column(db.String(512), nullable=True)
    category    = db.Column(db.String(64), nullable=True)              # 研发一级分类，如 成品/产成品/半成品
    source_file = db.Column(db.String(255), nullable=True)
    imported_by = db.Column(db.String(100), nullable=True)
    imported_at = db.Column(db.DateTime, nullable=False, default=now_cst)

    def to_dict(self):
        return {
            'id': self.id, 'code': self.code, 'version': self.version,
            'drawing': f'{self.code}-{self.version}' if self.version else self.code,
            'erp_code': self.erp_code, 'name': self.name, 'spec': self.spec,
            'category': self.category, 'source_file': self.source_file,
            'imported_by': self.imported_by,
            'imported_at': self.imported_at.strftime('%Y-%m-%d %H:%M') if self.imported_at else None,
        }


class MaterialBomLine(db.Model):
    """单层 BOM 的一个子件行；子件若自身也有 BOM，按 code+version 找对应的 MaterialBom。"""
    __tablename__ = 'material_bom_line'
    __table_args__ = (db.Index('ix_material_bom_line_code_version', 'code', 'version'),)
    id       = db.Column(db.Integer, primary_key=True, autoincrement=True)
    bom_id   = db.Column(db.Integer, db.ForeignKey('material_bom.id', ondelete='CASCADE'),
                         nullable=False, index=True)
    seq      = db.Column(db.Integer, nullable=False, default=0)
    code     = db.Column(db.String(64), nullable=False)
    version  = db.Column(db.String(16), nullable=False, default='')
    erp_code = db.Column(_join_key_string(255), nullable=True, index=True)
    name     = db.Column(db.String(255), nullable=True)
    spec     = db.Column(db.String(512), nullable=True)
    category = db.Column(db.String(64), nullable=True)
    qty      = db.Column(db.Numeric(14, 4, asdecimal=False), nullable=False, default=1)
    unit     = db.Column(db.String(16), nullable=True)
