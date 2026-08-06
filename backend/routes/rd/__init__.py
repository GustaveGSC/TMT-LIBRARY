from flask import Blueprint, request, Response
from auth import make_blueprint_guard
import io, urllib.parse, os, sys
from upload_validation import read_spreadsheet_upload, UploadValidationError
from error_handling import internal_error_response
from services.rd.change_documents import (
    build_ecr_xlsx,
    build_ecn_xlsx,
    compare_bom as compare_bom_files,
    parse_ecr_rows_xls,
    parse_ecr_rows_xlsx,
    validate_bom,
)
from services.rd.pdm_to_bom import build_bom_data, build_erp_data

rd_bp = Blueprint('rd', __name__)
rd_bp.before_request(make_blueprint_guard('rd:view', 'rd:edit'))

# ── 路由 ──────────────────────────────────────────────

@rd_bp.post('/ecr/export')
def export_ecr():
    from result import Result
    d = request.get_json() or {}
    changes = d.pop('changes', None)
    try:
        xlsx_bytes = build_ecr_xlsx(d, changes)
    except Exception:
        return internal_error_response('ECR 文件生成失败', '生成失败')

    ecr_code = d.get('ecr_code', 'ECR')
    project  = d.get('project', '')
    filename = f"{ecr_code} {project} 变更申请单.xlsx".replace('/', '-')
    encoded  = urllib.parse.quote(filename)

    return Response(
        xlsx_bytes,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={
            'Content-Disposition': f"attachment; filename*=UTF-8''{encoded}",
            'Content-Length': str(len(xlsx_bytes)),
        }
    )




@rd_bp.post('/ecr/parse-ecr')
def parse_ecr():
    """解析上传的 ECR xlsx/xls，字段名 ecr_file。"""
    from result import Result
    import tempfile

    f = request.files.get('ecr_file')
    if not f:
        return Result.fail('请上传 ECR 文件').to_response()
    try:
        read_spreadsheet_upload(f, label='ECR 文件')
    except UploadValidationError as exc:
        return Result.fail(str(exc)).to_response(413 if '不能超过' in str(exc) else 400)
    ext = os.path.splitext(f.filename)[1].lower() or '.xlsx'
    tmp = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
    path = tmp.name
    tmp.close()
    f.save(path)

    ext = os.path.splitext(path)[1].lower()
    try:
        if ext == '.xls':
            import xlrd
            wb = xlrd.open_workbook(path)
            ws = wb.sheet_by_index(0)
            fields, changes = parse_ecr_rows_xls(ws)
        else:
            from openpyxl import load_workbook
            wb = load_workbook(path, data_only=True)
            ws = wb.active
            fields, changes = parse_ecr_rows_xlsx(ws)
            wb.close()

        return Result.ok({**fields, 'changes': changes}).to_response()

    except Exception:
        return internal_error_response('ECN 文件解析失败', '解析失败')
    finally:
        if os.path.exists(path):
            os.unlink(path)


@rd_bp.post('/ecr/export-ecn')
def export_ecn():
    from result import Result
    d = request.get_json() or {}
    changes = d.pop('changes', None)
    try:
        xlsx_bytes = build_ecn_xlsx(d, changes)
    except Exception:
        return internal_error_response('ECN 文件生成失败', '生成失败')

    ecn_code = d.get('ecn_code', 'ECN')
    product  = d.get('product', d.get('project', ''))
    filename = f"{ecn_code} {product} 变更通知单.xlsx".replace('/', '-')
    encoded  = urllib.parse.quote(filename)

    return Response(
        xlsx_bytes,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={
            'Content-Disposition': f"attachment; filename*=UTF-8''{encoded}",
            'Content-Length': str(len(xlsx_bytes)),
        }
    )


