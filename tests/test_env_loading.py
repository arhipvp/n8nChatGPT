import importlib
import os
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import main


class _DummyResponse:
    status_code = 200

    def raise_for_status(self):
        return None

    def json(self):
        return {"tunnels": []}


def test_env_loaded_from_script_directory(tmp_path, monkeypatch):
    project_root = Path(main.__file__).resolve().parent
    env_path = project_root / ".env"

    backup = env_path.read_text() if env_path.exists() else None
    env_path.write_text("NGROK_AUTHTOKEN=from_test\n")

    workdir = tmp_path / "elsewhere"
    workdir.mkdir()
    monkeypatch.chdir(workdir)

    original_token = os.environ.get("NGROK_AUTHTOKEN")
    if original_token is not None:
        monkeypatch.setenv("NGROK_AUTHTOKEN", original_token)
    else:
        monkeypatch.delenv("NGROK_AUTHTOKEN", raising=False)

    orig_requests = sys.modules.get("requests")
    requests_stub = types.ModuleType("requests")
    requests_stub.get = lambda *args, **kwargs: _DummyResponse()
    sys.modules["requests"] = requests_stub

    orig_dotenv = sys.modules.get("dotenv")

    def _load_dotenv(path):
        assert Path(path) == env_path
        for raw_line in env_path.read_text().splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ[key] = value
        return True

    dotenv_stub = types.ModuleType("dotenv")
    dotenv_stub.load_dotenv = _load_dotenv
    sys.modules["dotenv"] = dotenv_stub

    try:
        importlib.reload(main)
        assert os.environ["NGROK_AUTHTOKEN"] == "from_test"
    finally:
        if backup is None:
            try:
                env_path.unlink()
            except FileNotFoundError:
                pass
        else:
            env_path.write_text(backup)

        if orig_requests is not None:
            sys.modules["requests"] = orig_requests
        else:
            sys.modules.pop("requests", None)

        if orig_dotenv is not None:
            sys.modules["dotenv"] = orig_dotenv
        else:
            sys.modules.pop("dotenv", None)

        if original_token is not None:
            os.environ["NGROK_AUTHTOKEN"] = original_token
        else:
            os.environ.pop("NGROK_AUTHTOKEN", None)

        importlib.reload(main)
