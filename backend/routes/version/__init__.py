from flask import Blueprint, request, g
from database.models.version import AppVersion
from services.version import version_service
from storage.client import get_bucket
from auth import verify_token
from result import Result
import os

version_bp = Blueprint('version', __name__)


def _require_version_auth():
    """GET 路由公开（供客户端检查更新）；写操作仅 admin。"""
    if request.method == 'GET':
        return None
    raw  = request.headers.get('Authorization', '') or ''
    token = raw.removeprefix('Bearer ').strip()
    user = verify_token(token)
    if not user:
        return Result.fail('未登录或会话已过期').to_response(401)
    g.current_user = user
    if 'admin' not in user.get('roles', []):
        return Result.fail('权限不足，需要管理员权限').to_response(403)


version_bp.before_request(_require_version_auth)

OSS_BASE_URL = os.getenv("OSS_BASE_URL", "").rstrip("/")
# OSS_BASE_URL 环境变量已包含 /tmt-library（如 https://tmt-oss.../tmt-library）
# bucket key 前缀从 bucket 根算起，包含 tmt-library/releases/
# 公开 URL = OSS_BASE_URL + /releases/filename（避免双重 tmt-library）
OSS_PREFIX  = "tmt-library/releases/"   # bucket key 前缀（OSS 操作用）
_URL_PREFIX = "releases/"               # URL 子路径（OSS_BASE_URL 后拼接）


def _key_to_url(filename: str) -> str:
    """bucket key 文件名 → 公开 URL"""
    return f"{OSS_BASE_URL}/{_URL_PREFIX}{filename}"


def _url_to_key(url: str):
    """公开 URL → bucket key，例如：
    https://…/tmt-library/releases/xxx.exe  →  tmt-library/releases/xxx.exe"""
    prefix = f"{OSS_BASE_URL}/{_URL_PREFIX}"
    if not url or not OSS_BASE_URL:
        return None
    if url.startswith(prefix):
        return f"{OSS_PREFIX}{url[len(prefix):]}"
    return None


def _archive_old_installers(bucket, old_version: AppVersion):
    """把旧版本的 .exe / .dmg 文件移动到 releases/old/ 目录（copy + delete）。
    yml 文件不归档，由新版本上传时直接覆盖即可。"""
    urls = [old_version.download_url, old_version.mac_download_url]
    for url in urls:
        key = _url_to_key(url)
        if not key:
            continue
        # 只处理安装包，跳过 yml
        if key.endswith(".yml") or key.endswith(".yaml"):
            continue
        filename  = key[len(OSS_PREFIX):]          # 去掉前缀只保留文件名
        dest_key  = f"{OSS_PREFIX}old/{filename}"
        try:
            bucket.copy_object(bucket.bucket_name, key, dest_key)
            bucket.delete_object(key)
        except Exception as e:
            # 归档失败不阻断发布，仅打印警告
            print(f"[warn] archive old installer failed: {key} → {dest_key}: {e}")


@version_bp.get("/latest")
def get_latest():
    return version_service.get_latest().to_response()


@version_bp.get("/list")
def get_list():
    versions = AppVersion.query.order_by(AppVersion.id.desc()).all()
    return Result.ok(data=[{
        "id":               v.id,
        "version":          v.version,
        "description":      v.description,
        "download_url":     v.download_url,
        "mac_download_url": v.mac_download_url,
        "created_at":       v.created_at.strftime("%Y-%m-%d"),
    } for v in versions]).to_response()


@version_bp.post("/")
def create_version():
    body             = request.get_json() or {}
    version          = body.get("version",          "").strip()
    description      = body.get("description",      "")
    download_url     = (body.get("download_url")     or "").strip() or None
    mac_download_url = (body.get("mac_download_url") or "").strip() or None
    if not version:
        return Result.fail("版本号不能为空").to_response()
    if not download_url and not mac_download_url:
        return Result.fail("至少需要上传 Windows 或 macOS 安装包之一").to_response()

    # 归档旧版本安装包：取当前最新版本，将其 .exe/.dmg 移到 releases/old/
    try:
        latest = AppVersion.query.order_by(AppVersion.id.desc()).first()
        if latest:
            _archive_old_installers(get_bucket(), latest)
    except Exception as e:
        print(f"[warn] archive step error: {e}")

    return version_service.create(version, description, download_url, mac_download_url).to_response()


@version_bp.post("/presign")
def presign_upload():
    """生成 OSS 预签名 PUT URL，供前端直接上传文件到 OSS（避免经过服务器中转）。"""
    body     = request.get_json() or {}
    filename = body.get("filename", "").strip()
    if not filename:
        return Result.fail("文件名不能为空").to_response()
    key = f"{OSS_PREFIX}{filename}"
    try:
        bucket      = get_bucket()
        presign_url = bucket.sign_url('PUT', key, 3600,
                                      headers={'Content-Type': 'application/octet-stream'})
        oss_url     = _key_to_url(filename)
        return Result.ok(data={"presign_url": presign_url, "oss_url": oss_url}).to_response()
    except Exception as e:
        return Result.fail(f"生成签名失败：{str(e)}").to_response()


@version_bp.post("/upload")
def upload_file():
    file = request.files.get("file")
    if not file:
        return Result.fail("未收到文件").to_response()
    filename = file.filename
    key      = f"{OSS_PREFIX}{filename}"
    try:
        bucket   = get_bucket()
        bucket.put_object(key, file.stream)
        return Result.ok(data={"url": _key_to_url(filename), "key": key}).to_response()
    except Exception as e:
        return Result.fail(f"上传失败：{str(e)}").to_response()
