"""研发 BOM 层次表格的公共解析能力（变更申请单比对与物料库 BOM 共用）。

只放与业务无关的 Excel 基础能力：表头识别、编码单元格转文本、分类名清洗。
状态口径、编码跳过规则、品名/规格拼接、版本推算等业务规则由各自模块保留，
不要往这里加——两个功能的口径本来就不同。
"""
from upload_validation import UploadValidationError


ERP_BOM_REQUIRED_COLS = ['层次', '图号', '品名', '规格', '数量', '单位', '状态']
PDM_BOM_REQUIRED_COLS = [
    '层次', '物料编码', '版本', '一级分类', '二级分类', '描述', '数量', '单位', '状态',
]


def bom_columns(ws):
    """返回 (格式, 首个同名表头映射)，必需表头重复时明确拒绝。"""
    occurrences = {}
    for column in range(1, ws.max_column + 1):
        value = ws.cell(1, column).value
        if value is None or not str(value).strip():
            continue
        occurrences.setdefault(str(value).strip(), []).append(column)

    names = set(occurrences)
    if '图号' in names:
        format_name = 'erp'
        required = ERP_BOM_REQUIRED_COLS
    elif {'物料编码', '一级分类'} <= names:
        format_name = 'pdm'
        required = PDM_BOM_REQUIRED_COLS
    else:
        raise UploadValidationError('无法识别的 BOM 文件格式')

    duplicates = [name for name in required if len(occurrences.get(name, [])) > 1]
    if duplicates:
        name = duplicates[0]
        columns = '、'.join(str(column) for column in occurrences[name])
        raise UploadValidationError(
            f'表头中「{name}」出现了 {len(occurrences[name])} 次（第 {columns} 列），请确认导出模板'
        )
    missing = [name for name in required if name not in occurrences]
    if missing:
        raise UploadValidationError('缺少必要列：' + ', '.join(missing))
    return format_name, {name: columns[0] for name, columns in occurrences.items()}


def numeric_code_text(cell):
    """读取混合类型编码；纯 0 数字格式用于恢复 Excel 展示中的前导零。"""
    value = cell.value
    if value is None:
        return ''
    if isinstance(value, bool):
        raise UploadValidationError(f'第 {cell.row} 行物料编码不是有效文本')
    if isinstance(value, int):
        text = str(value)
    elif isinstance(value, float):
        # PDM 偶尔会把带点的子件编码存成数值。这类编码会在后续按既有
        # 规则跳过，不应为了一个不参与 BOM 比对的值阻断整份文件。
        text = str(int(value)) if value.is_integer() else repr(value)
    else:
        return str(value).strip()
    number_format = str(cell.number_format or '').strip()
    if '.' not in text and number_format and set(number_format) == {'0'}:
        text = text.zfill(len(number_format))
    return text


def category_name(value):
    """去掉 PDM 分类的编号前缀：'14_原材料' → '原材料'。"""
    text = str(value or '').strip()
    return text.split('_', 1)[1] if '_' in text else text
