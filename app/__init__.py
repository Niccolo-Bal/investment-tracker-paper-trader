from pathlib import Path

from flask import Flask
from sqlalchemy import inspect, text

from app.models import db
from app.routes_api import api_bp
from app.routes_pages import pages_bp


def create_app(db_path: str | None = None) -> Flask:
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )

    if db_path is None:
        data_dir = Path(__file__).resolve().parent.parent / "instance"
        data_dir.mkdir(parents=True, exist_ok=True)
        db_path = str(data_dir / "tracker.db")

    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SECRET_KEY"] = "local-dev-only"
    app.config["TEMPLATES_AUTO_RELOAD"] = True

    db.init_app(app)

    app.register_blueprint(pages_bp)
    app.register_blueprint(api_bp, url_prefix="/api")

    with app.app_context():
        db.create_all()
        columns = {column["name"] for column in inspect(db.engine).get_columns("accounts")}
        if "reference_cash" in columns:
            with db.engine.begin() as connection:
                connection.execute(text("ALTER TABLE accounts DROP COLUMN reference_cash"))
        order_columns = {
            column["name"] for column in inspect(db.engine).get_columns("orders")
        }
        if "error_message" not in order_columns:
            with db.engine.begin() as connection:
                connection.execute(
                    text("ALTER TABLE orders ADD COLUMN error_message VARCHAR(240)")
                )

    return app
