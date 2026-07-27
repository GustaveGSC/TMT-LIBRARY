import os
import re
import secrets
from datetime import date, timedelta
from result import Result
from database.repository.aftersale import AftersaleRepository
from database.models.aftersale import (
    AftersaleReasonCategory, AftersaleReason,
    AftersaleShippingAlias,
    AftersaleShippingAmbiguousTerm,
    AftersaleCase, AftersaleCaseReason,
    AftersaleCaseMedia, AftersaleMediaUploadSession, AftersaleMediaCleanupFailure,
)
from database.base import db
from storage.client import get_bucket
from upload_validation import parse_declared_size, UploadValidationError
from utils import now_cst

_MEDIA_EXTENSIONS = {
    'png': ('image/png', 'image'), 'jpg': ('image/jpeg', 'image'),
    'jpeg': ('image/jpeg', 'image'), 'webp': ('image/webp', 'image'),
    'mp4': ('video/mp4', 'video'), 'mov': ('video/quicktime', 'video'),
    'webm': ('video/webm', 'video'),
}
_MEDIA_LIMIT = int(os.getenv('AFTERSALE_MEDIA_UPLOAD_LIMIT', 500 * 1024 * 1024))
_ORDER_NO_RE = re.compile(r'^[A-Za-z0-9_-]{1,100}$')
_MEDIA_SESSION_TTL_MINUTES = 60

_repo = AftersaleRepository()


