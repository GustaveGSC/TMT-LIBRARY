import re
from datetime import datetime
from typing import List, Dict, Tuple
from database.repository.product.import_raw import ImportProductRepository

from utils import now_cst

# 去除品名中"（已停用）"字样（兼容全角/半角括号）
_DISCONTINUED_RE = re.compile(r'[（(]已停用[）)]')


def _clean_name(name: str, spec: str) -> str:
    """品名去除停用标记后与规格拼接"""
    cleaned = _DISCONTINUED_RE.sub('', name).strip()
    spec = (spec or '').strip()
    return f"{cleaned} {spec}" if spec else cleaned


def _parse_rows(raw_rows: List[Dict]) -> Tuple[List[Dict], int]:
    """解析原始行，返回 (处理后的行列表, 跳过行数)"""
    parsed, skipped = [], 0
    for row in raw_rows:
        code       = (row.get('code')       or '').strip()
        name       = (row.get('name')       or '').strip()
        spec       = (row.get('spec')       or '').strip()
        status     = (row.get('status')     or '').strip()
        group_code = (row.get('group_code') or '').strip()
        group_name = (row.get('group_name') or '').strip()

        if not code or not name or not group_code or not group_name:
            skipped += 1
            continue

        parsed.append({
            'code':       code,
            'name':       _clean_name(name, spec),
            # 保留 ERP 原始品名供可配置停用关键词判定；既有 name 语义不变。
            'raw_name':   name,
            'spec':       spec or None,
            'status':     status or None,
            'group_code': group_code,
            'group_name': group_name,
        })
    return parsed, skipped


class ImportProductService:

    def import_rows(self, raw_rows: List[Dict]) -> Dict:
        parsed, skipped_invalid = _parse_rows(raw_rows)
        imported_at  = now_cst()
        result       = ImportProductRepository.bulk_upsert(parsed, imported_at)
        # 物料库按类型筛选/分组计数用的判定结果缓存依赖 ERP 物料清单，导入后必须失效
        from services.product.material import material_service
        material_service.invalidate_classification_cache()
        # 研发 BOM 里导入时没匹配上的编码，ERP 新增后自动补关联（只处理 erp_code 为空的）
        from services.product.material_bom import material_bom_service
        relinked = material_bom_service.relink_unmatched_erp_codes()
        return {
            'total':           len(raw_rows),
            **result,
            **relinked,
            # 兼容旧前端字段；现在仅代表内容完全相同、无需写入的重复行。
            'skipped_dup':     result['unchanged'],
            'skipped_invalid': skipped_invalid,
        }

    def get_stats(self) -> Dict:
        return ImportProductRepository.get_stats()


import_product_service = ImportProductService()
