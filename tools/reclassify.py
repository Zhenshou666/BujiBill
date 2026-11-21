# -*- coding: utf-8 -*-
"""按当前规则重算已有记录的「分类」和「性质」。

为什么需要它：
    分类词表和去重规则改了之后，**已经入库的记录不会自动跟着变** ——
    它们存的是导入那一刻的判定结果。改了规则却看不到效果，多半是这个原因。

用法：
    python tools/reclassify.py 本人           # 只重算「本人」这个账本
    python tools/reclassify.py --all          # 全部账本
    python tools/reclassify.py 本人 --dry-run  # 只看会改哪些，不写库
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from billkit import store                      # noqa: E402
from billkit.classify import classify          # noqa: E402
from billkit.dedupe import mark_kind, pair_refunds  # noqa: E402
from billkit.models import Transaction         # noqa: E402


def rebuild(row) -> Transaction:
    """把数据库里的一行还原成 Transaction，好复用同一套判定逻辑。"""
    ts = row["ts"]
    if isinstance(ts, str):
        ts = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
    return Transaction(
        channel=row["channel"],
        time=ts,
        amount=float(row["amount"]),
        direction=row["direction"],
        counterparty=row["counterparty"] or "",
        product=row["product"] or "",
        raw_category=row["raw_category"] or "",
        pay_method=row["pay_method"] or "",
        status=row["status"] or "",
        order_id=row["order_id"] or "",
        merchant_id=row["merchant_id"] or "",
        note=row["note"] or "",
        source_file=row["source_file"] or "",
    )


def run(profile: str, dry: bool) -> None:
    db = store.profile_db(profile)
    if not db.exists():
        print(f"找不到账本「{profile}」")
        return
    df = store.load(db)
    if df.empty:
        print(f"「{profile}」是空的")
        return

    rows = df.to_dict("records")
    txns = []
    before = []
    for row in rows:
        txn = rebuild(row)
        txn.category = classify(txn)
        txn = mark_kind(txn)
        txns.append(txn)
        before.append((row["category"], row["kind"]))

    # 退款要跨行配对，必须整批跑完再配
    paired = pair_refunds(txns)

    changes = []
    for row, txn, (oc, ok_) in zip(rows, txns, before):
        if (txn.category, txn.kind) != (oc, ok_):
            changes.append((row["uid"], oc, ok_, txn.category, txn.kind))

    print(f"「{profile}」共 {len(df)} 笔，退款配对 {paired} 组，需要更新 {len(changes)} 笔")
    for _, oc, ok_, nc, nk in changes[:12]:
        print(f"   {oc}/{ok_}  →  {nc}/{nk}")
    if len(changes) > 12:
        print(f"   …还有 {len(changes) - 12} 笔")

    if dry or not changes:
        return
    with store.connect(db) as conn:
        conn.executemany(
            "UPDATE transactions SET category=?, kind=? WHERE uid=?",
            [(nc, nk, uid) for uid, _, _, nc, nk in changes],
        )
        conn.commit()
    print(f"已更新「{profile}」")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("profile", nargs="?", help="账本名；配合 --all 时忽略")
    ap.add_argument("--all", action="store_true", help="重算所有账本")
    ap.add_argument("--dry-run", action="store_true", help="只看结果不写库")
    args = ap.parse_args()

    targets = store.list_profiles() if args.all else ([args.profile] if args.profile else [])
    if not targets:
        print("请指定账本名，或用 --all")
        return
    for name in targets:
        run(name, args.dry_run)


if __name__ == "__main__":
    main()
