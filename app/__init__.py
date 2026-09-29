from pathlib import Path
import time

from flask import Flask


TEMP_FILE_TTL_SECONDS = 60 * 60


def _cleanup_old_temp_files(app: Flask) -> None:
    cutoff = time.time() - TEMP_FILE_TTL_SECONDS

    cleanup_dirs = [
        app.config["UPLOAD_FOLDER"],
        app.config["OUTPUT_FOLDER"],
    ]

    for directory in cleanup_dirs:
        for path in directory.glob("*"):
            try:
                if path.is_file() and path.stat().st_mtime < cutoff:
                    path.unlink(missing_ok=True)
            except OSError:
                continue

    profile_dir = app.config["PROFILE_PATH"].parent
    for path in profile_dir.glob("extracted_*.json"):
        try:
            if path.is_file() and path.stat().st_mtime < cutoff:
                path.unlink(missing_ok=True)
        except OSError:
            continue


def create_app() -> Flask:
    """Создаёт и настраивает Flask-приложение."""

    app = Flask(__name__)

    base_dir = Path(__file__).resolve().parent.parent

    app.config["UPLOAD_FOLDER"] = base_dir / "uploads"
    app.config["OUTPUT_FOLDER"] = base_dir / "outputs"
    app.config["PROFILE_PATH"] = base_dir / "profiles" / "gost_r_7_0_110_2025.json"
    app.config["UPLOAD_FOLDER"].mkdir(exist_ok=True)
    app.config["OUTPUT_FOLDER"].mkdir(exist_ok=True)

    @app.before_request
    def _cleanup_temp_storage() -> None:
        _cleanup_old_temp_files(app)

    from app.routes import main_bp

    app.register_blueprint(main_bp)

    return app
