# -*- coding: utf-8 -*-
"""SQLite 存储层。

用 uid 作主键 + INSERT OR IGNORE，天然做到「同一份账单导入两次不会翻倍」，
这是记账软件最基本的正确性要求。
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
import time
import sqlite3
from contextlib import closing
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _data_root() -> Path:
    """数据该存哪儿。

    开发时就是项目目录；打包成 exe 之后放在 **exe 同级目录**（便携式），
    这样整个程序文件夹删掉 = 数据一起清空，重新解压就是干净状态。
    """
    override = os.environ.get("BILLKIT_DATA_DIR")
    if override:
        return Path(override)
    if getattr(sys, "frozen", False):
        # 便携式：数据就放在 exe 旁边，删掉整个程序文件夹 = 数据一起清掉。
        # 这样"重新解压一份"永远是干净状态，不会翻出上一版留下的账本。
        portable = Path(sys.executable).resolve().parent
        try:
            probe = portable / ".write_test"
            probe.write_text("1", encoding="utf-8")
            probe.unlink()
            return portable
        except OSError:
            # 装在只读目录（比如 Program Files）时退回用户目录
            base = os.environ.get("LOCALAPPDATA") or Path.home().joinpath("AppData", "Local")
            return Path(base) / "不记账本"
    return PROJECT_ROOT


DATA_DIR = _data_root()
PROFILES_DIR = DATA_DIR / "data" / "profiles"
# 打包成 exe 分发时，不该带着演示账本落地：第一次打开就是一本空账本，
# 让用户自己去导入。开发时仍用「演示数据」，方便调试。
DEFAULT_PROFILE = os.environ.get("BILLKIT_DEFAULT_PROFILE") or (
    "我的账本" if getattr(sys, "frozen", False) else "演示数据"
)
LEGACY_DB = DATA_DIR / "data" / "bill.db"

# 打包后规则表在只读的包内，要复制一份到数据目录，否则"记住这个分类"会写不进去
_BUNDLED_RULES = PROJECT_ROOT / "data" / "rules.json"


def _seed_rules() -> None:
    target = DATA_DIR / "data" / "rules.json"
    if target.exists() or not _BUNDLED_RULES.exists():
        return
    if _BUNDLED_RULES.resolve() == target.resolve():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(_BUNDLED_RULES, target)


def _migrate_legacy() -> None:
    """老的单库 data/bill.db 自动升级成「演示数据」这个用户。"""
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    legacy = PROFILES_DIR / f"{DEFAULT_PROFILE}.db"
    if LEGACY_DB.exists() and not legacy.exists():
        LEGACY_DB.replace(legacy)


def safe_name(name: str) -> str:
    """用户名要当文件名用，去掉非法字符，防路径穿越。"""
    name = (name or "").strip()
    name = re.sub(r'[\\/:*?"<>|\s]+', "_", name)
    name = name.strip("._")
    if not name:
        raise ValueError("用户名不能为空")
    if len(name) > 40:
        raise ValueError("用户名太长（最多 40 字符）")
    return name


ORDER_FILE = PROFILES_DIR / "order.json"


def _read_order() -> list[str]:
    try:
        data = json.loads(ORDER_FILE.read_text(encoding="utf-8"))
        return [str(x) for x in data] if isinstance(data, list) else []
    except (FileNotFoundError, ValueError, OSError):
        return []


def _write_order(names: list[str]) -> None:
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    ORDER_FILE.write_text(
        json.dumps(names, ensure_ascii=False, indent=1), encoding="utf-8"
    )


def list_profiles() -> list[str]:
    """返回账本名，按用户手动调过的顺序排；新出现的账本接在后面。"""
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    names = sorted(p.stem for p in PROFILES_DIR.glob("*.db"))
    if not names:
        return [DEFAULT_PROFILE]
    order = [n for n in _read_order() if n in names]
    return order + [n for n in names if n not in order]


def set_order(names: list[str]) -> None:
    """整份覆盖顺序（拖拽排序用）。只保留真实存在的账本，其余按名字补在后面。"""
    exist = sorted(p.stem for p in PROFILES_DIR.glob("*.db"))
    kept = [n for n in names if n in exist]
    for n in exist:
        if n not in kept:
            kept.append(n)
    _write_order(kept)


def ensure_empty(name: str) -> None:
    """建一个空账本（访客从零开始时用）。已存在就什么都不做。"""
    path = profile_db(name)
    if not path.exists():
        with closing(connect(path)):
            pass


def clone_demo(dest_name: str) -> None:
    """给访客复制一份演示数据（分享演示用，互不干扰）。"""
    src, dst = profile_db(DEFAULT_PROFILE), profile_db(dest_name)
    if src.exists() and not dst.exists():
        shutil.copyfile(src, dst)


def purge_guests(max_age_hours: int = 24) -> int:
    """清掉过期的访客账本（分享模式会不断生成）。"""
    cutoff = time.time() - max_age_hours * 3600
    n = 0
    for f in PROFILES_DIR.glob("访客*.db"):
        try:
            if f.stat().st_mtime < cutoff:
                f.unlink()
                n += 1
        except OSError:
            pass
    return n


def move_profile(name: str, delta: int) -> bool:
    """把某个账本上移(-1)/下移(+1)，越界就不动。返回是否真的挪了。"""
    names = list_profiles()
    if name not in names:
        return False
    i = names.index(name)
    j = i + delta
    if not (0 <= j < len(names)):
        return False
    names[i], names[j] = names[j], names[i]
    _write_order(names)
    return True


def profile_db(name: str) -> Path:
    return PROFILES_DIR / f"{safe_name(name)}.db"


def create_profile(name: str) -> Path:
    path = profile_db(name)
    if path.exists():
        raise ValueError(f"用户「{path.stem}」已存在")
    with closing(connect(path)):
        pass
    return path


def rename_profile(old: str, new: str) -> str:
    """给账本改名：只改文件名和在顺序表里的位置，里面的账单一条不动。

    返回规范化之后的最终名字（名字里的空格、斜杠之类会被换掉）。
    """
    target = safe_name(new)
    if target == old:
        return old
    if target in list_profiles():
        raise ValueError(f"已经有个账本叫「{target}」了，换个名字吧")

    src, dst = profile_db(old), profile_db(target)
    if not src.exists():
        raise ValueError("找不到这个账本，可能已经被删掉了")
    src.rename(dst)

    order = [target if n == old else n for n in _read_order()]
    _write_order(order)
    return target


def delete_profile(name: str) -> None:
    if len(list_profiles()) <= 1:
        raise ValueError("至少保留一个用户")
    path = profile_db(name)
    if path.exists():
        path.unlink()
    order = [n for n in _read_order() if n != name]
    _write_order(order)


_migrate_legacy()
_seed_rules()

# 兼容旧调用：默认指向「演示数据」这个用户
DB_PATH = PROFILES_DIR / f"{DEFAULT_PROFILE}.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS transactions (
    uid           TEXT PRIMARY KEY,
    channel       TEXT NOT NULL,
    ts            TEXT NOT NULL,
    direction     TEXT NOT NULL,
    amount        REAL NOT NULL,
    counterparty  TEXT,
    product       TEXT,
    raw_category  TEXT,
    pay_method    TEXT,
    status        TEXT,
    order_id      TEXT,
    merchant_id   TEXT,
    note          TEXT,
    category      TEXT,
    kind          TEXT,
    source_file   TEXT,
    imported_at   TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_ts   ON transactions(ts);
CREATE INDEX IF NOT EXISTS idx_kind ON transactions(kind);
"""

