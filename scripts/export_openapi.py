"""Write contracts/openapi.json (run after changing any schema)."""

import json
from pathlib import Path

from app.core.config import Settings
from app.main import create_app

app = create_app(Settings(_env_file=None, fake_models=True, auth_disabled=True))
Path("contracts/openapi.json").write_text(
    json.dumps(app.openapi(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
)
print("Wrote contracts/openapi.json")
