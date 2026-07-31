from database.base import db
from utils import now_cst


class ErpGroupCategory(db.Model):
    """ERP 分组的默认大类配置。

    大类固定为五种且允许多标签，故使用布尔列而非额外的多对多关联表。
    未创建记录即代表该 ERP 分组尚未分类，不预灌种子数据。
    """
    __tablename__ = 'erp_group_category'
    id          = db.Column(db.Integer, primary_key=True, autoincrement=True)
    group_code  = db.Column(db.String(64), nullable=False, unique=True)
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
    code = db.Column(db.String(255), nullable=False, unique=True)
    short_name = db.Column(db.String(255), nullable=True)
    category = db.Column(db.String(100), nullable=True)
    spec = db.Column(db.String(512), nullable=True)
    cover_image = db.Column(db.String(500), nullable=True)
    cover_image_original = db.Column(db.String(500), nullable=True)
    img_updated_at = db.Column(db.Integer, nullable=True)
    remark = db.Column(db.Text, nullable=True)
    # NULL 跟随 ERP/关键词默认；True/False 分别为人工强制停用/启用。
    is_disabled = db.Column(db.Boolean, nullable=True, default=None, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=now_cst)
    updated_at = db.Column(db.DateTime, nullable=False, default=now_cst, onupdate=now_cst)

    def to_dict(self):
        return {
            'code': self.code, 'short_name': self.short_name, 'category': self.category,
            'spec': self.spec, 'cover_image': self.cover_image,
            'cover_image_original': self.cover_image_original,
            'img_updated_at': self.img_updated_at, 'remark': self.remark,
            'is_disabled_override': self.is_disabled,
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
