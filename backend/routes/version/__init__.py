from flask import Blueprint, request
from database.models.version import AppVersion
from services.version import version_service
from storage.client import get_bucket
from result import Result
import os

version_bp = Blueprint('version', __name__)

OSS_BASE_URL = os.getenv("OSS_BASE_URL", "").rstrip("/")
OSS_PREFIX   = "tmt-library/releases/"   # 当前存放目录的 key 前缀


def _url_to_key(url: str) -> str | None:
    """将 OSS URL 还原为 bucket key，例如：
    https://…/tmt-library/releases/xxx.exe  →  tmt-library/releases/xxx.exe"""
    if not url or not OSS_BASE_URL:
        return None
    if url.startswith(OSS_BASE_URL + "/"):
        return url[len(OSS_BASE_URL) + 1:]
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
    download_url     = body.get("download_url",     "").strip() or None
    mac_download_url = body.get("mac_download_url", "").strip() or None
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


@version_bp.post("/upload")
def upload_file():
    file = request.files.get("file")
    if not file:
        return Result.fail("未收到文件").to_response()
    filename = file.filename
    key      = f"tmt-library/releases/{filename}"
    try:
        bucket   = get_bucket()
        bucket.put_object(key, file.read())
        base_url = os.getenv("OSS_BASE_URL", "").rstrip("/")
        return Result.ok(data={"url": f"{base_url}/{key}", "key": key}).to_response()
    except Exception as e:
        return Result.fail(f"上传失败：{str(e)}").to_response()
