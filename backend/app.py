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
        "pool_size":     int(os.getenv("POOL_SIZE",    2)),
        "max_overflow":  int(os.getenv("MAX_OVERFLOW", 1)),
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

    # ── 数据库自动迁移（非破坏性，仅补充缺失变更）──────────
    with app.app_context():
        _run_migrations(db)

    # ── 健康检查 ──────────────────────────────────────
    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app


def _run_migrations(db):
    """轻量自动迁移：检测列定义，仅在需要时执行 ALTER TABLE；并确保新表存在。"""
    # 确保新增表存在（checkfirst=True 保证幂等）
    try:
        from database.models.rd import EcrReminder, EcrNote
        from database.models.aftersale import AftersaleSetting
        EcrReminder.__table__.create(bind=db.engine, checkfirst=True)
        EcrNote.__table__.create(bind=db.engine, checkfirst=True)
        AftersaleSetting.__table__.create(bind=db.engine, checkfirst=True)
    except Exception as e:
        print(f'[migration] 建表失败（可忽略）: {e}', flush=True)

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


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=int(os.getenv("FLASK_PORT", 8765)))
    args = parser.parse_args()

    application = create_app()
    application.run(host=os.getenv("FLASK_HOST", "127.0.0.1"), port=args.port, debug=False)