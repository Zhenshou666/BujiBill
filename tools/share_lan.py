# -*- coding: utf-8 -*-
"""给同学看的时候用这个启动：局域网 + 演示模式。

双击根目录的 share.bat 即可。做的事：
1. 打开「分享模式」——每人一份演示数据副本，看不到你自己的账本
2. 监听 0.0.0.0，同一个 WiFi 下的手机/电脑都能访问
3. 把访问地址打印出来
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PORT = "8501"


def lan_ip() -> str:
    """问系统要一个出口网卡的地址（不会真的发包）。"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def main() -> int:
    ip = lan_ip()
    line = "=" * 52
    print()
    print(line)
    print("  不记账本 · 演示模式")
    print(line)
    print(f"  你自己打开：      http://localhost:{PORT}")
    print(f"  同学打开：        http://{ip}:{PORT}")
    print()
    print("  同一个 WiFi 才连得上；手机用浏览器输上面的地址。")
    print("  第一次运行 Windows 可能弹防火墙提示，点「允许」。")
    print("  按 Ctrl+C 结束。")
    print(line)
    print()

    # 用 python -m streamlit 而不是 Scripts/streamlit.exe：
    # 那个 exe 里嵌了 venv 的绝对路径，项目文件夹一改名就静默退出（踩过）
    py = ROOT / ".venv" / "Scripts" / "python.exe"
    if not py.exists():
        py = Path(sys.executable)
    cmd = [
        str(py), "-m", "streamlit", "run", str(ROOT / "app.py"),
        "--server.address", "0.0.0.0",
        "--server.port", PORT,
        "--browser.gatherUsageStats", "false",
        # 手机通过 IP 访问时，Streamlit 的 XSRF 校验会让 WebSocket 握手被拒，
        # 表现就是「页面白板一片」。演示场景关掉这三项最省事。
        "--server.enableCORS", "false",
        "--server.enableXsrfProtection", "false",
        "--server.enableWebsocketCompression", "false",
    ]
    env = {**os.environ, "BILLKIT_SHARE": "1"}
    try:
        return subprocess.call(cmd, cwd=str(ROOT), env=env)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
