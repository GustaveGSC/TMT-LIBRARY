"""Excel 导出的文本安全处理。"""

# Excel 会把以这些字符开头的单元格当成公式（含制表/回车开头的变体）
_FORMULA_PREFIXES = ('=', '+', '-', '@', '\t', '\r')


def safe_excel_text(value):
    """外部文本（名称、编码、导入人等）写入 Excel 前调用：公式前缀的字符串前面加单引号，强制按文本显示。

    数字、None 原样返回；只处理字符串，避免把数值列也变成文本。
    """
    if isinstance(value, str) and value.startswith(_FORMULA_PREFIXES):
        return "'" + value
    return value