class AftersaleService:

    # ── 售后媒体 ───────────────────────────────────────────────────────────

    @staticmethod
    def _media_order_no(value):
        value = (value or '').strip()
        if not _ORDER_NO_RE.fullmatch(value) or '..' in value:
            raise ValueError('订单号只能包含字母、数字、下划线和连字符')
        return value

    @staticmethod
    def _media_ext(value):
        ext = (value or '').strip().lower().lstrip('.')
        if ext not in _MEDIA_EXTENSIONS:
            raise ValueError(f'不支持的媒体类型: {ext}')
        return ext

    def precheck_media(self, data):
        raw = data.get('order_nos') or []
        if not isinstance(raw, list) or not raw:
            return Result.fail('order_nos 至少需要一个订单号')
        order_nos = list(dict.fromkeys(self._media_order_no(value) for value in raw))
        if len(order_nos) > 200:
            return Result.fail('订单号数量不能超过 200')
        grouped = _repo.get_media_for_orders(order_nos)
        return Result.ok(data={order_no: {
            'exists': bool(grouped.get(order_no)),
            'count': len(grouped.get(order_no, [])),
            'files': [item.to_dict() for item in grouped.get(order_no, [])],
        } for order_no in order_nos})

    def presign_media(self, data, user_id):
        try:
            order_no = self._media_order_no(data.get('order_no'))
            mode = data.get('mode')
            if mode not in {'append', 'replace'}:
                raise ValueError('mode 必须是 append 或 replace')
            files = data.get('files') or []
            if not isinstance(files, list) or not 1 <= len(files) <= 100:
                raise ValueError('files 数量必须在 1 到 100 之间')
            normalized = []
            for item in files:
                if not isinstance(item, dict):
                    raise ValueError('files 格式错误')
                ext = self._media_ext(item.get('ext'))
                original = (item.get('original_filename') or '').strip()
                if not original or len(original) > 300 or any(c in original for c in '/\\\x00'):
                    raise ValueError('原文件名非法')
                size = parse_declared_size(item.get('file_size'), maximum=_MEDIA_LIMIT, label='售后媒体文件')
                normalized.append((ext, original, size))
        except (ValueError, UploadValidationError) as exc:
            return Result.fail(str(exc))

        # 已确认媒体和未过期预留共同占用 seq；唯一约束保护并发争抢，冲突时重试。
        for _ in range(3):
            try:
                now = now_cst()
                max_media = db.session.query(db.func.max(AftersaleCaseMedia.seq)).filter_by(order_no=order_no).scalar() or 0
                max_reserved = db.session.query(db.func.max(AftersaleMediaUploadSession.end_seq)).filter(
                    AftersaleMediaUploadSession.order_no == order_no,
                    AftersaleMediaUploadSession.expires_at > now,
                    AftersaleMediaUploadSession.confirmed_at.is_(None),
                ).scalar() or 0
                start_seq = 1 if mode == 'replace' else max(max_media, max_reserved) + 1
                token = secrets.token_urlsafe(48)
                manifest = []
                for offset, (ext, original, size) in enumerate(normalized):
                    seq = start_seq + offset
                    stored = f'{order_no}_{seq:03d}.{ext}'
                    rel_path = f'aftersale-media/{order_no}/{stored}'
                    manifest.append({
                        'seq': seq, 'ext': ext, 'file_type': _MEDIA_EXTENSIONS[ext][1],
                        'original_filename': original, 'stored_filename': stored,
                        'storage_key': f'tmt-library/{rel_path}', 'oss_url': f"{os.getenv('OSS_BASE_URL', '').rstrip('/')}/{rel_path}",
                        'file_size': size,
                    })
                session = AftersaleMediaUploadSession(
                    session_token=token, order_no=order_no, mode=mode,
                    start_seq=start_seq, reserved_start=start_seq, end_seq=start_seq + len(manifest) - 1,
                    manifest=manifest, uploaded_by=user_id,
                    expires_at=now + timedelta(minutes=_MEDIA_SESSION_TTL_MINUTES),
                )
                db.session.add(session)
                db.session.commit()
                bucket = get_bucket()
                items = []
                for item in manifest:
                    headers = {'Content-Type': _MEDIA_EXTENSIONS[item['ext']][0], 'Content-Length': str(item['file_size'])}
                    items.append({**item, 'presign_url': bucket.sign_url('PUT', item['storage_key'], 3600, headers=headers), 'required_headers': headers})
                return Result.ok(data={'session_token': token, 'expires_at': session.expires_at.strftime('%Y-%m-%d %H:%M:%S'), 'items': items})
            except Exception as exc:
                db.session.rollback()
                if 'uq_aftersale_media_session_start_seq' not in str(exc):
                    return Result.fail('生成媒体上传签名失败')
        return Result.fail('当前订单正在生成上传序号，请重试')

    def confirm_media(self, data, user_id):
        token = (data.get('session_token') or '').strip()
        if not token:
            return Result.fail('缺少 session_token')
        session = AftersaleMediaUploadSession.query.filter_by(session_token=token).first()
        if not session or session.uploaded_by != user_id:
            return Result.fail('上传会话不存在或无权限')
        if session.confirmed_at:
            return Result.ok(data={'order_no': session.order_no, 'confirmed': True, 'idempotent': True})
        if session.expires_at <= now_cst():
            return Result.fail('上传会话已过期，请重新获取上传签名')
        old_keys = []
        try:
            if session.mode == 'replace':
                old_keys = [row.storage_key for row in _repo.get_media(session.order_no)]
                AftersaleCaseMedia.query.filter_by(order_no=session.order_no).delete(synchronize_session=False)
            for item in session.manifest:
                db.session.add(AftersaleCaseMedia(
                    order_no=session.order_no, seq=item['seq'], file_type=item['file_type'],
                    original_filename=item['original_filename'], stored_filename=item['stored_filename'],
                    oss_url=item['oss_url'], storage_key=item['storage_key'], file_size=item['file_size'],
                    sort_order=item['seq'], uploaded_by=user_id,
                ))
            session.confirmed_at = now_cst()
            session.reserved_start = None
            db.session.commit()
        except Exception:
            db.session.rollback()
            return Result.fail('确认媒体上传失败')

        # DB 已提交后才做不可逆的旧对象删除；失败落库，绝不静默丢失。
        if old_keys:
            bucket = get_bucket()
            for key in old_keys:
                try:
                    bucket.delete_object(key)
                except Exception as exc:
                    db.session.add(AftersaleMediaCleanupFailure(
                        storage_key=key, order_no=session.order_no, error_message=str(exc)[:1000],
                    ))
            db.session.commit()
        return Result.ok(data={'order_no': session.order_no, 'confirmed': True, 'count': len(session.manifest)})

    def get_media_flags(self, data):
        try:
            raw = data.get('order_nos') or []
            if not isinstance(raw, list) or len(raw) > 200:
                raise ValueError('order_nos 数量必须在 1 到 200 之间')
            order_nos = list(dict.fromkeys(self._media_order_no(value) for value in raw))
        except ValueError as exc:
            return Result.fail(str(exc))
        return Result.ok(data=_repo.get_media_summaries(order_nos))

    def get_case_media(self, order_no):
        try:
            order_no = self._media_order_no(order_no)
        except ValueError as exc:
            return Result.fail(str(exc))
        return Result.ok(data=[row.to_dict() for row in _repo.get_media(order_no)])

    def delete_case_media(self, media_id):
        """Delete the DB record first; an OSS failure is compensatable, not a failed delete."""
        media = db.session.get(AftersaleCaseMedia, media_id)
        if not media:
            return Result.fail('媒体不存在')
        storage_key, order_no = media.storage_key, media.order_no
        try:
            db.session.delete(media)
            db.session.commit()
        except Exception:
            db.session.rollback()
            return Result.fail('删除媒体记录失败')

        try:
            get_bucket().delete_object(storage_key)
        except Exception as exc:
            # The user-visible deletion has succeeded; persist a retryable cleanup task.
            try:
                db.session.add(AftersaleMediaCleanupFailure(
                    storage_key=storage_key, order_no=order_no,
                    error_message=str(exc)[:1000],
                ))
                db.session.commit()
            except Exception:
                db.session.rollback()
        return Result.ok(data={'id': media_id, 'deleted': True})

    # ── 一级分类 ───────────────────────────────────────────────────────────────

    def get_categories(self):
        cats = _repo.get_all_categories()
        return Result.ok(data=[c.to_dict() for c in cats])

    def create_category(self, data):
        name = (data.get('name') or '').strip()
        if not name:
            return Result.fail('分类名称不能为空')
        if AftersaleReasonCategory.query.filter_by(name=name).first():
            return Result.fail('该分类名称已存在')
        cat = _repo.create_category(name=name, sort_order=data.get('sort_order', 0))
        return Result.ok(data=cat.to_dict())

    def update_category(self, category_id, data):
        name = (data.get('name') or '').strip()
        if not name:
            return Result.fail('分类名称不能为空')
        # 名称唯一性校验（排除自身）
        existing = AftersaleReasonCategory.query.filter_by(name=name).first()
        if existing and existing.id != category_id:
            return Result.fail('该分类名称已存在')
        cat = _repo.update_category(
            category_id=category_id,
            name=name,
            sort_order=data.get('sort_order'),
        )
        if not cat:
            return Result.fail('分类不存在')
        return Result.ok(data=cat.to_dict())

    def delete_category(self, category_id):
        ok, count = _repo.delete_category(category_id)
        if not ok:
            if count > 0:
                return Result.fail(f'该分类下还有 {count} 个原因，请先移除或删除这些原因',
                                   data={'reason_count': count})
            return Result.fail('分类不存在')
        return Result.ok()


    # ── 二级原因 ───────────────────────────────────────────────────────────────

    def get_reasons(self):
        """按一级分类聚合返回，包含无分类的原因"""
        categories = _repo.get_all_categories()
        all_reasons = _repo.get_all_reasons()

        # 按 category_id 分组
        reason_map = {}
        for r in all_reasons:
            reason_map.setdefault(r.category_id, []).append(r.to_dict())

        # 按分类顺序构建结果
        result = []
        for cat in categories:
            result.append({
                'category_id':   cat.id,
                'category_name': cat.name,
                'sort_order':    cat.sort_order,
                'reasons':       reason_map.get(cat.id, []),
            })

        # 追加未归类原因
        uncategorized = reason_map.get(None, [])
        if uncategorized:
            result.append({
                'category_id':   None,
                'category_name': '未分类',
                'sort_order':    9999,
                'reasons':       uncategorized,
            })

        return Result.ok(data=result)

    def create_reason(self, data):
        name = (data.get('name') or '').strip()
        if not name:
            return Result.fail('原因名称不能为空')
        if AftersaleReason.query.filter_by(name=name).first():
            return Result.fail('该原因名称已存在')
        reason = _repo.create_reason(
            name=name,
            category_id=data.get('category_id'),
            keywords=data.get('keywords', ''),
            negative_keywords=data.get('negative_keywords', ''),
            sort_order=data.get('sort_order', 0),
        )
        return Result.ok(data=reason.to_dict())

    def update_reason(self, reason_id, data):
        name = (data.get('name') or '').strip()
        if not name:
            return Result.fail('原因名称不能为空')
        reason = _repo.update_reason(
            reason_id=reason_id,
            name=name,
            category_id=data.get('category_id'),
            keywords=data.get('keywords', ''),
            negative_keywords=data.get('negative_keywords', ''),
            sort_order=data.get('sort_order'),
        )
        if not reason:
            return Result.fail('原因不存在')
        return Result.ok(data=reason.to_dict())

    def delete_reason(self, reason_id):
        usage = _repo.get_reason_usage(reason_id)
        if usage > 0:
            return Result.fail(f'该原因已被 {usage} 条记录引用，无法删除', data={'usage_count': usage})
        ok, _ = _repo.delete_reason(reason_id)
        if not ok:
            return Result.fail('删除失败')
        return Result.ok()

    def get_reason_usage(self, reason_id):
        usage = _repo.get_reason_usage(reason_id)
        return Result.ok(data={'usage_count': usage})

    def merge_reason(self, source_id, target_id):
        if source_id == target_id:
            return Result.fail('不能将原因合并到自身')
        ok = _repo.merge_reason(source_id, target_id)
        if not ok:
            return Result.fail('原因不存在')
        return Result.ok()

    def get_case_edit_options(self):
        return _repo.get_case_edit_options()

    def update_case_reason(self, cr_id, data):
        return _repo.update_case_reason(cr_id, data)

    # ── 发货物料简称库 ─────────────────────────────────────────────────────────

    def get_shipping_aliases(self):
        return Result.ok(data=[a.to_dict() for a in _repo.get_all_shipping_aliases()])

    def create_shipping_alias(self, data):
        name = (data.get('name') or '').strip()
        if not name:
            return Result.fail('简称不能为空')
        if AftersaleShippingAlias.query.filter_by(name=name).first():
            return Result.fail('该简称已存在')
        keywords = [k.strip() for k in (data.get('keywords') or []) if str(k).strip()]
        obj = _repo.create_shipping_alias(name=name, keywords=keywords,
                                          sort_order=data.get('sort_order', 0))
        return Result.ok(data=obj.to_dict())

    def update_shipping_alias(self, alias_id, data):
        name = (data.get('name') or '').strip()
        if not name:
            return Result.fail('简称不能为空')
        existing = AftersaleShippingAlias.query.filter_by(name=name).first()
        if existing and existing.id != alias_id:
            return Result.fail('该简称已存在')
        keywords = [k.strip() for k in (data.get('keywords') or []) if str(k).strip()]
        obj = _repo.update_shipping_alias(alias_id, name=name, keywords=keywords,
                                          sort_order=data.get('sort_order'))
        if not obj:
            return Result.fail('简称不存在')
        return Result.ok(data=obj.to_dict())

    def delete_shipping_alias(self, alias_id):
        ok = _repo.delete_shipping_alias(alias_id)
        if not ok:
            return Result.fail('简称不存在')
        return Result.ok()

    def merge_shipping_alias(self, source_id, target_id):
        if source_id == target_id:
            return Result.fail('不能将简称合并到自身')
        ok = _repo.merge_shipping_alias(source_id, target_id)
        if not ok:
            return Result.fail('简称不存在')
        return Result.ok(message='已合并')

    # ── 待处理订单 ──────────────────────────────────────────────────────────

    def get_pending_orders(self, page, page_size, search, date_start, date_end):
        items, total = _repo.get_pending_orders(
            page=page, page_size=page_size,
            search=search, date_start=date_start, date_end=date_end,
        )
        return Result.ok(data={'items': items, 'total': total, 'page': page, 'page_size': page_size})

    def get_pending_count(self):
        count = _repo.get_pending_count()
        return Result.ok(data={'count': count})

    # ── 工单 ────────────────────────────────────────────────────────────────

    def get_cases(self, page, page_size, status, date_start, date_end,
                  reason_id, channel_name, province, city, district,
                  reason_category, reason_name, shipping_alias,
                  model_code=None, search=None, sort_by=None, sort_order='desc',
                  model_ids=None, series_ids=None, category_ids=None,
                  reason_ids=None, reason_category_ids=None,
                  shipping_alias_ids=None, channel_names=None,
                  provinces=None, cities=None,
                  max_days_since_purchase=None,
                  exclude_no_sales_series=False, has_media=False):
        items, total = _repo.get_cases(
            page=page, page_size=page_size,
            status=status, date_start=date_start, date_end=date_end,
            reason_id=reason_id, channel_name=channel_name,
            province=province, city=city, district=district,
            reason_category=reason_category, reason_name=reason_name,
            shipping_alias=shipping_alias,
            model_code=model_code, search=search,
            sort_by=sort_by, sort_order=sort_order,
            model_ids=model_ids, series_ids=series_ids, category_ids=category_ids,
            reason_ids=reason_ids, reason_category_ids=reason_category_ids,
            shipping_alias_ids=shipping_alias_ids, channel_names=channel_names,
            provinces=provinces, cities=cities,
            max_days_since_purchase=max_days_since_purchase,
            exclude_no_sales_series=exclude_no_sales_series,
            has_media=has_media,
        )
        response_items = [c.to_dict(include_reasons=False) for c in items]
        _repo.apply_import_names_to_case_snapshots(response_items)
        return Result.ok(data={
            'items':     response_items,
            'total':     total,
            'page':      page,
            'page_size': page_size,
        })

    def export_cases_to_file(self, output_path, status, date_start, date_end,
                     reason_id, channel_name, province, city, district,
                     reason_category, reason_name, shipping_alias,
                     model_code=None, search=None, sort_by=None, sort_order='desc',
                     category_ids=None, series_ids=None, model_ids=None,
                     reason_ids=None, reason_category_ids=None,
                     shipping_alias_ids=None, channel_names=None, provinces=None):
        """分页读取并以 write-only 模式导出到磁盘，避免大结果常驻 worker 内存。"""
        import openpyxl
        from openpyxl.cell import WriteOnlyCell
        from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
        from openpyxl.utils import get_column_letter
        from sqlalchemy.orm import selectinload
        from database.models.product.category import ProductModel, ProductSeries

        # 限制导出行数，防止超大数据集打满 DB/内存
        EXPORT_MAX_ROWS = max(1, int(os.getenv('EXPORT_MAX_ROWS', 50000)))
        EXPORT_PAGE_SIZE = max(1, min(int(os.getenv('EXPORT_PAGE_SIZE', 1000)), EXPORT_MAX_ROWS))

        def _get_page(page, count_total):
            return _repo.get_cases(
                page=page, page_size=EXPORT_PAGE_SIZE,
                status=status, date_start=date_start, date_end=date_end,
                reason_id=reason_id, channel_name=channel_name,
                province=province, city=city, district=district,
                reason_category=reason_category, reason_name=reason_name,
                shipping_alias=shipping_alias,
                model_code=model_code, search=search,
                sort_by=sort_by, sort_order=sort_order,
                category_ids=category_ids, series_ids=series_ids, model_ids=model_ids,
                reason_ids=reason_ids, reason_category_ids=reason_category_ids,
                shipping_alias_ids=shipping_alias_ids, channel_names=channel_names,
                provinces=provinces,
                count_total=count_total,
            )

        def _load_reasons(items):
            case_ids = [case.id for case in items]
            if not case_ids:
                return {}
            cases_with_reasons = (
                AftersaleCase.query
                .filter(AftersaleCase.id.in_(case_ids))
                .options(
                    selectinload(AftersaleCase.case_reasons)
                    .selectinload(AftersaleCaseReason.reason)
                    .selectinload(AftersaleReason.category_obj),
                    selectinload(AftersaleCase.case_reasons)
                    .selectinload(AftersaleCaseReason.product_model)
                    .selectinload(ProductModel.series)
                    .selectinload(ProductSeries.category),
                    selectinload(AftersaleCase.case_reasons)
                    .selectinload(AftersaleCaseReason.shipping_alias),
                )
                .all()
            )
            return {case.id: case.case_reasons for case in cases_with_reasons}

        # ── 构建 xlsx ─────────────────────────────────────────────
        wb = openpyxl.Workbook(write_only=True)
        ws = wb.create_sheet()
        ws.title = '售后数据'

        # 表头样式
        header_font    = Font(name='Microsoft YaHei UI', bold=True, size=10)
        header_fill    = PatternFill('solid', fgColor='F5F0E8')
        center_align   = Alignment(horizontal='center', vertical='center', wrap_text=False)
        left_align     = Alignment(horizontal='left',   vertical='center', wrap_text=False)
        thin_side      = Side(style='thin', color='C0C0C0')
        thin_border    = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)
        normal_font    = Font(name='Microsoft YaHei UI', size=10)

        # 列顺序与页面表格一致，新增「发货物料」列
        headers = [
            ('订单号',      22),
            ('产品品类',    14),
            ('系列',        16),
            ('产品型号',    14),
            ('原因分类',    14),
            ('具体原因',    20),
            ('发货物料',    32),
            ('发货简称',    16),
            ('售后日期',    12),
            ('购买日期',    12),
            ('售后间隔(天)', 11),
            ('渠道',        14),
            ('省份',        10),
            ('买家留言',    30),
            ('商家备注',    30),
        ]

        # 左对齐列（1-based）
        LEFT_COLS = {1, 4, 6, 7, 8, 14, 15}

        header_row = []
        for col_idx, (label, width) in enumerate(headers, 1):
            cell = WriteOnlyCell(ws, value=label)
            cell.font      = header_font
            cell.fill      = header_fill
            cell.alignment = left_align if col_idx in LEFT_COLS else center_align
            cell.border    = thin_border
            header_row.append(cell)
            ws.column_dimensions[get_column_letter(col_idx)].width = width

        ws.freeze_panes = 'A2'
        ws.append(header_row)

        # 预构建产品型号→系列/品类 id 映射（用于 reason 过滤）
        def _reason_matches_filter(cr):
            """判断一条 reason 是否满足产品/原因/发货维度的筛选条件"""
            if model_ids:
                if not cr or cr.model_id not in model_ids:
                    return False
            elif series_ids:
                if not cr or not cr.product_model or cr.product_model.series_id not in series_ids:
                    return False
            elif category_ids:
                if not cr or not cr.product_model or not cr.product_model.series:
                    return False
                if cr.product_model.series.category_id not in category_ids:
                    return False
            if reason_ids:
                if not cr or cr.reason_id not in reason_ids:
                    return False
            elif reason_category_ids:
                if not cr or not cr.reason or cr.reason.category_id not in reason_category_ids:
                    return False
            elif reason_category:
                if not cr or not cr.reason or not cr.reason.category_obj:
                    return False
                if cr.reason.category_obj.name != reason_category:
                    return False
            elif reason_name:
                if not cr or not cr.reason or cr.reason.name != reason_name:
                    return False
            if shipping_alias_ids:
                if not cr or cr.shipping_alias_id not in shipping_alias_ids:
                    return False
            elif shipping_alias:
                if not cr or cr.shipping_alias_id != shipping_alias:
                    return False
            return True

        def _cell(col_idx, value, wrap=False):
            cell = WriteOnlyCell(ws, value=value)
            cell.font = normal_font
            cell.border = thin_border
            cell.alignment = (
                Alignment(horizontal='left', vertical='center', wrap_text=True)
                if wrap else (left_align if col_idx in LEFT_COLS else center_align)
            )
            return cell

        # 每页只保留有限 ORM 对象；write-only worksheet 不缓存历史单元格。
        from database.base import db
        page = 1
        exported_cases = 0
        total = 0
        while page == 1 or exported_cases < min(total, EXPORT_MAX_ROWS):
            items, page_total = _get_page(page, count_total=(page == 1))
            if page == 1:
                total = page_total
            remaining = EXPORT_MAX_ROWS - exported_cases
            items = items[:remaining]
            if not items:
                break
            reasons_map = _load_reasons(items)

            for case in items:
                all_reasons = reasons_map.get(case.id, [])
                reasons = [cr for cr in all_reasons if _reason_matches_filter(cr)] or [None]

                products_text = None
                if case.products:
                    parts = [
                        f"{product.get('name', '')}×{product.get('quantity', '')}"
                        for product in case.products if product.get('name')
                    ]
                    products_text = '\n'.join(parts) if parts else None

                for cr in reasons:
                    cat_name = None
                    if cr and cr.product_model and cr.product_model.series and cr.product_model.series.category:
                        cat_name = cr.product_model.series.category.name
                    series_str = None
                    if cr and cr.product_model and cr.product_model.series:
                        series = cr.product_model.series
                        series_str = f"{series.code} {series.name}" if series.name else series.code
                    reason_cat = None
                    if cr and cr.reason and cr.reason.category_obj:
                        reason_cat = cr.reason.category_obj.name

                    values = [
                        case.ecommerce_order_no,
                        cat_name,
                        series_str,
                        cr.product_model.model_code if cr and cr.product_model else None,
                        reason_cat,
                        cr.reason.name if cr and cr.reason else None,
                        products_text,
                        cr.shipping_alias.name if cr and cr.shipping_alias else None,
                        case.shipped_date.strftime('%Y-%m-%d') if case.shipped_date else None,
                        cr.purchase_date.strftime('%Y-%m-%d') if cr and cr.purchase_date else None,
                        cr.days_since_purchase if cr else None,
                        case.channel_name,
                        case.province,
                        case.buyer_remark,
                        case.seller_remark,
                    ]
                    ws.append([
                        _cell(index, value, wrap=(index == 7 and bool(products_text and '\n' in products_text)))
                        for index, value in enumerate(values, 1)
                    ])

            exported_cases += len(items)
            page += 1
            db.session.expunge_all()

        # 命中上限时在末行追加提示，让用户知晓数据被截断
        if total > EXPORT_MAX_ROWS:
            ws.append([f'⚠ 数据已超过 {EXPORT_MAX_ROWS} 条上限，仅导出前 {EXPORT_MAX_ROWS} 条。请缩小筛选范围后重新导出。'])

        wb.save(output_path)
        return {'exported_cases': exported_cases, 'total': total}

    def get_cases_reasons(self, case_ids):
        """批量返回指定工单的 reasons，用于前端两阶段加载"""
        if not case_ids:
            return Result.ok(data={})
        from sqlalchemy.orm import selectinload
        from database.models.product.category import ProductModel, ProductSeries
        cases = (
            AftersaleCase.query
            .filter(AftersaleCase.id.in_(case_ids))
            .options(
                selectinload(AftersaleCase.case_reasons)
                .selectinload(AftersaleCaseReason.reason)
                .selectinload(AftersaleReason.category_obj),
                selectinload(AftersaleCase.case_reasons)
                .selectinload(AftersaleCaseReason.product_model)
                .selectinload(ProductModel.series)
                .selectinload(ProductSeries.category),
                selectinload(AftersaleCase.case_reasons)
                .selectinload(AftersaleCaseReason.shipping_alias),
            )
            .all()
        )
        return Result.ok(data={
            str(c.id): [r.to_dict() for r in c.case_reasons]
            for c in cases
        })

    def get_filter_options(self):
        return Result.ok(data=_repo.get_filter_options())

    def get_filtered_table_options(self, data: dict):
        # 支持列表、逗号分隔字符串、单个数字字符串三种格式
        def _ints(key):
            val = data.get(key)
            if val is None: return []
            if isinstance(val, (int, float)): return [int(val)]
            if isinstance(val, str): val = [v.strip() for v in val.split(',')]
            return [int(x) for x in val if str(x).strip().lstrip('-').isdigit()]
        # 单值参数合并到对应的列表参数
        channel_names = list(data.get('channel_names') or [])
        if data.get('channel_name'): channel_names = list(set(channel_names) | {data['channel_name']})
        provinces = list(data.get('provinces') or [])
        if data.get('province'): provinces = list(set(provinces) | {data['province']})
        filters = {
            'date_start':              data.get('date_start'),
            'date_end':                data.get('date_end'),
            'max_days_since_purchase': int(data['max_days_since_purchase']) if data.get('max_days_since_purchase') is not None else None,
            'model_ids':               _ints('model_ids'),
            'series_ids':              _ints('series_ids'),
            'category_ids':            _ints('category_ids'),
            'reason_ids':              _ints('reason_ids'),
            'reason_category_ids':     _ints('reason_category_ids'),
            'shipping_alias_ids':      _ints('shipping_alias_ids'),
            'channel_names':           channel_names,
            'provinces':               provinces,
            'cities':                  list(data.get('cities') or []),
            'reason_category':         data.get('reason_category') or None,
            'reason_name':             data.get('reason_name') or None,
        }
        return Result.ok(data=_repo.get_filtered_table_options(filters))

    def get_case(self, case_id):
        case = _repo.get_case_by_id(case_id)
        if not case:
            return Result.fail('工单不存在')
        return Result.ok(data=case.to_dict(include_reasons=True))

    def confirm_case(self, data):
        order_no = (data.get('ecommerce_order_no') or '').strip()
        if not order_no:
            return Result.fail('订单号不能为空')

        reasons_data = data.get('reasons', [])

        # 解析日期
        shipped_date = None
        if data.get('shipped_date'):
            try:
                shipped_date = date.fromisoformat(data['shipped_date'])
            except ValueError:
                pass

        case = _repo.confirm_case(
            order_no=order_no,
            products=data.get('products', []),
            seller_remark=data.get('seller_remark'),
            buyer_remark=data.get('buyer_remark'),
            shipped_date=shipped_date,
            operator=data.get('operator'),
            channel_name=data.get('channel_name'),
            province=data.get('province'),
            reasons_data=reasons_data,
            city=data.get('city'),
            district=data.get('district'),
        )
        return Result.ok(data=case.to_dict(include_reasons=True))

    def update_case(self, case_id, data):
        reasons_data = data.get('reasons', [])
        case = _repo.update_case(
            case_id=case_id,
            reasons_data=reasons_data,
            assigned_models=data.get('assigned_models'),
            shipping_materials=data.get('shipping_materials'),
            aftersale_materials=data.get('aftersale_materials'),
        )
        if not case:
            return Result.fail('工单不存在')
        return Result.ok(data=case.to_dict(include_reasons=True))

    def ignore_case(self, order_no):
        if not order_no:
            return Result.fail('订单号不能为空')
        case = _repo.ignore_case(order_no)
        return Result.ok(data=case.to_dict())

    # ── 产品型号推断 ────────────────────────────────────────────────────────

    def suggest_product(self, data, semantic=True):
        products      = data.get('products', [])
        product_codes = [p.get('code') for p in products if p.get('code')]
        purchase_date = data.get('purchase_date')
        seller_remark = data.get('seller_remark')
        buyer_remark  = data.get('buyer_remark')
        result = _repo.suggest_product(product_codes, purchase_date, seller_remark, buyer_remark, products, semantic=semantic)
        return Result.ok(data=result)

    # ── 自动匹配 ────────────────────────────────────────────────────────────

    def auto_match(self, text, buyer_remark=None, semantic=True, model_id=None):
        if not text:
            return Result.ok(data={'items': [], 'cleaned_text': ''})
        result = _repo.auto_match(text, buyer_remark=buyer_remark, semantic=semantic, model_id=model_id)
        return Result.ok(data=result)

    # ── 统计 & 图表 ─────────────────────────────────────────────────────────

    def get_stats(self):
        stats = _repo.get_stats()
        return Result.ok(data=stats)

    def get_cross_filter_options(self, data: dict):
        max_days = data.get('max_days_since_purchase')
        filters = {
            'date_start':               data.get('date_start'),
            'date_end':                 data.get('date_end'),
            'max_days_since_purchase':  int(max_days) if max_days is not None else None,
            'channel_names':            data.get('channel_names') or [],
            'provinces':                data.get('provinces') or [],
            'cities':                   data.get('cities') or [],
            'category_ids':             data.get('category_ids') or [],
            'series_ids':               data.get('series_ids') or [],
            'model_ids':                data.get('model_ids') or [],
            'reason_ids':               data.get('reason_ids') or [],
            'reason_category_ids':      data.get('reason_category_ids') or [],
            'shipping_alias_ids':       data.get('shipping_alias_ids') or [],
        }
        opts = _repo.get_cross_filter_options(filters)
        return Result.ok(data=opts)

    def get_chart_options(self):
        opts = _repo.get_chart_options()
        return Result.ok(data=opts)

    def get_chart_data(self, data):
        group_by = data.get('group_by', 'reason')
        if group_by not in ('product', 'reason', 'reason_category', 'shipping_alias', 'channel', 'province'):
            return Result.fail('group_by 参数无效')
        max_days = data.get('max_days_since_purchase')
        filters = {
            'group_by':                group_by,
            'date_start':              data.get('date_start'),
            'date_end':                data.get('date_end'),
            'max_days_since_purchase': int(max_days) if max_days is not None else None,
            'channel_names':           data.get('channel_names') or [],
            'provinces':               data.get('provinces') or [],
            'cities':                  data.get('cities') or [],
            'category_ids':            data.get('category_ids') or [],
            'series_ids':              data.get('series_ids') or [],
            'model_ids':               data.get('model_ids') or [],
            'reason_ids':              data.get('reason_ids') or [],
            'reason_category_ids':     data.get('reason_category_ids') or [],
            'shipping_alias_ids':      data.get('shipping_alias_ids') or [],
            'exclude_no_sales_series': bool(data.get('exclude_no_sales_series')),
        }
        result = _repo.get_chart_data(filters)
        return Result.ok(data=result)

    # ── 发货物料匹配过滤词 ────────────────────────────────────────────────────

    def get_ignore_terms(self):
        return Result.ok(data=[t.to_dict() for t in _repo.get_all_ignore_terms()])

    def create_ignore_term(self, data):
        term = (data.get('term') or '').strip()
        if not term:
            return Result.fail('过滤词不能为空')
        from database.models.aftersale import AftersaleShippingIgnoreTerm
        if AftersaleShippingIgnoreTerm.query.filter_by(term=term).first():
            return Result.fail('该过滤词已存在')
        obj = _repo.create_ignore_term(term=term)
        return Result.ok(data=obj.to_dict())

    def delete_ignore_term(self, term_id):
        ok = _repo.delete_ignore_term(term_id)
        if not ok:
            return Result.fail('过滤词不存在')
        return Result.ok()

    # ── 发货物料歧义词 ─────────────────────────────────────────────────────────

    def get_ambiguous_terms(self):
        return Result.ok(data=[t.to_dict() for t in _repo.get_all_ambiguous_terms()])

    def create_ambiguous_term(self, data):
        term = (data.get('term') or '').strip()
        if not term:
            return Result.fail('词不能为空')
        if AftersaleShippingAmbiguousTerm.query.filter_by(term=term).first():
            return Result.fail('该词已存在')
        obj = _repo.create_ambiguous_term(term=term)
        return Result.ok(data=obj.to_dict())

    def delete_ambiguous_term(self, term_id):
        ok = _repo.delete_ambiguous_term(term_id)
        if not ok:
            return Result.fail('词不存在')
        return Result.ok()

    # ── 词典自动建议 ────────────────────────────────────────────────────────────

    def get_dict_suggestions(self, type_filter=None, status='pending'):
        items = _repo.get_dict_suggestions(type_filter=type_filter, status=status)
        return Result.ok(data=[s.to_dict() for s in items])

    def accept_dict_suggestion(self, sug_id):
        sug, err = _repo.accept_dict_suggestion(sug_id)
        if err:
            return Result.fail(err)
        return Result.ok(data=sug.to_dict())

    def reject_dict_suggestion(self, sug_id):
        sug = _repo.reject_dict_suggestion(sug_id)
        if not sug:
            return Result.fail('建议不存在或已处理')
        return Result.ok(data=sug.to_dict())

    # ── 原因-简称亲和度 ──────────────────────────────────────────────────────────

    def get_alias_affinity(self, reason_id, alias_ids):
        affinity = _repo.get_alias_affinity(reason_id, alias_ids)
        return Result.ok(data=affinity)

    # ── 管理工具 ────────────────────────────────────────────────────────────────

    def migrate_alias_keywords(self):
        total, changed = _repo.migrate_alias_keywords()
        return Result.ok(data={'total': total, 'changed': changed},
                         message=f'迁移完成：共 {total} 条简称，更新 {changed} 条')

    # ── 售后原因关键词词典（标准档）────────────────────────────────────────────

    def get_reason_keyword_rules(self):
        return Result.ok(data=_repo.get_reason_keyword_rules())

    def update_reason_keyword_rules(self, data):
        stopwords = data.get('stopwords') or []
        if 'short_keep_terms' not in data:
            short_keep_terms = _repo.get_reason_keyword_rules().get('short_keep_terms', [])
        else:
            short_keep_terms = data.get('short_keep_terms')
            if not isinstance(short_keep_terms, list):
                return Result.fail('short_keep_terms 必须为数组')
        if not isinstance(stopwords, list):
            return Result.fail('词典字段必须为数组')
        _repo.replace_reason_keyword_rules(
            stopwords=stopwords,
            short_keep_terms=short_keep_terms,
        )
        return Result.ok(data=_repo.get_reason_keyword_rules())

    # ── 产品留言词典（材质/颜色/驱动/尺寸）────────────────────────────────────

    def get_product_remark_dict(self):
        return Result.ok(data=_repo.get_product_remark_dict())

    def put_product_remark_dict(self, items):
        if not isinstance(items, list):
            return Result.fail('items 必须为数组')
        valid_types = {'material', 'color', 'drive_type', 'size', 'series_alias'}
        for item in items:
            if item.get('type') not in valid_types:
                return Result.fail(f'无效的 type: {item.get("type")}')
            if not (item.get('value') or '').strip():
                return Result.fail('value 不能为空')
            if item.get('type') == 'size' and not (item.get('display') or '').strip():
                return Result.fail('size 类型必须填写 display（米制表达）')
            if item.get('type') == 'series_alias' and not (item.get('display') or '').strip():
                return Result.fail('series_alias 类型必须填写 display（官方系列名）')
        _repo.replace_product_remark_dict(items)
        return Result.ok(data=_repo.get_product_remark_dict())

    def cleanup_keyword_candidates(self, min_count=2, top_per_reason=200):
        result = _repo.cleanup_keyword_candidates(min_count=min_count, top_per_reason=top_per_reason)
        return Result.ok(data=result,
                         message=f'清理完成：噪声 {result["deleted_noise"]} 条，溢出 {result["deleted_overflow"]} 条，剩余 {result["remaining"]} 条')

    def get_keyword_candidate_stats(self):
        return Result.ok(data=_repo.get_keyword_candidate_stats())

    def get_series_monthly_by_model_id(self, model_id: int):
        data = _repo.get_series_monthly_by_model_id(model_id)
        return Result.ok(data=data)

    # ── 通用设置 ────────────────────────────────────────────────────────────

    def get_settings(self):
        return Result.ok(data=_repo.get_settings())

    def update_setting(self, data):
        key   = (data.get('key') or '').strip()
        value = data.get('value')
        if not key:
            return Result.fail('key 不能为空')
        if value is None:
            return Result.fail('value 不能为空')
        ok, err = _repo.update_setting(key, value)
        if not ok:
            return Result.fail(err)
        return Result.ok(message='保存成功')