FIELDS = [
    "uid", "channel", "ts", "direction", "amount", "counterparty", "product",
    "raw_category", "pay_method", "status", "order_id", "merchant_id",
    "note", "category", "kind", "source_file",
]


def connect(db_path: Path | str = DB_PATH) -> sqlite3.Connection:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)
    return conn


def save(txns, db_path: Path | str = DB_PATH) -> tuple[int, int]:
    """入库。返回 (新增条数, 因已存在而跳过的条数)。"""
    rows = [[r.get(f) for f in FIELDS] for r in (t.to_row() for t in txns)]
    if not rows:
        return 0, 0
    placeholders = ",".join("?" * len(FIELDS))
    sql = f"INSERT OR IGNORE INTO transactions ({','.join(FIELDS)}) VALUES ({placeholders})"
    with closing(connect(db_path)) as conn:
        before = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
        conn.executemany(sql, rows)
        conn.commit()
        after = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
    added = after - before
    return added, len(rows) - added


def load(db_path: Path | str = DB_PATH) -> pd.DataFrame:
    with closing(connect(db_path)) as conn:
        df = pd.read_sql("SELECT * FROM transactions ORDER BY ts", conn)
    if not df.empty:
        df["ts"] = pd.to_datetime(df["ts"])
    return df


def clear(db_path: Path | str = DB_PATH) -> None:
    with closing(connect(db_path)) as conn:
        conn.execute("DELETE FROM transactions")
        conn.commit()


