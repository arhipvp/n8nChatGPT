import os
import sys
import time
import json
import shutil
import signal
import subprocess
import threading
from pathlib import Path
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv

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


load_dotenv(ROOT / ".env")

procs = []  # [(name, Popen)]
_output_state = {}


def _start_reader(proc, name):
    state = {
        "name": name,
        "first_lines": [],
        "lock": threading.Lock(),
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
            _output_state.pop(proc, None)

    t = threading.Thread(target=reader, name=f"{name}-log-reader", daemon=True)
    _output_state[proc] = state
    t.start()


def find_ngrok_exe() -> str:
    """
    Ищем ngrok:
    - локально в каталоге проекта рядом со скриптом (./ngrok.exe / ./ngrok)
    - в PATH (shutil.which)
    - в типичных папках Windows
    """

    here = Path(ROOT).resolve()
    local_candidates = [here / "ngrok.exe", here / "ngrok"]
    for candidate in local_candidates:
        if candidate.is_file():
            return str(candidate)

    for name in ("ngrok", "ngrok.exe"):
        p = shutil.which(name)
        if p:
            return p

    # типичные места для Windows
    candidates = [
        r"%LOCALAPPDATA%\Programs\ngrok\ngrok.exe",
        r"%LOCALAPPDATA%\ngrok\ngrok.exe",
        r"%USERPROFILE%\AppData\Local\Programs\ngrok\ngrok.exe",
        r"C:\Program Files\ngrok\ngrok.exe",
    ]
    for c in candidates:
        c = os.path.expandvars(c)
        if os.path.exists(c):
            return c

    raise FileNotFoundError(
        "ngrok не найден. Положи ngrok.exe в папку проекта или добавь в PATH."
    )


def start(cmd, name, *, env=None):
    print(f"[start] {name}: {' '.join(map(str, cmd))}")
    try:
        p = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            # на Windows удобнее отдельная группа, чтобы корректно ловить Ctrl+C
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
            if os.name == "nt"
            else 0,
            env=env,
        )
    except FileNotFoundError as e:
        print(f"[error] Не найден исполняемый файл для {name}: {e}")
        sys.exit(1)
    _start_reader(p, name)
    procs.append((name, p))
    return p


def tail(prefix, proc, lines=12, timeout=1.5):
    """Лёгкий вывод первых строк лога процесса."""
    state = _output_state.get(proc)
    if not state:
        return

    printed = 0
    t0 = time.time()
    while printed < lines:
        with state["lock"]:
            available = state["first_lines"][:lines]
        if len(available) > printed:
            for line in available[printed:]:
                print(f"[{prefix}] {line}")
            printed = len(available)
        if printed >= lines or proc.poll() is not None:
            break
        if time.time() - t0 > timeout:
            break
        time.sleep(0.05)


def ngrok_api_alive() -> bool:
    try:
        r = requests.get(NGROK_API, timeout=1.5)
        return r.status_code == 200
    except Exception:
        return False


def _parse_addr(addr: str):
    if not addr:
        return None, None
    candidate = addr if "://" in addr else f"http://{addr}"
    try:
        parsed = urlparse(candidate)
    except ValueError:
        return None, None
    return parsed.hostname, parsed.port


def get_ngrok_url(timeout=20):
    t0 = time.time()
    loopback_hosts = {"127.0.0.1", "localhost", "::1"}
    while time.time() - t0 < timeout:
        try:
            r = requests.get(NGROK_API, timeout=2)
            r.raise_for_status()
            data = r.json()
            for t in data.get("tunnels", []):
                if t.get("proto") != "https":
                    continue
                config = t.get("config") or {}
                host, port = _parse_addr(config.get("addr", ""))
                if host and host.lower() in loopback_hosts and port == PORT:
                    return t.get("public_url")
        except Exception:
            pass
        time.sleep(0.5)
    return None


def shutdown():
    print("\n[stop] Останавливаем процессы…")
    # мягко
    for name, p in procs:
        if p.poll() is None:
            try:
                if os.name == "nt":
                    # отправим CTRL+BREAK группе процесса
                    os.kill(p.pid, signal.CTRL_BREAK_EVENT)
                p.terminate()
            except Exception:
                pass
    time.sleep(1.0)
    # жёстко
    for name, p in procs:
        if p.poll() is None:
            try:
                p.kill()
            except Exception:
                pass
    print("[stop] Готово.")


if __name__ == "__main__":
    # 1) MCP-сервер
    mcp = start(MCP_CMD, "mcp")
    time.sleep(0.8)
    tail("mcp", mcp)

    # Если MCP мгновенно упал — не продолжаем
    if mcp.poll() is not None:
        print("[error] MCP-сервер завершился при запуске. Проверь логи выше.")
        shutdown()
        sys.exit(1)

    # 2) ngrok
    ngrok_exe = None
    ng = None

    already_running = ngrok_api_alive()
    if already_running:
        print("[info] Найден уже запущенный ngrok (API на 4040 доступен). Используем его.")
    else:
        try:
            ngrok_exe = find_ngrok_exe()
        except FileNotFoundError as e:
            print(f"[error] {e}")
            shutdown()
            sys.exit(1)

        token = os.environ.get("NGROK_AUTHTOKEN", "").strip()

        NGROK_CMD = [ngrok_exe, "http", str(PORT)]
        popen_env = None
        if token:
            popen_env = {**os.environ, "NGROK_AUTHTOKEN": token}

        ng = start(NGROK_CMD, "ngrok", env=popen_env)
        time.sleep(1.0)
        tail("ngrok", ng)

        # Если агент отвалился (например, ERR_NGROK_108), но API поднялся — всё равно продолжим
        if ng.poll() is not None and not ngrok_api_alive():
            print(
                "[error] ngrok не запустился и локальный API 4040 недоступен. "
                "Проверь auth-token или закрой предыдущие сессии в dashboard."
            )
            shutdown()
            sys.exit(1)

    # 3) Публичный URL
    url = get_ngrok_url()
    if not url:
        print(
            "[error] Не удалось получить публичный URL от ngrok (проверь токен/интернет/активные сессии)."
        )
        shutdown()
        sys.exit(1)

    public_mcp = f"{url}/mcp"
    print("\n✅ Всё поднято!")
    print(f"• Локально:   http://127.0.0.1:{PORT}/mcp")
    print(f"• Публично:   {public_mcp}")
    print("\nОставь окно открытым. Нажми Ctrl+C, чтобы остановить.")

    # 4) Основной цикл
    try:
        while True:
            time.sleep(1)
            if mcp.poll() is not None:
                print("[error] MCP-сервер завершился. Останавливаемся.")
                break
            if ng and ng.poll() is not None and not ngrok_api_alive():
                print("[error] ngrok завершился. Останавливаемся.")
                break
    except KeyboardInterrupt:
        pass
    finally:
        shutdown()
