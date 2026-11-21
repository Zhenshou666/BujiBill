# -*- coding: utf-8 -*-
"""桌面版启动器：双击后开一个窗口，里面就是账本界面。

做法：这个程序启动时会把自己再拉起来一次（带 --serve），
那个子进程在**主线程**里跑 Streamlit 服务；本进程只负责开窗口。
不开线程是因为 Streamlit 的启动流程要注册信号量，在线程里会报错。

打包成 exe 后：账本数据存 %LOCALAPPDATA%\\不记账本\\data\\
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

APP_TITLE = "不记账本"


def _resource_dir() -> Path:
    """打包后资源在临时解压目录；开发时就是脚本所在目录。"""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent


def _free_port(start: int = 8501) -> int:
    for port in range(start, start + 40):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return start


def _wait_health(port: int, timeout: float = 60.0) -> bool:
    url = f"http://127.0.0.1:{port}/_stcore/health"
    end = time.time() + timeout
    while time.time() < end:
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                if r.status == 200:
                    return True
        except Exception:  # noqa: BLE001
            time.sleep(0.4)
    return False


def serve(port: int) -> None:
    """子进程的活：在主线程里把 Streamlit 跑起来。

    两个坑：
    1. bootstrap.run 的 flag_options 是「热重载监听的文件路径」，不是配置项；
    2. STREAMLIT_SERVER_PORT 这类环境变量在本版本里不生效，只有 config.set_option 管用。
    """
    os.environ.setdefault("BILLKIT_SHARE", "0")

    # 关键：把工作目录切到资源目录，Streamlit 才会读到打包进去的 .streamlit/config.toml。
    # 不切的话它用默认主题（纯白背景），图表卡片会变成白色、和纸色页面脱节。
    os.chdir(_resource_dir())

    from streamlit import config
    from streamlit.web import bootstrap

    for key, value in (
        ("server.port", port),
        ("server.address", "127.0.0.1"),
        ("server.headless", True),
        ("browser.gatherUsageStats", False),
        ("server.enableCORS", False),
        ("server.enableXsrfProtection", False),
        ("server.fileWatcherType", "none"),
        # 不关掉的话 Streamlit 以为在开发模式，页面会去连 Vite 的 3000 端口，
        # 结果访问 / 直接 404
        ("global.developmentMode", False),
        # 打包后 .streamlit/config.toml 读不到（它按工作目录找，exe 不一定在那儿启动），
        # 所以这里显式打开，否则 /app/static/ 下的字体文件会被首页兜底页顶掉
        ("server.enableStaticServing", True),
    ):
        try:
            config.set_option(key, value)
        except Exception:  # noqa: BLE001
            pass

    bootstrap.run(str(_resource_dir() / "app.py"), False, [], {})


def main() -> int:
    if "--serve" in sys.argv:
        port = 8501
        if "--port" in sys.argv:
            port = int(sys.argv[sys.argv.index("--port") + 1])
        serve(port)
        return 0

    port = _free_port()
    url = f"http://127.0.0.1:{port}"
    proc = subprocess.Popen([sys.executable, "--serve", "--port", str(port)])
    try:
        if not _wait_health(port):
            print("服务没能启动，请把窗口截图发我。")
            return 1

        try:
            import webview

            # 桌面版默认不允许下载：点「存成表格」没反应就是这么来的。
            # 打开后 WebView2 会把文件存进系统的下载目录。
            webview.settings["ALLOW_DOWNLOADS"] = True

            webview.create_window(
                APP_TITLE, url, width=1320, height=900, min_size=(900, 640),
            )
            webview.start()
        except Exception:  # noqa: BLE001
            # 没有 WebView2（老系统）就退回默认浏览器，程序照常能用
            import webbrowser

            webbrowser.open(url)
            print(f"已在浏览器打开：{url}\n关掉这个窗口即可退出。")
            while proc.poll() is None:
                time.sleep(1)
    finally:
        if proc.poll() is None:
            proc.terminate()
    return 0


def _log_startup_error() -> None:
    """窗口版没有控制台，出错得留个痕迹。"""
    import traceback

    base = os.environ.get("LOCALAPPDATA")
    folder = Path(base) / "不记账本" if base else Path.home() / ".不记账本"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "启动错误.log").write_text(
        traceback.format_exc(), encoding="utf-8"
    )


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:  # noqa: BLE001
        _log_startup_error()
        raise
