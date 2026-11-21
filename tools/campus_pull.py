# -*- coding: utf-8 -*-
"""一卡通账单抓取器：驱动已登录的账单页滚动翻页，边滚边收接口响应，导出 CSV。

为什么不直接调接口：GetDealRec 带 `Sign` 签名参数，硬拼参数会被拒。
这里让页面自己发请求，本脚本只负责滚动 + 收集响应，不碰签名。

前置：
    1. 浏览器打开并登录 http://etcard.hzcu.edu.cn:8088/easytong_webapp/index.html#/bill
    2. 用 browser-skill 建立会话（bsk open），拿到会话 id
    3. 起一个抓包 run：bsk debug start --session <id> --name campus

用法：
    python tools/campus_pull.py <session_id> [输出csv路径]

输出列：交易时间 / 交易类型 / 商户名称 / 交易金额 / 余额（余额一栏留空，接口未返回）

注意：一卡通的「第三方支付平台转账」= 微信/支付宝充值进来，
      本脚本把它映射成「交易类型=充值」，交给 billkit/dedupe.py 判为内部转账，
      避免与微信/支付宝那边的付款重复计支出。
"""
from __future__ import annotations

import csv
import json
import os
import re
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "data" / "campus" / "校园卡流水_真实.csv"

ENV = {**os.environ, "BSK_AUTO_START": "0"}

# 一卡通平台接口（2026-11 实测）
API_LIST = "GetDealRec"          # 列表，POST，参数含 BeginRecNum/Count/Sign
API_DETAIL = "GetConsumptionDetail"   # 详情（列表已带商户名，一般用不上）
FIELDS = ["交易时间", "交易类型", "商户名称", "交易金额", "余额"]

KIND_MAP = {
    "消费": "消费",
    "第三方支付平台转账": "充值",     # 微信/支付宝充值进来
}


def run(args, timeout=90):
    try:
        r = subprocess.run(["bsk", *args], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", env=ENV, timeout=timeout)
        return r.stdout or ""
    except subprocess.TimeoutExpired:
        return ""


def jrun(args):
    try:
        return json.loads(run([*args, "--json"]))
    except Exception:
        return None


def new_obs(session):
    return (jrun(["sync", "--session", session]) or {}).get("observation_id") or ""


def wheel(session):
    obs = new_obs(session)
    if not obs:
        return False
    run(["wheel", "--session", session, "--observation", obs, "--delta-y", "2400"])
    return True


def deal_ids(session):
    d = jrun(["debug", "requests", "--session", session, "--limit", "100"])
    if not d:
        return []
    return [r["id"] for r in d.get("requests", []) if API_LIST in r.get("url", "")]


def fetch_body(session, rid):
    d = jrun(["debug", "request", rid, "--session", session,
              "--part", "response", "--max-chars", "16384"])
    try:
        return d["request"]["response_body"]["text"]
    except Exception:
        return None


def parse_month(mon) -> tuple[int, int]:
    s = str(mon or "")
    m = re.search(r"(\d{4})\D*(\d{1,2})", s)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.search(r"(\d{1,2})", s)
    now = time.localtime()
    return (now.tm_year, int(m.group(1))) if m else (now.tm_year, now.tm_mon)


def main(session: str, out: Path) -> int:
    print(f"会话 {session}｜目标 {out}")
    print("重新载入账单页，让响应从头开始")
    obs = new_obs(session)
    if obs:
        run(["reload", "--session", session, "--observation", obs])
    time.sleep(2.5)

    records: dict[int, dict] = {}
    fetched: set[str] = set()
    total, idle = None, 0

    for rnd in range(1, 22):
        got = 0
        for rid in deal_ids(session):
            if rid in fetched:
                continue
            fetched.add(rid)
            body = fetch_body(session, rid)
            if not body:
                continue
            try:
                j = json.loads(body)
            except Exception:
                continue
            total = total or j.get("count")
            for g in j.get("list") or []:
                y, mo = parse_month(g.get("month"))
                for r in g.get("dealDetail") or []:
                    key = r.get("payRecNum")
                    if key is None or key in records:
                        continue
                    day = re.sub(r"[^0-9]", "", str(r.get("dealDate") or "")) or "01"
                    r["_dt"] = f"{y:04d}-{mo:02d}-{int(day):02d} {r.get('dealTime') or '00:00:00'}"
                    records[key] = r
                    got += 1
        print(f"  第{rnd}轮：新增 {got}，累计 {len(records)}"
              f"{f' / 接口声明 {total}' if total else ''}")
        if total and len(records) >= total:
            break
        idle = idle + 1 if got == 0 else 0
        if idle >= 3:
            print("  连续 3 轮无新增，停止")
            break
        if not wheel(session):
            print("  滚动失败，停止")
            break
        time.sleep(1.8)

    if not records:
        print("!! 一笔都没取到，检查会话是否登录、抓包 run 是否在跑")
        return 1

    rows, sign_stat = [], Counter()
    for r in records.values():
        fee = r.get("feeNumStr") or "消费"
        kind = KIND_MAP.get(fee, fee)
        money = float(r.get("money") or 0)
        sign_stat[(kind, "正" if money > 0 else "负")] += 1
        rows.append({
            "交易时间": r["_dt"],
            "交易类型": kind,
            "商户名称": r.get("businessName") or "",
            "交易金额": f"{abs(money):.2f}",
            "余额": "",
        })
    rows.sort(key=lambda x: x["交易时间"], reverse=True)

    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)

    print(f"\n已写入 {out}")
    print(f"  共 {len(rows)} 笔｜类型 {dict(Counter(r['交易类型'] for r in rows))}")
    print(f"  金额符号校验 {dict(sign_stat)}   （消费应为负、充值应为正）")
    print(f"  时间范围 {rows[-1]['交易时间']} → {rows[0]['交易时间']}")
    print(f"  商户去重 {len({r['商户名称'] for r in rows})} 个")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1], Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_OUT))
