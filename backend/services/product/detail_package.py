import os
import uuid

from sqlalchemy.exc import IntegrityError

from database.base import db
from database.models.product.detail_package import (
    ProductDetailPackageCleanupFailure, ProductDetailPackageMedia,
)
from database.repository.product.detail_package import DetailPackageRepository
from result import Result
from storage.client import get_bucket
from upload_validation import UploadValidationError, parse_declared_size

_EXTENSIONS = {
    'png': ('image/png', 'image'), 'jpg': ('image/jpeg', 'image'),
    'jpeg': ('image/jpeg', 'image'), 'webp': ('image/webp', 'image'),
    'mp4': ('video/mp4', 'video'), 'mov': ('video/quicktime', 'video'), 'webm': ('video/webm', 'video'),
}
_LIMIT = int(os.getenv('PRODUCT_DETAIL_PACKAGE_UPLOAD_LIMIT', 500 * 1024 * 1024))
_BASE_URL = os.getenv('OSS_BASE_URL', '').rstrip('/')


class DetailPackageService:
    @staticmethod
    def _record_cleanup_failure(package_id, storage_key, exc):
        try:
            db.session.add(ProductDetailPackageCleanupFailure(
                package_id=package_id,
                storage_key=storage_key,
                error_message=str(exc)[:1000] or exc.__class__.__name__,
            ))
            db.session.commit()
        except Exception:
            db.session.rollback()

    def list(self, search, page, size):
        items, total = DetailPackageRepository.list_packages(search, page, size)
        return Result.ok(data={'items': items, 'total': total, 'page': page, 'size': size})

    def get_one(self, package_id):
        package = DetailPackageRepository.get(package_id)
        if not package:
            return Result.fail('产品详情包不存在')
        media = DetailPackageRepository.media_for_packages([package_id])[package_id]
        return Result.ok(data=package.to_dict(media=media))

    def create(self, name):
        name = (name or '').strip()
        if not name or len(name) > 200:
            return Result.fail('包名称不能为空且不能超过 200 个字符')
        return Result.ok(data=DetailPackageRepository.create(name).to_dict())

    def update(self, package_id, name):
        package = DetailPackageRepository.get(package_id)
        name = (name or '').strip()
        if not package:
            return Result.fail('产品详情包不存在')
        if not name or len(name) > 200:
            return Result.fail('包名称不能为空且不能超过 200 个字符')
        return Result.ok(data=DetailPackageRepository.update(package, name=name).to_dict())

    def set_tags(self, package_id, tag_ids, tag_condition):
        package = DetailPackageRepository.get(package_id)
        if not package:
            return Result.fail('产品详情包不存在')
        if not isinstance(tag_ids, list) or not all(isinstance(value, int) and value > 0 for value in tag_ids):
            return Result.fail('tag_ids 必须为正整数数组')
        if tag_condition is not None and not isinstance(tag_condition, (dict, list)):
            return Result.fail('tag_condition 必须为对象、数组或 null')
        DetailPackageRepository.set_tags(package, tag_ids, tag_condition)
        return Result.ok(data=package.to_dict())

    def set_models(self, package_id, model_ids):
        package = DetailPackageRepository.get(package_id)
        if not package:
            return Result.fail('产品详情包不存在')
        if not isinstance(model_ids, list) or not all(isinstance(value, int) and value > 0 for value in model_ids):
            return Result.fail('model_ids 必须为正整数数组')
        DetailPackageRepository.set_models(package, model_ids)
        return Result.ok(data=package.to_dict())

    def presign_media(self, package_id, files):
        if not DetailPackageRepository.get(package_id):
            return Result.fail('产品详情包不存在')
        if not isinstance(files, list) or not 1 <= len(files) <= 100:
            return Result.fail('files 数量必须在 1 到 100 之间')
        items = []
        try:
            for file in files:
                ext = (file.get('ext') or '').lower().lstrip('.')
                original = (file.get('original_filename') or '').strip()
                if ext not in _EXTENSIONS or not original or len(original) > 300:
                    raise ValueError('文件类型或文件名不合法')
                size = parse_declared_size(file.get('file_size'), maximum=_LIMIT, label='产品详情媒体')
                content_type, file_type = _EXTENSIONS[ext]
                key = f'tmt-library/product-detail/{package_id}/{uuid.uuid4().hex}.{ext}'
                headers = {'Content-Type': content_type, 'Content-Length': str(size)}
                items.append({
                    'storage_key': key, 'oss_url': f'{_BASE_URL}/product-detail/{package_id}/{key.rsplit("/", 1)[-1]}',
                    'file_type': file_type, 'original_filename': original, 'file_size': size,
                    'required_headers': headers,
                })
        except (ValueError, UploadValidationError) as exc:
            return Result.fail(str(exc))
        try:
            bucket = get_bucket()
            for item in items:
                item['presign_url'] = bucket.sign_url('PUT', item['storage_key'], 3600, headers=item['required_headers'])
            return Result.ok(data={'items': items})
        except Exception:
            return Result.fail('生成上传签名失败')

    def confirm_media(self, package_id, files):
        if not DetailPackageRepository.get(package_id):
            return Result.fail('产品详情包不存在')
        if not isinstance(files, list) or not files:
            return Result.fail('files 不能为空')
        prefix = f'tmt-library/product-detail/{package_id}/'
        rows = []
        try:
            max_sort = db.session.query(db.func.max(ProductDetailPackageMedia.sort_order)).filter_by(package_id=package_id).scalar() or 0
            for index, file in enumerate(files, start=1):
                key = str(file.get('storage_key') or '')
                if not key.startswith(prefix) or '/' in key[len(prefix):]:
                    raise ValueError('storage_key 不属于当前产品详情包')
                ext = key.rsplit('.', 1)[-1].lower()
                if ext not in _EXTENSIONS:
                    raise ValueError('storage_key 文件类型不合法')
                original = (file.get('original_filename') or '').strip()
                size = parse_declared_size(file.get('file_size'), maximum=_LIMIT, label='产品详情媒体')
                if not original or len(original) > 300:
                    raise ValueError('原文件名不合法')
                rows.append(ProductDetailPackageMedia(
                    package_id=package_id, storage_key=key,
                    oss_url=f'{_BASE_URL}/product-detail/{package_id}/{key.rsplit("/", 1)[-1]}',
                    file_type=_EXTENSIONS[ext][1], original_filename=original, file_size=size,
                    sort_order=max_sort + index,
                ))
            db.session.add_all(rows)
            db.session.commit()
        except (ValueError, UploadValidationError, IntegrityError) as exc:
            db.session.rollback()
            return Result.fail(str(exc) if isinstance(exc, (ValueError, UploadValidationError)) else '媒体已确认或数据冲突')
        return Result.ok(data=[row.to_dict() for row in rows])

    def delete_media(self, package_id, media_id):
        media = db.session.get(ProductDetailPackageMedia, media_id)
        if not media or media.package_id != package_id:
            return Result.fail('媒体不存在')
        key = media.storage_key
        db.session.delete(media)
        db.session.commit()
        try:
            get_bucket().delete_object(key)
        except Exception as exc:
            self._record_cleanup_failure(package_id, key, exc)
        return Result.ok()

    def delete(self, package_id):
        package = DetailPackageRepository.get(package_id)
        if not package:
            return Result.fail('产品详情包不存在')
        media = DetailPackageRepository.media_for_packages([package_id])[package_id]
        keys = [item.storage_key for item in media]
        db.session.delete(package)
        db.session.commit()
        try:
            bucket = get_bucket()
            for key in keys:
                try:
                    bucket.delete_object(key)
                except Exception as exc:
                    self._record_cleanup_failure(package_id, key, exc)
        except Exception as exc:
            for key in keys:
                self._record_cleanup_failure(package_id, key, exc)
        return Result.ok()

    def for_finished(self, code):
        finished, rows = DetailPackageRepository.matching_finished_packages(code)
        if not finished:
            return Result.fail('成品不存在')
        return Result.ok(data=[package.to_dict(media=media) for package, media in rows])


detail_package_service = DetailPackageService()
