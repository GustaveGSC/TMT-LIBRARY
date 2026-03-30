from flask import Blueprint, request
from database.models.version import AppVersion
from services.version import version_service
from storage.client import get_bucket
from result import Result
import os

version_bp = Blueprint('version', __name__)


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
