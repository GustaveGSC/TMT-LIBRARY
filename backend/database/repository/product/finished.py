from typing import Optional, List, Tuple
from database.base import db
from database.models.product.finished import ProductFinished, ProductPackaged, now_cst
from database.models.product.erp_code_rules import ErpCodeRule
from database.models.product.import_raw import ImportProductRaw
from database.models.product.category import ProductModel, ProductSeries, ProductCategory
from sqlalchemy import or_, func


class FinishedRepository:

    @staticmethod
    def _get_prefixes(type_: str) -> List[str]:
        rules = ErpCodeRule.query.filter_by(type=type_).all()
        return [r.prefix for r in rules]

    @staticmethod
    def query_finished_list(
        page: int = 1,
        size: int = 20,
        search_field: str = '',
        search_value: str = '',
        sort_field: str = 'code',
        sort_order: str = 'asc',
    ) -> Tuple[int, List[dict]]:
        """
        联合查询成品列表：
        import_product_raw LEFT JOIN product_finished LEFT JOIN product_model/series/category
        并附带关联产成品的体积/毛重/净重合计（子查询）
        """
        prefixes = FinishedRepository._get_prefixes('finished')
        if not prefixes:
            return 0, []

        prefix_filters = [ImportProductRaw.code.like(f'{p}%') for p in prefixes]

        # 产成品合计子查询
        packaged_agg = (
            db.session.query(
                ProductFinished.id.label('finished_id'),
                func.sum(ProductPackaged.volume).label('total_volume'),
                func.sum(ProductPackaged.gross_weight).label('total_gross'),
                func.sum(ProductPackaged.net_weight).label('total_net'),
            )
            .join(ProductFinished.packaged_list)
            .group_by(ProductFinished.id)
            .subquery()
        )

        # 主查询
        query = (
            db.session.query(
                ImportProductRaw,
                ProductFinished,
                ProductModel,
                ProductSeries,
                ProductCategory,
                packaged_agg.c.total_volume,
                packaged_agg.c.total_gross,
                packaged_agg.c.total_net,
            )
            .outerjoin(ProductFinished,    ImportProductRaw.code == ProductFinished.code)
            .outerjoin(ProductModel,       ProductFinished.model_id == ProductModel.id)
            .outerjoin(ProductSeries,      ProductModel.series_id == ProductSeries.id)
            .outerjoin(ProductCategory,    ProductSeries.category_id == ProductCategory.id)
            .outerjoin(packaged_agg,       packaged_agg.c.finished_id == ProductFinished.id)
            .filter(or_(*prefix_filters))
        )

        # 字段搜索
        if search_field and search_value:
            sv = f'%{search_value}%'
            field_map = {
                'code':         ImportProductRaw.code.ilike(sv),
                'name':         ImportProductRaw.name.ilike(sv),
                'name_en':      ProductModel.name_en.ilike(sv),
                'category':     ProductCategory.name.ilike(sv),
                'series_code':  ProductSeries.code.ilike(sv),
                'series_name':  ProductSeries.name.ilike(sv),
                'model_code':   ProductModel.model_code.ilike(sv),
            }
            if search_field in field_map:
                query = query.filter(field_map[search_field])

        total = query.count()

        # 排序映射
        sort_col_map = {
            'code':               ImportProductRaw.code,
            'name':               ImportProductRaw.name,
            'category':           ProductCategory.name,
            'series_code':        ProductSeries.code,
            'model_code':         ProductModel.model_code,
            'listed_yymm':        ProductFinished.listed_yymm,
            'delisted_yymm':      ProductFinished.delisted_yymm,
            'total_volume':       packaged_agg.c.total_volume,
            'total_gross_weight': packaged_agg.c.total_gross,
            'total_net_weight':   packaged_agg.c.total_net,
        }
        sort_col = sort_col_map.get(sort_field, ImportProductRaw.code)
        if sort_order == 'desc':
            sort_col = sort_col.desc()

        rows = query.order_by(sort_col).offset((page - 1) * size).limit(size).all()

        items = []
        for raw, fin, model, series, category, t_vol, t_gross, t_net in rows:
            # 获取该成品关联的产成品 code 列表（用于包装列表列）
            packaged_codes = []
            if fin:
                packaged_codes = [p.code for p in fin.packaged_list]

            item = {
                # 基础信息
                'code':          raw.code,
                'name':          raw.name,                           # ERP 原始名称（中文）
                'name_en':       model.name_en if model else None,   # 英文名来自 product_model
                # 分类层级
                'category_name': category.name    if category else None,
                'series_code':   series.code      if series else None,
                'series_name':   series.name      if series else None,
                'model_code':    model.model_code if model else None,
                # 包装
                'packaged_list': packaged_codes,
                # 合计
                'total_volume':       round(t_vol,   4) if t_vol   is not None else None,
                'total_gross_weight': round(t_gross, 3) if t_gross is not None else None,
                'total_net_weight':   round(t_net,   3) if t_net   is not None else None,
                # 时间
                'listed_yymm':   fin.listed_yymm   if fin else None,
                'delisted_yymm': fin.delisted_yymm if fin else None,
                # 状态
                'status':        fin.status        if fin else 'unrecorded',
                'finished_id':   fin.id            if fin else None,
                'model_id':      fin.model_id      if fin else None,
            }
            items.append(item)

        return total, items

    @staticmethod
    def get_finished_by_code(code: str) -> Optional[ProductFinished]:
        return ProductFinished.query.filter_by(code=code).first()

    @staticmethod
    def get_finished_by_id(finished_id: int) -> Optional[ProductFinished]:
        return db.session.get(ProductFinished, finished_id)

    @staticmethod
    def create_finished(code: str, **kwargs) -> ProductFinished:
        obj = ProductFinished(code=code, created_at=now_cst(), updated_at=now_cst(), **kwargs)
        db.session.add(obj)
        db.session.commit()
        return obj

    @staticmethod
    def update_finished(obj: ProductFinished, **kwargs) -> ProductFinished:
        for k, v in kwargs.items():
            if hasattr(obj, k):
                setattr(obj, k, v)
        obj.updated_at = now_cst()
        db.session.commit()
        return obj

    # ── Packaged ──────────────────────────────────────────────────────────

    @staticmethod
    def get_all_packaged_candidate_codes() -> List[dict]:
        """返回所有满足产成品编码规则的 import_product_raw 记录（code + name）"""
        prefixes = FinishedRepository._get_prefixes('packaged')
        if not prefixes:
            return []
        prefix_filters = [ImportProductRaw.code.like(f'{p}%') for p in prefixes]
        rows = (ImportProductRaw.query
                .filter(or_(*prefix_filters))
                .order_by(ImportProductRaw.code)
                .all())
        return [{'code': r.code, 'name': r.name} for r in rows]

    @staticmethod
    def query_packaged_candidates(
        search: str = '',
        page: int = 1,
        size: int = 20,
    ) -> Tuple[int, List[dict]]:
        prefixes = FinishedRepository._get_prefixes('packaged')
        if not prefixes:
            return 0, []

        prefix_filters = [ImportProductRaw.code.like(f'{p}%') for p in prefixes]

        query = (
            db.session.query(ImportProductRaw, ProductPackaged)
            .outerjoin(ProductPackaged, ImportProductRaw.code == ProductPackaged.code)
            .filter(or_(*prefix_filters))
        )
        if search:
            query = query.filter(
                or_(
                    ImportProductRaw.code.ilike(f'%{search}%'),
                    ImportProductRaw.name.ilike(f'%{search}%'),
                )
            )

        total = query.count()
        rows  = query.order_by(ImportProductRaw.code).offset((page - 1) * size).limit(size).all()

        items = []
        for raw, pkg in rows:
            items.append({
                'code':         raw.code,
                'name':         raw.name,
                'is_recorded':  pkg is not None,
                'packaged_id':  pkg.id           if pkg else None,
                'length':       pkg.length       if pkg else None,
                'width':        pkg.width        if pkg else None,
                'height':       pkg.height       if pkg else None,
                'volume':       pkg.volume       if pkg else None,
                'gross_weight': pkg.gross_weight if pkg else None,
                'net_weight':   pkg.net_weight   if pkg else None,
            })
        return total, items

    @staticmethod
    def get_packaged_by_code(code: str) -> Optional[ProductPackaged]:
        return ProductPackaged.query.filter_by(code=code).first()

    @staticmethod
    def get_packaged_by_id(packaged_id: int) -> Optional[ProductPackaged]:
        return db.session.get(ProductPackaged, packaged_id)

    @staticmethod
    def create_packaged(code: str, name: str, **kwargs) -> ProductPackaged:
        obj = ProductPackaged(code=code, name=name,
                              created_at=now_cst(), updated_at=now_cst(), **kwargs)
        db.session.add(obj)
        db.session.commit()
        return obj

    @staticmethod
    def get_all_packaged() -> List[dict]:
        rows = ProductPackaged.query.order_by(ProductPackaged.code).all()
        return [r.to_dict() for r in rows]

    @staticmethod
    def update_packaged(obj: ProductPackaged, **kwargs) -> ProductPackaged:
        for k, v in kwargs.items():
            if hasattr(obj, k):
                setattr(obj, k, v)
        obj.updated_at = now_cst()
        db.session.commit()
        return obj

    # ── 关联管理 ──────────────────────────────────────────────────────────

    @staticmethod
    def get_packaged_by_finished(finished_id: int) -> List[ProductPackaged]:
        fin = db.session.get(ProductFinished, finished_id)
        return list(fin.packaged_list) if fin else []

    @staticmethod
    def add_packaged_to_finished(finished: ProductFinished, packaged: ProductPackaged) -> None:
        if packaged not in finished.packaged_list:
            finished.packaged_list.append(packaged)
            db.session.commit()

    @staticmethod
    def remove_packaged_from_finished(finished: ProductFinished, packaged: ProductPackaged) -> None:
        if packaged in finished.packaged_list:
            finished.packaged_list.remove(packaged)
            db.session.commit()