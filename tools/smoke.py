# -*- coding: utf-8 -*-
"""端到端自检：把三份示例账单解析一遍，验证去重/退款/内部转账判定是否符合预期。

用法：
    python tools/smoke.py          # 只在临时库上验证，不碰正式数据
    python tools/smoke.py --seed   # 顺手把示例数据灌进 data/bill.db，方便看界面效果
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from billkit import ADAPTERS, Channel, Kind, store  # noqa: E402

FILES = {
    Channel.WECHAT: ROOT / "data" / "wechat" / "微信支付账单流水文件(20261017-20261117)_模拟.xlsx",
    Channel.ALIPAY: ROOT / "data" / "alipay" / "cashbook_record_模拟.csv",
    Channel.CAMPUS: ROOT / "data" / "campus" / "校园卡流水_模拟.csv",
}


def ingest_all(db_path) -> None:
    for channel, path in FILES.items():
        if not path.exists():
            raise SystemExit(f"缺少示例文件：{path}\n先跑 python tools/make_sample.py")
        txns, warns = ADAPTERS[channel]().parse(path.read_bytes(), path.name)
        added, skipped = store.save(txns, db_path)
        print(f"  {channel:<4} 解析 {len(txns):>2} 笔 ｜ 新增 {added:>2} ｜ 重复跳过 {skipped}")
        for w in warns:
            print(f"      ⚠ {w}")


def main() -> None:
    seed = "--seed" in sys.argv
    db_path = store.DB_PATH if seed else ROOT / "data" / "smoke.db"
    if db_path.exists():
        db_path.unlink()

    print("1) 解析三份账单")
    ingest_all(db_path)

    print("\n2) 幂等性检查（同一份文件再导一次，应该全是重复）")
    ingest_all(db_path)

    df = store.load(db_path)
    print(f"\n3) 库内共 {len(df)} 笔")

    print("\n4) 按性质汇总")
    stat = df.groupby("kind").agg(笔数=("uid", "count"), 金额=("amount", "sum"))
    for kind, row in stat.iterrows():
        print(f"  {kind:<6} {int(row['笔数']):>3} 笔  ¥{row['金额']:>8,.2f}")

    consume = df[(df["kind"] == Kind.NORMAL) & (df["direction"] == "支出")]
    dropped = df[(df["kind"] != Kind.NORMAL) & (df["direction"] == "支出")]
    naive = consume["amount"].sum() + dropped["amount"].sum()
    print("\n5) 核心结论")
    print(f"  真实消费支出     ¥{consume['amount'].sum():,.2f}")
    print(f"  不剔除会算成     ¥{naive:,.2f}   （虚增 ¥{dropped['amount'].sum():,.2f}）")

    print("\n6) 关键判定抽查")
    checks = [
        ("一卡通充值 → 内部转账", lambda d: d[d["note"].str.contains("一卡通|校园卡", na=False)], Kind.TRANSFER),
        ("退款 → 退款（不计消费）", lambda d: d[d["category"].eq("退款")], Kind.REFUND),
        ("红包收入 → 正常收入", lambda d: d[d["raw_category"].str.contains("红包", na=False)
                                          & d["direction"].eq("收入")], Kind.NORMAL),
        # 记账本格式没有「商品」列，收益写在备注里
        ("余额宝收益 → 正常收入", lambda d: d[d["note"].str.contains("收益", na=False)], Kind.NORMAL),
        ("个人转账 → 待确认", lambda d: d[d["kind"] == Kind.UNCLEAR], Kind.UNCLEAR),
        ("提现/余额宝转入 → 内部转账", lambda d: d[d["raw_category"].isin(["零钱提现", "投资理财"])
                                              & d["kind"].eq(Kind.TRANSFER)], Kind.TRANSFER),
    ]
    failed = 0
    for name, picker, expect in checks:
        sub = picker(df)
        ok = (sub["kind"] == expect).all() if len(sub) else False
        failed += 0 if ok else 1
        print(f"  {'✅' if ok else '❌'} {name}：{len(sub)} 笔")
        for _, r in sub.head(8).iterrows():
            print(f"       {r['ts']:%m-%d} {r['channel']} {r['counterparty']} "
                  f"¥{r['amount']:.2f} → {r['kind']} / {r['category']}")
    if failed:
        print(f"  ⚠ {failed} 项判定不符合预期，去检查 billkit/dedupe.py")

    print("\n7) 分类分布")
    for cat, row in consume.groupby("category")["amount"].agg(["count", "sum"]).sort_values("sum", ascending=False).iterrows():
        print(f"  {cat:<6} {int(row['count']):>3} 笔  ¥{row['sum']:>8,.2f}")

    if seed:
        print(f"\n已灌入正式库：{db_path}")
        print("启动界面：.\\.venv\\Scripts\\streamlit run app.py")
    else:
        db_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
