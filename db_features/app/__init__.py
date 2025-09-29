# app/__init__.py
from __future__ import annotations
import os, secrets
import logging
import click
from flask import Flask

from .db import db
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# --- extensions ---
migrate = Migrate()
login_manager = LoginManager()
# dev-friendly in-memory limiter; swap for redis in prod
limiter = Limiter(get_remote_address, storage_uri="memory://")


def create_app() -> Flask:
    app = Flask(__name__, instance_relative_config=True)

    # ---------------------------
    # Config
    # ---------------------------
    app.config.from_pyfile("config.py", silent=True)  # instance/config.py (optional)

    app.config.setdefault(
        "SQLALCHEMY_DATABASE_URI",
        os.getenv("SQLALCHEMY_DATABASE_URI") or os.getenv("DATABASE_URL")
    )
    app.config.setdefault("SQLALCHEMY_TRACK_MODIFICATIONS", False)
    app.config.setdefault("GAME24_WARMUP", True)

    if not app.config.get("SQLALCHEMY_DATABASE_URI"):
        raise RuntimeError(
            "Missing SQLALCHEMY_DATABASE_URI (or DATABASE_URL). "
            "Set it via env or instance/config.py."
        )

    # ---------------------------
    # Logging (DEBUG everywhere useful)
    # ---------------------------
    level = logging.DEBUG
    app.logger.setLevel(level)
    logging.getLogger().setLevel(level)                # root
    logging.getLogger("werkzeug").setLevel(level)

    for name in ("app", "app.games", "app.games.core", "app.games.game24", "app.games.count_by_2s"):
        logging.getLogger(name).setLevel(level)

    for h in app.logger.handlers:
        h.setLevel(level)

    # ---------------------------
    # Extensions init
    # ---------------------------
    # Ensure SECRET_KEY is truthy (override falsy values from any loaded config)
    if not app.config.get("SECRET_KEY"):
        app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
    
    # (optional sanity while debugging)
    print("SECRET_KEY set in app?", bool(app.config.get("SECRET_KEY")))
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    limiter.init_app(app)

    # where to redirect when @login_required fails
    login_manager.login_view = "auth.login"

    # user loader
    from .models import User  # import after db/app set up
    @login_manager.user_loader
    def load_user(user_id):
        try:
            return User.query.get(int(user_id))
        except Exception:
            return None

    # ---------------------------
    # Blueprints
    # ---------------------------
    # Shared static assets (cards/css/js) at /games/assets/...
    try:
        # Your file defines `assets_bp = Blueprint(...)`
        from .games.assets_bp import assets_bp as games_assets_bp
        app.register_blueprint(games_assets_bp)  # static_url_path is set in the bp
    except Exception:
        app.logger.exception("Failed to register games_assets_bp")

    # Auth (login/logout) – only if you have it
    try:
        from .auth.routes import auth_bp as auth_bp
        app.register_blueprint(auth_bp)
    except Exception:
        app.logger.info("Auth blueprint not found; skipping")

    # Home
    try:
        from .home.routes import bp as home_bp
        app.register_blueprint(home_bp)
    except Exception:
        app.logger.exception("Failed to register Home blueprint")

    # Game24
    try:
        from .games.game24.game24_routes import bp as game24_bp
        # routes file already sets url_prefix="/games/game24" in the blueprint
        app.register_blueprint(game24_bp)
    except Exception:
        app.logger.exception("Failed to register Game24 blueprint")

    # sum-4-cards
    try:
        from app.games.sum_4_cards.sum4_routes import bp as sum4_bp
        app.register_blueprint(sum4_bp)
    except Exception:
        app.logger.info("sum-4-cards blueprint not found; skipping")

    # Count-by-2s
    try:
        from .games.count_by_2s.cb2s_routes import bp as cb2s_bp
        # use the prefix defined inside the blueprint file
        app.register_blueprint(cb2s_bp)
    except Exception:
        app.logger.info("Count-by-2s blueprint not found; skipping")

    # ---------------------------
    # Warmup Game24 store (DB-first, fallback JSON)
    # ---------------------------
    with app.app_context():
        if app.config.get("GAME24_WARMUP", True):
            try:
                from .games.core.puzzle_store_game24 import warmup_store
                warmup_store(force=False)
                app.logger.info("Game24 puzzle store warmed up at startup.")
            except Exception:
                app.logger.exception("Game24 warmup failed")

    # ---------------------------
    # CLI commands
    # ---------------------------
    @app.cli.command("game24-rebuild-store")
    def game24_rebuild_store():
        """Rebuild Game24 puzzle caches from DB (fallback to JSON)."""
        from .games.core.puzzle_store_game24 import warmup_store, get_store
        with app.app_context():
            warmup_store(force=True)
            store = get_store(load=False)
            click.echo(f"✅ Rebuilt Game24 store. Pools: {store.pool_report()}")

    @app.cli.command("game24-stats")
    def game24_stats():
        """Print Game24 store stats."""
        from .games.core.puzzle_store_game24 import get_store
        with app.app_context():
            store = get_store()
            total = len(store.by_id)
            with_solutions = sum(1 for p in store.by_id.values() if p.solutions)
            click.echo(
                f"Game24 puzzles loaded: total={total}, with_solutions={with_solutions}, pools={store.pool_report()}"
            )

    from flask import g

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
        resp.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "img-src 'self' data:; "
            "style-src 'self' 'unsafe-inline'; "
            f"script-src 'self' 'nonce-{g.csp_nonce}'"
        )
        return resp
    

    return app

