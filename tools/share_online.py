# -*- coding: utf-8 -*-
"""一键：本地应用 + 公网隧道。

双击根目录的「分享_公网.bat」。做的事：
1. 以分享模式启动应用（每个访客独立的空账本）
2. 先试 Cloudflare（域名好看、较稳），连不上就自动退回 serveo
3. 把拿到的 https 地址打在屏幕上

地址是临时的：关掉窗口就失效，重新运行会换一个。
"""
from __future__ import annotations

import os
import re
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PORT = 8501

# Cloudflare quick tunnel 的域名形如 xxx-yyy-zzz.trycloudflare.com
# 必须排除 api. —— 报错信息里会出现这个 API 地址，别当成隧道地址
CF_RE = re.compile(r"https://(?!api\.|www\.)[a-z0-9-]{4,}\.trycloudflare\.com")
# serveo 给的是 xxxxx-ip.serveousercontent.com
SV_RE = re.compile(r"https://[a-z0-9]+-[a-z0-9.-]+\.serveousercontent\.com")


_PROXY_KEYS = {"http_proxy", "https_proxy", "all_proxy", "no_proxy"}


def _tunnel_env() -> dict:
    """隧道进程用干净环境：绕开系统代理。

    加速器/代理软件常会把 HTTP(S)_PROXY 指到自己的端口，
    而它并不认识 trycloudflare.com，隧道就会一直超时。
    """
    return {k: v for k, v in os.environ.items() if k.lower() not in _PROXY_KEYS}


def _wait_port(timeout: float = 45.0) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        try:
            with socket.create_connection(("127.0.0.1", PORT), timeout=1):
                return True
        except OSError:
            time.sleep(0.6)
    return False


def _banner(url: str, via: str, note: str = "") -> None:
    bar = "=" * 58
    print("\n" + bar)
    print(f"  把下面这个网址发给同学（手机也能打开）· {via}")
    print("  " + url)
    print(bar)
    if note:
        print(note)
    print("  关掉这个窗口，网址就失效。按 Ctrl+C 结束。\n")


def _pump(proc, regex, timeout: float, via: str, note: str = "") -> str | None:
    """在 timeout 内盯着进程输出找网址；找到就打印并返回，进程继续跑。"""
    found: list[str] = []
    stdout = proc.stdout
    assert stdout is not None

    def reader() -> None:
        for line in stdout:
            m = regex.search(line)
            if m and not found:
                found.append(m.group(0))
                _banner(m.group(0), via, note)

    threading.Thread(target=reader, daemon=True).start()
    deadline = time.time() + timeout
    while time.time() < deadline:
        if found:
            return found[0]
        if proc.poll() is not None:
            return found[0] if found else None
        time.sleep(0.3)
    return found[0] if found else None


def _kill(proc) -> None:
    if proc is None:
        return
    try:
        proc.terminate()
    except Exception:  # noqa: BLE001
        pass


def main() -> int:
    # 后台/双击运行时 stdout 是块缓冲的，不打这一行屏幕上会长时间一片空白
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:  # noqa: BLE001
        pass

    py = ROOT / ".venv" / "Scripts" / "python.exe"
    if not py.exists():
        py = Path(sys.executable)

    print("正在启动应用…")
    log = ROOT / "tools" / "last_run.log"
    app_log = open(log, "w", encoding="utf-8", errors="replace")
    app = subprocess.Popen(
        [
            str(py), "-m", "streamlit", "run", str(ROOT / "app.py"),
            "--server.address", "0.0.0.0",
            "--server.port", str(PORT),
            "--browser.gatherUsageStats", "false",
            # 隧道/手机访问时 XSRF 会让 WebSocket 握手失败，页面就是一片空白
            "--server.enableCORS", "false",
            "--server.enableXsrfProtection", "false",
            "--server.enableWebsocketCompression", "false",
        ],
        cwd=str(ROOT),
        env={**os.environ, "BILLKIT_SHARE": "1"},
        stdout=app_log,
        stderr=subprocess.STDOUT,
    )
    if not _wait_port():
        _kill(app)
        print("应用没能启动。最近的错误：\n")
        try:
            lines = log.read_text(encoding="utf-8", errors="replace").strip().splitlines()
            print("\n".join(lines[-12:]))
        except OSError:
            pass
        return 1

    tun = None
    url = None

    proxies = [k for k in os.environ if k.lower() in _PROXY_KEYS]
    if proxies:
        print(f"  （检测到系统代理 {', '.join(proxies)}，隧道进程会绕过它直连）")

    tun_env = _tunnel_env()
    cf = ROOT / "tools" / "bin" / "cloudflared.exe"
    if cf.exists():
        print("尝试 Cloudflare 隧道…")
        tun = subprocess.Popen(
            [str(cf), "tunnel", "--url", f"http://localhost:{PORT}", "--no-autoupdate"],
            cwd=str(ROOT),
            env=tun_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        url = _pump(tun, CF_RE, timeout=35, via="Cloudflare")

    if not url:
        _kill(tun)
        print("Cloudflare 连不上，改用 serveo…")
        tun = subprocess.Popen(
            ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "ServerAliveInterval=20",
             "-R", f"80:localhost:{PORT}", "serveo.net"],
            cwd=str(ROOT),
            env=tun_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        url = _pump(
            tun, SV_RE, timeout=30, via="serveo",
            note="  ⚠️ serveo 免费版会先弹一个红色警告页，\n"
                 "     让同学点「Continue to Site」就能进，不是出错。\n",
        )

    if not url:
        print("\n两条隧道都没通。建议改用「分享_局域网.bat」—— 同一 WiFi 下最稳。")
        _kill(tun)
        _kill(app)
        return 2

    try:
        while True:
            if tun is not None and tun.poll() is not None:
                print("\n隧道断开了。重新双击本文件即可拿一个新地址。")
                break
            time.sleep(2)
    except KeyboardInterrupt:
        pass
    finally:
        _kill(tun)
        _kill(app)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