@rd_bp.post('/ecr/compare-bom')
def compare_bom():
    """比对上传的两个 BOM 文件，字段名 bom_before / bom_after。"""
    from result import Result
    import tempfile

    before_tmp = after_tmp = None
    try:
        before_f = request.files.get('bom_before')
        after_f  = request.files.get('bom_after')
        if not before_f or not after_f:
            return Result.fail('请上传两个BOM文件').to_response()
        try:
            read_spreadsheet_upload(before_f, label='变更前 BOM')
            read_spreadsheet_upload(after_f, label='变更后 BOM')
        except UploadValidationError as exc:
            return Result.fail(str(exc)).to_response(413 if '不能超过' in str(exc) else 400)
        t1 = tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False)
        before_tmp = t1.name; t1.close(); before_f.save(before_tmp)
        t2 = tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False)
        after_tmp  = t2.name; t2.close(); after_f.save(after_tmp)
        before_path, after_path = before_tmp, after_tmp

        # 文件合法性校验（变更前文件不校验状态）
        err = validate_bom(before_path, role='any')
        if err:
            return Result.fail(err).to_response()
        err = validate_bom(after_path, role='after')
        if err:
            return Result.fail(err).to_response()

        result = compare_bom_files(before_path, after_path)
        return Result.ok(result).to_response()
    except UploadValidationError as exc:
        return Result.fail(str(exc)).to_response(400)
    except Exception:
        return internal_error_response('BOM 文件比对失败', '比对失败')
    finally:
        if before_tmp and os.path.exists(before_tmp): os.unlink(before_tmp)
        if after_tmp  and os.path.exists(after_tmp):  os.unlink(after_tmp)


# ─────────────────────────────────────────────────────────────
# PDM 转 BOM
# ─────────────────────────────────────────────────────────────

def _get_resources_dir():
    # PyInstaller onefile 解压到 sys._MEIPASS，resources 打包进去后在 _MEIPASS/resources/
    # 开发时用 __file__ 相对路径
    if getattr(sys, 'frozen', False):
        return os.path.join(sys._MEIPASS, 'resources')
    return os.path.join(os.path.dirname(__file__), '..', '..', 'resources')

_PTB_RESOURCES_DIR = _get_resources_dir()

# PDM 文件中需要校验非空的列名（来自 page_PTB.py list_checked_column）
_PTB_CHECKED_COLUMNS = [
    '品号', '品名', '规格', '数量', '单位', '库存单位', '品号群组', '生产工厂', '品号类型', '出入仓库',
    '默认销售域', '默认采购域', '采购域', '采购税分类', '销售域', '销售税分类', '默认发货工厂', '公司',
    '存货会计分类', '存货成本分类',
]

@rd_bp.post('/pdm2bom/process')
def pdm2bom_process():
    """解析上传的 PDM 文件，字段名 pdm_file。"""
    from result import Result
    import openpyxl as _xl
    import tempfile

    tmp_path = None
    f = request.files.get('pdm_file')
    if not f:
        return Result.fail('请上传 PDM 导出文件').to_response()
    if not f.filename.lower().endswith('.xlsx'):
        return Result.fail('仅支持 .xlsx 格式').to_response()
    try:
        read_spreadsheet_upload(f, label='PDM 文件')
    except UploadValidationError as exc:
        return Result.fail(str(exc)).to_response(413 if '不能超过' in str(exc) else 400)
    tmp = tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False)
    tmp_path = tmp.name; tmp.close(); f.save(tmp_path)

    try:
        try:
            wb = _xl.load_workbook(tmp_path, read_only=True, data_only=True)
            ws = wb.active
            all_rows = list(ws.iter_rows(values_only=True))
            wb.close()
        except Exception:
            return internal_error_response('PTB 文件读取失败', '文件读取失败')

        if not all_rows:
            return Result.fail('文件为空').to_response()

        # 第一行为列名
        columns = [str(c) if c is not None else '' for c in all_rows[0]]

        # 校验关键列存在
        if '品号' not in columns or '层次' not in columns:
            return Result.fail('文件格式不符：缺少"品号"或"层次"列').to_response()

        code_idx  = columns.index('品号')
        level_idx = columns.index('层次')
        count_idx = columns.index('数量') if '数量' in columns else -1

        # 过滤数据行：跳过空行、含'.'的品号、14ST10前缀
        table_data = []
        total_level = 0
        for raw_row in all_rows[1:]:
            if not any(v for v in raw_row if v is not None):
                continue
            code = str(raw_row[code_idx]) if raw_row[code_idx] is not None else ''
            if '.' in code or code[:6] == '14ST10' or code == '-':
                continue
            level_val = str(raw_row[level_idx]) if raw_row[level_idx] is not None else ''
            depth = len(level_val.split('.'))
            if depth > total_level:
                total_level = depth
            table_data.append([str(v) if v is not None else '' for v in raw_row])

        # 必填列索引
        required_col_indices = [columns.index(c) for c in _PTB_CHECKED_COLUMNS if c in columns]

        # 逐行校验，记录缺失列
        error_map = {}
        for ri, row in enumerate(table_data):
            missing = [ci for ci in required_col_indices if not row[ci]]
            if missing:
                error_map[str(ri)] = missing

        return Result.ok({
            'columns':             columns,
            'table_data':          table_data,
            'required_col_indices': required_col_indices,
            'error_map':           error_map,
            'total_level':         total_level,
        }).to_response()
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


