"""Application context: paths, database, settings store and job runner.

One context is created per application instance (see main.create_app) and kept
on app.state so tests can build isolated instances with a temp data directory.
"""

from __future__ import annotations

from pathlib import Path

from . import db

BACKEND_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DATA_DIR = BACKEND_DIR / "data"
DEMO_DATA_DIR = BACKEND_DIR / "demo_data"


class Ctx:
    def __init__(self, data_dir: Path | None = None, demo_dir: Path | None = None):
        self.data_dir = Path(data_dir) if data_dir else DEFAULT_DATA_DIR
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.data_dir / "screening.db"
        self.uploads_dir = self.data_dir / "uploads"
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        self.config_path = self.data_dir / "config.json"
        self.demo_dir = Path(demo_dir) if demo_dir else DEMO_DATA_DIR
        self.jobs = None  # set by create_app (JobRunner)

    def connect(self):
        return db.connect(self.db_path)

    def init(self) -> None:
        db.init_db(self.db_path)

    # ---- settings (non-secret application settings live in a JSON file) ----

    def read_config(self) -> dict:
        import json

        if not self.config_path.exists():
            return {}
        try:
            return json.loads(self.config_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def write_config(self, config: dict) -> None:
        import json

        self.config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
