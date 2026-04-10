import argparse
import os
import sys
from flask import Flask
from flask_cors import CORS
from database.base import db
from dotenv import load_dotenv
from sqlalchemy.pool import NullPool

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
    # 单用户桌面应用使用 NullPool：每次请求用完即释放连接，
    # 彻底避免空闲连接被云端防火墙/NAT 静默关闭后复用失败的问题
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "poolclass": NullPool,
        "connect_args": {
            "connect_timeout": 10,   # 建连超时
            "read_timeout":    30,   # 读超时，防止查询挂起
            "write_timeout":   30,   # 写超时
        },
    }

    # ── 初始化扩展 ────────────────────────────────────
    db.init_app(app)
    CORS(app, origins=["http://localhost:5173", "file://"])

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

    # ── 健康检查 ──────────────────────────────────────
    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=int(os.getenv("FLASK_PORT", 8765)))
    args = parser.parse_args()

    application = create_app()
    application.run(host="127.0.0.1", port=args.port, debug=False)