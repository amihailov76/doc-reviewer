"""
Точка входа для production-сборки (.exe).
"""
import os
import sys
import socket
import threading
import webbrowser
import time


def get_base_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def open_browser(port: int):
    time.sleep(2.5)
    webbrowser.open(f"http://localhost:{port}")


if __name__ == "__main__":
    base_dir = get_base_dir()
    os.chdir(base_dir)

    # Добавляем base_dir в sys.path — чтобы `import backend` работал
    if base_dir not in sys.path:
        sys.path.insert(0, base_dir)

    # При console=False stdout/stderr равны None — uvicorn падает на логировании
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")

    port = find_free_port()

    threading.Thread(target=open_browser, args=(port,), daemon=True).start()

    import uvicorn

    # Передаём log_config=None чтобы uvicorn не трогал стандартный логгер
    uvicorn.run(
        "backend.main:app",
        host="127.0.0.1",
        port=port,
        log_config=None,
        log_level="error",
    )