@rd_bp.post('/pdm2bom/export-erp')
def pdm2bom_export_erp():
    """生成 ERP 物料导入 xlsx，返回 arraybuffer"""
    from result import Result
    import openpyxl as _xl

    d = request.get_json() or {}
    columns    = d.get('columns')    or []
    table_data = d.get('table_data') or []
    if not columns or not table_data:
        return Result.fail('数据不能为空').to_response()

    erp_data   = build_erp_data(columns, table_data)
    code_idx   = columns.index('品号') if '品号' in columns else 0
    first_code = table_data[0][code_idx] if table_data else 'ERP'

    template_path = os.path.join(_PTB_RESOURCES_DIR, 'template_material.xlsx')
    try:
        wb = _xl.load_workbook(template_path)
    except Exception:
        return internal_error_response('PTB 物料模板加载失败', '物料模板加载失败')

    ws = wb.active
    for i, row in enumerate(erp_data, start=6):
        for j, value in enumerate(row, start=1):
            ws.cell(row=i, column=j, value=value)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    xlsx_bytes = buf.read()
    filename = f'ERP-{first_code}.xlsx'
    return Response(
        xlsx_bytes,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={
            'Content-Disposition': f"attachment; filename*=UTF-8''{urllib.parse.quote(filename)}",
            'Content-Length': str(len(xlsx_bytes)),
        },
    )


@rd_bp.post('/pdm2bom/export-bom')
def pdm2bom_export_bom():
    """生成 BOM 导入 xlsx，返回 arraybuffer"""
    from result import Result
    import openpyxl as _xl

    d = request.get_json() or {}
    columns     = d.get('columns')     or []
    table_data  = d.get('table_data')  or []
    total_level = d.get('total_level') or 0
    if not columns or not table_data:
        return Result.fail('数据不能为空').to_response()

    bom_data   = build_bom_data(columns, table_data, total_level)
    code_idx   = columns.index('品号') if '品号' in columns else 0
    first_code = table_data[0][code_idx] if table_data else 'BOM'

    template_path = os.path.join(_PTB_RESOURCES_DIR, 'template_bom.xlsx')
    try:
        wb = _xl.load_workbook(template_path)
    except Exception:
        return internal_error_response('PTB BOM 模板加载失败', 'BOM 模板加载失败')

    ws = wb.active
    for i, row in enumerate(bom_data, start=6):
        for j, value in enumerate(row, start=1):
            ws.cell(row=i, column=j, value=value)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    xlsx_bytes = buf.read()
    filename = f'BOM-{first_code}.xlsx'
    return Response(
        xlsx_bytes,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={
            'Content-Disposition': f"attachment; filename*=UTF-8''{urllib.parse.quote(filename)}",
            'Content-Length': str(len(xlsx_bytes)),
        },
    )


# 子模块在 rd_bp 建立后导入，以便其路由继续挂载在同一个 Blueprint 上。
from . import notes as _notes_routes  # noqa: E402,F401
from . import reminders as _reminder_routes  # noqa: E402,F401
