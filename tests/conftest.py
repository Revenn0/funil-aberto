import sys
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import app

SEGREDO = "segredo-de-teste"
ADMIN = "admin-de-teste"


@pytest.fixture()
def srv(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("WEBHOOK_SECRET", SEGREDO)
    monkeypatch.setenv("ADMIN_TOKEN", ADMIN)
    for k in ("META_PIXEL_ID", "META_CAPI_TOKEN", "EVOLUTION_URL", "WA_CLOUD_TOKEN", "SMTP_HOST", "META_AD_LIBRARY_TOKEN",
              "TELEGRAM_BOT_TOKEN", "COMPOSIO_API_KEY", "EMAIL_VIA", "FUNIL_CONFIG", "CONEXOES_URL"):
        monkeypatch.delenv(k, raising=False)
    s = ThreadingHTTPServer(("127.0.0.1", 0), app.H)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{s.server_port}"
    s.shutdown()


