from pathlib import Path
import sys
import types

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if "requests" not in sys.modules:
    requests_stub = types.ModuleType("requests")
    requests_stub.get = lambda *args, **kwargs: None
    sys.modules["requests"] = requests_stub

if "dotenv" not in sys.modules:
    dotenv_stub = types.ModuleType("dotenv")
    dotenv_stub.load_dotenv = lambda *_args, **_kwargs: False
    sys.modules["dotenv"] = dotenv_stub

import main


class _DummyProcess:
    def __init__(self, poll_values):
        self._values = iter(poll_values)

    def poll(self):
        try:
            return next(self._values)
        except StopIteration:
            return None


def test_monitor_processes_handles_reused_ngrok_drop(monkeypatch):
    statuses = iter([False])

    def fake_ngrok_api_alive():
        try:
            return next(statuses)
        except StopIteration:
            return False

    monkeypatch.setattr(main, "ngrok_api_alive", fake_ngrok_api_alive)
    monkeypatch.setattr(main.time, "sleep", lambda *_args, **_kwargs: None)

    mcp = _DummyProcess([None])

    exit_code, reason = main.monitor_processes(mcp, None, True)

    assert exit_code == 1
    assert "Переиспользованный ngrok-туннель остановился" in reason


def test_mcp_process_uses_project_root(monkeypatch, tmp_path):
    # Меняем рабочий каталог, чтобы эмулировать запуск из другого места
    monkeypatch.chdir(tmp_path)
    assert Path.cwd() == tmp_path

    captured = {}

    class DummyProcess:
        def __init__(self, cmd, **kwargs):
            captured["cmd"] = cmd
            captured["kwargs"] = kwargs
            self.stdout = None

        def poll(self):
            return None

    monkeypatch.setattr(main, "_start_reader", lambda *args, **kwargs: None)
    monkeypatch.setattr(main, "procs", [])
    monkeypatch.setattr(main.subprocess, "Popen", DummyProcess)

    proc = main.start(main.MCP_CMD, "mcp", cwd=main.ROOT)

    assert captured["cmd"] == main.MCP_CMD
    assert captured["kwargs"].get("cwd") == main.ROOT
    assert captured["kwargs"].get("env") is None
    assert proc is not None
