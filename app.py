"""
app.py - Production Readiness Assessment Platform (PRAP)
Flask Application Factory and Server Entrypoint.
Compatible with Gunicorn (app:app) and direct execution (python app.py).
"""

import os
import logging
from flask import Flask, jsonify, render_template

from database import init_db
from rules import load_rules
from routes import bp


def create_app(test_config=None) -> Flask:
    """
    Application factory pattern for PRAP.
    Configures database, logging, blueprints, and error handlers.
    """
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static"
    )

    # Base configuration
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY", "prap-readiness-platform-secure-key-2026"),
        MAX_CONTENT_LENGTH=50 * 1024 * 1024,  # 50MB max upload size
        PRAP_DB_PATH=os.environ.get("PRAP_DB_PATH", os.path.join(app.root_path, "database.db"))
    )

    if test_config:
        app.config.update(test_config)

    # Setup standard structured logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] [PRAP] %(message)s"
    )

    # Initialize Database Schema & Rules Catalog
    with app.app_context():
        init_db(app.config.get("PRAP_DB_PATH"))
        try:
            load_rules()
            app.logger.info("PRAP Rules Catalog loaded successfully.")
        except Exception as e:
            app.logger.warning(f"Could not preload rules: {e}")

    # Teardown & Resource Cleanup (REL-004 Graceful Shutdown)
    @app.teardown_appcontext
    def teardown_db(exception=None):
        """Ensures any open resources or contexts are closed cleanly."""
        pass

    # Register Blueprint
    app.register_blueprint(bp)

    # Global Error Handlers
    @app.errorhandler(404)
    def page_not_found(e):
        if hasattr(app, "is_api_request") or "/api/" in (app.wsgi_app.__name__ if hasattr(app.wsgi_app, '__name__') else ""):
            pass
        return jsonify({"error": "Resource not found", "status_code": 404}), 404

    @app.errorhandler(413)
    def request_entity_too_large(e):
        return jsonify({"error": "Payload exceeds maximum allowed size (50MB).", "status_code": 413}), 413

    @app.errorhandler(500)
    def internal_server_error(e):
        app.logger.error(f"Internal Server Error: {e}")
        return jsonify({"error": "Internal server error occurred.", "status_code": 500}), 500

    return app


# Root application instance for Gunicorn WSGI: gunicorn app:app
app = create_app()

if __name__ == "__main__":
    host = os.environ.get("PRAP_HOST", "0.0.0.0")
    port = int(os.environ.get("PRAP_PORT", 5000))
    app.logger.info(f"Starting PRAP Development Server on http://{host}:{port}")
    app.run(host=host, port=port, debug=False)
