# -*- coding: utf-8 -*-
"""把 dist/<名字> 打成可分发的 zip。

用法：python tools/make_zip.py [名字]      （默认 不记账本）
排除 data/（跑过程序会有账本）、__pycache__、*.db、*.pyc、*.log。
"""
from __future__ import annotations

import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NAME = (sys.argv[1] if len(sys.argv) > 1 else "不记账本").strip()
SRC = ROOT / "dist" / NAME
OUT = ROOT / "dist" / f"{NAME}.zip"

SKIP_PARTS = {"data", "__pycache__"}
SKIP_SUFFIX = {".db", ".pyc", ".log"}


def main() -> int:
    if not SRC.exists():
        print(f"找不到 dist/{NAME}，先跑 PyInstaller")
        return 1
    OUT.unlink(missing_ok=True)
    n = skipped = 0
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for p in SRC.rglob("*"):
            if not p.is_file():
                continue
            rel = p.relative_to(SRC)
            if set(rel.parts) & SKIP_PARTS or p.suffix in SKIP_SUFFIX:
                skipped += 1
                continue
            z.write(p, Path(NAME) / rel)
            n += 1
    print(f"打包完成：{OUT.name}  {n} 个文件，跳过 {skipped} 个（数据/缓存）")
    print(f"大小 {OUT.stat().st_size / 1024 / 1024:.1f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
