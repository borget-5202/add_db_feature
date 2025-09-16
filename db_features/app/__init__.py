# app/__init__.py
from flask import Flask, send_from_directory
import click, os
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from .models import User
import secrets
from flask import g

from .db import db
migrate = Migrate()
login_manager = LoginManager()
limiter = Limiter(get_remote_address, storage_uri="memory://")

def create_app(config_object="config.Config"):
    app = Flask(__name__)
    app.config.from_object(config_object)
    app.config.setdefault("GAME24_WARMUP", True)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    limiter.init_app(app)

    # register blueprints
    from .home.routes import bp as home_bp
    app.register_blueprint(home_bp)

    from .auth.routes import auth_bp
    app.register_blueprint(auth_bp, url_prefix="/auth")

    from .games.assets_bp import assets_bp
    app.register_blueprint(assets_bp)

    from .games.game24.routes import bp as game24_bp
    app.register_blueprint(game24_bp, url_prefix="/game24")

    from .games.count_by_2s.routes import bp as cb2s_bp
    app.register_blueprint(cb2s_bp, url_prefix="/count_by_2s")

    # --- Legacy alias: /api/game24/* -> /game24/api/* (preserve query string; 307 keeps method/body) ---
    from flask import redirect, request
    
    # In your __init__.py file, update the config section:
    app.config.setdefault("GAME24_WARMUP", True)
    
    # And update the warmup section:
    with app.app_context():
        if app.config["GAME24_WARMUP"]:
            try:
                from .games.game24.logic.puzzle_store import init_store as _init_store
                _init_store(force=False)
                app.logger.info("Game24 puzzle store initialized at startup.")
            except Exception:
                app.logger.exception("Game24 warmup failed")


    # ---- CLI: rebuild Game24 puzzle store caches (DB-first, JSON fallback) ----
    @app.cli.command("game24-rebuild-store")
    def game24_rebuild_store():
        """Rebuild Game24 puzzle caches from DB (fallback to JSON)."""
        from .games.game24.logic.puzzle_store import init_store
        with app.app_context():
            init_store()
            click.echo("✅ Rebuilt Game24 puzzle store (DB-first, JSON fallback).")

    # --- Per-request CSP nonce ---
    @app.before_request
    def _set_csp_nonce():
        g.csp_nonce = secrets.token_urlsafe(16)

    @app.context_processor
    def _inject_csp_nonce():
        return {"csp_nonce": getattr(g, "csp_nonce", "")}

    @app.after_request
    def set_security_headers(resp):
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        # Only enable HSTS in HTTPS prod:
        # resp.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        # CSP with per-request nonce for inline scripts
        csp = (
            "default-src 'self'; "
            "img-src 'self' data:; "
            "style-src 'self' 'unsafe-inline'; "
            f"script-src 'self' 'nonce-{g.csp_nonce}'"
        )
        resp.headers["Content-Security-Policy"] = csp
        return resp

    @app.cli.command("game24-stats")
    def game24_stats():
        from .games.game24.logic.puzzle_store import PUZZLES_BY_ID
        total = len(PUZZLES_BY_ID)
        with_solutions = sum(1 for p in PUZZLES_BY_ID.values() if p.get("solutions"))
        click.echo(f"Game24 puzzles loaded: {total} total, {with_solutions} with solutions")


    @app.route("/favicon.ico")
    def favicon():
        return send_from_directory(
            os.path.join(app.root_path, "static"),
            "favicon.ico",
            mimetype="image/vnd.microsoft.icon",
        )

    @app.cli.command("stats-refresh")
    def stats_refresh():
        from .db import db
        db.session.execute(db.text("REFRESH MATERIALIZED VIEW CONCURRENTLY app.mv_user_daily_attempts;"))
        db.session.commit()
        print("Refreshed mv_user_daily_attempts")

    @app.route("/games/assets/<path:filename>")
    def games_assets(filename):
        # Files live at app/games/assets/*
        return send_from_directory(
            os.path.join(app.root_path, "games", "assets"),
            filename,
        )

    return app



@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

