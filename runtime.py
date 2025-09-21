import os
import sys
import time
import shutil
import signal
import subprocess
import threading
from pathlib import Path
from typing import Iterable, Optional, Tuple
from urllib.parse import urlparse

import requests

ROOT = Path(__file__).resolve().parent
PORT = 8000
MCP_CMD = [
    "fastmcp",
    "run",
    "server.py:app",
    "--transport",
    "http",
    "--host",
    "127.0.0.1",
    "--port",
    str(PORT),
]

NGROK_API = "http://127.0.0.1:4040/api/tunnels"


class ProcessSupervisor:
    """Управляет запуском процессов и их логами."""

    def __init__(
        self,
        *,
        subprocess_module=subprocess,
        os_module=os,
        signal_module=signal,
        time_module=time,
        threading_module=threading,
    ):
        self._subprocess = subprocess_module
        self._os = os_module
        self._signal = signal_module
        self._time = time_module
        self._threading = threading_module
        self._processes: list[Tuple[str, subprocess.Popen]] = []
        self._output_state: dict[subprocess.Popen, dict] = {}

    def start(self, cmd: Iterable[str], name: str, *, env=None, cwd=None):
        """Запускает новый подпроцесс и начинает поток чтения логов."""

        print(f"[start] {name}: {' '.join(map(str, cmd))}")
        creationflags = (
            getattr(self._subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            if self._os.name == "nt"
            else 0
        )
        try:
            proc = self._subprocess.Popen(
                cmd,
                stdout=self._subprocess.PIPE,
                stderr=self._subprocess.STDOUT,
                text=True,
                bufsize=1,
                creationflags=creationflags,
                env=env,
                cwd=cwd,
            )
        except FileNotFoundError as exc:
            print(f"[error] Не найден исполняемый файл для {name}: {exc}")
            sys.exit(1)
        self._start_reader(proc, name)
        self._processes.append((name, proc))
        return proc

    def tail(self, prefix: str, proc, lines: int = 12, timeout: float = 1.5):
        """Выводит первые строки лога процесса."""

        state = self._output_state.get(proc)
        if not state:
            return

        printed = 0
        start_time = self._time.time()
        while printed < lines:
            with state["lock"]:
                available = state["first_lines"][:lines]
            if len(available) > printed:
                for line in available[printed:]:
                    print(f"[{prefix}] {line}")
                printed = len(available)
            if printed >= lines or proc.poll() is not None:
                break
            if self._time.time() - start_time > timeout:
                break
            self._time.sleep(0.05)

    def sleep(self, seconds: float):
        self._time.sleep(seconds)

    def shutdown(self):
        print("\n[stop] Останавливаем процессы…")
        # мягкая остановка
        for name, proc in self._processes:
            if proc.poll() is None:
                try:
                    if self._os.name == "nt" and hasattr(self._os, "kill"):
                        try:
                            self._os.kill(proc.pid, self._signal.CTRL_BREAK_EVENT)  # type: ignore[attr-defined]
                        except AttributeError:
                            pass
                    proc.terminate()
                except Exception:
                    pass
        self._time.sleep(1.0)
        # жёсткая остановка
        for name, proc in self._processes:
            if proc.poll() is None:
                try:
                    proc.kill()
                except Exception:
                    pass
        print("[stop] Готово.")

    def monitor_processes(self, mcp, ngrok_proc, reused_ngrok: bool, ngrok_monitor) -> Tuple[int, str]:
        """Следит за состоянием процессов и возвращает код выхода и причину остановки."""

        exit_code = 0
        stop_reason = "Остановка по запросу пользователя (Ctrl+C)."

        def api_alive() -> bool:
            return bool(ngrok_monitor and ngrok_monitor.api_alive())

        try:
            while True:
                self._time.sleep(1)
                if mcp.poll() is not None:
                    print("[error] MCP-сервер завершился. Останавливаемся.")
                    exit_code = 1
                    stop_reason = (
                        "MCP-сервер завершился. Проверь логи выше, перезапусти сервер и повтори."
                    )
                    break
                if ngrok_proc and ngrok_proc.poll() is not None and not api_alive():
                    print("[error] ngrok завершился. Останавливаемся.")
                    exit_code = 1
                    stop_reason = (
                        "ngrok завершился. Переустанови туннель и повтори запуск."
                    )
                    break
                if reused_ngrok and not api_alive():
                    print(
                        "[warning] Ранее запущенный ngrok-туннель больше недоступен.",
                        " Останавливаем сервер.",
                    )
                    exit_code = 1
                    stop_reason = (
                        "Переиспользованный ngrok-туннель остановился."
                        " Запусти ngrok вручную и повтори попытку."
                    )
                    break
        except KeyboardInterrupt:
            stop_reason = "Остановка по запросу пользователя (Ctrl+C)."
        return exit_code, stop_reason

    def _start_reader(self, proc, name: str):
        state = {
            "name": name,
            "first_lines": [],
            "lock": self._threading.Lock(),
            "max_first": 100,
        }

        def reader():
            try:
                if not proc.stdout:
                    return
                for raw_line in proc.stdout:
                    if raw_line == "":
                        break
                    line = raw_line.rstrip("\r\n")
                    with state["lock"]:
                        if len(state["first_lines"]) < state["max_first"]:
                            state["first_lines"].append(line)
                    print(f"[{name}] {line}")
            except Exception:
                pass
            finally:
                try:
                    if proc.stdout and not proc.stdout.closed:
                        proc.stdout.close()
                except Exception:
                    pass
                self._output_state.pop(proc, None)

        thread = self._threading.Thread(
            target=reader, name=f"{name}-log-reader", daemon=True
        )
        self._output_state[proc] = state
        thread.start()


class NgrokTunnel:
    """Инкапсулирует взаимодействие с ngrok."""

    def __init__(
        self,
        port: int,
        *,
        root: Optional[Path] = None,
        api_url: str = NGROK_API,
        requests_module=requests,
        time_module=time,
    ):
        self.port = port
        self.root = Path(root) if root is not None else ROOT
        self.root = self.root.resolve()
        self.api_url = api_url
        self._requests = requests_module
        self._time = time_module

    def find_executable(self) -> str:
        here = self.root
        local_candidates = [here / "ngrok.exe", here / "ngrok"]
        for candidate in local_candidates:
            if candidate.is_file():
                return str(candidate)

        for name in ("ngrok", "ngrok.exe"):
            path = shutil.which(name)
            if path:
                return path

        candidates = [
            r"%LOCALAPPDATA%\Programs\ngrok\ngrok.exe",
            r"%LOCALAPPDATA%\ngrok\ngrok.exe",
            r"%USERPROFILE%\AppData\Local\Programs\ngrok\ngrok.exe",
            r"C:\\Program Files\\ngrok\\ngrok.exe",
        ]
        for candidate in candidates:
            expanded = os.path.expandvars(candidate)
            if os.path.exists(expanded):
                return expanded

        raise FileNotFoundError(
            "ngrok не найден. Положи ngrok.exe в папку проекта или добавь в PATH."
        )

    def api_alive(self) -> bool:
        try:
            response = self._requests.get(self.api_url, timeout=1.5)
            return response is not None and response.status_code == 200
        except Exception:
            return False

    def get_public_url(self, timeout: float = 20) -> Optional[str]:
        start_time = self._time.time()
        loopback_hosts = {"127.0.0.1", "localhost", "::1"}
        while self._time.time() - start_time < timeout:
            try:
                response = self._requests.get(self.api_url, timeout=2)
                if response is None:
                    raise ValueError("Empty response")
                response.raise_for_status()
                data = response.json()
                for tunnel in data.get("tunnels", []):
                    if tunnel.get("proto") != "https":
                        continue
                    config = tunnel.get("config") or {}
                    host, port = self._parse_addr(config.get("addr", ""))
                    if host and host.lower() in loopback_hosts and port == self.port:
                        return tunnel.get("public_url")
            except Exception:
                pass
            self._time.sleep(0.5)
        return None

    @staticmethod
    def _parse_addr(addr: str):
        if not addr:
            return None, None
        candidate = addr if "://" in addr else f"http://{addr}"
        try:
            parsed = urlparse(candidate)
        except ValueError:
            return None, None
        return parsed.hostname, parsed.port


def run(supervisor: Optional[ProcessSupervisor] = None, tunnel: Optional[NgrokTunnel] = None) -> int:
    supervisor = supervisor or ProcessSupervisor()
    tunnel = tunnel or NgrokTunnel(port=PORT, root=ROOT)

    # 1) MCP-сервер
    mcp = supervisor.start(MCP_CMD, "mcp", cwd=tunnel.root)
    supervisor.sleep(0.8)
    supervisor.tail("mcp", mcp)

    if mcp.poll() is not None:
        print("[error] MCP-сервер завершился при запуске. Проверь логи выше.")
        supervisor.shutdown()
        return 1

    # 2) ngrok
    ngrok_process = None
    already_running = tunnel.api_alive()
    if already_running:
        print(
            "[info] Найден уже запущенный ngrok (API на 4040 доступен). Используем его."
        )
    else:
        try:
            ngrok_exe = tunnel.find_executable()
        except FileNotFoundError as exc:
            print(f"[error] {exc}")
            supervisor.shutdown()
            return 1

        token = os.environ.get("NGROK_AUTHTOKEN", "").strip()
        cmd = [ngrok_exe, "http", str(tunnel.port)]
        env = {**os.environ, "NGROK_AUTHTOKEN": token} if token else None
        ngrok_process = supervisor.start(cmd, "ngrok", env=env)
        supervisor.sleep(1.0)
        supervisor.tail("ngrok", ngrok_process)

        if ngrok_process.poll() is not None and not tunnel.api_alive():
            print(
                "[error] ngrok не запустился и локальный API 4040 недоступен. "
                "Проверь auth-token или закрой предыдущие сессии в dashboard."
            )
            supervisor.shutdown()
            return 1

    reused_ngrok = already_running and ngrok_process is None

    # 3) Публичный URL
    url = tunnel.get_public_url()
    if not url:
        print(
            "[error] Не удалось получить публичный URL от ngrok (проверь токен/интернет/активные сессии)."
        )
        supervisor.shutdown()
        return 1

    public_mcp = f"{url}/mcp"
    print("\n✅ Всё поднято!")
    print(f"• Локально:   http://127.0.0.1:{tunnel.port}/mcp")
    print(f"• Публично:   {public_mcp}")
    print("\nОставь окно открытым. Нажми Ctrl+C, чтобы остановить.")

    exit_code, stop_reason = supervisor.monitor_processes(
        mcp, ngrok_process, reused_ngrok, tunnel
    )
    print(f"\n[stop] Причина остановки: {stop_reason}")
    supervisor.shutdown()
    return exit_code
