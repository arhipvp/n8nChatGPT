import time
import types

import runtime


class _DummyProcess:
    def __init__(self, poll_values):
        self._values = iter(poll_values)
        self.stdout = None

    def poll(self):
        try:
            return next(self._values)
        except StopIteration:
            return None


def test_monitor_processes_handles_reused_ngrok_drop():
    statuses = iter([False])

    class TunnelStub:
        def api_alive(self):
            try:
                return next(statuses)
            except StopIteration:
                return False

    supervisor = runtime.ProcessSupervisor(
        time_module=types.SimpleNamespace(sleep=lambda *_args, **_kwargs: None)
    )
    mcp = _DummyProcess([None])

    exit_code, reason = supervisor.monitor_processes(mcp, None, True, TunnelStub())

    assert exit_code == 1
    assert "Переиспользованный ngrok-туннель остановился" in reason


def test_mcp_process_uses_project_root(tmp_path):
    captured = {}

    def fake_popen(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        return _DummyProcess([None])

    subprocess_module = types.SimpleNamespace(
        PIPE=object(),
        STDOUT=object(),
        CREATE_NEW_PROCESS_GROUP=0,
        Popen=fake_popen,
    )

    supervisor = runtime.ProcessSupervisor(
        subprocess_module=subprocess_module,
        time_module=types.SimpleNamespace(time=time.time, sleep=lambda *_: None),
    )
    supervisor._start_reader = lambda *args, **kwargs: None

    proc = supervisor.start(runtime.MCP_CMD, "mcp", cwd=runtime.ROOT)

    assert captured["cmd"] == runtime.MCP_CMD
    assert captured["kwargs"].get("cwd") == runtime.ROOT
    assert captured["kwargs"].get("env") is None
    assert proc is not None
