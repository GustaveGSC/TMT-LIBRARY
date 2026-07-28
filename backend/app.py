import argparse
import os
import sys
from pathlib import Path

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from flask import Flask
from flask_cors import CORS
from werkzeug.exceptions import RequestEntityTooLarge
from database.base import db
from dotenv import load_dotenv
from sqlalchemy.pool import QueuePool
from sqlalchemy import text
from security_config import validate_security_config
from result import Result
from upload_validation import GLOBAL_REQUEST_LIMIT
from rate_limit import limiter

# ── 环境变量加载（兼容打包后路径）────────────────────
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, '.env'), override=True)

# auth 在 .env 加载后导入，确保模块级 JWT_SECRET 使用部署配置。
from auth import clear_auth_cookies_on_unauthorized, validate_csrf_request


def create_app() -> Flask:
    app = Flask(__name__)

    # ── 生产安全配置检查 ──────────────────────────────
    validate_security_config()

    # ── 数据库配置 ────────────────────────────────────
    app.config["SQLALCHEMY_DATABASE_URI"] = (
        f"mysql+pymysql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}"
        f"@{os.getenv('DB_HOST', '127.0.0.1')}:{os.getenv('DB_PORT', '3306')}"
        f"/{os.getenv('DB_NAME')}"
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["MAX_CONTENT_LENGTH"] = int(os.getenv(
        "MAX_CONTENT_LENGTH", GLOBAL_REQUEST_LIMIT,
    ))
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
    limiter.init_app(app)
    with app.app_context():
        _validate_database_revision(db)

    # CORS_ORIGINS 可通过环境变量覆盖（逗号分隔），生产环境配置实际域名
    _cors_origins = _get_cors_origins()
    CORS(app, origins=_cors_origins, supports_credentials=True)

    @app.before_request
    def enforce_csrf():
        return validate_csrf_request()

    app.after_request(clear_auth_cookies_on_unauthorized)

    @app.errorhandler(RequestEntityTooLarge)
    def request_too_large(_error):
        return Result.fail(
            f'请求体不能超过 {app.config["MAX_CONTENT_LENGTH"] // (1024 * 1024)}MB'
        ).to_response(413)

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
    from routes.product.detail_package import detail_package_bp
    from routes.config import config_bp
    from database.repository.shipping import shipping_repository
    from database.repository.product.lifecycle import product_lifecycle_task_repository

    with app.app_context():
        interrupted_tasks = shipping_repository.interrupt_running_tasks()
        if interrupted_tasks:
            print(f'[task] 已标记 {interrupted_tasks} 个上次进程遗留任务为 interrupted', flush=True)
        interrupted_lifecycle_tasks = (
            product_lifecycle_task_repository.interrupt_running_tasks()
        )
        if interrupted_lifecycle_tasks:
            print(
                f'[task] 已标记 {interrupted_lifecycle_tasks} 个生命周期任务为 interrupted',
                flush=True,
            )

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
    app.register_blueprint(detail_package_bp, url_prefix="/api/product-detail-packages")
    app.register_blueprint(config_bp,         url_prefix="/api/config")

    # ── 健康检查 ──────────────────────────────────────
    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/ready")
    def ready():
        try:
            _check_database_readiness(db)
        except Exception:
            app.logger.exception('数据库 readiness 检查失败')
            return {"status": "not_ready"}, 503
        return {"status": "ready"}

    # ── 语义模型：启动时自动下载/加载 ────────────────
    import threading
    def _bg_model_init():
        try:
            from services import semantic_model
            semantic_model._auto_start_download_if_needed()
        except Exception as e:
            print(f'[app] 语义模型初始化失败: {e}', flush=True)
    threading.Thread(target=_bg_model_init, daemon=True, name='model-init').start()

    return app


def _get_cors_origins() -> list[str]:
    origins = [
        value.strip()
        for value in os.getenv('CORS_ORIGINS', '').split(',')
        if value.strip()
    ]
    if '*' in origins:
        raise RuntimeError('Cookie 会话启用 credentials 后，CORS_ORIGINS 禁止使用通配符 *')
    return origins or ['http://localhost:5173', 'http://localhost:5174']


def _check_database_readiness(database) -> None:
    """执行最小只读查询，确认数据库连接和查询均可用。"""
    database.session.execute(text('SELECT 1')).scalar_one()


def _validate_database_revision(database) -> None:
    """只读校验数据库 revision；迁移未执行时拒绝启动应用。"""
    config_path = Path(os.getenv(
        'ALEMBIC_CONFIG',
        str(Path(BASE_DIR).parent / 'alembic.ini'),
    )).resolve()
    if not config_path.is_file():
        raise RuntimeError(f'Alembic 配置不存在，拒绝启动: {config_path}')

    config = Config(str(config_path))
    expected_heads = set(ScriptDirectory.from_config(config).get_heads())
    if len(expected_heads) != 1:
        raise RuntimeError(
            f'Alembic 必须且只能有一个 head，当前为: {sorted(expected_heads)}'
        )

    with database.engine.connect() as connection:
        current_heads = set(
            MigrationContext.configure(connection).get_current_heads()
        )

    if current_heads != expected_heads:
        raise RuntimeError(
            '数据库迁移版本不匹配，拒绝启动；'
            f'current={sorted(current_heads)}, expected={sorted(expected_heads)}。'
            '请先执行 python -m alembic -c alembic.ini upgrade head。'
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=int(os.getenv("FLASK_PORT", 8765)))
    args = parser.parse_args()

    application = create_app()
    application.run(host=os.getenv("FLASK_HOST", "127.0.0.1"), port=args.port, debug=False)
