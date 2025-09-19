import os
import sys
import time
import json
import shutil
import signal
import subprocess
from pathlib import Path

import requests

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

procs = []  # [(name, Popen)]


def find_ngrok_exe() -> str:
    """
    Ищем ngrok:
    - локально в проекте (./ngrok.exe / ./ngrok)
    - в PATH (shutil.which)
    - в типичных папках Windows
    """
    here = Path.cwd()
    for candidate in ["ngrok.exe", "ngrok"]:
        p = here / candidate
        if p.exists():
            return str(p)

    p = shutil.which("ngrok")
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


def start(cmd, name):
    print(f"[start] {name}: {' '.join(map(str, cmd))}")
    try:
        p = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            # на Windows удобнее отдельная группа, чтобы корректно ловить Ctrl+C
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
            if os.name == "nt"
            else 0,
        )
    except FileNotFoundError as e:
        print(f"[error] Не найден исполняемый файл для {name}: {e}")
        sys.exit(1)
    procs.append((name, p))
    return p


def tail(prefix, proc, lines=12, timeout=1.5):
    """Лёгкий вывод первых строк лога процесса."""
    t0 = time.time()
    try:
        for _ in range(lines):
            if proc.poll() is not None:
                break
            if proc.stdout and not proc.stdout.closed:
                line = proc.stdout.readline()
                if line:
                    print(f"[{prefix}] {line.rstrip()}")
            if time.time() - t0 > timeout:
                break
    except Exception:
        pass


def ngrok_api_alive() -> bool:
    try:
        r = requests.get(NGROK_API, timeout=1.5)
        return r.status_code == 200
    except Exception:
        return False


def get_ngrok_url(timeout=20):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            r = requests.get(NGROK_API, timeout=2)
            r.raise_for_status()
            data = r.json()
            for t in data.get("tunnels", []):
                if t.get("proto") == "https":
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

        NGROK_CMD = [ngrok_exe, "http", str(PORT)]
        ng = start(NGROK_CMD, "ngrok")
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
