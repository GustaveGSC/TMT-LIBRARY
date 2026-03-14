import re
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Tuple
from database.repository.product.import_raw import ImportProductRepository

CST = timezone(timedelta(hours=8))
def now_cst(): return datetime.now(CST).replace(tzinfo=None)

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
        group_code = (row.get('group_code') or '').strip()
        group_name = (row.get('group_name') or '').strip()

        if not code or not name or not group_code or not group_name:
            skipped += 1
            continue

        parsed.append({
            'code':       code,
            'name':       _clean_name(name, spec),
            'group_code': group_code,
            'group_name': group_name,
        })
    return parsed, skipped


class ImportProductService:

    def import_rows(self, raw_rows: List[Dict]) -> Dict:
        parsed, skipped_invalid = _parse_rows(raw_rows)
        imported_at  = now_cst()
        inserted     = ImportProductRepository.bulk_insert(parsed, imported_at)
        skipped_dup  = len(parsed) - inserted
        return {
            'total':           len(raw_rows),
            'inserted':        inserted,
            'skipped_dup':     skipped_dup,
            'skipped_invalid': skipped_invalid,
        }

    def get_stats(self) -> Dict:
        return ImportProductRepository.get_stats()


import_product_service = ImportProductService()
