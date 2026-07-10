import argparse
import os
import sys
from flask import Flask
from flask_cors import CORS
from database.base import db
from dotenv import load_dotenv
from sqlalchemy.pool import QueuePool

# ── 环境变量加载（兼容打包后路径）────────────────────
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, '.env'), override=True)


def create_app() -> Flask:
    app = Flask(__name__)

    # ── JWT 密钥安全检查 ──────────────────────────────
    if os.environ.get('JWT_SECRET', '') in ('', 'tmt-dev-secret-change-in-production'):
        print('[WARNING] JWT_SECRET 使用默认开发值，生产环境请通过环境变量设置强密钥！', flush=True)

    # ── 数据库配置 ────────────────────────────────────
    app.config["SQLALCHEMY_DATABASE_URI"] = (
        f"mysql+pymysql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}"
        f"@{os.getenv('DB_HOST', '127.0.0.1')}:{os.getenv('DB_PORT', '3306')}"
        f"/{os.getenv('DB_NAME')}"
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    # pool_pre_ping：使用前探活，连接被 NAT/防火墙静默关闭时自动重连
    # pool_recycle：1800s 主动回收，早于云端 NAT 超时（通常 ~3600s）
    # POOL_SIZE / MAX_OVERFLOW 可通过环境变量调整（网页端多用户场景需调大）
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "poolclass":     QueuePool,
        "pool_size":     int(os.getenv("POOL_SIZE",    5)),
        "max_overflow":  int(os.getenv("MAX_OVERFLOW", 5)),
        "pool_pre_ping": True,
        "pool_recycle":  1800,
        "connect_args": {
            "connect_timeout": 10,
            "read_timeout":    30,
            "write_timeout":   30,
        },
    }

    # ── 初始化扩展 ────────────────────────────────────
    db.init_app(app)
    # CORS_ORIGINS 可通过环境变量覆盖（逗号分隔），生产环境配置实际域名
    _cors_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]
    if not _cors_origins:
        _cors_origins = ["http://localhost:5173", "file://"]
    CORS(app, origins=_cors_origins)

    # ── 注册蓝图 ──────────────────────────────────────
    from routes.account import account_bp
    from routes.version import version_bp
    from routes.product.import_raw import product_bp
    from routes.product.finished import finished_bp
    from routes.product.erp_code_rules import erp_code_rules_bp
    from routes.product.category import category_bp
    from routes.product.tag import bp as tag_bp
    from routes.product.param import param_bp
    from routes.shipping import shipping_bp
    from routes.aftersale import aftersale_bp
    from routes.product.lifecycle import lifecycle_bp
    from routes.rd import rd_bp
    from routes.rd.cost import cost_bp as rd_cost_bp
    from routes.product.resource import resource_bp
    from routes.config import config_bp

    app.register_blueprint(account_bp,        url_prefix="/api/account")
    app.register_blueprint(version_bp,        url_prefix="/api/version")
    app.register_blueprint(product_bp,        url_prefix="/api/product")
    app.register_blueprint(finished_bp,       url_prefix="/api/product")
    app.register_blueprint(erp_code_rules_bp, url_prefix="/api/erp-code-rules")
    app.register_blueprint(category_bp,       url_prefix="/api/category")
    app.register_blueprint(tag_bp,            url_prefix="/api/product/tags")
    app.register_blueprint(param_bp,          url_prefix="/api/product/params")
    app.register_blueprint(shipping_bp,       url_prefix="/api/shipping")
    app.register_blueprint(aftersale_bp,      url_prefix="/api/aftersale")
    app.register_blueprint(lifecycle_bp,      url_prefix="/api/product/lifecycle")
    app.register_blueprint(rd_bp,             url_prefix="/api/rd")
    app.register_blueprint(rd_cost_bp,        url_prefix="/api/rd/cost")
    app.register_blueprint(resource_bp,       url_prefix="/api/resources")
    app.register_blueprint(config_bp,         url_prefix="/api/config")

    # ── 数据库自动迁移（非破坏性，仅补充缺失变更）──────────
    with app.app_context():
        _run_migrations(db)

    # ── 健康检查 ──────────────────────────────────────
    @app.get("/health")
    def health():
        return {"status": "ok"}

    # ── 语义模型：启动时自动下载/加载 ────────────────
    import threading
    def _bg_model_init():
        try:
            import model_manager
            model_manager._auto_start_download_if_needed()
        except Exception as e:
            print(f'[app] 语义模型初始化失败: {e}', flush=True)
    threading.Thread(target=_bg_model_init, daemon=True, name='model-init').start()

    return app


