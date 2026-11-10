"""Launch the Attendance-Sight local desktop portal."""
import asyncio
import ctypes
import os
import secrets
import sys
import threading
import time
import webbrowser
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


if sys.platform == "win32":
    if sys.stdout is not None:
        sys.stdout.reconfigure(encoding="utf-8")
    if sys.stderr is not None:
        sys.stderr.reconfigure(encoding="utf-8")
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def configure_portable_data() -> None:
    """Keep installed-app data writable and separate from bundled resources."""
    if not getattr(sys, "frozen", False):
        return

    local_app_data = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "AttendSight"
    local_app_data.mkdir(parents=True, exist_ok=True)
    (local_app_data / "data").mkdir(exist_ok=True)
    (local_app_data / "logs").mkdir(exist_ok=True)
    env_file = local_app_data / ".env"
    if not env_file.exists():
        env_file.write_text(
            "\n".join(
                [
                    "APP_ENV=development",
                    "APP_HOST=127.0.0.1",
                    "SECRET_KEY=" + secrets.token_urlsafe(48),
                    "",
                ]
            ),
            encoding="utf-8",
        )

    os.environ.setdefault(
        "DATABASE_URL",
        f"sqlite+aiosqlite:///{(local_app_data / 'data' / 'attendance.db').as_posix()}",
    )
    os.environ.setdefault("FACE_IMAGES_DIR", str(local_app_data / "data" / "face_images"))
    os.environ.setdefault("MODEL_WEIGHTS_DIR", str(local_app_data / "data" / "models"))
    os.environ.setdefault("FAISS_INDEX_DIR", str(local_app_data / "data" / "faiss_index"))
    os.environ.setdefault("LOG_FILE", str(local_app_data / "logs" / "app.log"))
    os.chdir(local_app_data)


configure_portable_data()

import uvicorn
from src.core.config import get_settings
from src.main import app

settings = get_settings()


def open_browser_when_ready() -> None:
    """Open the dashboard after Uvicorn begins serving local requests."""
    url = f"http://{settings.app_host}:{settings.app_port}"
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        try:
            with urlopen(f"{url}/health", timeout=2):
                webbrowser.open(url)
                return
        except (OSError, URLError):
            time.sleep(0.5)


def show_message(title: str, message: str, *, error: bool = False) -> None:
    if sys.platform == "win32":
        icon = 0x10 if error else 0x40
        ctypes.windll.user32.MessageBoxW(None, message, title, icon)
    else:
        print(f"{title}: {message}")


def run_desktop_app() -> int:
    try:
        import webview
    except ImportError as exc:
        show_message(
            "Attendance-Sight could not start",
            f"The desktop window dependency is missing: {exc}",
            error=True,
        )
        return 1

    url = f"http://{settings.app_host}:{settings.app_port}"
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host=settings.app_host,
            port=settings.app_port,
            reload=False,
            workers=1,
            log_config=None,
        )
    )
    server_thread = threading.Thread(target=server.run, daemon=True)
    server_thread.start()

    deadline = time.monotonic() + 120
    while time.monotonic() < deadline and server_thread.is_alive():
        try:
            with urlopen(f"{url}/health", timeout=2):
                break
        except (OSError, URLError):
            time.sleep(0.5)
    else:
        server.should_exit = True
        show_message(
            "Attendance-Sight could not start",
            "The local service did not become ready. Check the log at "
            "%LOCALAPPDATA%\\AttendSight\\logs\\app.log.",
            error=True,
        )
        return 1

    window = webview.create_window(
        "Attendance-Sight",
        url,
        width=1280,
        height=850,
        min_size=(960, 640),
    )
    window.events.closed += lambda: setattr(server, "should_exit", True)
    try:
        webview_data_dir = Path(
            os.environ.get("LOCALAPPDATA", Path.home())
        ) / "AttendSight" / "webview"
        webview_data_dir.mkdir(parents=True, exist_ok=True)
        webview.start(
            gui="edgechromium",
            private_mode=False,
            storage_path=str(webview_data_dir),
        )
    except (RuntimeError, OSError) as exc:
        show_message("Attendance-Sight could not open its window", str(exc), error=True)
        server.should_exit = True
        return 1
    finally:
        server.should_exit = True
        server_thread.join(timeout=30)
    return 0


if __name__ == "__main__":
    if getattr(sys, "frozen", False):
        raise SystemExit(run_desktop_app())

    print("\n" + "=" * 60)
    print(">> Attendance-Sight is starting...")
    print("   Face recognition: local ONNX Runtime (GPU if available, otherwise CPU)")
    print("   The AI model pack downloads automatically on first launch.")
    print(f"   Portal: http://{settings.app_host}:{settings.app_port}")
    print("=" * 60 + "\n")

    threading.Thread(target=open_browser_when_ready, daemon=True).start()
    uvicorn.run(app, host=settings.app_host, port=settings.app_port, reload=False, workers=1)
