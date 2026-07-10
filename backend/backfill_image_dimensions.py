"""
批量回填 product_finished.cover_image_width / cover_image_height
对所有有 cover_image_original 但尚无尺寸记录的成品，从 OSS 拉取原图读取像素尺寸并写回 DB。
用法：cd backend && python3.11 backfill_image_dimensions.py
"""
import io
import os
import sys

# 让脚本能找到 backend 模块
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv()

from PIL import Image as PilImage
from storage.client import get_bucket
from app import create_app

OSS_BASE_URL = os.getenv('OSS_BASE_URL', '').rstrip('/')

def url_to_oss_key(url: str) -> str:
    """把完整 URL 转回 OSS key（去掉 BASE_URL 前缀再加 tmt-library/ 前缀）。"""
    # OSS_BASE_URL = https://tmt-oss.oss-cn-hangzhou.aliyuncs.com/tmt-library
    # URL 示例   = https://tmt-oss.oss-cn-hangzhou.aliyuncs.com/tmt-library/products/XXX_orig.png
    # OSS key    = tmt-library/products/XXX_orig.png
    prefix = OSS_BASE_URL.split('.com/', 1)[-1]   # tmt-library
    path   = url.split('.com/', 1)[-1]             # tmt-library/products/XXX_orig.png
    return path

def main():
    app = create_app()
    with app.app_context():
        from database.models.product.finished import ProductFinished
        from app import db

        # 只处理有原图但没有尺寸的记录
        rows = ProductFinished.query.filter(
            ProductFinished.cover_image_original.isnot(None),
            ProductFinished.cover_image_width.is_(None),
        ).all()

        print(f'找到 {len(rows)} 条待回填记录', flush=True)
        if not rows:
            return

        bucket = get_bucket()
        ok = fail = 0

        for row in rows:
            url = row.cover_image_original
            try:
                key = url_to_oss_key(url)
                obj = bucket.get_object(key)
                data = obj.read()
                with PilImage.open(io.BytesIO(data)) as img:
                    w, h = img.size
                row.cover_image_width  = w
                row.cover_image_height = h
                ok += 1
                print(f'  ✓ {row.code}: {w}×{h}', flush=True)
            except Exception as e:
                fail += 1
                print(f'  ✗ {row.code}: {e}', flush=True)

        db.session.commit()
        print(f'\n完成：成功 {ok} 条，失败 {fail} 条', flush=True)

if __name__ == '__main__':
    main()