def _run_migrations(db):
    """轻量自动迁移：检测列定义，仅在需要时执行 ALTER TABLE；并确保新表存在。"""
    # 确保新增表存在（checkfirst=True 保证幂等）
    try:
        from database.models.rd import EcrReminder, EcrNote
        from database.models.aftersale import AftersaleSetting
        from database.models.product.finished import ProductTagCategory
        from database.models.product.resource import ProductResourceType, ProductResource, finished_resource, resource_tag, resource_model
        from database.models.account import SiteConfig
        from database.models.rd.cost import (
            CostBomNode, CostSnapshot, CostSnapshotSku,
            CostBomLine, CostMaterialSupplier, CostMaterialRule,
        )
        EcrReminder.__table__.create(bind=db.engine, checkfirst=True)
        EcrNote.__table__.create(bind=db.engine, checkfirst=True)
        AftersaleSetting.__table__.create(bind=db.engine, checkfirst=True)
        ProductTagCategory.__table__.create(bind=db.engine, checkfirst=True)
        ProductResourceType.__table__.create(bind=db.engine, checkfirst=True)
        ProductResource.__table__.create(bind=db.engine, checkfirst=True)
        finished_resource.create(bind=db.engine, checkfirst=True)
        resource_tag.create(bind=db.engine, checkfirst=True)
        resource_model.create(bind=db.engine, checkfirst=True)
        SiteConfig.__table__.create(bind=db.engine, checkfirst=True)
        # BOM 成本库表（节点表需先于其他表创建，因为其他表有外键指向它）
        CostBomNode.__table__.create(bind=db.engine, checkfirst=True)
        CostSnapshot.__table__.create(bind=db.engine, checkfirst=True)
        CostSnapshotSku.__table__.create(bind=db.engine, checkfirst=True)
        CostBomLine.__table__.create(bind=db.engine, checkfirst=True)
        CostMaterialSupplier.__table__.create(bind=db.engine, checkfirst=True)
        CostMaterialRule.__table__.create(bind=db.engine, checkfirst=True)
        # 种子数据：预置资料类型
        _seed_resource_types(db)
    except Exception as e:
        print(f'[migration] 建表失败（可忽略）: {e}', flush=True)

    # 为 product_tag 表补充 category_id 列
    try:
        with db.engine.connect() as conn:
            row = conn.execute(db.text(
                "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE() "
                "AND TABLE_NAME = 'product_tag' "
                "AND COLUMN_NAME = 'category_id'"
            )).fetchone()
            if not row:
                conn.execute(db.text(
                    "ALTER TABLE product_tag "
                    "ADD COLUMN category_id INT NULL, "
                    "ADD CONSTRAINT fk_tag_category "
                    "FOREIGN KEY (category_id) REFERENCES product_tag_category(id) ON DELETE SET NULL"
                ))
                conn.commit()
                print('[migration] product_tag.category_id 列已添加', flush=True)
    except Exception as e:
        print(f'[migration] product_tag 迁移失败（可忽略）: {e}', flush=True)

    # 为 product_finished 补充 img_updated_at 列（阻断问题：列不存在会 Unknown column）
    try:
        with db.engine.connect() as conn:
            row = conn.execute(db.text(
                "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE() "
                "AND TABLE_NAME = 'product_finished' "
                "AND COLUMN_NAME = 'img_updated_at'"
            )).fetchone()
            if not row:
                conn.execute(db.text(
                    "ALTER TABLE product_finished ADD COLUMN img_updated_at INT NULL"
                ))
                conn.commit()
                print('[migration] product_finished.img_updated_at 列已添加', flush=True)
    except Exception as e:
        print(f'[migration] product_finished img_updated_at 迁移失败（可忽略）: {e}', flush=True)

    try:
        with db.engine.connect() as conn:
            # aftersale_product_remark_dict.type Enum 中补充 series_alias
            row = conn.execute(db.text(
                "SELECT COLUMN_TYPE FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE() "
                "AND TABLE_NAME = 'aftersale_product_remark_dict' "
                "AND COLUMN_NAME = 'type'"
            )).fetchone()
            if row and 'series_alias' not in (row[0] or ''):
                conn.execute(db.text(
                    "ALTER TABLE aftersale_product_remark_dict "
                    "MODIFY COLUMN type ENUM('material','color','drive_type','size','series_alias') NOT NULL"
                ))
                conn.commit()
    except Exception as e:
        print(f'[migration] 自动迁移失败（可忽略）: {e}', flush=True)


def _seed_resource_types(db):
    """幂等写入预置资料类型种子数据。"""
    try:
        from database.models.product.resource import ProductResourceType
        preset = ['说明书', '安装视频', '售后视频', '专利', '认证']
        existing = {t.name for t in ProductResourceType.query.all()}
        new_types = [
            ProductResourceType(name=name, sort_order=idx)
            for idx, name in enumerate(preset)
            if name not in existing
        ]
        if new_types:
            db.session.add_all(new_types)
            db.session.commit()
            print(f'[seed] 新增资料类型: {[t.name for t in new_types]}', flush=True)
    except Exception as e:
        print(f'[seed] 资料类型种子数据写入失败（可忽略）: {e}', flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=int(os.getenv("FLASK_PORT", 8765)))
    args = parser.parse_args()

    application = create_app()
    application.run(host=os.getenv("FLASK_HOST", "127.0.0.1"), port=args.port, debug=False)