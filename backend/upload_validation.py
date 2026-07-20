"""上传大小与文件内容校验；所有限制均作用于读取/解析之前。"""

import io
import zipfile
from PIL import Image, UnidentifiedImageError


MIB = 1024 * 1024
GLOBAL_REQUEST_LIMIT = 500 * MIB
SPREADSHEET_LIMIT = 20 * MIB
SPREADSHEET_UNCOMPRESSED_LIMIT = 100 * MIB
SPREADSHEET_MAX_FILES = 2000
SPREADSHEET_MAX_SHEETS = 50
SPREADSHEET_MAX_ROWS = 100_000
COVER_IMAGE_LIMIT = 10 * MIB
RESOURCE_UPLOAD_LIMIT = 500 * MIB
ALLOWED_IMAGE_FORMATS = {'PNG': 'png', 'JPEG': 'jpg', 'WEBP': 'webp'}
SPREADSHEET_MIMES = {
    '.xlsx': {
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'application/octet-stream',
    },
    '.xls': {'application/vnd.ms-excel', 'application/octet-stream'},
    '.csv': {'text/csv', 'application/csv', 'text/plain', 'application/octet-stream'},
}


class UploadValidationError(ValueError):
    pass


def ensure_spreadsheet_row_limit(row_number: int) -> None:
    if row_number > SPREADSHEET_MAX_ROWS:
        raise UploadValidationError(f'表格数据行不能超过 {SPREADSHEET_MAX_ROWS} 行')


def parse_declared_size(value, *, maximum: int, label: str) -> int:
    try:
        size = int(value)
    except (TypeError, ValueError):
        raise UploadValidationError(f'{label}大小参数缺失或无效') from None
    if size <= 0:
        raise UploadValidationError(f'{label}大小必须大于 0')
    if size > maximum:
        raise UploadValidationError(f'{label}不能超过 {maximum // MIB}MB')
    return size


def read_limited(stream, *, maximum: int, label: str) -> bytes:
    data = stream.read(maximum + 1)
    if len(data) > maximum:
        raise UploadValidationError(f'{label}不能超过 {maximum // MIB}MB')
    if not data:
        raise UploadValidationError(f'{label}为空')
    return data


def _validate_xlsx(data: bytes) -> None:
    if not data.startswith(b'PK\x03\x04'):
        raise UploadValidationError('文件扩展名为 .xlsx，但内容不是有效的 Excel 文件')
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            infos = archive.infolist()
            if len(infos) > SPREADSHEET_MAX_FILES:
                raise UploadValidationError('Excel 内部文件数量异常')
            total_uncompressed = sum(item.file_size for item in infos)
            if total_uncompressed > SPREADSHEET_UNCOMPRESSED_LIMIT:
                raise UploadValidationError(
                    f'Excel 解压后不能超过 {SPREADSHEET_UNCOMPRESSED_LIMIT // MIB}MB'
                )
            sheet_count = sum(
                1 for item in infos
                if item.filename.startswith('xl/worksheets/sheet') and item.filename.endswith('.xml')
            )
            if sheet_count > SPREADSHEET_MAX_SHEETS:
                raise UploadValidationError(f'Excel 工作表不能超过 {SPREADSHEET_MAX_SHEETS} 个')
            if '[Content_Types].xml' not in archive.namelist() or 'xl/workbook.xml' not in archive.namelist():
                raise UploadValidationError('文件缺少 Excel 工作簿结构')
    except zipfile.BadZipFile:
        raise UploadValidationError('Excel 压缩结构损坏') from None


def validate_spreadsheet_bytes(data: bytes, filename: str, *, allow_csv: bool = False) -> bytes:
    name = (filename or '').lower()
    if name.endswith('.xlsx'):
        _validate_xlsx(data)
    elif name.endswith('.xls'):
        if not data.startswith(bytes.fromhex('D0CF11E0A1B11AE1')):
            raise UploadValidationError('文件扩展名为 .xls，但内容不是有效的 Excel 文件')
    elif allow_csv and name.endswith('.csv'):
        if b'\x00' in data[:4096]:
            raise UploadValidationError('CSV 内容包含二进制数据')
        for encoding in ('utf-8-sig', 'gb18030'):
            try:
                data[:65536].decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        else:
            raise UploadValidationError('CSV 文本编码无法识别')
    else:
        allowed = '.xlsx / .xls / .csv' if allow_csv else '.xlsx / .xls'
        raise UploadValidationError(f'仅支持 {allowed} 格式')
    return data


def read_spreadsheet_upload(file, *, label: str, allow_csv: bool = False) -> bytes:
    filename = (file.filename or '').lower()
    extension = next((ext for ext in SPREADSHEET_MIMES if filename.endswith(ext)), None)
    mimetype = (file.mimetype or '').lower()
    if extension and mimetype and mimetype not in SPREADSHEET_MIMES[extension]:
        raise UploadValidationError(f'{label}的 MIME 类型与扩展名不一致')
    data = read_limited(file.stream, maximum=SPREADSHEET_LIMIT, label=label)
    validate_spreadsheet_bytes(data, file.filename, allow_csv=allow_csv)
    file.stream.seek(0)
    return data


def validate_image_bytes(data: bytes, *, label: str):
    if len(data) > COVER_IMAGE_LIMIT:
        raise UploadValidationError(f'{label}不能超过 {COVER_IMAGE_LIMIT // MIB}MB')
    if not data:
        raise UploadValidationError(f'{label}为空')
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.verify()
            ext = ALLOWED_IMAGE_FORMATS.get(image.format)
    except (UnidentifiedImageError, OSError):
        raise UploadValidationError(f'{label}不是有效的 PNG/JPEG/WebP 图片') from None
    if not ext:
        raise UploadValidationError(f'{label}仅支持 PNG/JPEG/WebP')
    return ext