def count(db_path: Path | str = DB_PATH) -> int:
    with closing(connect(db_path)) as conn:
        return conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]


def set_category(uid: str, category: str, db_path: Path | str = DB_PATH) -> int:
    """给某一条记录改分类（按 uid 精确定位）。"""
    uid = (uid or "").strip()
    category = (category or "").strip()
    if not uid or not category:
        return 0
    with closing(connect(db_path)) as conn:
        cur = conn.execute(
            "UPDATE transactions SET category = ? WHERE uid = ?", (category, uid)
        )
        conn.commit()
        return cur.rowcount


def set_category_by_merchant(
    merchant: str, category: str, direction: str | None = None,
    db_path: Path | str = DB_PATH,
) -> int:
    """把某个商户的所有记录都改成同一分类（修历史用）。

    direction 传了就只有这个方向（支出/收入）的记录，避免把退款也一起改了。
    """
    name = (merchant or "").strip()
    category = (category or "").strip()
    if not name or not category:
        return 0
    sql = "UPDATE transactions SET category = ? WHERE TRIM(counterparty) = ?"
    params: list = [category, name]
    if direction:
        sql += " AND direction = ?"
        params.append(direction)
    with closing(connect(db_path)) as conn:
        cur = conn.execute(sql, params)
        conn.commit()
        return cur.rowcount


def delete_txn(uid: str, db_path: Path | str = DB_PATH) -> int:
    """删掉一条记录（按 uid）。用来清掉重复入账、记错的账。"""
    uid = (uid or "").strip()
    if not uid:
        return 0
    with closing(connect(db_path)) as conn:
        cur = conn.execute("DELETE FROM transactions WHERE uid = ?", (uid,))
        conn.commit()
        return cur.rowcount


def update_category(keyword: str, category: str, db_path: Path | str = DB_PATH) -> int:
    """把还没归类的记录里、含该关键词的，直接改成指定分类。返回影响行数。

    用于「用户教它认一个新商户」：改完词库立刻把已有数据也纠正，
    否则用户会看到提示说记住了、表格却没变。
    """
    kw = (keyword or "").strip()
    if not kw:
        return 0
    like = f"%{kw}%"
    with closing(connect(db_path)) as conn:
        cur = conn.execute(
            "UPDATE transactions SET category = ? "
            "WHERE category IN ('未分类', '') "
            "AND (counterparty LIKE ? OR note LIKE ? OR product LIKE ?)",
            (category, like, like, like),
        )
        conn.commit()
        return cur.rowcount
